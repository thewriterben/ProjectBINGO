"""Manual-mode node: operator-attested batch fabrication for machines without
a live driver (MSLA resin printers like the Halot Mage Pro, or any process
where telemetry isn't wired yet).

Evidence model per specs/NODE-AGENT.md tier scaling: for batch/manual work the
trust load shifts from live telemetry to (a) operator-attested stage events,
(b) photo commitments (file hashes as FRAME events, hashed at attestation
time), and (c) first-article / spot-check inspection by a certified inspector.
The chain is still hash-linked and signed — what changes is who observes.

Run a batch job end to end (from v3/):

  python -m bingo.node.manual --store out/registry ^
      --design-id <asset_id> --package-id <asset_id> ^
      --qty 30 --material siraya-blu-v2 ^
      --buyer acct:foundation --est-minutes 90 --grams 6 ^
      --node-name "Ben's Halot Mage Pro" --operator acct:ben-shop

The runner prompts at each stage: batch start, plate photo, post-cure photo,
good-unit count, receipt confirmation — then settles atomically and writes
out/ledger.json + out/dashboard.html.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from ..dfm import DfmReport
from ..ledger import Ledger
from ..models import Machine, NodeInfo
from ..orchestrator import Orchestrator
from ..registry import AssetRegistry
from .agent import NodeAgent
from ..demo.dashboard import render_dashboard

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "out")


class ManualDriver:
    """Operator-attested batch driver. Photo paths are hashed at attestation
    time — the commitment is real even though observation is human."""

    def __init__(self, machine_id: str, ask=input, say=print):
        self.machine_id = machine_id
        self.ask = ask
        self.say = say

    def prepare(self, package: bytes) -> dict:
        return {"package_sha256": hashlib.sha256(package).hexdigest(),
                "machine_id": self.machine_id, "mode": "manual-attested"}

    def _photo(self, prompt: str) -> str | None:
        path = self.ask(prompt).strip().strip('"')
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            self.say("    (couldn't read that path — continuing without photo)")
            return None

    def run_batch(self, job_id: str, qty: int, est_minutes: float):
        self.ask(f"    [manual] plate loaded for {qty} units — press Enter when "
                 f"the print STARTS… ")
        yield {"type": "TELEMETRY", "stage": "batch-start",
               "attested_by": "operator", "qty_plated": qty}
        h = self._photo("    [manual] pre-print plate photo path (Enter to skip): ")
        if h:
            yield {"type": "FRAME", "stage": "plate-pre", "frame_sha256": h}

        self.ask(f"    [manual] press Enter when the batch is COMPLETE and "
                 f"post-processed (wash/cure)… ")
        h = self._photo("    [manual] post-cure batch photo path (Enter to skip): ")
        if h:
            yield {"type": "FRAME", "stage": "batch-cured", "frame_sha256": h}

        while True:
            raw = self.ask(f"    [manual] good units out of {qty}: ").strip()
            try:
                good = int(raw)
                if 0 <= good <= qty:
                    break
            except ValueError:
                pass
            self.say(f"    enter a number 0–{qty}")

        if good < qty:
            yield {"type": "TELEMETRY", "stage": "batch-defects",
                   "attested_by": "operator", "good": good, "scrapped": qty - good}
        for i in range(good):
            yield {"type": "UNIT_COMPLETE", "unit_serial": f"{job_id}-u{i + 1:03d}",
                   "duration_min": round(est_minutes / max(qty, 1), 1)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO manual-mode batch node")
    ap.add_argument("--store", required=True, help="registry store directory")
    ap.add_argument("--design-id", required=True)
    ap.add_argument("--package-id", help="process-package asset id (its per-unit "
                    "royalty is added to the order as a second royalty line)")
    ap.add_argument("--qty", type=int, required=True)
    ap.add_argument("--material", default="siraya-blu-v2")
    ap.add_argument("--buyer", default="acct:foundation")
    ap.add_argument("--est-minutes", type=float, required=True, help="whole-batch minutes")
    ap.add_argument("--grams", type=float, default=6.0, help="grams per unit")
    ap.add_argument("--node-name", default="Manual node")
    ap.add_argument("--operator", default="acct:operator")
    ap.add_argument("--machine", default="halot-mage-pro")
    ap.add_argument("--rate", type=int, default=400, help="cents/hour")
    args = ap.parse_args(argv)

    registry = AssetRegistry.load(args.store)
    design = registry.get(args.design_id)
    package = registry.get(args.package_id) if args.package_id else None

    ledger = Ledger()
    node = NodeInfo(
        node_id=f"n-{uuid.uuid4().hex[:6]}", operator=args.operator,
        name=args.node_name, lat=0.0, lon=0.0, tier=1,
        rate_cents_per_hour=args.rate,
        machines=[Machine(machine_id=args.machine, make_model=args.machine,
                          process="msla", envelope_mm=(228, 128, 230),
                          materials=[args.material], kw=0.10)],
        materials_on_hand=[args.material], reputation=0.6)
    agent = NodeAgent(node, driver=ManualDriver(args.machine))
    orch = Orchestrator(registry, ledger, [agent])

    dfm = DfmReport(ok=True, issues=[], triangles=0, bbox_mm=(0, 0, 0),
                    volume_mm3=0.0, est_grams_per_unit=args.grams,
                    est_hours_per_unit=(args.est_minutes / max(args.qty, 1)) / 60.0)

    order, dfm = orch.place_order(buyer=args.buyer, asset_id=design.asset_id,
                                  qty=args.qty, material=args.material,
                                  buyer_lat=0.0, buyer_lon=0.0,
                                  required_tier=1, dfm_override=dfm,
                                  extra_royalty_assets=[package] if package else None)
    if package:
        print(f"✓ package royalty attached: {package.license.per_unit_cents}¢/unit → "
              f"'{package.title}' (settles to its own split)")

    print(f"✓ order {order.order_id}: {args.qty} × '{design.title}' — "
          f"escrow ${order.total_cents / 100:.2f}")
    print(f"  royalty lines: design '{design.title}'"
          + (f" + package '{package.title}'" if package else ""))

    def confirm_delivery(job):
        input("  batch delivered/handed off? Press Enter to confirm receipt "
              "and release settlement… ")
        return f"operator:{args.operator}"

    # Each royalty line settles to its OWN asset's split: the design royalty
    # to the design's payees, the package royalty to the package's payees, in
    # one atomic transaction (multi-asset routing landed v0.2).
    try:
        settled = orch.execute_order(order, dfm, narrate=print,
                                     gcode=registry.get_content(package or design),
                                     confirm_delivery=confirm_delivery)
    except (RuntimeError, KeyboardInterrupt) as e:
        print(f"\n✗ batch halted: {e}")
        return 1

    print(f"\n★ BATCH SETTLED: {sum(j.qty for j in settled)} unit(s)")
    for p in design.effective_split.payees:
        print(f"  {p.account:<20} ${ledger.balance(p.account) / 100:>7.2f}")
    print(f"  {'shop (' + args.operator + ')':<20} "
          f"${ledger.balance('acct:node:' + node.node_id) / 100:>7.2f}")
    print(f"  {'network fee':<20} ${ledger.balance('acct:network') / 100:>7.2f}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "ledger.json"), "w") as f:
        f.write(ledger.to_json())
    with open(os.path.join(OUT_DIR, "dashboard.html"), "w") as f:
        f.write(render_dashboard(registry, ledger, [order], [agent]))
    print("  wrote out/ledger.json and out/dashboard.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
