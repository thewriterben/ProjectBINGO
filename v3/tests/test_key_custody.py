"""Key custody: where private keys come from, where they live, and what happens
when one is rotated, revoked, or lost.

The headline case is a real vulnerability that ten rounds of red-team missed,
because every round attacked the VERIFIERS and nobody attacked key GENERATION:
`Actor.create` used to default the private seed to the actor's own published
`actor_id`. `actor_id` is printed in the clear as the `signer` of every event in
every shipped document, so reading a passport handed you the private key of any
party in it -- and `Actor` is the identity primitive for all five provenance
verticals (passport, token, transport, coin, machine-RWA).

  python -m tests.test_key_custody
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile

from bingo import crypto, keys, keydir
from bingo.keydir import KeyDirectory, verify_directory, verify_as_identity
from bingo.training import Trainer
from provenance.passport import Actor, CutPassport, verify_passport


# -- the vulnerability: a private key derived from a public id -----------------

def test_actor_key_is_not_derivable_from_its_public_id():
    """The exploit: read the document, recompute the signer's private key.

    FAILS on pre-fix code, where `Actor.create` seeded from `actor_id`.
    """
    rancher = Actor.create("rancher-sadu", "SADU Farms", "rancher", "acct:sadu")
    pp = CutPassport(subject={"product": "A5", "lot": "L1", "weight_lb": 2})
    pp.attest(rancher, "HUSBANDRY", {"feed": "barley"})
    doc = pp.to_dict()
    assert verify_passport(doc)[0], "honest passport must verify"

    # everything an attacker gets from the shipped document:
    victim_id = doc["events"][0]["signer"]
    assert victim_id == "rancher-sadu", "signer id is public, in the clear"

    # the old attack: re-derive the identity from that public string
    attacker = Actor.create(victim_id, "whoever", "rancher", "acct:ATTACKER")
    assert attacker.pubkey_hex != rancher.pubkey_hex, (
        "a private key must NOT be a function of a published identifier -- "
        "anyone holding the document could recompute it")

    # and the forgery it enabled must no longer verify as the victim
    evil = CutPassport(subject={"product": "A5", "lot": "FAKE", "weight_lb": 99})
    evil.attest(attacker, "HUSBANDRY", {"feed": "fabricated"})
    forged = evil.to_dict()
    # the forged doc carries the ATTACKER's key under the victim's id; it cannot
    # be checked against the real rancher's key
    assert forged["signers"][victim_id]["pubkey"] != rancher.pubkey_hex, (
        "forged document must not carry the victim's real public key")


def test_two_actors_with_the_same_id_get_different_keys():
    """Independent CSPRNG draws, not a deterministic function of the id."""
    a = Actor.create("same-id", "A", "rancher", "acct:a")
    b = Actor.create("same-id", "B", "rancher", "acct:b")
    assert a.pubkey_hex != b.pubkey_hex, "keys must be independently random"


def test_trainer_key_is_not_derivable_either():
    """Same defect, same fix, in the training-royalty vertical."""
    t = Trainer.create("trainer-rosa", "acct:rosa")
    guess = Trainer.create("trainer-rosa", "acct:ATTACKER")
    assert t.pubkey_hex != guess.pubkey_hex, (
        "trainer key must not be derivable from the published trainer_id")


def test_test_fixtures_are_deterministic_AND_honestly_labelled_forgeable():
    """`for_testing` keeps fixtures reproducible -- and really is forgeable, which
    is exactly why it is a separate, loudly-named constructor and never a
    default. If this ever stops being forgeable the docstring is lying."""
    a = Actor.for_testing("fixture", "F", "rancher", "acct:f")
    b = Actor.for_testing("fixture", "F", "rancher", "acct:f")
    assert a.pubkey_hex == b.pubkey_hex, "fixtures must be reproducible"
    # forgeable-by-design: derivable from the public id alone
    derived = keys.insecure_test_signer("fixture")
    assert derived.public_key_hex == a.pubkey_hex


# -- custody at rest -----------------------------------------------------------

def test_encrypted_keystore_roundtrip_and_no_plaintext_on_disk():
    with tempfile.TemporaryDirectory() as d:
        ks = keys.EncryptedFileKeyStore(d, passphrase="correct horse battery")
        signer = ks.create("node-k2")
        pub = signer.public_key_hex

        reloaded = ks.signer("node-k2")
        assert reloaded.public_key_hex == pub, "must round-trip to the same key"
        msg = b"settle job j-1"
        assert crypto.verify(msg, reloaded.sign(msg), bytes.fromhex(pub))

        # the raw seed must not be sitting on disk
        path = os.path.join(d, "node-k2.key.json")
        raw = open(path, encoding="utf-8").read()
        assert signer.export_seed().hex() not in raw, "seed must not be stored in clear"
        assert "seed_hex" not in raw, "the old plaintext field must be gone"
        env = json.loads(raw)
        assert set(env) >= {"salt", "nonce", "ciphertext", "tag"}

        # 0600 on POSIX. Windows does not implement POSIX mode bits at all --
        # os.open(..., 0o600) is effectively ignored and st_mode reports 0o666 --
        # so the at-rest file there is protected only by the user-profile ACL,
        # which this code does NOT set. Asserting POSIX perms on Windows would be
        # a test that lies about the guarantee; see specs/KEY-CUSTODY.md.
        if os.name == "posix":
            mode = stat.S_IMODE(os.stat(path).st_mode)
            assert not (mode & 0o077), (
                f"key file must not be group/world accessible: {mode:o}")


def test_wrong_passphrase_and_tampering_fail_closed():
    with tempfile.TemporaryDirectory() as d:
        ks = keys.EncryptedFileKeyStore(d, passphrase="right")
        ks.create("node-a")
        wrong = keys.EncryptedFileKeyStore(d, passphrase="wrong")
        try:
            wrong.signer("node-a")
            assert False, "a wrong passphrase must not yield a key"
        except ValueError as e:
            assert "passphrase" in str(e) or "tag" in str(e)

        # flipping a ciphertext byte must be caught by the MAC, not silently
        # decrypt to a DIFFERENT key (which would sign with a key nobody knows)
        path = os.path.join(d, "node-a.key.json")
        env = json.load(open(path, encoding="utf-8"))
        ct = bytearray(bytes.fromhex(env["ciphertext"]))
        ct[0] ^= 0x01
        env["ciphertext"] = bytes(ct).hex()
        json.dump(env, open(path, "w", encoding="utf-8"))
        try:
            keys.EncryptedFileKeyStore(d, passphrase="right").signer("node-a")
            assert False, "tampered key file must be refused"
        except ValueError:
            pass


def test_keystore_refuses_empty_passphrase_and_silent_overwrite():
    with tempfile.TemporaryDirectory() as d:
        try:
            keys.EncryptedFileKeyStore(d, passphrase="").create("n")
            assert False, "must refuse to write a private key unencrypted"
        except ValueError:
            pass
        ks = keys.EncryptedFileKeyStore(d, passphrase="pw")
        ks.create("n")
        try:
            ks.create("n")      # clobbering orphans every signature it ever made
            assert False, "must refuse to silently overwrite an existing key"
        except FileExistsError:
            pass


def test_missing_key_and_unconfigured_kms_fail_closed():
    with tempfile.TemporaryDirectory() as d:
        try:
            keys.EncryptedFileKeyStore(d, passphrase="pw").signer("nobody")
            assert False, "must not invent a key for an unknown identity"
        except FileNotFoundError:
            pass
    try:
        keys.ExternalKmsSigner("op", key_ref="").sign(b"x")
        assert False, "an unconfigured KMS signer must refuse to sign"
    except RuntimeError as e:
        assert "refusing to sign" in str(e)


def test_env_keystore():
    seed = keys.new_seed()
    os.environ["BINGO_SEED_NODE_X"] = seed.hex()
    try:
        s = keys.EnvKeyStore().signer("node-x")
        assert s.public_key() == crypto.publickey(seed)
    finally:
        del os.environ["BINGO_SEED_NODE_X"]


# -- rotation / revocation / recovery -----------------------------------------

def _identity():
    signing = keys.LocalSigner.generate("node-k2")
    recovery = keys.LocalSigner.generate("node-k2/recovery")
    d = KeyDirectory.genesis("node-k2", signing, recovery.public_key())
    return d, signing, recovery


def test_directory_verifies_and_rotation_preserves_history():
    d, k1, _rec = _identity()
    msg = b"settlement signed while k1 was active"
    sig = k1.sign_hex(msg)
    at = len(d.events) - 1                      # position when it was signed

    k2 = keys.LocalSigner.generate("node-k2")
    d.rotate(k1, k2.public_key())
    ok, notes = verify_directory(d.to_dict())
    assert ok, notes
    assert d.active_pubkey() == k2.public_key()

    # the OLD signature must still verify at its historical position: rotating
    # must not retroactively invalidate everything the previous key ever signed
    ok, notes = verify_as_identity(msg, sig, d.to_dict(), at_seq=at)
    assert ok, notes
    # and the new key is what's current
    m2 = b"signed after rotation"
    assert verify_as_identity(m2, k2.sign_hex(m2), d.to_dict())[0]


def test_revoked_key_is_refused_by_default():
    """A key that is still CURRENT but declared compromised must stop verifying.
    This is the case revocation exists for: the operator cannot rotate (the
    attacker has the key too), so the recovery key revokes it."""
    d, k1, rec = _identity()
    msg = b"anything"
    sig = k1.sign_hex(msg)
    assert verify_as_identity(msg, sig, d.to_dict())[0], "valid before revocation"

    d.revoke(rec, k1.public_key(), reason="laptop stolen")   # recovery key revokes
    assert verify_directory(d.to_dict())[0]

    ok, notes = verify_as_identity(msg, sig, d.to_dict())
    assert not ok and "revoked" in notes[-1], notes


def test_rotated_away_key_no_longer_signs_as_the_identity():
    """After rotation the identity means the NEW key; the old one cannot keep
    authorizing new work just because it was once valid."""
    d, k1, _rec = _identity()
    k2 = keys.LocalSigner.generate("node-k2")
    d.rotate(k1, k2.public_key())
    fresh = b"work claimed after the rotation"
    ok, notes = verify_as_identity(fresh, k1.sign_hex(fresh), d.to_dict())
    assert not ok, notes


def test_pre_revocation_acceptance_now_requires_PROOF_not_an_assertion():
    """Tightened once `bingo/anchor.py` existed.

    This used to accept an explicitly-asserted historical position, because a
    self-contained document cannot prove its own age and there was nothing better
    available. That assertion costs an attacker holding the stolen key exactly
    nothing, so it is now REFUSED: predating the revocation has to be proven
    against the external append-only log. See tests/test_anchor.py for the proof
    path that does get accepted."""
    d, k1, rec = _identity()
    msg = b"signed before the compromise"
    sig, at = k1.sign_hex(msg), len(d.events) - 1        # position 0, pre-revocation
    revoke_seq = d.revoke(rec, k1.public_key(), reason="compromised").seq

    assert not verify_as_identity(msg, sig, d.to_dict())[0], "default must refuse"
    ok, notes = verify_as_identity(msg, sig, d.to_dict(), at_seq=at)
    assert not ok, "asserting a pre-revocation position must not be enough"
    assert "anchor proof" in notes[-1], notes
    ok, notes = verify_as_identity(msg, sig, d.to_dict(), at_seq=revoke_seq)
    assert not ok and "revoked" in notes[-1], notes


def test_rotation_must_be_signed_by_the_outgoing_key():
    """Continuity: someone who steals a key cannot rewrite the chain to claim the
    identity, because every link back to genesis needs a key they never had."""
    d, k1, _rec = _identity()
    attacker = keys.LocalSigner.generate("attacker")
    try:
        d.rotate(attacker, keys.LocalSigner.generate("x").public_key())
        assert False, "rotation signed by a stranger must be refused"
    except keydir.KeyDirectoryError:
        pass

    # and forging it directly into the document is caught on replay
    doc = d.to_dict()
    ev = {"seq": 1, "type": keydir.ROTATE,
          "data": {"new_pubkey": attacker.public_key().hex()},
          "prev_hash": doc["events"][0]["hash"]}
    from bingo.models import canonical_json, sha256_hex
    body = canonical_json(ev)
    ev["sig"] = attacker.sign(body).hex()
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    doc["events"].append(ev)
    doc["head"] = ev["hash"]
    ok, notes = verify_directory(doc)
    assert not ok and "not signed by the required key" in notes[-1], notes


def test_recovery_without_the_lost_key():
    """The ordinary disaster: the signing key is gone. The pre-committed offline
    recovery key adopts a new one; a stranger's key cannot."""
    d, _k1, rec = _identity()
    k_new = keys.LocalSigner.generate("node-k2")

    imposter = keys.LocalSigner.generate("imposter")
    try:
        d.recover(imposter, k_new.public_key())
        assert False, "recovery by an uncommitted key must be refused"
    except keydir.KeyDirectoryError:
        pass

    d.recover(rec, k_new.public_key())
    ok, notes = verify_directory(d.to_dict())
    assert ok, notes
    assert d.active_pubkey() == k_new.public_key()
    m = b"signed with the recovered key"
    assert verify_as_identity(m, k_new.sign_hex(m), d.to_dict())[0]


