"""Regressions for the round-3 red-team breaks (workflow wf_a6711b6f-9df).
Round 3 found 10 confirmed breaks (2 were the same machine_id gap) against the
round-2-hardened HEAD 5667449 — all the same recurring class: an unsigned
top-level field the round-2 fixes bound field-by-field but missed, plus two new
classes (acceptance replay/freshness, split-bps-sum validation). Each assertion
FAILS on the round-2 code and PASSES now.

  python -m tests.test_redteam_r3_regressions
"""

from __future__ import annotations

import copy
import sys

from provenance.passport import Actor, CutPassport, verify_passport
from provenance.token import AssetToken, verify_token
from provenance.machine_rwa import verify_machine_share
from provenance import raise_readiness as RR
from provenance.transport import (TransportPassport, condition, make_acceptance,
                                  verify_transport)
import bingo.evidence as evidence

from tests.test_passport import build as build_passport
from tests.test_machine_rwa import build as build_machine
from tests.test_transport import actors as t_actors, subject as t_subject, booked as t_booked


# ── machine_rwa: machine_id pinned to signed OPEN (#1 / #10) ─────────────────
def test_machine_id_bound_to_signed_open():
    ms = build_machine()[0]
    doc = ms.to_dict()
    assert verify_machine_share(doc)[0]
    t = copy.deepcopy(doc)
    t["machine_id"] = "haas-vf2-cnc-flagship"      # signed OPEN still says the real id
    assert not verify_machine_share(t)[0], "top-level machine_id must be pinned to signed OPEN"
    # term_sheet is verify-gated, so it refuses the forged doc (no 'signed offering'
    # banner over an attacker-chosen machine, and no KeyError on a missing id)
    try:
        RR.term_sheet(t)
        assert False, "term_sheet must refuse a doc whose machine_id doesn't verify"
    except ValueError:
        pass


# ── transport: acceptance bound to the booking (#2 replay, #3 outsider mint) ──
def test_transport_acceptance_not_replayable():
    broker, c1, ghost, cust = t_actors()
    vin = t_subject()["vin"]
    # legit transport #1 with carrier c1
    pp1 = t_booked(broker, c1, cust)
    pp1.pickup(c1, condition(12340), ts="t1")
    acc1 = make_acceptance(cust, vin=vin, cond=condition(12995),
                           booking_hash=pp1.events[0]["hash"], ts="t2")
    pp1.deliver(c1, acc1, condition(12995), ts="t3")
    assert verify_transport(pp1.to_dict())[0], "honest transport must verify"
    # transport #2: a DIFFERENT carrier/amount, same VIN+customer, replay acc1
    pp2 = t_booked(broker, ghost, cust)
    pp2.pickup(ghost, condition(12340), ts="t1")
    pp2.deliver(ghost, acc1, condition(12995), ts="t3")     # replayed acceptance
    ok, why = verify_transport(pp2.to_dict())
    assert not ok and "not bound to this booking" in why[-1], \
        "a stale acceptance from a different booking must be rejected"


def test_transport_outsider_cannot_mint():
    broker, c1, _g, cust = t_actors()
    vin = t_subject()["vin"]
    # a real transport where the customer signed a (public) acceptance
    pp1 = t_booked(broker, c1, cust)
    pp1.pickup(c1, condition(12340), ts="t1")
    acc1 = make_acceptance(cust, vin=vin, cond=condition(12995),
                           booking_hash=pp1.events[0]["hash"], ts="t2")
    pp1.deliver(c1, acc1, condition(12995), ts="t3")
    # an outsider self-signs a booking naming themselves carrier + the victim as
    # customer, and reuses the victim's public acceptance to try to settle
    mallory = Actor.create("mal", "Mallory", "carrier", "acct:carrier:MALLORY")
    pp2 = TransportPassport(t_subject())
    pp2.book(mallory, mallory, cust, price_cents=480000, carrier_cents=480000,
             pickup_window="w", delivery_window="w", ts="t0")
    pp2.pickup(mallory, condition(12340), ts="t1")
    pp2.deliver(mallory, acc1, condition(12995), ts="t3")   # replayed public acceptance
    ok, _ = verify_transport(pp2.to_dict())
    assert not ok, "outsider-minted transport reusing a public acceptance must be rejected"


