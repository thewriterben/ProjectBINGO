"""Auto-transport custody passport — makes double brokering unable to settle.

Double brokering works because auto transport runs on trust-by-paperwork: on
documents everything looks right, but the truck actually holding the customer's
car has no verified relationship to the party getting paid. The defense the
industry sells is *detection* (vet harder, call FMCSA, monitor). This makes it
*structural*: the carrier's identity is cryptographically bound at booking, and
escrow can only release to that same identity after a delivery it signed and the
customer accepted. A re-brokered load doesn't have to be caught — it can't
settle, because the identity at delivery isn't the one bound at pickup.

Same primitives as the rest of BINGO — Ed25519, canonical-JSON, hash-chained
signed events (see provenance/passport.py). The links here are:

  BOOKING   broker binds the carrier identity + escrow (broker-signed)
  PICKUP    carrier signs the condition at origin — odometer, damage, photos
  TRANSIT   optional location attestations (carrier-signed)
  DELIVERY  carrier signs handoff; customer's acceptance receipt is co-signed

verify_transport() rejects a chain whose PICKUP/DELIVERY isn't signed by the
identity bound at BOOKING (the double-broker guarantee), plus tamper / reorder /
unauthorized signer / missing customer acceptance. escrow_decision() then says
whether the money may move, to whom, and flags any new damage at delivery.
"""

from __future__ import annotations

from bingo.models import canonical_json, now_iso, sha256_hex
from .passport import Actor

SCHEMA = "bingo/transport/0.1"
ZERO = "0" * 64


class TransportError(Exception):
    pass


# --------------------------------------------------------------- condition

def condition(odometer: int, damage: list[str] | None = None,
              photos_sha256: str = "", notes: str = "") -> dict:
    """A condition report captured at a handoff. `photos_sha256` is the hash of
    the photo set (the images live wherever; the hash binds them to the chain)."""
    return {"odometer": odometer, "damage": sorted(damage or []),
            "photos_sha256": photos_sha256, "notes": notes}


def damage_delta(pickup_cond: dict, delivery_cond: dict) -> list[str]:
    """Damage present at delivery that wasn't noted at pickup — the basis of an
    honest damage claim, and impossible to argue once both ends are signed."""
    before = set(pickup_cond.get("damage", []))
    return sorted(d for d in delivery_cond.get("damage", []) if d not in before)


# --------------------------------------------------------------- receipts

def _acceptance_body(r: dict) -> bytes:
    return canonical_json({k: r[k] for k in
                           ("passport_subject_vin", "customer", "condition", "ts")})


def make_acceptance(customer: Actor, *, vin: str, cond: dict, ts: str) -> dict:
    """The customer's signed acceptance of the vehicle at delivery, in the
    condition recorded. Co-signs the DELIVERY so a middleman can't fake receipt."""
    r = {"passport_subject_vin": vin, "customer": customer.actor_id,
         "condition": cond, "ts": ts}
    r["sig"] = customer.sign(_acceptance_body(r))
    r["pubkey"] = customer.pubkey_hex
    return r


# --------------------------------------------------------------- passport

