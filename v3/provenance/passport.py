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

from bingo import crypto, keys
from bingo.models import Split, SplitPayee, canonical_json, now_iso, sha256_hex

SCHEMA = "bingo/passport/0.1"
ZERO = "0" * 64


# --------------------------------------------------------------------- actors

@dataclass
class Actor:
    """A party who can attest to a link in the chain, with a signing key.

    This is the identity primitive for EVERY provenance vertical - passport,
    token, transport, coin, machine-RWA all build their signers from it - so its
    default behaviour is load-bearing for the whole stack.

    `create()` with no key mints a fresh CSPRNG key (`keys.new_seed()`). It must
    never derive one from `actor_id` or any other published value: `actor_id`
    appears in the clear as the `signer` of every event in every shipped
    document, so a key derived from it is a key that anyone who reads the
    document can recompute. (It did exactly that until 2026-08-11; see
    `specs/KEY-CUSTODY.md`.) For reproducible fixtures use `for_testing()`,
    which is deliberately loud about being forgeable.

    Pass `signer=` to sign through custody you control - an encrypted keystore or
    an HSM/KMS - in which case this object never holds the private key at all.
    """
    actor_id: str
    name: str
    role: str                      # rancher | ranch | processor | carrier | grocer | operation
    account: str                   # settlement account the money routes to
    _seed: bytes = b""
    _pub: bytes = b""
    _signer: object = None         # bingo.keys.Signer, when custody is external

    @classmethod
    def create(cls, actor_id: str, name: str, role: str, account: str,
               seed: bytes | None = None, signer=None) -> "Actor":
        """Mint an actor. No key given => a real random key, never a derived one."""
        if signer is not None:
            return cls(actor_id, name, role, account, b"", signer.public_key(), signer)
        seed = seed if seed is not None else keys.new_seed()
        sk, pk = crypto.keypair(seed)
        return cls(actor_id, name, role, account, sk, pk)

    @classmethod
    def for_testing(cls, actor_id: str, name: str, role: str,
                    account: str) -> "Actor":
        """A reproducible actor for tests and demos.

        **Forgeable on purpose**: the key is derived from `actor_id`, so anyone
        holding a document signed this way can recompute the private key. Never
        use it where real value moves - that is what `create()` is for.
        """
        return cls.create(actor_id, name, role, account,
                          seed=keys.insecure_test_signer(actor_id).export_seed())

    @property
    def pubkey_hex(self) -> str:
        return self._pub.hex()

    def sign(self, message: bytes) -> str:
        if self._signer is not None:               # custody holds the key, not us
            return self._signer.sign(message).hex()
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
        data = dict(data)
        # the GENESIS link commits to the subject (product/lot/weight) inside its
        # SIGNED body, so the human-facing asset identity a certificate displays —
        # and register_rwa titles the asset with — is bound to the chain and can't
        # be relabeled (counterfeit "Kobe A5" swap) without breaking a signature.
        if not self.events:
            data["_subject_commit"] = sha256_hex(canonical_json(self.subject))
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
        if price_cents < 0 or sum(l["cents"] for l in legs) != price_cents:
            raise ValueError("sale price must be non-negative and legs must conserve it")
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

    Fails CLOSED on any malformed/adversarial document: the verifier is contracted
    to return (ok, notes) for ANY input (a buyer's script / CI / the CLI runs it on
    untrusted JSON), so a missing field or wrong type is a rejection, not a crash.
    """
    try:
        return _verify_passport(passport)
    except Exception as e:
        return False, [f"malformed passport document: {type(e).__name__}: {e}"]


def _verify_passport(passport: dict) -> tuple[bool, list[str]]:
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

    # subject binding: the genesis link committed to the subject inside its signed
    # body (all signatures verified above), so a relabeled top-level `subject`
    # (counterfeit product/lot/weight) no longer matches and is rejected.
    commit = (events[0].get("data") or {}).get("_subject_commit")
    if commit is None:
        return False, notes + ["genesis link does not commit to the subject "
                               "(unbound provenance — cannot trust the asset identity)"]
    if commit != sha256_hex(canonical_json(passport.get("subject", {}))):
        return False, notes + ["subject doesn't match the signed genesis commitment "
                               "(product/lot/weight relabeled)"]

    # the advertised chain_head is the passport's content-address (tokens pin to
    # it) — it MUST equal the real head, or a cheap passport can masquerade as a
    # premium one by copying its head, and a token's provenance pin is defeated.
    if passport.get("chain_head", events[-1]["hash"]) != events[-1]["hash"]:
        return False, notes + ["top-level chain_head != actual chain head "
                               "(provenance substitution)"]

    # settlement conservation — check EVERY SALE, not just the first. Each signed,
    # hash-chained SALE link must INDEPENDENTLY conserve to the cent and match its
    # declared split; otherwise a second signed SALE can pay out far more than its
    # price (value created from nothing) while the first one looks honest.
    sales = [e for e in events if e["type"] == "SALE"]
    for sale in sales:
        price = sale["data"]["price_cents"]
        # price must be a non-negative int — a negative price with negative legs
        # "conserves" (sum == price) but injects never-paid negative settlement
        # legs that poison downstream earnings rollups
        if not isinstance(price, int) or price < 0:
            return False, notes + [f"SALE seq {sale['seq']}: price must be a non-negative integer"]
        # conserve against the SIGNED legs inside the SALE event — NOT the
        # unsigned top-level `settlement` field, which an attacker can rewrite to
        # reroute the money while keeping the total intact.
        signed_legs = sale["data"].get("legs", [])
        paid = sum(l["cents"] for l in signed_legs)
        if paid != price:
            return False, notes + [f"SALE seq {sale['seq']}: settlement {paid}¢ != price {price}¢"]
        # the legs must MATCH the declared split — not merely conserve the total.
        split_payees = (sale["data"].get("split") or {}).get("payees", [])
        # each payee's bps must be strictly positive (Split.validate's rule, which a
        # hand-crafted SALE bypasses) AND the split must allocate 100% — else a
        # negative bps pays one account >100% while another takes an impossible
        # negative debit, or the residue rule misroutes an under-allocated shortfall.
        if split_payees and any(p["bps"] <= 0 for p in split_payees):
            return False, notes + [f"SALE seq {sale['seq']}: split has a non-positive bps"]
        if split_payees and sum(p["bps"] for p in split_payees) != 10_000:
            return False, notes + [f"SALE seq {sale['seq']}: split bps don't sum to 10000"]
        # no negative per-leg payouts — the by-account aggregate check below can be
        # satisfied by offsetting +/- legs (e.g. rancher +$10.39 / -$9.99) that
        # conserve on net but render a VERIFIED certificate showing a payee getting
        # far more than the sale price, and would over-pay any consumer that pays
        # positive legs without netting. The sibling token verifier guards this too.
        if any(l["cents"] < 0 for l in signed_legs):
            return False, notes + [f"SALE seq {sale['seq']}: negative payout leg"]
        exp, dist = [], 0
        for p in split_payees:
            amt = (price * p["bps"]) // 10_000
            exp.append({"account": p["account"], "cents": amt})
            dist += amt
        if exp and price - dist:
            exp[0]["cents"] += price - dist
        agg_legs, agg_exp = {}, {}
        for l in signed_legs:
            agg_legs[l["account"]] = agg_legs.get(l["account"], 0) + l["cents"]
        for l in exp:
            agg_exp[l["account"]] = agg_exp.get(l["account"], 0) + l["cents"]
        if agg_legs != agg_exp:
            return False, notes + [f"SALE seq {sale['seq']}: legs don't match the "
                                   f"declared split (money routed differently than shown)"]
    if sales:
        # the unsigned top-level settlement mirror must equal the LATEST sale's legs
        last_legs = sales[-1]["data"].get("legs", [])
        if passport.get("settlement", last_legs) != last_legs:
            return False, notes + ["top-level settlement doesn't match the signed SALE legs"]
        notes.append(f"{len(sales)} SALE(s) conserve to the cent and match their "
                     f"declared splits")
    elif passport.get("settlement"):
        # no SALE was recorded, so there is nothing to pay — a non-empty top-level
        # settlement is injected payout legs downstream code (earnings rollups,
        # certificates) would otherwise treat as authoritative money movement
        return False, notes + ["top-level settlement present with no SALE event "
                               "(injected payout legs)"]

    notes.append(f"{len(events)} links, {len(signers)} signer(s): "
                 f"{' -> '.join(roles_seen)}")
    notes.append(f"chain head {events[-1]['hash'][:16]}… (verified)")
    return True, notes
