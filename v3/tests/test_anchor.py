"""The external anchor: an append-only Merkle log that makes rewriting history
detectable, and the ordering proof that closes the backdating gap in key custody.

Two limitations documented in this codebase were the same limitation - the coin
anti-rollback sidecar ("if an attacker can rewrite the anchor too...") and the key
directory ("a document cannot prove its own age"). Both needed an ordering witness
outside the artifact. This is it.

The headline test is `test_backdating_attack_is_now_defeated`: an attacker holding
a stolen-then-revoked key could previously get a signature accepted by simply
ASSERTING it predated the revocation. That assertion is now refused, and only a
real inclusion proof against the log is accepted.

  python -m tests.test_anchor
"""

from __future__ import annotations

import random
import sys

from bingo import keys
from bingo.anchor import (AnchorError, TransparencyLog, Witness, leaf_hash,
                          merkle_root, verify_anchored, verify_consistency,
                          verify_inclusion, verify_signed_head,
                          verify_witness_quorum)
from bingo.keydir import KeyDirectory, verify_as_identity
from bingo.models import canonical_json


def _log(n=0, log_id="log-1"):
    signer = keys.LocalSigner.generate(log_id)
    lg = TransparencyLog(log_id, signer=signer)
    for i in range(n):
        lg.append(f"entry-{i}".encode())
    return lg, signer


# -- the Merkle primitives -----------------------------------------------------

def test_inclusion_proofs_across_every_size_and_index():
    """Exhaustive over sizes 1..24: every entry proves in, and a proof does not
    transfer to a different index."""
    for n in range(1, 25):
        lg, _ = _log(n)
        root = lg.root()
        for i in range(n):
            path = lg.inclusion_proof(i)
            leaf = leaf_hash(f"entry-{i}".encode())
            assert verify_inclusion(leaf, i, n, root, path), (n, i)
            if n > 1:
                j = (i + 1) % n
                assert not verify_inclusion(leaf, j, n, root, path), (
                    f"proof for index {i} must not verify at {j}")


def test_consistency_proofs_across_every_pair():
    """Exhaustive over every (old, new) pair up to 24: an honestly-extended log
    always proves consistent."""
    for n in range(1, 25):
        lg, _ = _log()
        roots = [merkle_root([])]
        for i in range(n):
            lg.append(f"entry-{i}".encode())
            roots.append(lg.root())
        for m in range(n + 1):
            assert verify_consistency(m, roots[m], n, roots[n],
                                      lg.consistency_proof(m)), (m, n)


def test_a_rewritten_log_cannot_prove_consistency():
    """The point of the whole exercise: edit anything in the committed prefix and
    no consistency proof exists. This is what makes rollback DETECTABLE rather
    than merely forbidden."""
    rng = random.Random(1234)
    for _ in range(200):
        n = rng.randint(2, 24)
        m = rng.randint(1, n)
        entries = [f"e{i}".encode() for i in range(n)]
        old, _ = _log()
        for e in entries[:m]:
            old.append(e)
        victim = rng.randrange(m)
        rewritten_entries = list(entries)
        rewritten_entries[victim] = b"REWRITTEN"
        rewritten, _ = _log()
        for e in rewritten_entries:
            rewritten.append(e)
        assert not verify_consistency(m, old.root(), n, rewritten.root(),
                                      rewritten.consistency_proof(m)), (
            f"a log that rewrote entry {victim} must not prove consistent")


def test_truncation_cannot_prove_consistency():
    """Dropping entries is the coin-rollback shape: the tree shrinks, and a
    shrunken tree can never be an append-only extension."""
    full, _ = _log(12)
    short, _ = _log(8)
    assert not verify_consistency(12, full.root(), 8, short.root(), [])
    assert not verify_consistency(12, full.root(), 8, short.root(),
                                  [b"\x00" * 32])


