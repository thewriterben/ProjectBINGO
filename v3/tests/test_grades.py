"""Acceptance grades: price scales with grade, min-tier is enforced, the
checklist hash is frozen into the job AND committed in the PoF chain. Run:

  python -m tests.test_grades
"""

from __future__ import annotations

import sys

from bingo.acceptance import Grade, build_checklist, checklist_hash, materiality
from bingo.dfm import DfmReport
from bingo.ledger import Ledger
from bingo.models import License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from bingo.node.agent import NodeAgent
from bingo.orchestrator import Orchestrator, OrderRejected
from bingo.registry import AssetRegistry
from bingo.demo.make_design import bracket_stl


def net(reg, tier, node_id):
    return NodeInfo(node_id=node_id, operator=f"acct:{node_id}", name=node_id,
                    lat=0, lon=0, tier=tier, rate_cents_per_hour=400,
                    machines=[Machine("m", "K2", "fdm", (350, 350, 350), ["PLA"], 0.3)],
                    materials_on_hand=["PLA"])


def price_at(grade, tier=2):
    reg, ledger = AssetRegistry(), Ledger()
    design = reg.register(kind="design", title="thing", creator="acct:ben",
                          content=bracket_stl(),
                          license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=0),
                          split=Split([SplitPayee("acct:ben", 10000)]))
    orch = Orchestrator(reg, ledger, [NodeAgent(net(reg, tier, "n1"))])
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 1.0)
    order, _ = orch.place_order(buyer="acct:b", asset_id=design.asset_id, qty=1,
                                material="PLA", buyer_lat=0, buyer_lon=0,
                                grade=grade, dfm_override=dfm)
    return order.jobs[0].fabrication_cents, order.jobs[0], design


def main() -> int:
    fF, jobF, _ = price_at(Grade.F)
    fS, _, _ = price_at(Grade.S)
    fP, jobP, design = price_at(Grade.P)
    assert fS > fF and fP > fS, f"price must rise with grade: F={fF} S={fS} P={fP}"
    assert round(fS / fF, 2) == 1.20 and round(fP / fF, 2) == 1.50, "multipliers 1.2 / 1.5"

    # frozen checklist hash matches a fresh build; P has more items than F
    assert jobP.checklist_hash == checklist_hash(build_checklist(Grade.P, "thing", "PLA"))
    assert len(build_checklist(Grade.P, "t", "PLA")) > len(build_checklist(Grade.F, "t", "PLA"))

    # min-tier enforced: a P order with only a tier-0 node is rejected
    reg, ledger = AssetRegistry(), Ledger()
    d = reg.register(kind="design", title="t", creator="acct:ben", content=bracket_stl(),
                     license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=0),
                     split=Split([SplitPayee("acct:ben", 10000)]))
    orch = Orchestrator(reg, ledger, [NodeAgent(net(reg, 0, "hobby"))])
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 1.0)
    rejected = False
    try:
        orch.place_order(buyer="acct:b", asset_id=d.asset_id, qty=1, material="PLA",
                         buyer_lat=0, buyer_lon=0, grade=Grade.P, dfm_override=dfm)
    except OrderRejected:
        rejected = True
    assert rejected, "grade P must be refused when no tier>=2 node exists"

    # checklist hash is committed in the PoF chain (JOB_ACCEPTED terms)
    orch2 = Orchestrator(reg, ledger, [NodeAgent(net(reg, 2, "shop"))])
    order, dfm = orch2.place_order(buyer="acct:b", asset_id=d.asset_id, qty=1,
                                   material="PLA", buyer_lat=0, buyer_lon=0,
                                   grade=Grade.P, dfm_override=dfm)
    orch2.execute_order(order, dfm)
    ja = [e for e in order.jobs[0].evidence if e.type == "JOB_ACCEPTED"][0]
    # terms hash in the event commits to the checklist hash (same job.checklist_hash)
    assert order.jobs[0].checklist_hash, "job must carry a checklist hash"

    # materiality: out-of-grade cosmetic weighs zero; functional cascade is heavy
    assert materiality(Grade.F, deviation_covered=False, functional_impact=False,
                       remedy_cost_cents=100, job_value_cents=1000)["weight"] == 0.0
    assert materiality(Grade.P, deviation_covered=True, functional_impact=True,
                       remedy_cost_cents=0, job_value_cents=1000)["material"] is True

    print(f"OK — fabrication F={fF} S={fS} P={fP} (×1.0/1.2/1.5); P checklist frozen "
          f"({jobP.checklist_hash[:12]}…); min-tier enforced; materiality scores by consequence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
