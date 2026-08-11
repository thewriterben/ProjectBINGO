"""The external anchor - an append-only log that makes rewriting history detectable.

Two limitations documented elsewhere in this codebase are the same limitation:

  * `provenance/coin.py`: the anti-rollback sidecar pins the last head+length, but
    "if an attacker can rewrite the anchor too," a self-contained artifact cannot
    detect a rollback.
  * `bingo/keydir.py`: a document cannot prove its own age, so someone holding a
    stolen-then-revoked key can always *assert* the signature predates the
    revocation.

Both are the same missing primitive: **an ordering witness the holder of the
document cannot forge or rewrite.** No amount of signing fixes it, because the
attacker controls every byte of the artifact they hand you - including any
sequence number or timestamp it claims. You need something outside the document.

This is a Merkle transparency log, the construction Certificate Transparency uses
for exactly this problem (RFC 6962), in stdlib:

  * **Inclusion proof** - "this statement is in the log at index i, under a tree
    of size n whose root is R." O(log n) hashes. Answers *was this ever logged?*
  * **Consistency proof** - "the tree of size n with root R is an append-only
    extension of the earlier tree of size m with root R'." Answers *did the log
    operator quietly rewrite history?* A log that drops or edits a past entry
    cannot produce a valid consistency proof, so rollback becomes detectable
    rather than merely disallowed.

Hashing is domain-separated exactly as RFC 6962 specifies - `0x00` prefix for
leaves, `0x01` for internal nodes - so an internal node can never be presented as
a leaf (without it, a two-leaf subtree hash could be replayed as a single logged
statement).

## What this does and does not buy

A log operator can still **equivocate**: show one history to you and a different
one to someone else. Consistency proofs make a *rewrite* detectable to anyone who
saw the earlier head; they do not, alone, make a *split view* detectable. That is
what `Witness` is for - independent parties that cosign a tree head only if it is
consistent with the last head they signed, so equivocation requires colluding with
a quorum of them. This is the same reason CT added witness cosigning.

What remains, honestly: a witness quorum is a trust assumption, not a proof. It
converts "trust the log operator" into "trust that k independent witnesses are not
all colluding," which is meaningfully better and still not free. And nothing here
proves *wall-clock* time - it proves *order*, which is what the two problems above
actually need.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from . import crypto
from .models import canonical_json, sha256_hex

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


class AnchorError(Exception):
    """A log/proof operation was refused. Never swallowed into a silent default."""


# -- RFC 6962 hashing ----------------------------------------------------------

def leaf_hash(data: bytes) -> bytes:
    """Hash of a logged statement. Domain-separated from internal nodes so a
    subtree hash can never be replayed as if it were a single logged entry."""
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _largest_power_of_two_below(n: int) -> int:
    """The split point k for a tree of size n: largest power of 2 strictly < n."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root(leaves: list) -> bytes:
    """Merkle Tree Hash of the leaf hashes (RFC 6962 MTH)."""
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    k = _largest_power_of_two_below(len(leaves))
    return node_hash(merkle_root(leaves[:k]), merkle_root(leaves[k:]))


def _inclusion_path(index: int, leaves: list) -> list:
    n = len(leaves)
    if n <= 1:
        return []
    k = _largest_power_of_two_below(n)
    if index < k:
        return _inclusion_path(index, leaves[:k]) + [merkle_root(leaves[k:])]
    return _inclusion_path(index - k, leaves[k:]) + [merkle_root(leaves[:k])]


def _consistency_path(m: int, leaves: list, is_full: bool = True) -> list:
    """RFC 6962 SUBPROOF."""
    n = len(leaves)
    if m == n:
        return [] if is_full else [merkle_root(leaves)]
    k = _largest_power_of_two_below(n)
    if m <= k:
        return _consistency_path(m, leaves[:k], is_full) + [merkle_root(leaves[k:])]
    return _consistency_path(m - k, leaves[k:], False) + [merkle_root(leaves[:k])]


# -- proof verification (the part a relying party runs) ------------------------

def verify_inclusion(leaf: bytes, index: int, tree_size: int, root: bytes,
                     path: list) -> bool:
    """Was `leaf` in the log at `index`, under the tree of size `tree_size`?

    Fails closed on nonsense input rather than raising - a verifier that crashes
    on a hostile proof is a verifier an attacker can turn into a denial of
    service, which is the round-5 lesson applied here.
    """
    try:
        if index < 0 or tree_size < 0 or index >= tree_size:
            return False
        if not isinstance(leaf, (bytes, bytearray)) or len(leaf) != 32:
            return False
        fn, sn = index, tree_size - 1
        r = bytes(leaf)
        for sibling in path:
            if not isinstance(sibling, (bytes, bytearray)) or len(sibling) != 32:
                return False
            if sn == 0:
                return False
            if fn & 1 or fn == sn:
                r = node_hash(bytes(sibling), r)
                while fn != 0 and not (fn & 1):
                    fn >>= 1
                    sn >>= 1
            else:
                r = node_hash(r, bytes(sibling))
            fn >>= 1
            sn >>= 1
        return sn == 0 and r == root
    except Exception:
        return False


