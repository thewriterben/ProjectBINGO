"""Regressions for the round-4 red-team breaks (workflow wf_967de90b-854).
Round 4 found 7 confirmed breaks against the round-3-hardened HEAD d3095ca
(machine_rwa found nothing; coin's one claim was rejected as a test-stub
artifact). Each assertion FAILS on the round-3 code and PASSES now.

  python -m tests.test_redteam_r4_regressions
"""

from __future__ import annotations

import copy
import sys

from bingo import crypto
from bingo.models import Split, SplitPayee, canonical_json, sha256_hex
from provenance.passport import Actor, CutPassport, verify_passport
from provenance.token import AssetToken, verify_token
from provenance.machine_rwa import verify_machine_share
from provenance.transport import (TransportPassport, condition, make_acceptance,
                                  verify_transport, escrow_decision)
import bingo.evidence as evidence

from tests.test_machine_rwa import build as build_machine
from tests.test_transport import actors as t_actors, subject as t_subject, booked as t_booked


# ── transport: escrow amounts must be sane; null condition can't slip through ──
def test_transport_carrier_cents_bounded():
    broker, c1, _g, cust = t_actors()
    pp = TransportPassport(t_subject())
    # a broker-signed BOOKING with carrier_cents > price_cents (book() would refuse,
    # but the verifier is the settlement gate and must re-enforce it)
    pp._emit(broker, "BOOKING", {"carrier": c1.public(), "customer": cust.public(),
             "authority": "", "price_cents": 100000, "carrier_cents": 250000,
             "pickup_window": "w", "delivery_window": "w"}, ts="t0")
    pp.bound_carrier = c1.public()
    pp.bound_customer = cust.public()
    pp.escrow = {"amount_cents": 100000, "carrier_cents": 250000,
                 "broker_fee_cents": -150000, "status": "HELD", "released_to": None}
    pp.pickup(c1, condition(12340), ts="t1")
    acc = make_acceptance(cust, vin=t_subject()["vin"], cond=condition(12995),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(c1, acc, condition(12995), ts="t3")
    ok, why = verify_transport(pp.to_dict())
    assert not ok and "out of range" in why[-1], "carrier_cents > price_cents must be rejected"


def test_transport_null_condition_rejected():
    broker, c1, _g, cust = t_actors()
    pp = t_booked(broker, c1, cust)
    pp.pickup(c1, condition(12340), ts="t1")
    # a JSON-null condition passes the None==None equality check then crashes
    # escrow_decision — the verifier must reject it up front
    acc = make_acceptance(cust, vin=t_subject()["vin"], cond=None,
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(c1, acc, None, ts="t3")
    ok, _ = verify_transport(pp.to_dict())
    assert not ok, "null delivery condition must be rejected (was: escrow_decision crash)"
    # and the settlement authority must not raise on it
    dec = escrow_decision(pp.to_dict())
    assert dec["status"] == "BLOCKED"


# ── passport: every SALE conserves; per-payee bps must be positive ───────────
def test_passport_second_sale_conserves():
    op = Actor.create("op", "Op", "operation", "acct:op")
    pp = CutPassport(subject={"product": "A5", "lot": "L", "weight_lb": 1})
    pp.attest(op, "LINEAGE", {"tajima_pct": 96})
    split = Split([SplitPayee("acct:op", 4000), SplitPayee("acct:rancher", 6000)])
    pp.record_sale(op, 10000, split, buyer="b", unit="1")     # honest first sale
    assert verify_passport(pp.to_dict())[0]
    # append a SECOND signed, chained SALE whose legs pay $10,000 for a $1 sale
    pp.attest(op, "SALE", {"buyer": "b2", "unit": "1", "price_cents": 100,
                           "split": split.to_dict(),
                           "legs": [{"account": "acct:op", "bps": 4000, "cents": 1000000},
                                    {"account": "acct:rancher", "bps": 6000, "cents": 0}]})
    ok, _ = verify_passport(pp.to_dict())
    assert not ok, "a second non-conserving SALE must be rejected (value from nothing)"


def test_passport_negative_bps_rejected():
    op = Actor.create("op", "Op", "operation", "acct:op")
    pp = CutPassport(subject={"product": "A5", "lot": "L", "weight_lb": 1})
    pp.attest(op, "LINEAGE", {"tajima_pct": 96})
    price = 10000
    # bps sum to 10000 but one is negative -> attacker paid 200%, victim -100%
    split = {"payees": [{"account": "acct:attacker", "bps": 20000},
                        {"account": "acct:victim", "bps": -10000}]}
    legs = [{"account": "acct:attacker", "bps": 20000, "cents": 20000},
            {"account": "acct:victim", "bps": -10000, "cents": -10000}]
    pp.attest(op, "SALE", {"buyer": "b", "unit": "1", "price_cents": price,
                           "split": split, "legs": legs})
    pp.settlement = legs
    ok, why = verify_passport(pp.to_dict())
    assert not ok and "non-positive bps" in why[-1], "negative-bps split must be rejected"


# ── token: account ownership is bound to a key (CRITICAL) ─────────────────────
def test_token_account_not_stealable():
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    alice = Actor.create("alice", "Alice", "holder", "acct:alice")
    eve = Actor.create("eve", "Eve", "holder", "acct:eve")
    tok = AssetToken(backing_asset_id="a", passport_head="0" * 64, unit="cut",
                     total_supply=100, issuer=iss,
                     value_split=[{"account": "acct:creator", "bps": 10000}], ts="t0")
    tok.transfer(iss, alice, 40, ts="t1")      # Actor recipient binds acct:alice -> alice's key
    doc = tok.to_dict()
    assert verify_token(doc)[0]
    # Eve, with ONLY her own key, appends a holder record claiming acct:alice and a
    # self-signed TRANSFER sweeping Alice's shares to herself
    t = copy.deepcopy(doc)
    t["holders"]["eve"] = {"actor_id": "eve", "name": "Eve", "role": "holder",
                           "account": "acct:alice", "pubkey": eve.pubkey_hex}
    ev = {"seq": len(t["events"]), "ts": "t9", "type": "TRANSFER", "signer": "eve",
          "data": {"from": "acct:alice", "to": "acct:eve", "to_pubkey": None, "shares": 40},
          "prev_hash": t["events"][-1]["hash"]}
    body = canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})
    ev["sig"] = eve.sign(body)
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    t["events"].append(ev)
    t["balances"] = {"acct:iss": 60, "acct:eve": 40}
    ok, _ = verify_token(t)
    assert not ok, "Eve claiming Alice's account with her own key must be rejected"


