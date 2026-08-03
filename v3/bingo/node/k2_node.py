"""Run the BINGO thin vertical against a REAL Creality K2 Plus.

This is Phase B's milestone: the first physical fabrication settled through
the network's full loop — registry royalty split, escrow, PoF evidence from
real telemetry and camera frames, atomic settlement.

Usage (on the machine that can reach the printer):

    # 1. Safe read-only check — connects, reports state, prints the plan:
    python -m bingo.node.k2_node --host 192.168.1.230

    # 2. The real thing — supply a sliced gcode file (slice the bracket in
    #    Creality Print / Orca first; this tool NEVER generates gcode):
    python -m bingo.node.k2_node --host 192.168.1.230 ^
        --gcode "C:\\path\\to\\bracket_PLA.gcode" --go

Options:
    --qty N        units (default 1; you'll be prompted to clear the bed between)
    --stl PATH     use your own STL for registration/DFM (default: built-in PB-001)
    --royalty C    creator royalty in cents/unit (default 40)
    --port P       Moonraker port (default 7125)
    --api-key K    Moonraker API key if required

Every run writes out/ledger.json and out/dashboard.html. Nothing settles
unless the print completes and you confirm receipt — a failed or cancelled
print leaves escrow untouched (refund path), exactly per specs/SETTLEMENT.md.
"""

from __future__ import annotations

import argparse
import os
import sys

# Windows consoles often default to cp1252; keep the runner's output portable.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import re

from ..dfm import analyze, DfmReport
from ..ledger import Ledger
from ..models import License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from ..orchestrator import Orchestrator
from ..registry import AssetRegistry
from .agent import NodeAgent
from .k2 import K2Driver, K2Error
from ..demo.make_design import bracket_stl
from ..demo.dashboard import render_dashboard

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "out")