def verify_consistency(old_size: int, old_root: bytes, new_size: int,
                       new_root: bytes, proof: list) -> bool:
    """Is the tree of size `new_size` an append-only extension of the earlier
    tree of size `old_size`? This is the check that catches a rewritten log."""
    try:
        if old_size < 0 or new_size < 0 or old_size > new_size:
            return False
        if old_size == new_size:
            return not proof and old_root == new_root
        if old_size == 0:
            return not proof
        node, last_node = old_size - 1, new_size - 1
        p = list(proof)
        for h in p:
            if not isinstance(h, (bytes, bytearray)) or len(h) != 32:
                return False
        while node & 1:
            node >>= 1
            last_node >>= 1
        if node:
            if not p:
                return False
            old_hash = new_hash = bytes(p.pop(0))
        else:
            old_hash = new_hash = bytes(old_root)
        while node:
            if node & 1:
                if not p:
                    return False
                h = bytes(p.pop(0))
                old_hash = node_hash(h, old_hash)
                new_hash = node_hash(h, new_hash)
            elif node < last_node:
                if not p:
                    return False
                new_hash = node_hash(new_hash, bytes(p.pop(0)))
            node >>= 1
            last_node >>= 1
        while last_node:
            if not p:
                return False
            new_hash = node_hash(new_hash, bytes(p.pop(0)))
            last_node >>= 1
        return not p and old_hash == old_root and new_hash == new_root
    except Exception:
        return False


# -- the log -------------------------------------------------------------------

@dataclass
class SignedTreeHead:
    """The log's signed claim: 'my tree has this size and this root.' Everything a
    relying party checks hangs off one of these."""
    size: int
    root_hex: str
    log_id: str
    sig: str = ""

    def body(self) -> dict:
        return {"size": self.size, "root": self.root_hex, "log_id": self.log_id}

    def to_dict(self) -> dict:
        return {**self.body(), "sig": self.sig}

    @classmethod
    def from_dict(cls, d: dict) -> "SignedTreeHead":
        return cls(size=d["size"], root_hex=d["root"], log_id=d["log_id"],
                   sig=d.get("sig", ""))


@dataclass
class TransparencyLog:
    """Append-only log of statement hashes, with a signed tree head.

    The log stores *hashes*, not content: what is being anchored is "this exact
    artifact existed by the time the log reached size n", and the artifact itself
    stays with whoever holds it. That keeps the anchor cheap and leaks nothing.
    """
    log_id: str
    signer: object = None                       # bingo.keys.Signer
    leaves: list = field(default_factory=list)  # leaf hashes, in order

    def append(self, payload: bytes) -> int:
        """Log `payload` (normally a chain head or document hash). Returns its
        index - the position a later inclusion proof will cite."""
        self.leaves.append(leaf_hash(payload))
        return len(self.leaves) - 1

    def size(self) -> int:
        return len(self.leaves)

    def root(self) -> bytes:
        return merkle_root(self.leaves)

    def signed_head(self) -> SignedTreeHead:
        sth = SignedTreeHead(size=self.size(), root_hex=self.root().hex(),
                             log_id=self.log_id)
        if self.signer is not None:
            sth.sig = self.signer.sign(canonical_json(sth.body())).hex()
        return sth

    def inclusion_proof(self, index: int) -> list:
        if not 0 <= index < len(self.leaves):
            raise AnchorError(f"index {index} outside log of size {len(self.leaves)}")
        return _inclusion_path(index, self.leaves)

    def consistency_proof(self, old_size: int) -> list:
        if not 0 <= old_size <= len(self.leaves):
            raise AnchorError(f"old size {old_size} outside log of size {len(self.leaves)}")
        if old_size == 0:
            return []
        return _consistency_path(old_size, self.leaves)


def verify_signed_head(sth, log_pubkey: bytes) -> tuple:
    """Check an STH's signature. Fails closed on malformed input."""
    try:
        s = sth if isinstance(sth, SignedTreeHead) else SignedTreeHead.from_dict(sth)
        if not s.sig:
            return False, ["tree head is unsigned"]
        if not crypto.verify(canonical_json(s.body()), bytes.fromhex(s.sig), log_pubkey):
            return False, ["tree head signature does not verify"]
        return True, [f"signed tree head verified: size {s.size}"]
    except Exception as e:
        return False, [f"malformed tree head: {type(e).__name__}: {e}"]


