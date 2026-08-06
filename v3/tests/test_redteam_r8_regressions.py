"""Regressions for the round-8 red-team break (workflow wf_1eb0eed2-ad3).
Round 8: 6 of 7 surfaces found NOTHING; one CRITICAL remained. The R6/R7
completeness gate checked qty "if present" in the signed JOB_ACCEPTED, so a node
could carry job_id (dodging the fail-closed else) but OMIT qty — skipping both the
qty binding AND the completed==qty check — and be paid for zero fabricated units.
Both the money gate (NodeAgent.verify_chain) and the shipped document verifier
(evidence.verify) shared the hole. Fix: the identity fields are now
REQUIRED-present and bound unconditionally. Each assertion FAILS on the round-7
code and PASSES now.

  python -m tests.test_redteam_r8_regressions
"""

from __future__ import annotations

import sys

from bingo import crypto
from bingo.models import Job, EvidenceEvent, canonical_json, sha256_hex
from bingo.node.agent import NodeAgent
import bingo.evidence as evidence


def _ev(seq, typ, data, prev):
    ev = EvidenceEvent(seq=seq, ts="t", type=typ, data=data, prev_hash=prev)
    ev.sig = "00"                       # dummy; verify_chain(pk=None) skips sig check
    ev.hash = sha256_hex(canonical_json(ev.body()) + ev.sig.encode())
    return ev


# ── agent: verify_chain requires qty (and all identity) bound in signed event ─
def test_verify_chain_requires_qty_bound():
    # JOB_ACCEPTED carries job_id (dodging the fail-closed else) but OMITS qty
    ja = _ev(0, "JOB_ACCEPTED",
             {"node_id": "n", "job_id": "j", "order_id": "o", "asset_id": "a",
              "royalty_assets": []},           # <-- no qty
             "0" * 64)
    job = Job(job_id="j", order_id="o", asset_id="a", node_id="n", qty=10, material="PLA")
    job.evidence = [ja]                          # zero UNIT_COMPLETE
    assert NodeAgent.verify_chain(job, None) is False, \
        "a JOB_ACCEPTED that omits qty must not pass the settlement gate"
    # honest control: all fields bound + produced qty verifies
    ja2 = _ev(0, "JOB_ACCEPTED",
              {"node_id": "n", "job_id": "j", "order_id": "o", "asset_id": "a",
               "qty": 1, "royalty_assets": []}, "0" * 64)
    uc = _ev(1, "UNIT_COMPLETE", {"unit_serial": "j-u001"}, ja2.hash)
    job2 = Job(job_id="j", order_id="o", asset_id="a", node_id="n", qty=1, material="PLA")
    job2.evidence = [ja2, uc]
    assert NodeAgent.verify_chain(job2, None) is True, "an honest bound chain must still pass"


# ── evidence.verify: same required-present binding for the document verifier ───
def test_evidence_verify_requires_qty_bound():
    seed = bytes(range(1, 33))
    sk, pk = crypto.keypair(seed)
    pub = pk.hex()

    def mk(seq, typ, data, prev):
        body = canonical_json({"seq": seq, "ts": "t", "type": typ,
                               "data": data, "prev_hash": prev})
        sig = crypto.sign(body, sk, pk).hex()
        return {"seq": seq, "ts": "t", "type": typ, "data": data, "prev_hash": prev,
                "sig": sig, "hash": sha256_hex(body + sig.encode())}

    ja = mk(0, "JOB_ACCEPTED",
            {"node_pubkey": pub, "node_id": "n", "job_id": "j", "order_id": "o",
             "asset_id": "a", "royalty_assets": []},   # <-- no qty
            "0" * 64)
    doc = {"schema": "bingo/evidence/0.1", "job_id": "j", "order_id": "o",
           "asset_id": "a", "node_id": "n", "node_pubkey": pub, "qty": 10,
           "royalty_assets": [], "events": [ja]}
    ok, why = evidence.verify(doc, pub)
    assert not ok and "fully-bound" in why[-1], \
        "the document verifier must reject a JOB_ACCEPTED that omits qty"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-8 regression groups pass: both the "
          "settlement money gate (NodeAgent.verify_chain) and the shipped document "
          "verifier (evidence.verify) now REQUIRE the full job identity "
          "(incl. qty) to be present and bound in the signed JOB_ACCEPTED, so a "
          "node cannot omit qty to be paid for zero fabricated units.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