def test_leaf_and_node_hashing_are_domain_separated():
    """Without the 0x00/0x01 prefixes an internal node could be replayed as a
    logged statement. Two entries hashed as a node must not equal a leaf."""
    a, b = leaf_hash(b"a"), leaf_hash(b"b")
    from bingo.anchor import node_hash
    assert node_hash(a, b) != leaf_hash(a + b)
    assert leaf_hash(b"") != merkle_root([])


def test_proof_verification_fails_closed_on_junk():
    lg, signer = _log(5)
    root, path = lg.root(), lg.inclusion_proof(2)
    leaf = leaf_hash(b"entry-2")
    for bad in ([b"\x00" * 31], [b""], ["not bytes"], [None]):
        assert verify_inclusion(leaf, 2, 5, root, bad) is False
    assert verify_inclusion(leaf, 9, 5, root, path) is False   # index >= size
    assert verify_inclusion(leaf, -1, 5, root, path) is False
    assert verify_consistency(5, root, 3, root, []) is False    # shrink
    assert verify_consistency(-1, root, 5, root, []) is False


# -- signed heads and witnesses ------------------------------------------------

def test_signed_tree_head_and_tampering():
    lg, signer = _log(6)
    sth = lg.signed_head()
    ok, _ = verify_signed_head(sth, signer.public_key())
    assert ok
    # a head claiming a different size/root must not verify
    d = sth.to_dict()
    d["size"] = 99
    assert not verify_signed_head(d, signer.public_key())[0]
    # unsigned head is refused
    d2 = sth.to_dict()
    d2["sig"] = ""
    assert not verify_signed_head(d2, signer.public_key())[0]
    assert not verify_signed_head({"garbage": True}, signer.public_key())[0]


def test_witness_refuses_to_cosign_a_rewritten_log():
    """Consistency proofs catch a rewrite for anyone who saw the old head. A
    witness is what makes someone always have seen it."""
    lg, _ = _log(5)
    w = Witness("w1", signer=keys.LocalSigner.generate("w1"))
    w.cosign(lg.signed_head(), [])                    # first head: nothing to check
    for i in range(5, 9):
        lg.append(f"entry-{i}".encode())
    w.cosign(lg.signed_head(), lg.consistency_proof(5))   # honest extension: fine

    # now the operator rewrites history and asks for a cosignature
    evil, _ = _log()
    for i in range(9):
        evil.append(b"TAMPERED" if i == 2 else f"entry-{i}".encode())
    for i in range(9, 11):
        evil.append(f"entry-{i}".encode())
    try:
        w.cosign(evil.signed_head(), evil.consistency_proof(9))
        assert False, "witness must refuse to cosign a rewritten history"
    except AnchorError as e:
        assert "NOT a consistent extension" in str(e)


def test_witness_refuses_a_shrinking_tree():
    lg, _ = _log(10)
    w = Witness("w1", signer=keys.LocalSigner.generate("w1"))
    w.cosign(lg.signed_head(), [])
    small, _ = _log(4)
    try:
        w.cosign(small.signed_head(), [])
        assert False, "witness must refuse a tree that shrank"
    except AnchorError as e:
        assert "shrank" in str(e)


def test_witness_quorum_is_fail_closed():
    lg, _ = _log(4)
    sth = lg.signed_head()
    ws = [Witness(f"w{i}", signer=keys.LocalSigner.generate(f"w{i}")) for i in range(3)]
    keyring = {w.witness_id: w.signer.public_key() for w in ws}
    cosigs = {w.witness_id: w.cosign(sth, []) for w in ws}

    assert verify_witness_quorum(sth, cosigs, keyring, 2)[0]
    assert verify_witness_quorum(sth, cosigs, keyring, 3)[0]
    # too few
    assert not verify_witness_quorum(sth, {"w0": cosigs["w0"]}, keyring, 2)[0]
    # an unknown witness contributes nothing
    ok, notes = verify_witness_quorum(sth, {"stranger": cosigs["w0"]}, keyring, 1)
    assert not ok and any("unknown witness" in n for n in notes)
    # a cosignature over a DIFFERENT head does not count
    other = _log(7)[0].signed_head()
    assert not verify_witness_quorum(other, cosigs, keyring, 1)[0]
    assert not verify_witness_quorum(sth, cosigs, keyring, 0)[0]   # 0 is not a quorum


