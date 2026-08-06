"""Regressions for the round-7 red-team breaks (workflow wf_8b749e65-5fd).
Round 7 was a full attacker+verifier pass: 5 of 7 surfaces (coin, machine_rwa,
passport, token, raise_readiness) found NOTHING. Two confirmed breaks remained —
one HIGH (settlement-gate asymmetry) and one LOW (odometer crash). Each assertion
FAILS on the round-6 code and PASSES now.

  python -m tests.test_redteam_r7_regressions
"""

from __future__ import annotations

import sys

from bingo.models import Job, EvidenceEvent, canonical_json, sha256_hex
from bingo.node.agent import NodeAgent


def _ev(seq, typ, data, prev):
    ev = EvidenceEvent(seq=seq, ts="t", type=typ, data=data, prev_hash=prev)
    ev.sig = "00"                       # dummy; verify_chain(pk=None) skips sig check
    ev.hash = sha256_hex(canonical_json(ev.body()) + ev.sig.encode())
    return ev


# ── evidence/agent: the settlement gate must FAIL CLOSED with no job identity ─
def test_verify_chain_fails_closed_without_identity():
    # a JOB_ACCEPTED that omits job_id (and zero UNIT_COMPLETE) must NOT pass the
    # money gate — it did on round-6 code because the identity/qty block had no else
    job = Job(job_id="j", order_id="o", asset_id="a", node_id="n", qty=5, material="PLA")
    job.evidence = [_ev(0, "JOB_ACCEPTED", {"node_id": "n"}, "0" * 64)]   # NO job_id
    assert NodeAgent.verify_chain(job, None) is False, \
        "an identity-less JOB_ACCEPTED must fail the settlement gate"
    # empty evidence likewise cannot be attributed -> refuse
    job2 = Job(job_id="j", order_id="o", asset_id="a", node_id="n", qty=1, material="PLA")
    assert NodeAgent.verify_chain(job2, None) is False, "empty evidence must fail closed"
    # honest control: a bound JOB_ACCEPTED with the produced qty still verifies
    ja = _ev(0, "JOB_ACCEPTED",
             {"node_id": "n", "job_id": "j", "order_id": "o", "asset_id": "a",
              "qty": 1, "royalty_assets": []},
             "0" * 64)
    uc = _ev(1, "UNIT_COMPLETE", {"unit_serial": "j-u001"}, ja.hash)
    job3 = Job(job_id="j", order_id="o", asset_id="a", node_id="n", qty=1, material="PLA")
    job3.evidence = [ja, uc]
    assert NodeAgent.verify_chain(job3, None) is True, "an honest bound chain must still pass"


# ── transport: a non-int odometer verifies then crashes escrow_decision (LOW) ─
def test_transport_odometer_must_be_int():
    from provenance.transport import (condition, make_acceptance, verify_transport,
                                      escrow_decision)
    from tests.test_transport import actors, subject, booked
    broker, c1, _g, cust = actors()
    pp = booked(broker, c1, cust)
    pp.pickup(c1, condition(12340, damage=[]), ts="t1")
    dcond = condition(12995, damage=["dent"])
    acc = make_acceptance(cust, vin=subject()["vin"], cond=dcond,
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(c1, acc, dcond, ts="t3")
    d = pp.to_dict()
    # poison the carrier-signed delivery odometer with a string (damage non-empty
    # so escrow_decision reaches the odometer_delta subtraction)
    d["events"][2]["data"]["condition"]["odometer"] = "99999"
    ok, _ = verify_transport(d)
    assert not ok, "a non-int odometer must be rejected before settlement"
    assert escrow_decision(d)["status"] == "BLOCKED"   # and must not crash


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-7 regression groups pass: the settlement "
          "gate (NodeAgent.verify_chain) now fails CLOSED with no bound job "
          "identity — matching the shipped document verifier, so a node can't be "
          "paid for zero fabricated units — and a non-int odometer is rejected "
          "before it can crash escrow_decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