class TransportPassport:
    """The signed custody chain + escrow for moving ONE vehicle."""

    def __init__(self, subject: dict):
        self.subject = subject          # {vin, vehicle, origin, destination}
        self.signers: dict[str, dict] = {}
        self.events: list[dict] = []
        self.bound_carrier: dict | None = None      # carrier identity pinned at booking
        self.bound_customer: dict | None = None      # customer identity pinned at booking
        self.escrow = {"amount_cents": 0, "carrier_cents": 0, "broker_fee_cents": 0,
                       "status": "NONE", "released_to": None}

    # -- signed, hash-chained ledger --------------------------------------

    def _emit(self, actor: Actor, type_: str, data: dict, ts: str | None = None):
        self.signers.setdefault(actor.actor_id, actor.public())
        ev = {"seq": len(self.events), "ts": ts or now_iso(), "type": type_,
              "signer": actor.actor_id, "data": data,
              "prev_hash": self.events[-1]["hash"] if self.events else ZERO}
        body = canonical_json({k: ev[k] for k in
                               ("seq", "ts", "type", "signer", "data", "prev_hash")})
        ev["sig"] = actor.sign(body)
        ev["hash"] = sha256_hex(body + ev["sig"].encode())
        self.events.append(ev)
        return ev

    # -- lifecycle ---------------------------------------------------------

    def book(self, broker: Actor, carrier: Actor, customer: Actor, *,
             price_cents: int, carrier_cents: int, pickup_window: str,
             delivery_window: str, ts: str | None = None):
        """Broker books the load and BINDS this carrier's identity. Escrow is
        funded here; the carrier bound now is the only one it can ever pay."""
        if carrier_cents > price_cents:
            raise TransportError("carrier payment cannot exceed the escrow amount")
        self.bound_carrier = carrier.public()
        self.bound_customer = customer.public()
        self.escrow = {"amount_cents": price_cents, "carrier_cents": carrier_cents,
                       "broker_fee_cents": price_cents - carrier_cents,
                       "status": "HELD", "released_to": None}
        self._emit(broker, "BOOKING", {
            "carrier": carrier.public(), "customer": customer.public(),
            "authority": carrier.public().get("authority", ""),
            "price_cents": price_cents, "carrier_cents": carrier_cents,
            "pickup_window": pickup_window, "delivery_window": delivery_window}, ts=ts)
        return self

    def pickup(self, carrier: Actor, cond: dict, location: str = "",
               ts: str | None = None):
        """Carrier signs the vehicle's condition at origin. (Recorded whoever
        signs — a fraudulent pickup by the wrong carrier is captured, then
        exposed by verify_transport, not silently blocked.)"""
        self._emit(carrier, "PICKUP",
                   {"condition": cond, "location": location}, ts=ts)
        return self

    def transit(self, carrier: Actor, location: str, ts: str | None = None):
        self._emit(carrier, "TRANSIT", {"location": location}, ts=ts)
        return self

    def deliver(self, carrier: Actor, acceptance: dict, cond: dict,
                location: str = "", ts: str | None = None):
        """Carrier signs the handoff; the customer's signed acceptance receipt
        is embedded so both ends of the delivery are attested."""
        self._emit(carrier, "DELIVERY",
                   {"condition": cond, "location": location,
                    "acceptance": acceptance}, ts=ts)
        return self

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "subject": self.subject,
                "bound_carrier": self.bound_carrier,
                "bound_customer": self.bound_customer, "escrow": self.escrow,
                "signers": self.signers, "events": self.events,
                "chain_head": self.events[-1]["hash"] if self.events else ZERO}


# --------------------------------------------------------------- verify

def _body(ev: dict) -> bytes:
    return canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})


def _crypto_verify(body: bytes, sig_hex: str, pub_hex: str) -> bool:
    from bingo import crypto
    return crypto.verify(body, bytes.fromhex(sig_hex), bytes.fromhex(pub_hex))


