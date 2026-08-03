"""Multi-asset royalty routing: a design + a process package on one order,
each settling to its OWN split, in one atomic transaction. Run from v3/:

  python -m tests.test_multi_royalty
"""

from __future__ import annotations

import sys

from bingo.dfm import DfmReport
from bingo.ledger import Ledger
from bingo.models import License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from bingo.node.agent import NodeAgent
from bingo.orchestrator import Orchestrator
from bingo.registry import AssetRegistry
from bingo.demo.make_design import bracket_stl


def main() -> int:
    reg, ledger = AssetRegistry(), Ledger()

    design = reg.register(
        kind="design", title="DGD token", creator="acct:ben",
        content=bracket_stl(),
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
        split=Split([SplitPayee("acct:ben", 6000), SplitPayee("acct:john", 4000)]))
    package = reg.register(
        kind="profile", title="Halot process package", creator="acct:ben",
        content=b"exposure=2.1s;lift=3mm",
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=10),
        split=Split([SplitPayee("acct:ben", 10000)]))

    node = NodeInfo(node_id="n-x", operator="acct:shop", name="shop", lat=0, lon=0,
                    tier=1, rate_cents_per_hour=400,
                    machines=[Machine("m", "K2", "fdm", (350, 350, 350), ["PLA"], 0.3)],
                    materials_on_hand=["PLA"])
    orch = Orchestrator(reg, ledger, [NodeAgent(node)])
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 0.1)

    qty = 10
    order, dfm = orch.place_order(buyer="acct:foundation", asset_id=design.asset_id,
                                  qty=qty, material="PLA", buyer_lat=0, buyer_lon=0,
                                  required_tier=1, dfm_override=dfm,
                                  extra_royalty_assets=[package])
    orch.execute_order(order, dfm)

    # design royalty 40¢×10 = 400c split 60/40 -> ben 240, john 160
    # package royalty 10¢×10 = 100c split 100 -> ben 100
    # ben total = 240 + 100 = 340 ; john = 160
    assert ledger.escrow[order.order_id] == 0, "escrow must zero"
    assert ledger.balance("acct:john") == 160, ledger.balance("acct:john")
    assert ledger.balance("acct:ben") == 340, ledger.balance("acct:ben")

    # conservation: every funded cent landed somewhere
    assert sum(ledger.balances.values()) == order.total_cents, "cents conserved"

    # provenance records BOTH assets
    entry = [e for e in ledger.journal if e.kind == "JOB_SETTLEMENT"][0]
    assert set(entry.provenance["royalty_assets"]) == {design.asset_id, package.asset_id}

    print(f"OK — design→(ben 240 / john 160), package→(ben 100); "
          f"ben ${ledger.balance('acct:ben')/100:.2f}, john ${ledger.balance('acct:john')/100:.2f}. "
          f"Each line settled to its own split; escrow zeroed; both assets in provenance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
