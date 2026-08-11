"""The signing path: audited and constant-time where it counts, pure-Python where
it is safe.

`bingo/crypto.py` is a correct RFC 8032 Ed25519, but Python big-integer
arithmetic is **variable-time by construction** - execution time depends on the
secret scalar - so the pure-Python SIGNING path leaks key material to anyone who
can measure it. That is not fixable inside pure Python; the only real answer is to
sign somewhere else.

The asymmetry that makes this tractable:

  * **signing** takes a secret -> must be constant-time -> `AuditedSigner`
  * **verification** takes only public inputs (message, signature, public key) ->
    has no secret to leak -> stays pure-Python forever, which is what keeps
    "a stranger can verify this document with nothing installed" true

The load-bearing claim is that the audited path is a true drop-in. RFC 8032
signatures are deterministic, so that is checkable rather than hopeful: same seed
and message must give **byte-identical** output, and each implementation must
verify the other's signatures. This suite checks that over random inputs.

Where no audited library is installed (the reference node's own machine, today)
these checks skip and say so - a skipped check must never read as a passed one.

  python -m tests.test_signing_path
"""

from __future__ import annotations

import os
import sys

from bingo import crypto, keys

SKIPPED: list = []


def _need_audited(what: str) -> bool:
    if not keys.HAS_AUDITED_SIGNING:
        SKIPPED.append(what)
        return False
    return True


# -- the drop-in claim ---------------------------------------------------------

def test_audited_signatures_are_byte_identical_to_the_kernel():
    """Determinism makes this a proof of equivalence, not a smoke test."""
    if not _need_audited("byte-identical signatures"):
        return
    rng = os.urandom
    for _ in range(150):
        seed = rng(32)
        msg = rng(1 + rng(1)[0])              # 1..256 bytes, including 1-byte
        pure = keys.LocalSigner(seed).sign(msg)
        audited = keys.AuditedSigner(seed).sign(msg)
        assert pure == audited, (
            "the audited signer must be a true drop-in - a different signature "
            "would mean documents signed on one host verify differently on another")


def test_public_keys_agree():
    """`AuditedSigner` derives the public key through the audited library
    specifically to avoid a second variable-time pure-Python operation on the
    secret seed. It must still land on exactly the same key."""
    if not _need_audited("public-key derivation agreement"):
        return
    for _ in range(100):
        seed = os.urandom(32)
        assert keys.AuditedSigner(seed).public_key() == crypto.publickey(seed)


def test_each_implementation_verifies_the_other():
    """The interop that matters in the field: a node with the library signs, a
    stranger with nothing installed verifies."""
    if not _need_audited("cross-verification"):
        return
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    for _ in range(50):
        seed, msg = os.urandom(32), os.urandom(64)
        aud = keys.AuditedSigner(seed)
        pure = keys.LocalSigner(seed)
        # stdlib verifier accepts audited signatures
        assert crypto.verify(msg, aud.sign(msg), aud.public_key())
        # audited verifier accepts stdlib signatures
        Ed25519PublicKey.from_public_bytes(pure.public_key()).verify(
            pure.sign(msg), msg)
        # and a tampered message still fails under both
        assert not crypto.verify(msg + b"!", aud.sign(msg), aud.public_key())


# -- selection, reporting, and failing honestly --------------------------------

def test_best_local_signer_picks_the_audited_path_when_available():
    s = keys.best_local_signer(os.urandom(32), "n")
    if keys.HAS_AUDITED_SIGNING:
        assert isinstance(s, keys.AuditedSigner), (
            "with an audited library installed, nothing should be signing in "
            "pure Python by default")
    else:
        assert isinstance(s, keys.LocalSigner)
        SKIPPED.append("audited-signer selection")


def test_audited_signer_refuses_rather_than_pretending():
    """If the library is missing, constructing one must fail loudly. Silently
    degrading to pure-Python under an 'Audited' name would be a lie in the type."""
    if keys.HAS_AUDITED_SIGNING:
        SKIPPED.append("refusal-without-library")
        return
    try:
        keys.AuditedSigner(os.urandom(32))
        assert False, "AuditedSigner must refuse when no audited library exists"
    except RuntimeError as e:
        assert "refusing to pretend" in str(e)


def test_signing_path_report_tells_the_truth():
    """An operator deciding whether this host may hold real value should not have
    to infer the answer."""
    r = keys.signing_path_report()
    assert r["audited_constant_time_signing"] is keys.HAS_AUDITED_SIGNING
    if keys.HAS_AUDITED_SIGNING:
        assert "constant-time" in r["note"]
    else:
        assert "VARIABLE-TIME" in r["note"] and "side-channel" in r["note"]
    # verification is public-input-only in BOTH cases; that is the whole reason
    # the pure-Python verifier is allowed to stay
    assert "public inputs only" in r["verification"]


def test_keystore_hands_out_the_safest_signer():
    """Custody and the signing path have to agree - a keystore that quietly
    returned a variable-time signer would undo the point."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ks = keys.EncryptedFileKeyStore(d, passphrase="pw")
        created = ks.create("node-1")
        loaded = ks.signer("node-1")
        assert created.public_key() == loaded.public_key()
        if keys.HAS_AUDITED_SIGNING:
            assert isinstance(created, keys.AuditedSigner)
            assert isinstance(loaded, keys.AuditedSigner)
        # and it still signs something the stdlib verifier accepts
        msg = b"settle job j-1"
        assert crypto.verify(msg, loaded.sign(msg), loaded.public_key())


def test_signers_never_print_their_seed():
    """Cheap, and the kind of leak that shows up in a log or a traceback."""
    seed = os.urandom(32)
    for s in ([keys.LocalSigner(seed)] +
              ([keys.AuditedSigner(seed)] if keys.HAS_AUDITED_SIGNING else [])):
        assert seed.hex() not in repr(s)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    if keys.HAS_AUDITED_SIGNING:
        detail = ("an audited constant-time library IS installed here, and it is "
                  "byte-identical to the kernel over 150 random seeds/messages, "
                  "agrees on public keys, and cross-verifies both ways")
    else:
        detail = ("NO audited library on this host, so signing is pure-Python and "
                  "VARIABLE-TIME - the equivalence checks were skipped, not passed; "
                  "install `cryptography` (or sign in an HSM) before this host holds "
                  "real value")
    skipped = f" [skipped here: {', '.join(SKIPPED)}]" if SKIPPED else ""
    print(f"OK - all {len(tests)} signing-path groups pass: {detail}. Verification "
          "stays pure-Python either way, because it takes only public inputs and "
          "has no secret to leak - which is what keeps zero-dependency, "
          f"document-only verification true.{skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