# -- the payoff: backdating -----------------------------------------------------

def _revoked_identity():
    """An identity whose signing key is stolen, used, then revoked."""
    d_signer = keys.LocalSigner.generate("node")
    recovery = keys.LocalSigner.generate("node/rec")
    d = KeyDirectory.genesis("node", d_signer, recovery.public_key())
    return d, d_signer, recovery


def test_backdating_attack_is_now_defeated():
    """THE headline.

    Before the anchor, a revoked key's signature could be accepted by asserting
    a historical directory position - an assertion the holder of the stolen key
    makes for free. Now the assertion is refused and only a logged position is
    accepted.
    """
    d, k1, rec = _revoked_identity()
    msg = b"attacker's fabricated settlement"
    sig = k1.sign_hex(msg)
    pre_revocation_seq = len(d.events) - 1
    d.revoke(rec, k1.public_key(), reason="key stolen")

    # 1. default: refused (as before)
    assert not verify_as_identity(msg, sig, d.to_dict())[0]

    # 2. the OLD escape hatch - just assert an earlier position - is now REFUSED
    ok, notes = verify_as_identity(msg, sig, d.to_dict(), at_seq=pre_revocation_seq)
    assert not ok, "asserting a pre-revocation position must no longer be enough"
    assert "anchor proof" in notes[-1], notes

    # 3. a real anchor proof, with the signature logged BEFORE the revocation
    lg, log_signer = _log()
    sig_index = lg.append(msg)                     # logged first...
    revocation_payload = d.events[-1].hash.encode()
    rev_index = lg.append(revocation_payload)      # ...revocation logged after
    sth = lg.signed_head()
    anchor = {
        "log_pubkey": log_signer.public_key(),
        "revoked_payload": revocation_payload,
        "receipt": {"index": sig_index, "sth": sth.to_dict(),
                    "inclusion": [h.hex() for h in lg.inclusion_proof(sig_index)]},
        "revocation_receipt": {"index": rev_index, "sth": sth.to_dict(),
                               "inclusion": [h.hex() for h in lg.inclusion_proof(rev_index)]},
    }
    ok, notes = verify_as_identity(msg, sig, d.to_dict(), anchor=anchor)
    assert ok, notes
    assert any("PROVEN" in n for n in notes)


def test_anchor_proof_in_the_wrong_ORDER_is_refused():
    """The proof has to show the signature was logged FIRST. An attacker who logs
    their forgery after the revocation gets a perfectly valid inclusion proof -
    and must still be refused, because order is the whole claim."""
    d, k1, rec = _revoked_identity()
    msg = b"forged after the revocation was public"
    sig = k1.sign_hex(msg)
    d.revoke(rec, k1.public_key(), reason="stolen")

    lg, log_signer = _log()
    revocation_payload = d.events[-1].hash.encode()
    rev_index = lg.append(revocation_payload)      # revocation logged FIRST
    sig_index = lg.append(msg)                     # forgery logged after
    sth = lg.signed_head()
    anchor = {
        "log_pubkey": log_signer.public_key(),
        "revoked_payload": revocation_payload,
        "receipt": {"index": sig_index, "sth": sth.to_dict(),
                    "inclusion": [h.hex() for h in lg.inclusion_proof(sig_index)]},
        "revocation_receipt": {"index": rev_index, "sth": sth.to_dict(),
                               "inclusion": [h.hex() for h in lg.inclusion_proof(rev_index)]},
    }
    ok, notes = verify_as_identity(msg, sig, d.to_dict(), anchor=anchor)
    assert not ok and any("NOT before" in n for n in notes), notes


