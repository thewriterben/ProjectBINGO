"""The key directory - rotation, revocation, and recovery as a signed record.

A keystore says where a key *lives*. This says which key an identity is *allowed
to sign with right now*, and it has to answer that question the same way the rest
of BINGO answers everything: from a signed, hash-chained document that a stranger
can verify offline. A mutable server-side table would not survive the threat
model the red-team spent ten rounds enforcing.

Same kernel as every other vertical - `sha256_hex` + `canonical_json` +
Ed25519 from `bingo.crypto`, hash-chained events, each signed by the party the
protocol says must have authorized it:

    GENESIS  identity's first key, plus a commitment to a RECOVERY key
             (signed by the genesis key itself)
    ROTATE   move to a new key                (signed by the CURRENT key)
    REVOKE   declare a key compromised        (signed by the current OR recovery key)
    RECOVER  adopt a new key without the old  (signed by the RECOVERY key)

`ROTATE` must be signed by the outgoing key. That is what makes the chain a
continuity proof rather than a list of claims: someone who steals today's key
cannot rewrite history to show they held the identity all along, because every
link back to GENESIS is signed by a key they never had.

`RECOVER` exists because "the operator lost the key" is the ordinary case, not an
exotic one, and a protocol with no answer to it just means the identity dies. The
recovery key is committed at GENESIS and is meant to live offline (paper, a safe,
an HSM in a drawer) and never touch the signing host.

## What rotation does to history

Rotating must not invalidate the past. A settlement signed last month by the key
that was active last month is still a valid settlement. `active_key_at()` resolves
the key that was authoritative at a given position in the directory chain, so a
verifier can check a historical signature against the key that was actually in
force when it was made - not against whatever key is current.

## Revocation, and the limit of what a document can prove

`verify_as_identity()` defaults to evaluating against the directory HEAD, which
means **a revoked key is refused outright**. Accepting a signature from a key that
has since been revoked is possible, but only by explicitly passing the historical
position - it is opt-in, and the caller is stating that they have independent
reason to believe the signature predates the compromise.

That opt-in is where the honesty is required. A self-contained document cannot
prove *when* it was signed, because the attacker controls every byte of the
document they hand you - including any position or timestamp it claims. An
attacker holding a stolen key that was later revoked can always assert "this was
signed before the revocation." Nothing inside the document refutes it.

Closing that gap needs an external ordering witness: a countersignature from an
independent party, a directory head published somewhere the attacker cannot
rewrite, or a timestamp authority. This is the same shape as the anti-rollback
limitation already documented in `provenance/coin.py` - if the adversary can
rewrite the anchor too, a single self-contained artifact cannot detect it. The
mitigation here is the fail-closed default: unless a relying party goes out of
its way to accept a historical position, a revoked key does not verify.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import crypto
from .models import canonical_json, sha256_hex

GENESIS = "GENESIS"
ROTATE = "ROTATE"
REVOKE = "REVOKE"
RECOVER = "RECOVER"

_ZERO = "0" * 64


class KeyDirectoryError(Exception):
    """Refused a key-directory operation. Never swallowed into a silent default."""


@dataclass
class DirEvent:
    seq: int
    type: str
    data: dict
    prev_hash: str
    sig: str = ""
    hash: str = ""

    def body(self) -> dict:
        return {"seq": self.seq, "type": self.type, "data": self.data,
                "prev_hash": self.prev_hash}

    def to_dict(self) -> dict:
        return {**self.body(), "sig": self.sig, "hash": self.hash}


@dataclass
class KeyDirectory:
    """The signed key history for ONE identity."""

    identity: str
    events: list = field(default_factory=list)

    # -- construction ----------------------------------------------------------

    @classmethod
    def genesis(cls, identity: str, signer, recovery_pubkey: bytes) -> "KeyDirectory":
        """Open a directory. `signer` is the identity's first signing key;
        `recovery_pubkey` is the offline key that can rescue the identity later.

        The recovery key is committed HERE, at the start, and can never be changed
        by anyone holding only the signing key - otherwise an attacker who stole
        the signing key would simply install their own recovery key and own the
        identity permanently.
        """
        if not isinstance(recovery_pubkey, (bytes, bytearray)) or len(recovery_pubkey) != 32:
            raise KeyDirectoryError("recovery public key must be 32 bytes")
        if bytes(recovery_pubkey) == signer.public_key():
            raise KeyDirectoryError(
                "recovery key must differ from the signing key - a recovery key "
                "kept beside the key it rescues recovers nothing")
        d = cls(identity=identity)
        d._append(GENESIS, {"identity": identity,
                            "pubkey": signer.public_key().hex(),
                            "recovery_pubkey": bytes(recovery_pubkey).hex()}, signer)
        return d

    def _append(self, type_: str, data: dict, signer) -> DirEvent:
        prev = self.events[-1].hash if self.events else _ZERO
        ev = DirEvent(seq=len(self.events), type=type_, data=data, prev_hash=prev)
        ev.sig = signer.sign(canonical_json(ev.body())).hex()
        ev.hash = sha256_hex(canonical_json(ev.body()) + ev.sig.encode())
        self.events.append(ev)
        return ev

    def rotate(self, current_signer, new_pubkey: bytes) -> DirEvent:
        """Move to `new_pubkey`, authorized by the key being retired."""
        if current_signer.public_key() != self.active_pubkey():
            raise KeyDirectoryError(
                "rotation must be signed by the CURRENTLY ACTIVE key")
        if bytes(new_pubkey) == self.active_pubkey():
            raise KeyDirectoryError("rotation must move to a different key")
        return self._append(ROTATE, {"new_pubkey": bytes(new_pubkey).hex()},
                            current_signer)

    def revoke(self, signer, pubkey: bytes, reason: str = "") -> DirEvent:
        """Declare `pubkey` compromised. Signable by the active key (orderly) or
        the recovery key (the active key is the one that was stolen)."""
        allowed = {self.active_pubkey(), self.recovery_pubkey()}
        if signer.public_key() not in allowed:
            raise KeyDirectoryError(
                "revocation must be signed by the active key or the recovery key")
        return self._append(REVOKE, {"pubkey": bytes(pubkey).hex(),
                                     "reason": reason}, signer)

    def recover(self, recovery_signer, new_pubkey: bytes) -> DirEvent:
        """Adopt `new_pubkey` using the offline recovery key - the path when the
        signing key is lost or stolen and cannot authorize its own rotation."""
        if recovery_signer.public_key() != self.recovery_pubkey():
            raise KeyDirectoryError(
                "recovery must be signed by the committed recovery key")
        return self._append(RECOVER, {"new_pubkey": bytes(new_pubkey).hex()},
                            recovery_signer)

    # -- queries ---------------------------------------------------------------

    def recovery_pubkey(self) -> bytes:
        return bytes.fromhex(self.events[0].data["recovery_pubkey"])

    def active_pubkey(self) -> bytes:
        return self.active_key_at(len(self.events) - 1)

    def active_key_at(self, seq: int) -> bytes:
        """The key authoritative at directory position `seq`. This is what makes
        a historical signature checkable after a rotation."""
        pub = None
        for ev in self.events:
            if ev.seq > seq:
                break
            if ev.type == GENESIS:
                pub = bytes.fromhex(ev.data["pubkey"])
            elif ev.type in (ROTATE, RECOVER):
                pub = bytes.fromhex(ev.data["new_pubkey"])
        if pub is None:
            raise KeyDirectoryError("directory has no genesis event")
        return pub

    def revoked_at(self, pubkey: bytes) -> int | None:
        """Directory position at which `pubkey` was revoked, or None."""
        target = bytes(pubkey).hex()
        for ev in self.events:
            if ev.type == REVOKE and ev.data.get("pubkey") == target:
                return ev.seq
        return None

    def head(self) -> str:
        return self.events[-1].hash if self.events else _ZERO

    def to_dict(self) -> dict:
        return {"schema": "bingo.keydir.v1", "identity": self.identity,
                "events": [e.to_dict() for e in self.events], "head": self.head()}

    @classmethod
    def from_dict(cls, doc: dict) -> "KeyDirectory":
        d = cls(identity=doc.get("identity", ""))
        for raw in doc.get("events", []):
            d.events.append(DirEvent(seq=raw["seq"], type=raw["type"],
                                     data=raw["data"], prev_hash=raw["prev_hash"],
                                     sig=raw.get("sig", ""), hash=raw.get("hash", "")))
        return d


# -- anchored ordering (closes the "a document cannot prove its own age" gap) --

def _anchored_before_revocation(message: bytes, anchor: dict | None) -> tuple:
    """Did the external log receive `message` strictly before it received the
    revocation? Both halves must be proven; a missing or malformed half is a
    refusal, never a pass.
    """
    if not anchor:
        return False, []
    notes: list = []
    try:
        from .anchor import verify_anchored          # local import: optional dep
        log_pubkey = anchor.get("log_pubkey")
        receipt = anchor.get("receipt")
        rev_receipt = anchor.get("revocation_receipt")
        if not (log_pubkey and receipt and rev_receipt):
            return False, ["anchor proof incomplete (need log_pubkey, receipt, "
                           "revocation_receipt)"]
        wk, q = anchor.get("witness_keys"), anchor.get("quorum", 0)

        ok, n = verify_anchored(message, receipt, log_pubkey, wk, q)
        notes += [f"signature anchor: {x}" for x in n]
        if not ok:
            return False, notes
        # the revocation's own logged payload is the directory event hash
        ok, n = verify_anchored(anchor["revoked_payload"], rev_receipt,
                                log_pubkey, wk, q)
        notes += [f"revocation anchor: {x}" for x in n]
        if not ok:
            return False, notes

        # both are in the SAME log, so their indices are comparable
        if receipt["sth"]["log_id"] != rev_receipt["sth"]["log_id"]:
            return False, notes + ["anchor proofs come from different logs"]
        if not receipt["index"] < rev_receipt["index"]:
            return False, notes + [
                f"signature was logged at index {receipt['index']}, NOT before the "
                f"revocation at index {rev_receipt['index']}"]
        return True, notes
    except Exception as e:
        return False, notes + [f"malformed anchor proof: {type(e).__name__}: {e}"]


# -- document-only verification ------------------------------------------------

def verify_directory(doc) -> tuple:
    """Replay a key directory from the document alone.

    Checks the chain links, that every event is signed by the key the protocol
    REQUIRES for that event type (rotation by the outgoing key, recovery by the
    committed recovery key), and that nothing was reordered or inserted.

    Fails CLOSED on arbitrary input - returns `(False, notes)`, never raises -
    matching every other verifier in the kernel (the round-5 lesson).
    """
    notes: list = []
    try:
        if not isinstance(doc, dict):
            return False, ["directory must be an object"]
        events = doc.get("events")
        if not isinstance(events, list) or not events:
            return False, ["directory has no events"]

        prev_hash = _ZERO
        active: bytes | None = None
        recovery: bytes | None = None
        revoked: set = set()

        for i, raw in enumerate(events):
            if not isinstance(raw, dict):
                return False, notes + [f"event {i}: not an object"]
            seq, type_ = raw.get("seq"), raw.get("type")
            data, sig = raw.get("data"), raw.get("sig")
            if seq != i:
                return False, notes + [f"event {i}: seq {seq!r} out of order"]
            if not isinstance(data, dict) or not isinstance(sig, str):
                return False, notes + [f"event {i}: malformed data/sig"]
            if raw.get("prev_hash") != prev_hash:
                return False, notes + [f"event {i}: broken chain link"]

            body = {"seq": seq, "type": type_, "data": data, "prev_hash": prev_hash}
            payload = canonical_json(body)

            # who was REQUIRED to sign this event?
            if type_ == GENESIS:
                if i != 0:
                    return False, notes + [f"event {i}: GENESIS must be first"]
                try:
                    active = bytes.fromhex(data["pubkey"])
                    recovery = bytes.fromhex(data["recovery_pubkey"])
                except (KeyError, ValueError):
                    return False, notes + ["event 0: malformed genesis keys"]
                if len(active) != 32 or len(recovery) != 32:
                    return False, notes + ["event 0: keys must be 32 bytes"]
                if active == recovery:
                    return False, notes + ["event 0: recovery key equals signing key"]
                required = active
            elif type_ == ROTATE:
                required = active                    # outgoing key authorizes
            elif type_ == RECOVER:
                required = recovery                  # only the offline key
            elif type_ == REVOKE:
                required = None                      # active OR recovery
            else:
                return False, notes + [f"event {i}: unknown event type {type_!r}"]

            if active is None or recovery is None:
                return False, notes + [f"event {i}: no genesis established"]

            try:
                sig_bytes = bytes.fromhex(sig)
            except ValueError:
                return False, notes + [f"event {i}: signature is not hex"]

            if required is None:                      # REVOKE: either authority
                if not (crypto.verify(payload, sig_bytes, active)
                        or crypto.verify(payload, sig_bytes, recovery)):
                    return False, notes + [
                        f"event {i}: REVOKE not signed by the active or recovery key"]
            elif not crypto.verify(payload, sig_bytes, required):
                return False, notes + [
                    f"event {i}: {type_} not signed by the required key "
                    f"({'outgoing' if type_ == ROTATE else 'committed recovery' if type_ == RECOVER else 'genesis'} key)"]

            # apply the event
            if type_ in (ROTATE, RECOVER):
                try:
                    new_pub = bytes.fromhex(data["new_pubkey"])
                except (KeyError, ValueError):
                    return False, notes + [f"event {i}: malformed new_pubkey"]
                if len(new_pub) != 32:
                    return False, notes + [f"event {i}: new key must be 32 bytes"]
                active = new_pub
            elif type_ == REVOKE:
                try:
                    revoked.add(bytes.fromhex(data["pubkey"]).hex())
                except (KeyError, ValueError):
                    return False, notes + [f"event {i}: malformed revoked pubkey"]

            expected_hash = sha256_hex(payload + sig.encode())
            if raw.get("hash") != expected_hash:
                return False, notes + [f"event {i}: hash does not commit to the event"]
            prev_hash = expected_hash

        if doc.get("head") not in (None, prev_hash):
            return False, notes + ["published head does not match the replayed chain"]

        notes.append(f"key directory verified: {len(events)} events, "
                     f"{len(revoked)} revoked key(s)")
        return True, notes
    except Exception as e:                            # fail closed, never raise
        return False, notes + [f"malformed key directory: {type(e).__name__}: {e}"]


def verify_as_identity(message: bytes, sig_hex: str, directory_doc,
                       at_seq: int | None = None, anchor: dict | None = None) -> tuple:
    """Verify a signature as an IDENTITY rather than as a raw public key.

    This is the call that makes rotation usable: the caller asks "did this
    identity sign this?", and the directory decides which key that means.

    `at_seq=None` (the default) evaluates against the directory HEAD. An explicit
    earlier `at_seq` resolves the key that was active then - which is the ordinary
    way to check a signature made before a ROTATION, and is not a security
    question, because rotation does not mean the old key leaked.

    **Revoked keys are different, and `at_seq` alone will not buy you one.** A
    revoked key is refused unless the caller supplies `anchor` proving the
    signature was logged BEFORE the revocation was logged:

        anchor = {"log_pubkey": bytes,
                  "receipt": {...},              # this message, in the log
                  "revocation_receipt": {...},   # the revocation, in the log
                  "witness_keys": {...}, "quorum": int}

    That is the whole reason `bingo/anchor.py` exists. Before it, "this was signed
    before the compromise" was an assertion the holder of the stolen key could
    simply make, and nothing in a self-contained document could contradict it.
    Now it is a claim about positions in an append-only log that a third party
    keeps and witnesses cosign - so it can be checked instead of believed.
    """
    notes: list = []
    try:
        ok, dnotes = verify_directory(directory_doc)
        if not ok:
            return False, dnotes
        d = KeyDirectory.from_dict(directory_doc)
        seq = (len(d.events) - 1) if at_seq is None else at_seq
        if not isinstance(seq, int) or seq < 0 or seq >= len(d.events):
            return False, notes + [f"directory position {at_seq!r} out of range"]
        pub = d.active_key_at(seq)
        # Revocation is checked against the key this position resolves to. Being
        # revoked is fatal at ANY position now: predating the revocation has to be
        # PROVEN against the external log, not asserted by choosing an at_seq.
        revoked_seq = d.revoked_at(pub)
        if revoked_seq is not None:
            ok, anotes = _anchored_before_revocation(message, anchor)
            notes += anotes
            if not ok:
                return False, notes + [
                    f"key was revoked at directory position {revoked_seq} - refusing "
                    "(supply an anchor proof that this signature was logged before "
                    "the revocation to accept it)"]
            notes.append("pre-revocation position PROVEN against the external log")
        try:
            sig = bytes.fromhex(sig_hex)
        except (ValueError, TypeError):
            return False, notes + ["signature is not hex"]
        if not crypto.verify(message, sig, pub):
            return False, notes + ["signature does not verify under the identity's key"]
        notes.append(f"signature verified as {d.identity!r} using the key active "
                     f"at directory position {seq}")
        return True, notes
    except Exception as e:
        return False, notes + [f"malformed verification input: {type(e).__name__}: {e}"]
