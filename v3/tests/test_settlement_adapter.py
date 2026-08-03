"""The settlement seam: the SAME orchestrator settles through the local Ledger
OR the Stripe-Connect stub with no code change, and both split money
identically via the shared leg math. Run:

  python -m tests.test_settlement_adapter
"""

from __future__ import annotations

import sys

from bingo.dfm import DfmReport
from bingo.ledger import Ledger
from bingo.settlement import StripeConnectStub
from bingo.models import License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from bingo.node.agent import NodeAgent
from bingo.orchestrator import Orchestrator
from bingo.registry import AssetRegistry
from bingo.demo.make_design import bracket_stl


def run_with(backend):
    reg = AssetRegistry()
    design = reg.register(kind="design", title="thing", creator="acct:ben",
                          content=bracket_stl(),
                          license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
                          split=Split([SplitPayee("acct:ben", 6000), SplitPayee("acct:john", 4000)]))
    node = NodeInfo(node_id="n1", operator="acct:shop", name="shop", lat=0, lon=0,
                    tier=1, rate_cents_per_hour=400,
                    machines=[Machine("m", "K2", "fdm", (350, 350, 350), ["PLA"], 0.3)],
                    materials_on_hand=["PLA"])
    orch = Orchestrator(reg, Ledger() if backend is None else backend, [NodeAgent(node)])
    # NOTE: orchestrator was handed `backend` as its settlement layer, unchanged
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 0.1)
    order, dfm = orch.place_order(buyer="acct:buyer", asset_id=design.asset_id, qty=4,
                                  material="PLA", buyer_lat=0, buyer_lon=0,
                                  required_tier=1, dfm_override=dfm)
    orch.execute_order(order, dfm)
    return orch.ledger, order


def main() -> int:
    # local ledger
    local, o1 = run_with(None)
    # stripe stub — same orchestrator path
    stub = StripeConnectStub()
    remote, o2 = run_with(stub)

    # both zero out escrow and pay the same accounts the same amounts
    assert local.escrow_remaining(o1.order_id) == 0
    assert remote.escrow_remaining(o2.order_id) == 0
    for acct in ("acct:ben", "acct:john", "acct:node:n1",
                 "acct:carrier-pool", "acct:network"):
        assert local.balance(acct) == remote.balance(acct), \
            f"{acct}: local {local.balance(acct)} != stub {remote.balance(acct)}"

    # the stub recorded real PSP-shaped intents (a hold + transfers)
    holds = [i for i in stub.intents if i.kind == "PAYMENT_INTENT"]
    transfers = [i for i in stub.intents if i.kind == "TRANSFER"]
    assert len(holds) == 1 and holds[0].amount_cents == o2.total_cents
    assert transfers and sum(t.amount_cents for t in transfers) == o2.total_cents

    print(f"OK — identical payouts via Ledger and StripeConnectStub with the same "
          f"orchestrator; stub logged 1 hold + {len(transfers)} transfers "
          f"summing to the order total (${o2.total_cents/100:.2f}). Zero orchestration change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