def test_forged_and_incomplete_anchor_proofs_are_refused():
    d, k1, rec = _revoked_identity()
    msg = b"m"
    sig = k1.sign_hex(msg)
    d.revoke(rec, k1.public_key(), "stolen")
    lg, log_signer = _log()
    i = lg.append(msg)
    rev_payload = d.events[-1].hash.encode()
    j = lg.append(rev_payload)
    sth = lg.signed_head()
    good = {
        "log_pubkey": log_signer.public_key(), "revoked_payload": rev_payload,
        "receipt": {"index": i, "sth": sth.to_dict(),
                    "inclusion": [h.hex() for h in lg.inclusion_proof(i)]},
        "revocation_receipt": {"index": j, "sth": sth.to_dict(),
                               "inclusion": [h.hex() for h in lg.inclusion_proof(j)]},
    }
    assert verify_as_identity(msg, sig, d.to_dict(), anchor=good)[0]

    # a head signed by somebody else's log key
    stranger = keys.LocalSigner.generate("evil-log")
    bad = {**good, "log_pubkey": stranger.public_key()}
    assert not verify_as_identity(msg, sig, d.to_dict(), anchor=bad)[0]

    # a garbage inclusion path
    bad2 = {**good, "receipt": {**good["receipt"], "inclusion": ["ff" * 32]}}
    assert not verify_as_identity(msg, sig, d.to_dict(), anchor=bad2)[0]

    # missing halves / junk
    for incomplete in ({}, {"log_pubkey": log_signer.public_key()},
                       {**good, "receipt": None}, {**good, "revocation_receipt": {}}):
        assert not verify_as_identity(msg, sig, d.to_dict(), anchor=incomplete)[0]


def test_anchor_receipt_requires_the_witness_quorum_when_asked():
    """A relying party that demands witnesses must not be satisfied without them."""
    lg, log_signer = _log()
    payload = b"a chain head worth anchoring"
    idx = lg.append(payload)
    sth = lg.signed_head()
    receipt = {"index": idx, "sth": sth.to_dict(),
               "inclusion": [h.hex() for h in lg.inclusion_proof(idx)]}

    ws = [Witness(f"w{i}", signer=keys.LocalSigner.generate(f"w{i}")) for i in range(2)]
    keyring = {w.witness_id: w.signer.public_key() for w in ws}

    # no cosignatures but a quorum demanded -> refused
    assert not verify_anchored(payload, receipt, log_signer.public_key(),
                               keyring, quorum=2)[0]
    receipt["cosignatures"] = {w.witness_id: w.cosign(sth, []) for w in ws}
    assert verify_anchored(payload, receipt, log_signer.public_key(),
                           keyring, quorum=2)[0]
    # a payload that was never logged
    assert not verify_anchored(b"never logged", receipt, log_signer.public_key(),
                               keyring, quorum=2)[0]


def test_rotation_still_works_without_any_anchor():
    """Anchors are for REVOKED keys. Verifying a signature made before an ordinary
    rotation is not a security question and must stay simple."""
    d, k1, _rec = _revoked_identity()
    msg = b"signed before a routine rotation"
    sig, at = k1.sign_hex(msg), len(d.events) - 1
    k2 = keys.LocalSigner.generate("node")
    d.rotate(k1, k2.public_key())
    assert verify_as_identity(msg, sig, d.to_dict(), at_seq=at)[0]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} anchor groups pass: an RFC-6962-style append-only "
          "Merkle log gives inclusion proofs (exhaustive over sizes 1..24 and every "
          "index) and consistency proofs (every old/new pair), so a rewritten or "
          "truncated log cannot prove consistency - 200 randomized rewrites all "
          "caught. Witnesses refuse to cosign a history that is not a consistent "
          "extension of what they last signed, and a quorum is fail-closed. And the "
          "backdating attack is DEFEATED: a revoked key's signature is no longer "
          "accepted by asserting an earlier position - only by proving, against the "
          "log, that it was recorded before the revocation was.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
