"""The independent-verification promise, proven: persist a real job's chain,
verify it from the file alone, and confirm tampering is caught. Run from v3/:

  python -m tests.test_verifier
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

from bingo import evidence
from bingo.dfm import DfmReport
from bingo.ledger import Ledger
from bingo.models import License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from bingo.node.agent import NodeAgent
from bingo.orchestrator import Orchestrator
from bingo.registry import AssetRegistry
from bingo.demo.make_design import bracket_stl


def main() -> int:
    tmp = tempfile.mkdtemp()
    reg, ledger = AssetRegistry(), Ledger()
    design = reg.register(kind="design", title="thing", creator="acct:ben",
                          content=bracket_stl(),
                          license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
                          split=Split([SplitPayee("acct:ben", 10000)]))
    node = NodeInfo(node_id="n1", operator="acct:shop", name="shop", lat=0, lon=0,
                    tier=1, rate_cents_per_hour=400,
                    machines=[Machine("m", "K2", "fdm", (350, 350, 350), ["PLA"], 0.3)],
                    materials_on_hand=["PLA"])
    agent = NodeAgent(node)
    ev_dir = os.path.join(tmp, "evidence")
    orch = Orchestrator(reg, ledger, [agent], evidence_dir=ev_dir)
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 0.1)
    order, dfm = orch.place_order(buyer="acct:b", asset_id=design.asset_id, qty=2,
                                  material="PLA", buyer_lat=0, buyer_lon=0,
                                  required_tier=1, dfm_override=dfm)
    settled = orch.execute_order(order, dfm)
    job = settled[0]

    path = os.path.join(ev_dir, f"{job.job_id}.json")
    assert os.path.exists(path), "evidence must be persisted"

    # 1) verifies from file alone using the EMBEDDED pubkey (self-describing)
    ev = evidence.load(path)
    ok, notes = evidence.verify(ev)
    assert ok, f"self-describing verify must pass: {notes}"

    # 2) verifies with the correct pubkey supplied
    ok, _ = evidence.verify(ev, agent.public_key_hex)
    assert ok, "verify with correct key must pass"

    # 3) rejects a wrong pubkey
    from bingo import crypto
    _, other = crypto.keypair()
    ok, _ = evidence.verify(ev, other.hex())
    assert not ok, "verify with wrong key must fail"

    # 4) rejects tampering: flip a byte in an event's data, keep its hash — caught
    tampered = json.loads(json.dumps(ev))
    for e in tampered["events"]:
        if e["type"] == "TELEMETRY":
            e["data"]["progress"] = 0.999
            break
    ok, notes = evidence.verify(tampered)
    assert not ok, "tampered event must fail verification"

    print(f"OK — persisted {len(ev['events'])} events; verifies from file with "
          f"embedded key; rejects wrong key and tampering. ({notes[0] if notes else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