def test_recovery_key_must_differ_from_the_signing_key():
    s = keys.LocalSigner.generate("n")
    try:
        KeyDirectory.genesis("n", s, s.public_key())
        assert False, "a recovery key kept beside the signing key recovers nothing"
    except keydir.KeyDirectoryError:
        pass


def test_directory_catches_tamper_and_reorder_and_fails_closed():
    d, k1, rec = _identity()
    k2 = keys.LocalSigner.generate("node-k2")
    d.rotate(k1, k2.public_key())
    d.revoke(k2, k1.public_key(), "rotated out")
    assert verify_directory(d.to_dict())[0]

    # tamper: swap in an attacker key on the rotation event
    doc = d.to_dict()
    doc["events"][1]["data"]["new_pubkey"] = keys.new_seed().hex() * 1
    assert not verify_directory(doc)[0], "tampered rotation must be caught"

    # reorder
    doc = d.to_dict()
    doc["events"][1], doc["events"][2] = doc["events"][2], doc["events"][1]
    assert not verify_directory(doc)[0], "reordering must be caught"

    # fail CLOSED on arbitrary junk -- returns (False, notes), never raises
    for junk in (None, [], {}, {"events": "no"}, {"events": [{"seq": 0}]},
                 {"events": [{"seq": 0, "type": "GENESIS", "data": {},
                              "prev_hash": "0" * 64, "sig": "zz"}]}):
        ok, notes = verify_directory(junk)
        assert ok is False and isinstance(notes, list), junk


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} key-custody groups pass: a private key is never "
          "derived from a published identifier (the forgery that let anyone who "
          "read a document sign as any party in it is closed, across all five "
          "provenance verticals); seeds are encrypted at rest with 0600 perms and "
          "fail closed on a wrong passphrase or tampering; an unconfigured KMS "
          "signer refuses to sign; and the signed key directory rotates without "
          "invalidating history, refuses a revoked key by default, requires the "
          "outgoing key to authorize a rotation, and recovers a lost identity only "
          "with the pre-committed offline key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
