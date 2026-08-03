"""Creator earnings aggregation from the settlement journal. Run:

  python -m tests.test_earnings
"""

from __future__ import annotations

import sys

from bingo.earnings import creator_earnings, statement_text
from bingo.dfm import DfmReport
from bingo.ledger import Ledger
from bingo.models import Derivation, License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from bingo.node.agent import NodeAgent
from bingo.orchestrator import Orchestrator
from bingo.registry import AssetRegistry
from bingo.demo.make_design import bracket_stl, clip_stl


def build():
    reg, ledger = AssetRegistry(), Ledger()
    bracket = reg.register(kind="design", title="PB-001 bracket", creator="acct:ben",
                           content=bracket_stl(),
                           license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
                           split=Split([SplitPayee("acct:ben", 8000), SplitPayee("acct:alex", 2000)]))
    clip = reg.register(kind="design", title="PB-002 clip (remix)", creator="acct:carol",
                        content=clip_stl(),
                        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=25),
                        split=Split([SplitPayee("acct:carol", 10000)]),
                        derives_from=[Derivation(bracket.asset_id, parent_share_bps=2000)])

    def node(nid, lat, lon, tier=1):
        return NodeInfo(node_id=nid, operator=f"acct:{nid}", name=nid, lat=lat, lon=lon,
                        tier=tier, rate_cents_per_hour=400,
                        machines=[Machine("m", "K2", "fdm", (350, 350, 350), ["PLA"], 0.3)],
                        materials_on_hand=["PLA"])
    agents = [NodeAgent(node("n-a", 40, -111)), NodeAgent(node("n-b", 35, -106)),
              NodeAgent(node("n-c", 39, -94))]
    orch = Orchestrator(reg, ledger, agents)
    return reg, ledger, orch, bracket, clip


def order(orch, asset_id, qty, lat, lon):
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 0.2)
    o, dfm = orch.place_order(buyer="acct:buyer", asset_id=asset_id, qty=qty,
                              material="PLA", buyer_lat=lat, buyer_lon=lon, dfm_override=dfm)
    orch.execute_order(o, dfm)


def main() -> int:
    reg, ledger, orch, bracket, clip = build()
    order(orch, bracket.asset_id, 12, 39.7, -105.0)   # 12 brackets
    order(orch, clip.asset_id, 8, 33.4, -112.0)       # 8 clips (remix of bracket)

    ben = creator_earnings(ledger, reg, "acct:ben")
    alex = creator_earnings(ledger, reg, "acct:alex")
    carol = creator_earnings(ledger, reg, "acct:carol")

    # bracket royalty 40¢×12 = 480 → ben 80% =384, alex 20% =96
    # clip royalty 25¢×8 = 200 → carol; PLUS remix sends 20% of clip royalty to
    #   bracket's split: clip effective split embeds ben+alex. So ben/alex also
    #   earn on the 8 clips.
    assert ben.total_cents > 384, ben.total_cents          # bracket + remix share
    assert carol.total_cents > 0
    assert ben.units >= 12
    # ben earned across BOTH designs (bracket direct + clip via remix)
    assert len(ben.designs) == 2, [d.title for d in ben.designs]
    # machines: ben's royalties came from jobs fanned across up to 3 nodes
    assert ben.machines >= 1

    # conservation sanity: every royalty cent paid equals sum of creators' totals
    total_paid = ben.total_cents + alex.total_cents + carol.total_cents
    royalties_in_ledger = sum(
        l.amount_cents for e in ledger.journal for l in e.legs if l.memo.startswith("royalty"))
    assert total_paid == royalties_in_ledger, (total_paid, royalties_in_ledger)

    stmt = statement_text(ben)
    assert "creator statement" in stmt and "PB-001 bracket" in stmt

    print(f"OK — ben ${ben.total_cents/100:.2f} across {ben.units} units / "
          f"{len(ben.designs)} designs / {ben.machines} machines; "
          f"carol ${carol.total_cents/100:.2f}; conservation holds "
          f"(${royalties_in_ledger/100:.2f} royalties = sum of creator earnings).")
    print("\n--- sample statement ---\n" + statement_text(ben))
    return 0


if __name__ == "__main__":
    sys.exit(main())