def test_transport_damage_cannot_be_suppressed():
    broker, c1, _g, cust = t_actors()
    vin = t_subject()["vin"]
    pp = t_booked(broker, c1, cust)
    pp.pickup(c1, condition(12340, damage=[]), ts="t1")
    # the customer co-signs DAMAGE at delivery...
    acc = make_acceptance(cust, vin=vin, cond=condition(12995, damage=["bumper dent"]),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    # ...but the carrier stamps a CLEAN delivery condition to suppress the claim
    pp.deliver(c1, acc, condition(12995, damage=[]), ts="t3")
    ok, _ = verify_transport(pp.to_dict())
    assert not ok, "carrier delivery condition != customer-accepted condition must be rejected"


# ── passport: subject bound (#5) + split must allocate 100% (#6) ─────────────
def test_passport_subject_bound():
    pp = build_passport().to_dict()
    assert verify_passport(pp)[0]
    t = copy.deepcopy(pp)
    t["subject"] = dict(t["subject"], product="Kobe A5 (COUNTERFEIT RELABEL)",
                        lot="FORGED-LOT-999")
    ok, why = verify_passport(t)
    assert not ok and "subject" in why[-1], "relabeled subject must break the genesis commitment"


def test_passport_split_must_sum_full():
    op = Actor.create("op", "Op", "operation", "acct:op")
    pp = CutPassport(subject={"product": "A5 strip", "lot": "L1", "weight_lb": 1})
    pp.attest(op, "LINEAGE", {"tajima_pct": 96})
    price = 10_000
    # an under-summed split (6000 bps): the residue rule would dump the 4000 bps
    # shortfall onto the first payee while the per-payee bps read as an even 30/30
    split = {"payees": [{"account": "acct:op", "bps": 3000},
                        {"account": "acct:rancher", "bps": 3000}]}
    legs = [{"account": "acct:op", "bps": 3000, "cents": 7000},
            {"account": "acct:rancher", "bps": 3000, "cents": 3000}]
    pp.attest(op, "SALE", {"buyer": "b", "unit": "1", "price_cents": price,
                           "split": split, "legs": legs})
    pp.settlement = legs
    ok, why = verify_passport(pp.to_dict())
    assert not ok and "sum to 10000" in why[-1], "under-summed split must be rejected"


# ── token: fulfiller (#7) + value_split (#8) bound to the signed ISSUE ────────
def test_token_fulfiller_bound():
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    ful = Actor.create("ful", "Ful", "fulfiller", "acct:ful")
    tok = AssetToken(backing_asset_id="a", passport_head="0" * 64, unit="cut",
                     total_supply=10, issuer=iss,
                     value_split=[{"account": "acct:creator", "bps": 10000}],
                     fulfiller=ful, ts="t0")
    doc = tok.to_dict()
    assert verify_token(doc)[0]
    t = copy.deepcopy(doc)
    t["fulfiller"] = None            # strip the physical-settlement gate
    assert not verify_token(t)[0], "stripping top-level fulfiller must be rejected"


def test_token_value_split_bound():
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    tok = AssetToken(backing_asset_id="a", passport_head="0" * 64, unit="cut",
                     total_supply=10, issuer=iss,
                     value_split=[{"account": "acct:rancher", "bps": 3000},
                                  {"account": "acct:iss", "bps": 7000}], ts="t0")
    doc = tok.to_dict()
    assert verify_token(doc)[0]
    t = copy.deepcopy(doc)
    t["value_split"] = [{"account": "acct:iss", "bps": 10000}]   # rancher zeroed
    assert not verify_token(t)[0], "forged value_split on a pre-sale token must be rejected"


# ── evidence: node_id (the payout account) bound to signed JOB_ACCEPTED (#9) ──
def test_evidence_node_id_bound():
    from tests.test_redteam_r2_regressions import _one_evidence_doc
    doc, pub = _one_evidence_doc()
    assert evidence.verify(doc, pub)[0], "honest evidence must verify"
    t = copy.deepcopy(doc)
    t["node_id"] = "attacker-mule"          # redirect who is credited/paid
    assert not evidence.verify(t, pub)[0], "relabeled node_id must be rejected"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-3 regression groups pass: the 9 distinct "
          "breaks are closed — machine_id / passport subject / token fulfiller & "
          "value_split / evidence node_id now bound to their signatures, customer "
          "acceptance bound to its booking (no replay / outsider mint), delivery "
          "condition bound to the customer's, and SALE splits must allocate 100%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
