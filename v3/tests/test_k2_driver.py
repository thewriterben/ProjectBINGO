"""Integration test: K2Driver against the fake Moonraker, wrapped in the full
node-agent PoF chain and settled through the ledger — the real-hardware code
path, minus the hardware.

Run from v3/:  python -m tests.test_k2_driver
"""

from __future__ import annotations

import sys

from bingo.ledger import Ledger
from bingo.models import Job, License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from bingo.node.agent import NodeAgent
from bingo.node.k2 import K2Driver
import bingo.node.k2 as k2mod
from bingo.registry import AssetRegistry
from bingo.demo.make_design import bracket_stl
from tests.fake_moonraker import start


def main() -> int:
    srv = start(port=7126, print_seconds=6.0)
    try:
        k2mod.POLL_SECONDS = 0.5                     # fast polling for test

        registry, ledger = AssetRegistry(), Ledger()
        asset = registry.register(
            kind="design", title="PB-001 shelf bracket", creator="acct:ben",
            content=bracket_stl(),
            license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
            split=Split([SplitPayee("acct:ben", 10_000)]))

        driver = K2Driver("127.0.0.1", 7126, confirm=lambda *_: None, say=print)
        node = NodeInfo(node_id="n-test", operator="acct:ben-shop", name="fake K2",
                        lat=0, lon=0, tier=1, rate_cents_per_hour=300,
                        machines=[Machine("m1", "Creality K2 Plus", "fdm",
                                          (350, 350, 350), ["PLA"], 0.35)])
        agent = NodeAgent(node, driver=driver)

        job = Job(job_id="job-test1", order_id="ord-test1", asset_id=asset.asset_id,
                  node_id="n-test", qty=2, material="PLA",
                  fabrication_cents=300, material_cents=60, energy_cents=5,
                  logistics_cents=550, royalty_cents=80, fee_cents=30)

        assert agent.offer(job, {"payment_cents": job.job_total_cents})
        agent.fabricate(job, b"; fake sliced gcode\nG28\n", est_minutes_per_unit=0.1)
        agent.ship(job, "local", "handoff")
        agent.confirm_delivery(job, "operator:test")

        assert NodeAgent.verify_chain(job), "PoF chain must verify"
        types = [e.type for e in job.evidence]
        for required in ("JOB_ACCEPTED", "INPUT_HASH", "TELEMETRY", "FRAME",
                         "UNIT_COMPLETE", "SHIPMENT", "DELIVERY_CONFIRMED"):
            assert required in types, f"missing {required} in evidence: {types}"
        assert types.count("UNIT_COMPLETE") == 2, "both units must complete"

        class FakeOrder:
            order_id, total_cents = "ord-test1", job.job_total_cents
            buyer = "acct:test-buyer"
        ledger.fund_escrow(FakeOrder)
        ledger.settle_job(FakeOrder, job, asset.effective_split.payees)
        assert ledger.escrow["ord-test1"] == 0
        assert ledger.balance("acct:ben") == 80, ledger.balances

        print(f"\nOK — {len(job.evidence)} PoF events "
              f"({types.count('TELEMETRY')} telemetry, {types.count('FRAME')} frames), "
              f"chain verified, settlement exact.")
        return 0
    finally:
        srv.shutdown()


if __name__ == "__main__":
    sys.exit(main())