# -- witnesses: making a split view expensive ----------------------------------

@dataclass
class Witness:
    """An independent party that cosigns a tree head ONLY if it is consistent with
    the last head it signed.

    Consistency proofs let anyone who saw an earlier head detect a rewrite. They
    do not stop the operator showing two different histories to two different
    parties. A witness that remembers what it last signed turns that split view
    into something requiring collusion: to fool a relying party checking k
    witnesses, the operator must corrupt k independent parties.
    """
    witness_id: str
    signer: object = None
    last_size: int = 0
    last_root: bytes = b""

    def cosign(self, sth: SignedTreeHead, consistency: list) -> str:
        """Cosign, or refuse. Refusal is the useful behaviour - it is the alarm."""
        root = bytes.fromhex(sth.root_hex)
        if self.last_size:
            if sth.size < self.last_size:
                raise AnchorError(
                    f"witness {self.witness_id}: tree shrank "
                    f"({sth.size} < {self.last_size}) - refusing to cosign")
            if not verify_consistency(self.last_size, self.last_root,
                                      sth.size, root, consistency):
                raise AnchorError(
                    f"witness {self.witness_id}: head is NOT a consistent extension "
                    "of the last head I signed - refusing to cosign (the log was "
                    "rewritten, or I am being shown a different history)")
        self.last_size, self.last_root = sth.size, root
        payload = canonical_json({"witness": self.witness_id, **sth.body()})
        return self.signer.sign(payload).hex() if self.signer else ""

    def public(self) -> dict:
        return {"witness_id": self.witness_id,
                "pubkey": self.signer.public_key().hex() if self.signer else ""}


def verify_witness_quorum(sth, cosignatures: dict, witness_keys: dict,
                          quorum: int) -> tuple:
    """Require `quorum` valid, distinct witness cosignatures over this head.

    Fail-closed: an unknown witness, a bad signature, or too few cosignatures is a
    refusal, never a warning.
    """
    notes: list = []
    try:
        s = sth if isinstance(sth, SignedTreeHead) else SignedTreeHead.from_dict(sth)
        if quorum <= 0:
            return False, ["a quorum of 0 witnesses is not a quorum"]
        good = 0
        for wid, sig in (cosignatures or {}).items():
            pub = witness_keys.get(wid)
            if pub is None:
                notes.append(f"unknown witness {wid!r} - ignored")
                continue
            payload = canonical_json({"witness": wid, **s.body()})
            try:
                if crypto.verify(payload, bytes.fromhex(sig), pub):
                    good += 1
                else:
                    notes.append(f"witness {wid!r}: bad signature")
            except (ValueError, TypeError):
                notes.append(f"witness {wid!r}: malformed signature")
        if good < quorum:
            return False, notes + [
                f"only {good} valid witness cosignature(s), need {quorum}"]
        return True, notes + [f"{good} witness cosignature(s) verified"]
    except Exception as e:
        return False, notes + [f"malformed quorum input: {type(e).__name__}: {e}"]


# -- what a relying party actually calls ---------------------------------------

def verify_anchored(payload: bytes, receipt: dict, log_pubkey: bytes,
                    witness_keys: dict | None = None, quorum: int = 0) -> tuple:
    """Verify that `payload` was logged, from an anchor receipt.

    A receipt is what an artifact carries so a stranger can check its position:
    `{"index", "sth": {...}, "inclusion": [hex...], "cosignatures": {...}}`.

    Returns `(ok, notes)` and never raises. On success the caller knows the
    payload was in the log by the time it reached `sth.size` - which is the
    ordering fact that neither the coin store nor a key directory could establish
    on its own.
    """
    notes: list = []
    try:
        if not isinstance(receipt, dict):
            return False, ["anchor receipt must be an object"]
        sth = SignedTreeHead.from_dict(receipt["sth"])
        ok, n = verify_signed_head(sth, log_pubkey)
        notes += n
        if not ok:
            return False, notes
        if witness_keys or quorum:
            ok, n = verify_witness_quorum(sth, receipt.get("cosignatures", {}),
                                          witness_keys or {}, quorum)
            notes += n
            if not ok:
                return False, notes
        path = [bytes.fromhex(h) for h in receipt.get("inclusion", [])]
        if not verify_inclusion(leaf_hash(payload), receipt["index"], sth.size,
                                bytes.fromhex(sth.root_hex), path):
            return False, notes + ["inclusion proof does not verify"]
        notes.append(f"anchored at index {receipt['index']} of {sth.size}")
        return True, notes
    except Exception as e:
        return False, notes + [f"malformed anchor receipt: {type(e).__name__}: {e}"]
