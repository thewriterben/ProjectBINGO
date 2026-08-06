"""Regressions for the 19 confirmed red-team breaks (workflow wf_38b722a3-538).
Each assertion here would FAIL on the pre-fix code and PASS now. Grouped by the
finding numbers in REDTEAM-FINDINGS.md.

  python -m tests.test_redteam_regressions
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

from bingo.models import Job, RoyaltyLine, SplitPayee
from bingo.settlement import compute_settlement_legs, SettlementError
from bingo import crypto
from provenance.passport import Actor, verify_passport
from provenance.token import (AssetToken, verify_token, route, TokenError,
                              make_fulfillment)
from provenance.machine_rwa import verify_machine_share
from provenance.coin import (mint_coin, RedemptionRegistry, StubValidationBackend)
from bingo.training import RoyaltyMeter, TrainingError
from bingo.payout import PayoutEngine, MockRail
from bingo.settlement import Leg

from tests.test_passport import build as build_passport
from tests.test_machine_rwa import build as build_machine


def _job(*, fab=100, mat=0, energy=0, logi=10, fee=9, royalties=None) -> Job:
    return Job(job_id="j", order_id="o", asset_id="a", node_id="n", qty=1,
               material="PLA", fabrication_cents=fab, material_cents=mat,
               energy_cents=energy, logistics_cents=logi, fee_cents=fee,
               royalty_lines=royalties or [])


def test_conservation_and_inputs():          # #1, #2, #17, #18
    # #1 token routing: nonzero amount with no payees must RAISE, not lose funds
    try:
        route(100_000, [])
        assert False, "route with empty payees must raise"
    except TokenError:
        pass
    # a no-split token can't do a primary sale silently (proceeds would vanish)
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    tok = AssetToken(backing_asset_id="a", passport_head="0" * 64, unit="u",
                     total_supply=10, issuer=iss, value_split=[], ts="t0")
    try:
        tok.sell(iss, "acct:buyer", 1, price_cents=1000, ts="t1")
        assert False, "primary sale with no split must raise"
    except TokenError:
        pass

    # #2/#18 tiny multi-payee royalty line conserves (residue placed, not dropped)
    line = RoyaltyLine("assetX", 1, [SplitPayee("p1", 5000), SplitPayee("p2", 5000)])
    legs = compute_settlement_legs(_job(royalties=[line]))
    j = _job(royalties=[line])
    assert sum(l.amount_cents for l in legs) == j.job_total_cents

    # #2/#18 conservation is enforced by a raise (survives python -O), not assert:
    #   an over-subscribed royalty line (bps sum > 10000) must be rejected
    bad = RoyaltyLine("assetY", 100, [SplitPayee("p1", 10000), SplitPayee("p2", 10000)])
    try:
        compute_settlement_legs(_job(royalties=[bad]))
        assert False, "over-distribution must raise"
    except SettlementError:
        pass

    # #17 negative components must be refused, not paid as negative legs
    try:
        compute_settlement_legs(_job(fee=-100))
        assert False, "negative component must raise"
    except SettlementError:
        pass


def test_passport_unsigned_settlement():      # #8 (critical)
    pp = build_passport().to_dict()
    assert verify_passport(pp)[0]
    # reroute the unsigned top-level settlement to an attacker, same total
    t = copy.deepcopy(pp)
    price = next(e for e in t["events"] if e["type"] == "SALE")["data"]["price_cents"]
    t["settlement"] = [{"account": "acct:attacker", "bps": 10000, "cents": price}]
    ok, why = verify_passport(t)
    assert not ok and "settlement" in why[-1].lower(), why


def test_coin_unsigned_postings_injection():  # #3, #6, #13 (critical)
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    coin = mint_coin(dgd, serial="DGD-1", passport_head="a" * 64, credit_cents=2500)
    d = tempfile.mkdtemp(); path = os.path.join(d, "store.json")
    try:
        r = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                               backend=StubValidationBackend())
        r.redeem(coin, "acct:holder", ts="t1")
        # attacker edits the store, injecting an unsigned posting crediting himself
        data = json.load(open(path))
        data["postings"]["DGD-EVIL"] = {"serial": "DGD-EVIL", "account": "acct:thief",
                                        "cents": 1_000_000, "status": "pending", "ref": None}
        json.dump(data, open(path, "w"))
        # reload + retry: the injected posting must never cause a real credit
        b2 = StubValidationBackend()
        r2 = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=b2)
        r2.retry_pending(ts="t2")
        assert all(p["account"] != "acct:thief" for p in b2.postings), b2.postings
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


def test_coin_no_double_credit_on_status_flip():  # #14
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    coin = mint_coin(dgd, serial="DGD-2", passport_head="b" * 64, credit_cents=2500)
    d = tempfile.mkdtemp(); path = os.path.join(d, "store.json")
    try:
        b1 = StubValidationBackend()
        r = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=b1)
        r.redeem(coin, "acct:holder", ts="t1")
        assert len(b1.postings) == 1
        # attacker flips the (unsigned) posting back to 'pending' to force a re-credit
        data = json.load(open(path))
        data["postings"]["DGD-2"]["status"] = "pending"
        json.dump(data, open(path, "w"))
        b2 = StubValidationBackend()
        r2 = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=b2)
        r2.retry_pending(ts="t2")
        assert b2.postings == [], "signed POSTED must prevent a second credit"
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


def test_machine_rwa_unsigned_terms():         # #9
    ms = build_machine()[0]
    doc = ms.to_dict()
    assert verify_machine_share(doc)[0]
    for field, val in (("total_shares", 999999), ("investor_share_bps", 1),
                       ("repayment_cap_cents", 10 ** 12), ("price_cents", 1)):
        t = copy.deepcopy(doc)
        t[field] = val
        ok, why = verify_machine_share(t)
        assert not ok and "OPEN" in why[-1], (field, why)


def test_machine_rwa_no_fragment_starvation():  # #16
    ms, op, alice, bob = build_machine()
    # operator drips revenue in 1-cent events; investors must still accrue their
    # cumulative share (pre-fix each event floored their pool to 0)
    for i in range(50):
        ms.earn(op, 1, f"drip-{i}", ts=f"d{i}")
    expected = (50 * ms.investor_share_bps) // 10_000      # 50 * 0.6 = 30
    assert expected > 0
    assert ms.cumulative_paid() == expected, (ms.cumulative_paid(), expected)
    assert verify_machine_share(ms.to_dict())[0]


def _token_with_passport(fulfiller=None):
    pp = build_passport().to_dict()
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    tok = AssetToken(backing_asset_id="wagyu", passport_head=pp["chain_head"],
                     unit="cut", total_supply=10, issuer=iss,
                     value_split=[{"account": "acct:iss", "bps": 10000}],
                     fulfiller=fulfiller, ts="t0")
    return pp, iss, tok


def test_token_passport_pin_and_balances():    # #10, #12
    pp, iss, tok = _token_with_passport()
    doc = tok.to_dict()
    assert verify_token(doc, pp)[0]
    # #10 relabel the pin onto a different (premium) passport head
    t = copy.deepcopy(doc); t["passport_head"] = "c" * 64
    assert not verify_token(t)[0]
    # #12 inflate a displayed balance the ledger never granted
    t = copy.deepcopy(doc); t["balances"] = {"acct:thief": 10}
    assert not verify_token(t)[0]


def test_token_receipt_reuse_and_anchor():     # #5, #11
    ful = Actor.create("ful", "Grocer", "grocer", "acct:ful")
    pp, iss, tok = _token_with_passport(fulfiller=ful)
    custody = next(e["hash"] for e in pp["events"] if e["type"] == "CUSTODY")
    # #5 one signed delivery of 5 units can't redeem 10 shares across two redeems
    rcpt = make_fulfillment(ful, token_id=tok.token_id, delivery_ref=custody,
                            units=5, ts="t1")
    tok.redeem(iss, 5, receipt=rcpt, ts="t2")
    try:
        tok.redeem(iss, 5, receipt=rcpt, ts="t3")
        assert False, "reusing a 5-unit receipt for 10 total must raise"
    except TokenError:
        pass
    # #11 a redemption anchored to a NON-delivery event is rejected on verify
    _, iss2, tok2 = _token_with_passport(fulfiller=ful)
    harvest = next(e["hash"] for e in pp["events"] if e["type"] == "HARVEST")
    rc2 = make_fulfillment(ful, token_id=tok2.token_id, delivery_ref=harvest,
                           units=5, ts="t1")
    tok2.redeem(iss2, 5, receipt=rc2, ts="t2")   # runtime accepts a valid receipt…
    ok, why = verify_token(tok2.to_dict(), pp)   # …but verify rejects the anchor
    assert not ok and "CUSTODY" in why[-1], why


def test_payout_reorder_no_double_pay():       # #7, #15
    legs = [Leg("acct:node:x", 550, "fab"), Leg("acct:carrier-pool", 22, "logi"),
            Leg("acct:ben", 148, "royalty"), Leg("acct:network", 40, "fee")]
    rail = MockRail(); eng = PayoutEngine(rail)
    eng.pay_legs(legs, order_id="o", job_id="j")
    n = len(rail.sent)
    eng.pay_legs(list(reversed(legs)), order_id="o", job_id="j")   # reordered replay
    assert len(rail.sent) == n, "reordering identical legs must not re-pay"
    assert eng.reconcile_job("j", legs)["fully_settled"]


def test_training_negative_fee():              # #19
    m = RoyaltyMeter()
    try:
        m.record_usage("model-1", "evt-1", fee_cents=-1_000_000, training_share_bps=5000)
        assert False, "negative fee must raise"
    except TrainingError:
        pass


def test_crypto_low_order_key():               # #4
    # forge a signature that verifies under the identity public key: S=1, R=[1]B,
    # so [S]B == R + [k]*identity == R. Must now be rejected (small-subgroup guard).
    ident_pub = crypto._encodepoint((0, 1))
    R = crypto._encodepoint(crypto._scalarmult(crypto.B, 1))
    S = crypto._encodeint(1)
    forged = R + S
    assert crypto.verify(b"anything", forged, ident_pub) is False
    # a legitimate key still verifies (sanity)
    sk, pk = crypto.keypair(bytes(range(32)))
    assert crypto.verify(b"m", crypto.sign(b"m", sk, pk), pk)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} red-team regression groups pass: the 19 confirmed "
          "breaks (2 critical, 9 high, 7 medium, 1 low) are closed — unsigned-field "
          "trust, receipt/anchor reuse, positional idempotency, assert/-O & negative "
          "conservation, fragmentation griefing, negative fees, and low-order-key "
          "forgery all now fail closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
