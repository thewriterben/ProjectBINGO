"""Auto-transport custody passport: the double-broker guarantee (escrow can only
release to the carrier bound at booking), plus tamper/reorder/acceptance checks,
damage-delta claims, and escrow conservation. Run:

  python -m tests.test_transport
"""

from __future__ import annotations

import copy
import json
import sys

from provenance.passport import Actor
from provenance.transport import (TransportPassport, condition, make_acceptance,
                                  verify_transport, escrow_decision, damage_delta)

VIN = "WP0AB2A99NS227614"


def actors():
    return (Actor.create("apex", "Apex (broker)", "broker", "acct:broker"),
            Actor.create("bound", "Bound Carrier", "carrier", "acct:carrier:bound"),
            Actor.create("ghost", "Ghost (re-broker)", "carrier", "acct:carrier:ghost"),
            Actor.create("cust", "Owner", "customer", "acct:customer"))


def subject():
    return {"vin": VIN, "vehicle": "2022 Porsche 911", "origin": "AZ", "destination": "ID"}


def booked(broker, carrier, cust):
    pp = TransportPassport(subject())
    pp.book(broker, carrier, cust, price_cents=185000, carrier_cents=160000,
            pickup_window="w1", delivery_window="w2", ts="t0")
    return pp


def main() -> int:
    broker, bound, ghost, cust = actors()

    # ---- honest move: verifies, escrow releases to the bound carrier ----
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), location="AZ", ts="t1")
    acc = make_acceptance(cust, vin=VIN, cond=condition(12995),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(bound, acc, condition(12995), location="ID", ts="t3")
    d = pp.to_dict()
    ok, notes = verify_transport(d)
    assert ok, notes
    dec = escrow_decision(d)
    assert dec["release"] and dec["status"] == "RELEASED"
    assert dec["to"] == "acct:carrier:bound" and dec["amount_cents"] == 160000
    # escrow conservation
    esc = d["escrow"]
    assert esc["carrier_cents"] + esc["broker_fee_cents"] == esc["amount_cents"]

    # ---- THE guarantee: a different truck delivers -> can't verify, can't settle ----
    pp = booked(broker, bound, cust)
    pp.pickup(ghost, condition(12340), ts="t1")             # re-broker picks up
    acc = make_acceptance(cust, vin=VIN, cond=condition(12995),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(ghost, acc, condition(12995), ts="t3")
    bad, why = verify_transport(pp.to_dict())
    assert not bad and "double brokering detected" in why[-1], why
    assert escrow_decision(pp.to_dict())["status"] == "BLOCKED"

    # a re-broker who swaps in only at DELIVERY is caught too
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), ts="t1")
    acc = make_acceptance(cust, vin=VIN, cond=condition(12995),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(ghost, acc, condition(12995), ts="t3")       # delivered by wrong carrier
    bad, why = verify_transport(pp.to_dict())
    assert not bad and "double brokering detected" in why[-1], why

    # ---- customer acceptance must be the booked customer, for this vehicle ----
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), ts="t1")
    imposter = Actor.create("imp", "Imposter", "customer", "acct:customer")
    acc_bad = make_acceptance(imposter, vin=VIN, cond=condition(12995),
                              booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(bound, acc_bad, condition(12995), ts="t3")
    bad, why = verify_transport(pp.to_dict())
    assert not bad and "not by the booked customer" in why[-1], why

    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), ts="t1")
    acc_vin = make_acceptance(cust, vin="OTHERVIN00000000", cond=condition(12995),
                              booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(bound, acc_vin, condition(12995), ts="t3")
    bad, why = verify_transport(pp.to_dict())
    assert not bad and "different vehicle" in why[-1], why

    # forged acceptance signature (right customer id, wrong key) is rejected
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), ts="t1")
    from provenance.transport import _acceptance_body
    forged = {"passport_subject_vin": VIN, "customer": "cust",
              "condition": condition(12995), "booking_hash": pp.events[0]["hash"],
              "ts": "t2"}
    forged["sig"] = imposter.sign(_acceptance_body(forged))     # not cust's key
    forged["pubkey"] = imposter.pubkey_hex
    pp.deliver(bound, forged, condition(12995), ts="t3")
    bad, why = verify_transport(pp.to_dict())
    assert not bad and "acceptance signature invalid" in why[-1], why

    # ---- tamper & reorder are caught ----
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), ts="t1")
    acc = make_acceptance(cust, vin=VIN, cond=condition(12995),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(bound, acc, condition(12995), ts="t3")
    good = pp.to_dict()

    t = copy.deepcopy(good)
    t["events"][1]["data"]["condition"]["odometer"] = 1          # tamper pickup odo
    bad, why = verify_transport(t)
    assert not bad and "tampered" in why[-1], why

    t = copy.deepcopy(good)
    t["events"][1], t["events"][2] = t["events"][2], t["events"][1]
    bad, why = verify_transport(t)
    assert not bad and "hash chain" in why[-1], why

    # ---- damage delta: new damage at delivery becomes an undeniable claim ----
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340, damage=[]), ts="t1")
    dmg = condition(12995, damage=["door scuff"])
    acc = make_acceptance(cust, vin=VIN, cond=dmg,
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(bound, acc, dmg, ts="t3")
    d = pp.to_dict()
    ok, _ = verify_transport(d)
    assert ok
    dec = escrow_decision(d)
    assert dec["release"] and dec["damage_claim"]["new_damage"] == ["door scuff"]
    assert damage_delta(condition(1, damage=["old"]),
                        condition(2, damage=["old", "new"])) == ["new"]

    # ---- before delivery, escrow is HELD (not released, not blocked) ----
    pp = booked(broker, bound, cust)
    pp.pickup(bound, condition(12340), ts="t1")
    dec = escrow_decision(pp.to_dict())
    assert not dec["release"] and dec["status"] == "HELD"

    # round-trips as JSON, verifiable offline
    assert verify_transport(json.loads(json.dumps(good)))[0]

    print("OK — custody chain verifies; escrow releases ONLY to the carrier bound at "
          "booking (double brokering at pickup OR delivery blocks settlement); "
          "customer acceptance must be the booked owner for the right VIN; tamper, "
          "reorder & forged acceptance caught; new damage at delivery flagged as an "
          "undeniable claim; escrow conserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
