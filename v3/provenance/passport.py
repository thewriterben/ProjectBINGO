"""A verifiable provenance passport for a physical real-world asset.

This is BINGO's proof-of-fabrication grammar pointed at a ribeye instead of a
print job. A premium A5 Wagyu cut is worth $65/lb because of its *provenance*,
not its protein: the genetics, the specific grains and alfalfa a named rancher
grew, the grade, the cold chain. Today that provenance lives in a paper label
and blind trust — which is why "Wagyu" and "Kobe" are the most counterfeited
words in food. This makes each link cryptographically attestable and routes
value back to the humans who created it.

Same primitives as the rest of BINGO — no new crypto:
  * bingo.crypto            Ed25519 sign/verify (pure Python, third-party verifiable)
  * bingo.models            canonical_json, sha256_hex, Split/SplitPayee
  * identical construction to bingo.evidence: each link is SHA-256 over its
    canonical-JSON body, Ed25519-signed, with hash = sha256(body + sig) and
    every link hash-chained onto the last. A proof-of-fabrication job is this
    same chain specialized to ONE signer (its body omits the per-event signer).

What's new here is only what the physical world demands that a print farm
didn't: many DIFFERENT actors each vouch for their own link (the rancher signs
the feed, the processor signs the cut, the carrier signs custody), so the body
carries a `signer` and the passport a registry of whose key is allowed to sign.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bingo import crypto
from bingo.models import Split, SplitPayee, canonical_json, now_iso, sha256_hex

SCHEMA = "bingo/passport/0.1"
ZERO = "0" * 64


# --------------------------------------------------------------------- actors

@dataclass
class Actor:
    """A party who can attest to a link in the chain, with a signing key.

    In production the seed is an actor's private key held in their own wallet;
    here we derive a deterministic keypair so demos and tests are reproducible.
    """
    actor_id: str
    name: str
    role: str                      # rancher | ranch | processor | carrier | grocer | operation
    account: str                   # settlement account the money routes to
    _seed: bytes = b""
    _pub: bytes = b""

    @classmethod
    def create(cls, actor_id: str, name: str, role: str, account: str,
               seed: bytes | None = None) -> "Actor":
        seed = seed if seed is not None else (actor_id.encode() + b"\x00" * 32)[:32]
        sk, pk = crypto.keypair(seed)
        return cls(actor_id, name, role, account, sk, pk)

    @property
    def pubkey_hex(self) -> str:
        return self._pub.hex()

    def sign(self, message: bytes) -> str:
        return crypto.sign(message, self._seed, self._pub).hex()

    def public(self) -> dict:
        return {"actor_id": self.actor_id, "name": self.name,
                "role": self.role, "account": self.account,
                "pubkey": self.pubkey_hex}


# --------------------------------------------------------------------- events

@dataclass
class PassportEvent:
    """One hash-chained, signer-attested link. Body/hash/sig identical to a
    bingo.evidence PoF event, plus a `signer` naming which actor vouched."""
    seq: int
    ts: str
    type: str
    signer: str                    # actor_id who attests to this link
    data: dict
    prev_hash: str
    sig: str = ""
    hash: str = ""

    def body(self) -> dict:
        # signer is inside the signed body — you can't reassign an attestation.
        return {"seq": self.seq, "ts": self.ts, "type": self.type,
                "signer": self.signer, "data": self.data, "prev_hash": self.prev_hash}

    def to_dict(self) -> dict:
        d = self.body()
        d["sig"], d["hash"] = self.sig, self.hash
        return d


# --------------------------------------------------------------------- passport

class CutPassport:
    """Builds and holds the signed chain for ONE physical unit (one cut / lot)."""

    def __init__(self, subject: dict):
        self.subject = subject          # what this passport is about (product, lot, weight)
        self.signers: dict[str, dict] = {}   # actor_id -> public actor record
        self.events: list[PassportEvent] = []
        self.settlement: list[dict] = []

    # -- chain construction ------------------------------------------------

    def attest(self, actor: Actor, type_: str, data: dict, ts: str | None = None) -> PassportEvent:
        """Append a link, signed by `actor`, hash-chained onto the head."""
        self.signers.setdefault(actor.actor_id, actor.public())
        ev = PassportEvent(
            seq=len(self.events),
            ts=ts or now_iso(),
            type=type_,
            signer=actor.actor_id,
            data=data,
            prev_hash=self.events[-1].hash if self.events else ZERO,
        )
        body = canonical_json(ev.body())
        ev.sig = actor.sign(body)
        ev.hash = sha256_hex(body + ev.sig.encode())
        self.events.append(ev)
        return ev

    # -- value routing -----------------------------------------------------

    def record_sale(self, seller: Actor, price_cents: int, split: Split,
                    buyer: str, unit: str, ts: str | None = None) -> list[dict]:
        """Record the sale AND the split of its proceeds. The whole point:
        the rancher who grew the feed shows up in the money, automatically,
        not just in the marketing. Integer-floor residue -> first payee, so
        cents are conserved exactly (same rule as bingo.settlement)."""
        legs, distributed = [], 0
        for p in split.payees:
            amt = (price_cents * p.bps) // 10_000
            legs.append({"account": p.account, "bps": p.bps, "cents": amt})
            distributed += amt
        residue = price_cents - distributed
        if legs and residue:
            legs[0]["cents"] += residue
        assert sum(l["cents"] for l in legs) == price_cents
        self.settlement = legs
        self.attest(seller, "SALE", {
            "buyer": buyer, "unit": unit, "price_cents": price_cents,
            "split": split.to_dict(), "legs": legs}, ts=ts)
        return legs

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "subject": self.subject,
            "signers": self.signers,
            "events": [e.to_dict() for e in self.events],
            "settlement": self.settlement,
            "chain_head": self.events[-1].hash if self.events else ZERO,
        }


# --------------------------------------------------------------------- verify

def _event_body(ev: dict) -> dict:
    return {"seq": ev["seq"], "ts": ev["ts"], "type": ev["type"],
            "signer": ev["signer"], "data": ev["data"], "prev_hash": ev["prev_hash"]}


def verify_passport(passport: dict) -> tuple[bool, list[str]]:
    """Independently verify a passport from nothing but the document itself.

    Checks, per link: (1) hash-chain continuity, (2) event-hash integrity,
    (3) the Ed25519 signature under the *declared signer's* registered key,
    and (4) that the signer is a known actor. Then confirms the recorded
    settlement conserves the sale price to the cent. Needs no rancher, no
    processor, no server online — just the passport and this function.
    """
    notes: list[str] = []
    events = passport.get("events", [])
    signers = passport.get("signers", {})
    if not events:
        return False, ["no events"]

    prev = ZERO
    roles_seen = []
    for ev in events:
        who = ev.get("signer", "")
        rec = signers.get(who)
        if not rec:
            return False, notes + [f"event {ev['seq']}: signer '{who}' not in registry"]
        if ev["prev_hash"] != prev:
            return False, notes + [f"event {ev['seq']}: broken hash chain"]
        body = canonical_json(_event_body(ev))
        if ev["hash"] != sha256_hex(body + ev["sig"].encode()):
            return False, notes + [f"event {ev['seq']}: hash mismatch (tampered)"]
        try:
            if not crypto.verify(body, bytes.fromhex(ev["sig"]), bytes.fromhex(rec["pubkey"])):
                return False, notes + [f"event {ev['seq']}: bad signature for '{who}'"]
        except ValueError:
            return False, notes + [f"event {ev['seq']}: signature/key not hex"]
        prev = ev["hash"]
        roles_seen.append(rec.get("role", who))

    # settlement conservation, if a sale was recorded
    sale = next((e for e in events if e["type"] == "SALE"), None)
    if sale:
        price = sale["data"]["price_cents"]
        paid = sum(l["cents"] for l in passport.get("settlement", []))
        if paid != price:
            return False, notes + [f"settlement {paid}¢ != sale price {price}¢"]
        notes.append(f"settlement conserves {price}¢ across {len(passport['settlement'])} payees")

    notes.append(f"{len(events)} links, {len(signers)} signer(s): "
                 f"{' -> '.join(roles_seen)}")
    notes.append(f"chain head {events[-1]['hash'][:16]}… (verified)")
    return True, notes