def _parse_minutes(filename: str) -> float | None:
    """'…_PLA_1h37m49s.gcode' -> 97.8; '…_PLA_14m22s.gcode' -> 14.4"""
    m = re.search(r"(?:(\d+)h)?(\d+)m(\d+)s", filename)
    if not m:
        return None
    h, mins, secs = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return h * 60 + mins + secs / 60.0


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO node runner — Creality K2 Plus")
    ap.add_argument("--host", required=True, help="printer IP/hostname on your LAN")
    ap.add_argument("--port", type=int, default=7125)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--gcode", help="path to a sliced .gcode file (required with --go)")
    ap.add_argument("--printer-file", help="use an already-proven gcode file that lives "
                    "on the printer: downloads it, registers it as the content-addressed "
                    "asset, and reprints it (no local slicing needed)")
    ap.add_argument("--title", help="asset title (printer-file mode)")
    ap.add_argument("--est-minutes", type=float, default=0.0,
                    help="est print minutes (printer-file mode; default: parsed from filename)")
    ap.add_argument("--grams", type=float, default=25.0,
                    help="est grams/unit (printer-file mode)")
    ap.add_argument("--stl", help="STL to register/DFM (default: built-in PB-001 bracket)")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--royalty", type=int, default=40, help="creator cents/unit")
    ap.add_argument("--go", action="store_true",
                    help="actually upload and print (default is a dry-run check)")
    args = ap.parse_args(argv)

    driver = K2Driver(args.host, args.port, args.api_key)

    # ── connectivity + state check (always) ─────────────────────────────────
    try:
        info = driver.info()
    except K2Error as e:
        print(f"✗ {e}")
        return 1
    print(f"✓ printer: {info.get('hostname', args.host)} — state '{info.get('state')}' "
          f"(klipper {info.get('software_version', '?')})")

    if args.printer_file:
        # Proven-file mode: the design IS the gcode that already printed
        # successfully on this machine. Download → hash → register → reprint.
        gcode = driver.download_gcode(args.printer_file)
        content, title = gcode, (args.title or args.printer_file.split(".stl")[0])
        est_min = args.est_minutes or _parse_minutes(args.printer_file) or 30.0
        dfm = DfmReport(ok=True, issues=[], triangles=0, bbox_mm=(0, 0, 0),
                        volume_mm3=0.0, est_grams_per_unit=args.grams,
                        est_hours_per_unit=est_min / 60.0)
        print(f"✓ proven file: {args.printer_file} ({len(gcode):,} bytes, "
              f"~{est_min:.0f} min/unit)")
        if not args.go:
            print("\ndry-run complete. Re-run with --go to fabricate and settle for real.")
            return 0
    else:
        stl = open(args.stl, "rb").read() if args.stl else bracket_stl()
        content, title = stl, "PB-001 shelf bracket"
        dfm = analyze(stl, (350.0, 350.0, 350.0))      # K2 Plus build volume
        print(f"✓ DFM: {dfm.triangles} tris, bbox {tuple(round(b, 1) for b in dfm.bbox_mm)} mm, "
              f"{'watertight' if dfm.ok else 'ISSUES: ' + '; '.join(dfm.issues)}")
        if not args.go:
            print("\ndry-run complete. Slice the part, then re-run with "
                  "--gcode <file> --go to fabricate and settle for real.")
            return 0
        if not args.gcode:
            print("✗ --go requires --gcode <sliced file> (this tool never generates gcode)")
            return 1
        gcode = open(args.gcode, "rb").read()

    # ── the network, with one real node in it ────────────────────────────────
    registry, ledger = AssetRegistry(), Ledger()
    node = NodeInfo(
        node_id="n-k2plus", operator="acct:ben-shop", name="Ben's K2 Plus",
        lat=0.0, lon=0.0, tier=1, rate_cents_per_hour=300,
        machines=[Machine(machine_id=info.get("hostname", "k2plus"),
                          make_model="Creality K2 Plus", process="fdm",
                          envelope_mm=(350, 350, 350),
                          materials=["PLA", "PETG", "ABS", "ASA"], kw=0.35)],
        reputation=0.6)
    agent = NodeAgent(node, driver=driver)
    orch = Orchestrator(registry, ledger, [agent])

    asset = registry.register(
        kind="design" if not args.printer_file else "design-gcode",
        title=title, creator="acct:ben",
        content=content,
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=args.royalty),
        split=Split([SplitPayee("acct:ben", 10_000)]))
    print(f"✓ registered '{asset.title}' — {args.royalty}¢/unit, id {asset.asset_id[:12]}…")

    order, dfm = orch.place_order(buyer="acct:first-buyer", asset_id=asset.asset_id,
                                  qty=args.qty, material="PLA",
                                  buyer_lat=0.0, buyer_lon=0.0, required_tier=1,
                                  dfm_override=dfm if args.printer_file else None)
    print(f"✓ order {order.order_id}: {args.qty} unit(s), escrow ${order.total_cents / 100:.2f}")

    resp = input(f"\nAbout to upload and PRINT on {info.get('hostname')}. Type 'print' to proceed: ")
    if resp.strip().lower() != "print":
        print("aborted; escrow would refund (nothing settled)")
        return 0

    def confirm_delivery(job):
        input(f"  unit(s) off the bed and in hand? Press Enter to confirm receipt "
              f"of {job.job_id} and release settlement… ")
        return "operator:ben"

    try:
        settled = orch.execute_order(order, dfm, narrate=print, gcode=gcode,
                                     confirm_delivery=confirm_delivery)
    except (K2Error, KeyboardInterrupt) as e:
        print(f"\n✗ fabrication halted: {e}\n  escrow untouched — nothing settles on failure.")
        return 1

    print(f"\n★ FIRST REAL FABRICATION SETTLED: {sum(j.qty for j in settled)} unit(s)")
    print(f"  creator royalty paid:  ${ledger.balance('acct:ben') / 100:.2f}")
    print(f"  shop paid:             ${ledger.balance('acct:node:n-k2plus') / 100:.2f}")
    print(f"  network fee:           ${ledger.balance('acct:network') / 100:.2f}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "ledger.json"), "w") as f:
        f.write(ledger.to_json())
    with open(os.path.join(OUT_DIR, "dashboard.html"), "w") as f:
        f.write(render_dashboard(registry, ledger, [order], [agent]))
    print("  wrote out/ledger.json and out/dashboard.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