# ── evidence: the chain must evidence the signed quantity ────────────────────
def test_evidence_requires_all_units():
    seed = bytes(range(32))
    sk, pk = crypto.keypair(seed)
    pub = pk.hex()
    data = {"node_id": "n1", "node_pubkey": pub, "job_id": "j1", "order_id": "o1",
            "asset_id": "a1", "qty": 1, "royalty_assets": []}
    body = canonical_json({"seq": 0, "ts": "t", "type": "JOB_ACCEPTED",
                           "data": data, "prev_hash": "0" * 64})
    sig = crypto.sign(body, sk, pk).hex()
    ja = {"seq": 0, "ts": "t", "type": "JOB_ACCEPTED", "data": data,
          "prev_hash": "0" * 64, "sig": sig, "hash": sha256_hex(body + sig.encode())}
    doc = {"schema": "bingo/evidence/0.1", "job_id": "j1", "order_id": "o1",
           "asset_id": "a1", "node_id": "n1", "node_pubkey": pub, "qty": 1,
           "royalty_assets": [], "events": [ja]}
    ok, why = evidence.verify(doc, pub)
    assert not ok and "incomplete" in why[-1], "0 units for a signed qty of 1 must be rejected"


# ── machine_rwa: non-string event_ref fails closed (no crash) ────────────────
def test_machine_earn_ref_hashable():
    ms, op, alice, bob = build_machine()
    # forge an operator-signed EARN whose event_ref is a list; earn() now refuses
    # it, and verify_machine_share must RETURN False rather than raise TypeError
    ms._emit(op, "EARN", {"revenue_cents": 10000, "event_ref": [],
                          "to_investors": 0, "to_operator": 10000, "legs": [],
                          "cumulative_after": ms.cumulative_paid()}, ts="t9")
    ok, _ = verify_machine_share(ms.to_dict())   # must not raise
    assert not ok, "non-string event_ref must fail closed"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-4 regression groups pass: token account "
          "ownership is bound to a key (no account theft); passport checks EVERY "
          "sale's conservation and rejects non-positive bps; transport rejects "
          "carrier_cents>price and null conditions; evidence requires #units==qty; "
          "and a non-string EARN event_ref fails closed instead of crashing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