def verify_transport(pp: dict) -> tuple[bool, list[str]]:
    """Verify the custody chain from the document alone. The load-bearing check
    is identity binding: PICKUP and DELIVERY must be signed by the carrier bound
    at BOOKING. If they aren't, that's a re-brokered load and it's rejected —
    which is what stops the money."""
    notes: list[str] = []
    events = pp.get("events", [])
    signers = pp.get("signers", {})
    if not events or events[0]["type"] != "BOOKING":
        return False, ["custody chain must open with a BOOKING"]

    # the carrier/customer/escrow bound "at booking" come from the broker-SIGNED
    # BOOKING event, NOT the unsigned top-level fields (which a re-broker can
    # rewrite to swap the carrier, redirect the payout account, change the amount,
    # or swap in a colluding customer). Anything a settlement reads must trace to
    # the signature.
    bd = events[0].get("data", {})
    bound = bd.get("carrier") or {}
    bound_pub = bound.get("pubkey")
    if not bound_pub:
        return False, ["no carrier identity bound in the signed BOOKING"]
    bound_customer = bd.get("customer") or {}
    # the unsigned top-level mirrors must equal the signed BOOKING, or the doc lies
    if pp.get("bound_carrier") not in (None, bound):
        return False, ["top-level bound_carrier != signed BOOKING carrier"]
    if pp.get("bound_customer") not in (None, bound_customer):
        return False, ["top-level bound_customer != signed BOOKING customer"]
    esc = pp.get("escrow") or {}
    if esc:
        if esc.get("amount_cents") != bd.get("price_cents") or \
           esc.get("carrier_cents") != bd.get("carrier_cents"):
            return False, ["top-level escrow != signed BOOKING amounts"]

    prev = ZERO
    saw_pickup = saw_delivery = False
    for ev in events:
        who = ev.get("signer", "")
        rec = signers.get(who)
        if not rec:
            return False, notes + [f"event {ev['seq']}: signer '{who}' not registered"]
        if ev["prev_hash"] != prev:
            return False, notes + [f"event {ev['seq']}: broken hash chain"]
        body = _body(ev)
        if ev["hash"] != sha256_hex(body + ev["sig"].encode()):
            return False, notes + [f"event {ev['seq']}: hash mismatch (tampered)"]
        try:
            if not _crypto_verify(body, ev["sig"], rec["pubkey"]):
                return False, notes + [f"event {ev['seq']}: bad signature for '{who}'"]
        except (ValueError, KeyError):
            return False, notes + [f"event {ev['seq']}: signature/key not hex"]
        prev = ev["hash"]

        t = ev["type"]
        # THE double-broker guarantee: custody events must be the bound carrier
        if t in ("PICKUP", "TRANSIT", "DELIVERY"):
            if rec["pubkey"] != bound_pub:
                return False, notes + [
                    f"event {ev['seq']}: {t} signed by '{rec.get('name', who)}', "
                    f"NOT the carrier bound at booking — double brokering detected"]
        if t == "PICKUP":
            saw_pickup = True
        if t == "DELIVERY":
            saw_delivery = True
            # customer (bound at booking) must have co-signed acceptance for THIS vehicle
            acc = ev["data"].get("acceptance") or {}
            crec = bound_customer          # from the SIGNED BOOKING, not top-level
            if not crec.get("pubkey"):
                return False, notes + [f"event {ev['seq']}: no customer bound at booking"]
            if acc.get("customer") != crec.get("actor_id"):
                return False, notes + [f"event {ev['seq']}: acceptance not by the booked customer"]
            try:
                if not _crypto_verify(_acceptance_body(acc), acc["sig"], crec["pubkey"]):
                    return False, notes + [f"event {ev['seq']}: customer acceptance signature invalid"]
            except (ValueError, KeyError):
                return False, notes + [f"event {ev['seq']}: acceptance not signed properly"]
            if acc.get("passport_subject_vin") != pp["subject"].get("vin"):
                return False, notes + [f"event {ev['seq']}: acceptance is for a different vehicle"]

    notes.append(f"{len(events)} custody links; carrier identity bound at booking "
                 f"held through {'delivery' if saw_delivery else 'pickup' if saw_pickup else 'booking'}")
    if saw_delivery:
        notes.append("PICKUP and DELIVERY both signed by the bound carrier — not re-brokered")
    notes.append(f"chain head {pp['chain_head'][:16]}… (verified)")
    return True, notes


def escrow_decision(pp: dict) -> dict:
    """Given a verified custody chain, decide the escrow outcome. Releases only
    on a valid delivery by the bound carrier with customer acceptance; surfaces
    any new damage as a claim (release still allowed, claim flagged for the
    broker to resolve — the point is nobody can hide it)."""
    ok, notes = verify_transport(pp)
    if not ok:
        return {"release": False, "status": "BLOCKED", "to": None, "amount_cents": 0,
                "reason": notes[-1], "damage_claim": None}
    # amounts + payout account come from the SIGNED BOOKING (verify already
    # confirmed any top-level mirror matches), never the unsigned top-level fields
    bd = pp["events"][0].get("data", {})
    carrier_cents = bd.get("carrier_cents", 0)
    broker_fee_cents = bd.get("price_cents", 0) - carrier_cents
    carrier_acct = (bd.get("carrier") or {}).get("account")

    evs = {e["type"]: e for e in pp["events"]}
    if "DELIVERY" not in evs:
        return {"release": False, "status": "HELD", "to": None, "amount_cents": 0,
                "reason": "awaiting delivery + customer acceptance", "damage_claim": None}

    pickup_cond = evs.get("PICKUP", {}).get("data", {}).get("condition", {})
    delivery_cond = evs["DELIVERY"]["data"].get("condition", {})
    new_damage = damage_delta(pickup_cond, delivery_cond)

    return {
        "release": True, "status": "RELEASED", "to": carrier_acct,
        "amount_cents": carrier_cents,
        "broker_fee_cents": broker_fee_cents,
        "reason": "delivered by the bound carrier and accepted by the customer",
        "damage_claim": {"new_damage": new_damage,
                         "odometer_delta": delivery_cond.get("odometer", 0)
                         - pickup_cond.get("odometer", 0)} if new_damage else None,
    }
