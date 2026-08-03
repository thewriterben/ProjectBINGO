"""The thin vertical, end to end:

  design -> royalty -> distributed fabrication -> proof -> atomic settlement

Run:  python -m bingo.demo.run   (from v3/)
Outputs: console narrative, out/ledger.json, out/dashboard.html
"""

from __future__ import annotations

import os

from ..ledger import Ledger, NETWORK_ACCOUNT, CARRIER_ACCOUNT
from ..models import (Derivation, License, LicenseTemplate, Machine,
                      NodeInfo, Split, SplitPayee)
from ..node.agent import NodeAgent
from ..orchestrator import Orchestrator
from ..registry import AssetRegistry
from .dashboard import render_dashboard
from .make_design import bracket_stl, clip_stl

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "out")


def build_network() -> list[NodeAgent]:
    """Three heterogeneous nodes in three places — a bedroom Bambu, a Prusa
    farm, a pro shop. All mock-driven here; drivers.py shows the real seams."""
    def fdm(machine_id, model, kw=0.12):
        return Machine(machine_id=machine_id, make_model=model, process="fdm",
                       envelope_mm=(250, 250, 250), materials=["PLA", "PETG"], kw=kw)

    nodes = [
        NodeInfo(node_id="n-slc", operator="acct:dana", name="Dana's spare-room Bambu (SLC)",
                 lat=40.76, lon=-111.89, tier=0, rate_cents_per_hour=250,
                 machines=[fdm("m-x1c-01", "Bambu X1C")], reputation=0.55),
        NodeInfo(node_id="n-abq", operator="acct:mia", name="Mia's print farm (ABQ)",
                 lat=35.08, lon=-106.65, tier=1, rate_cents_per_hour=400,
                 machines=[fdm("m-mk4-07", "Prusa MK4", kw=0.10)], reputation=0.72),
        NodeInfo(node_id="n-kc", operator="acct:ray", name="Ray's job shop (KC)",
                 lat=39.10, lon=-94.58, tier=2, rate_cents_per_hour=650,
                 machines=[fdm("m-x1e-02", "Bambu X1E", kw=0.14)], reputation=0.85),
    ]
    return [NodeAgent(n) for n in nodes]


def main():
    registry, ledger = AssetRegistry(), Ledger()
    agents = build_network()
    orch = Orchestrator(registry, ledger, agents,
                        evidence_dir=os.path.join(OUT_DIR, "evidence"))
    say = print

    say("═" * 72)
    say("PROJECT BINGO v3 — thin vertical demo")
    say("═" * 72)

    # ── L1: creators register designs with royalty splits ───────────────────
    bracket = registry.register(
        kind="design", title="PB-001 shelf bracket", creator="acct:ben",
        content=bracket_stl(),
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
        split=Split([SplitPayee("acct:ben", 8000), SplitPayee("acct:alex", 2000)]))
    say(f"\n[L1] registered '{bracket.title}'  id={bracket.asset_id[:12]}…")
    say(f"     license: 40¢/unit · split: ben 80% / alex 20%")

    clip = registry.register(
        kind="design", title="PB-002 cable clip (remix of PB-001)", creator="acct:carol",
        content=clip_stl(),
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=25),
        split=Split([SplitPayee("acct:carol", 10000)]),
        derives_from=[Derivation(bracket.asset_id, parent_share_bps=2000)])
    eff = {p.account: p.bps for p in clip.effective_split.payees}
    say(f"[L1] registered '{clip.title}'  id={clip.asset_id[:12]}…")
    say(f"     license: 25¢/unit · effective split (composed): {eff}")
    say(f"     → carol's remix automatically owes ben+alex 20% of every royalty")

    # ── L5→L3: buyer orders; pipeline quotes, matches, escrows ────────────────
    say("\n[L3] order #1: 12 shelf brackets → buyer in Denver")
    o1, dfm1 = orch.place_order(buyer="acct:buyer-denver", asset_id=bracket.asset_id,
                                qty=12, material="PLA",
                                buyer_lat=39.74, buyer_lon=-104.99)
    say(f"     DFM: {dfm1.triangles} tris, bbox "
        f"{tuple(round(b, 1) for b in dfm1.bbox_mm)} mm, "
        f"{dfm1.volume_mm3 / 1000:.1f} cm³, watertight ✓ · "
        f"~{dfm1.est_grams_per_unit:.0f} g, ~{dfm1.est_hours_per_unit:.1f} h/unit")
    say(f"     allocation: " + ", ".join(
        f"{orch.nodes[j.node_id].info.name.split(' (')[0]} ×{j.qty}" for j in o1.jobs))
    say(f"     escrow funded: ${o1.total_cents / 100:.2f}")

    say("\n[L2] fabrication + PoF + [L4] atomic settlement per delivery:")
    orch.execute_order(o1, dfm1, narrate=say)

    say("\n[L3] order #2: 6 cable clips (the remix) → buyer in Phoenix")
    o2, dfm2 = orch.place_order(buyer="acct:buyer-phx", asset_id=clip.asset_id,
                                qty=6, material="PLA",
                                buyer_lat=33.45, buyer_lon=-112.07)
    say(f"     escrow funded: ${o2.total_cents / 100:.2f}")
    orch.execute_order(o2, dfm2, narrate=say)

    # ── invariants ───────────────────────────────────────────────────────────
    assert ledger.escrow[o1.order_id] == 0, "order 1 escrow must zero out"
    assert ledger.escrow[o2.order_id] == 0, "order 2 escrow must zero out"
    paid_out = sum(ledger.balances.values())
    funded = o1.total_cents + o2.total_cents
    assert paid_out == funded, f"cents conservation violated: {paid_out} != {funded}"
    say("\n[✓] invariants hold: both escrows exactly zero; "
        f"every funded cent accounted for (${funded / 100:.2f})")

    # ── the number that is the whole vision ─────────────────────────────────────
    say("\n" + "─" * 72)
    say("CREATOR EARNINGS (royalties only, paid atomically with fabrication):")
    for acct in ("acct:ben", "acct:alex", "acct:carol"):
        say(f"   {acct:<14} ${ledger.balance(acct) / 100:>7.2f}")
    say("NODE OPERATOR EARNINGS:")
    for a in agents:
        say(f"   {a.info.operator:<14} ${ledger.balance(f'acct:node:{a.info.node_id}') / 100:>7.2f}"
            f"   ({a.info.name})")
    say(f"   {'network fee':<14} ${ledger.balance(NETWORK_ACCOUNT) / 100:>7.2f}")
    say(f"   {'carrier pool':<14} ${ledger.balance(CARRIER_ACCOUNT) / 100:>7.2f}")

    say("\n★ '{}' has earned its creators ${:.2f} across {} units on {} machines.".format(
        bracket.title,
        (ledger.balance("acct:ben") + ledger.balance("acct:alex")) / 100,
        o1.qty + o2.qty,  # ben+alex earn on the remix too, via composition
        len({j.node_id for j in o1.jobs + o2.jobs})))

    # ── artifacts ──────────────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "ledger.json"), "w") as f:
        f.write(ledger.to_json())
    dash = render_dashboard(registry, ledger, [o1, o2], agents)
    with open(os.path.join(OUT_DIR, "dashboard.html"), "w") as f:
        f.write(dash)
    say(f"\nwrote out/ledger.json and out/dashboard.html")


if __name__ == "__main__":
    main()
