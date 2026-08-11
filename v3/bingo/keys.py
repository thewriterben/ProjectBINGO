"""Key custody - where private keys live, and who is allowed to sign with them.

Every signature in BINGO authorizes value movement: a node's PoF chain releases
settlement, an operator's EARN distributes revenue, a rancher's attestation sets
what a cut is worth. The kernel proves *a key signed this*. This module is the
other half of that sentence: **whose key, kept how, and what happens when it is
lost or stolen.**

The design has three pieces:

  * **`Signer`** - the seam. A signer exposes `public_key()` and `sign()`, and
    NOTHING else. That shape is deliberate: a local signer holds the seed in
    memory, but an HSM/KMS signer never has the private key at all - it ships the
    message out to hardware that signs and returns a signature. Code that takes a
    `Signer` works with both, so moving to hardware is a construction change, not
    a rewrite. Anything that demands raw seed bytes forecloses that option, which
    is why `Actor`/`NodeAgent` now hold a signer rather than a seed.
  * **`KeyStore`** - custody at rest. `EncryptedFileKeyStore` keeps seeds
    encrypted under a passphrase with `0600` permissions; `EnvKeyStore` reads
    them from the environment (containers/CI); `ExternalKmsSigner` is the
    fail-closed seam for real hardware. A keystore never returns a seed to
    ordinary code - it returns a `Signer`.
  * **Generation.** `new_seed()` is `os.urandom(32)` and nothing else. A private
    key must never be a function of anything public. (It once was here: actor
    identities defaulted to a seed derived from the actor's own published id, so
    reading a document handed you the signer's private key. See
    `specs/KEY-CUSTODY.md`.)

Rotation, revocation and recovery live in `bingo/keydir.py` - they need a signed,
verifiable *record*, not just a place to put bytes.

**Honest note on the file encryption.** The kernel is stdlib-only (no
`cryptography`), and the standard library ships no AEAD. `EncryptedFileKeyStore`
therefore uses a construction assembled from stdlib primitives:
PBKDF2-HMAC-SHA256 for the passphrase, an HMAC-SHA256 counter-mode keystream, and
encrypt-then-MAC with a constant-time tag compare. That is a sound, conventional
construction and it is far better than the plaintext `seed_hex` it replaces - but
it is hand-rolled and unaudited, and it cannot protect a key from someone who
already has code execution as you. For anything holding real value, put the key
in an HSM or KMS and use `ExternalKmsSigner`; that is what the seam is for.

**Honest note on file permissions.** `EncryptedFileKeyStore` creates key files
`0600`, but POSIX mode bits are a no-op on Windows: `os.open(..., 0o600)` is
ignored there and the file inherits the directory ACL. On Windows the passphrase
encryption is doing ALL the work, with no OS-level access control behind it -
setting a proper ACL is not implemented. Choose a strong passphrase there, keep
the volume encrypted, and prefer the KMS seam.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
from abc import ABC, abstractmethod

from . import crypto

# PBKDF2 cost. Deliberately expensive: this guards an at-rest key file against
# offline guessing, so the cost is paid once at unlock, not per signature.
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_NONCE_BYTES = 16
_TAG_BYTES = 32
_KEYFILE_VERSION = 1


def new_seed() -> bytes:
    """A fresh 32-byte Ed25519 seed from the OS CSPRNG.

    The ONLY supported way to mint a private key. Never derive a seed from a
    name, an id, a timestamp, or any other value that appears in a document -
    if it is public, or guessable, the key is forgeable by anyone who reads it.
    """
    return os.urandom(32)


# -- the signing seam ----------------------------------------------------------

class Signer(ABC):
    """Something that can sign as an identity, without necessarily revealing how.

    Deliberately minimal - `public_key()` and `sign()`. A `LocalSigner` holds the
    seed; an HSM-backed signer holds a handle to hardware that will never release
    the key. Callers that only need signatures should accept a `Signer` so both
    work unchanged.
    """

    @property
    @abstractmethod
    def identity(self) -> str:
        """The identity this signer signs as (node id, actor id, ...)."""

    @abstractmethod
    def public_key(self) -> bytes:
        """The 32-byte Ed25519 public key."""

    @abstractmethod
    def sign(self, message: bytes) -> bytes:
        """The 64-byte Ed25519 signature over `message`."""

    # convenience shared by all signers
    @property
    def public_key_hex(self) -> str:
        return self.public_key().hex()

    def sign_hex(self, message: bytes) -> str:
        return self.sign(message).hex()


class LocalSigner(Signer):
    """Holds the seed in process memory. Fine for a node that controls its own
    machine; the key is exposed to anything that can read this process."""

    def __init__(self, seed: bytes, identity: str = ""):
        if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
            raise ValueError("seed must be exactly 32 bytes")
        self._seed = bytes(seed)
        self._pub = crypto.publickey(self._seed)
        self._identity = identity

    @classmethod
    def generate(cls, identity: str = "") -> "LocalSigner":
        return cls(new_seed(), identity)

    @property
    def identity(self) -> str:
        return self._identity

    def public_key(self) -> bytes:
        return self._pub

    def sign(self, message: bytes) -> bytes:
        return crypto.sign(message, self._seed, self._pub)

    def export_seed(self) -> bytes:
        """The raw private seed. Only for writing to a keystore - never log,
        transmit, or put this in a document."""
        return self._seed

    def __repr__(self) -> str:                      # never print the seed
        return f"LocalSigner(identity={self._identity!r}, pub={self._pub.hex()[:16]}...)"


class ExternalKmsSigner(Signer):
    """Seam for a real HSM / cloud KMS, where the private key never exists in
    this process. Fails closed: with no client configured it refuses to sign
    rather than falling back to something weaker.

    The point of having this here even unimplemented is that the *shape* is
    right - `sign()` sends bytes out and gets a signature back, so nothing in
    the codebase assumes a seed is reachable.
    """

    def __init__(self, identity: str, key_ref: str = "", client=None,
                 public_key: bytes | None = None):
        self._identity = identity
        self._key_ref = key_ref or os.environ.get("BINGO_KMS_KEY_REF", "")
        self._client = client
        self._pub = public_key

    @property
    def identity(self) -> str:
        return self._identity

    def public_key(self) -> bytes:
        if self._pub is None:
            raise RuntimeError(
                "no public key available from the KMS seam (configure a client)")
        return self._pub

    def sign(self, message: bytes) -> bytes:
        if self._client is None or not self._key_ref:
            raise RuntimeError(
                "ExternalKmsSigner is not configured (no client/key ref) - refusing "
                "to sign. Wire a real KMS/HSM client, or use LocalSigner with an "
                "EncryptedFileKeyStore.")
        # TODO(real): sig = self._client.sign(key_ref=self._key_ref,
        #                                     message=message, alg="ED25519")
        raise NotImplementedError("real KMS signing is not wired in this environment")


# -- at-rest custody -----------------------------------------------------------

def _derive(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    """PBKDF2-HMAC-SHA256 -> (encryption key, MAC key). Separate keys for the two
    jobs so a weakness in one does not become a weakness in the other."""
    material = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt,
                                   _PBKDF2_ITERATIONS, dklen=64)
    return material[:32], material[32:]


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """HMAC-SHA256 in counter mode. Each block is HMAC(key, nonce || counter),
    so blocks are independent and the stream never repeats for a fresh nonce."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + struct.pack(">I", counter), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def encrypt_seed(seed: bytes, passphrase: str) -> dict:
    """Encrypt-then-MAC a private seed under a passphrase. Returns a JSON-safe
    envelope; the passphrase is never stored."""
    if not passphrase:
        raise ValueError("refusing to encrypt a key with an empty passphrase")
    salt, nonce = os.urandom(_SALT_BYTES), os.urandom(_NONCE_BYTES)
    enc_key, mac_key = _derive(passphrase, salt)
    ciphertext = bytes(a ^ b for a, b in zip(seed, _keystream(enc_key, nonce, len(seed))))
    tag = hmac.new(mac_key, salt + nonce + ciphertext, hashlib.sha256).digest()
    return {"v": _KEYFILE_VERSION, "kdf": "pbkdf2-hmac-sha256",
            "iterations": _PBKDF2_ITERATIONS, "salt": salt.hex(),
            "nonce": nonce.hex(), "ciphertext": ciphertext.hex(), "tag": tag.hex()}


def decrypt_seed(envelope: dict, passphrase: str) -> bytes:
    """Reverse `encrypt_seed`, verifying the tag FIRST (constant-time) so a
    tampered or wrong-passphrase file is refused instead of yielding garbage
    that would silently become a different, wrong signing key."""
    if envelope.get("v") != _KEYFILE_VERSION:
        raise ValueError(f"unsupported key file version: {envelope.get('v')!r}")
    try:
        salt = bytes.fromhex(envelope["salt"])
        nonce = bytes.fromhex(envelope["nonce"])
        ciphertext = bytes.fromhex(envelope["ciphertext"])
        tag = bytes.fromhex(envelope["tag"])
    except (KeyError, ValueError) as e:
        raise ValueError(f"malformed key file: {e}") from None
    iterations = envelope.get("iterations", _PBKDF2_ITERATIONS)
    material = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt,
                                   iterations, dklen=64)
    enc_key, mac_key = material[:32], material[32:]
    expected = hmac.new(mac_key, salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):       # constant-time
        raise ValueError("wrong passphrase or corrupted key file (tag mismatch)")
    seed = bytes(a ^ b for a, b in zip(ciphertext,
                                       _keystream(enc_key, nonce, len(ciphertext))))
    if len(seed) != 32:
        raise ValueError("decrypted key is not a 32-byte seed")
    return seed


class KeyStore(ABC):
    """Custody backend. Hands out `Signer`s, not seeds."""

    @abstractmethod
    def signer(self, identity: str) -> Signer:
        """The signer for `identity`. Raises if there is no key - fail closed,
        never silently mint one where a caller expected an existing identity."""

    @abstractmethod
    def has(self, identity: str) -> bool: ...


class EncryptedFileKeyStore(KeyStore):
    """Seeds encrypted at rest under a passphrase, one JSON file per identity,
    `0600`, written atomically.

    Replaces the previous `out/node_identity.json`, which stored `seed_hex` in
    the clear next to a comment asking the operator not to share it.
    """

    def __init__(self, directory: str, passphrase: str | None = None):
        self.directory = directory
        self._passphrase = (passphrase if passphrase is not None
                            else os.environ.get("BINGO_KEY_PASSPHRASE", ""))
        os.makedirs(directory, exist_ok=True)
        try:                                        # best-effort on POSIX
            os.chmod(directory, 0o700)
        except OSError:
            pass

    def _path(self, identity: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in identity)
        return os.path.join(self.directory, f"{safe}.key.json")

    def has(self, identity: str) -> bool:
        return os.path.exists(self._path(identity))

    def create(self, identity: str, *, overwrite: bool = False) -> Signer:
        """Mint a NEW random key for `identity` and store it encrypted.
        Refuses to clobber an existing key unless `overwrite` - silently
        replacing a key would orphan every signature it ever made."""
        if self.has(identity) and not overwrite:
            raise FileExistsError(
                f"a key already exists for {identity!r}; refusing to overwrite "
                "(use the key directory to ROTATE instead - rotation keeps the "
                "old key verifiable for history)")
        return self._write(identity, new_seed())

    def _write(self, identity: str, seed: bytes) -> Signer:
        if not self._passphrase:
            raise ValueError(
                "no passphrase (set BINGO_KEY_PASSPHRASE or pass one) - refusing "
                "to write a private key to disk unencrypted")
        envelope = encrypt_seed(seed, self._passphrase)
        envelope["identity"] = identity
        envelope["public_key_hex"] = crypto.publickey(seed).hex()
        path = self._path(identity)
        tmp = path + ".tmp"
        # create 0600 from the start - never briefly world-readable
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        os.replace(tmp, path)
        return LocalSigner(seed, identity)

    def signer(self, identity: str) -> Signer:
        path = self._path(identity)
        if not os.path.exists(path):
            raise FileNotFoundError(f"no stored key for identity {identity!r}")
        if not self._passphrase:
            raise ValueError("no passphrase (set BINGO_KEY_PASSPHRASE) - cannot unlock")
        with open(path, encoding="utf-8") as f:
            envelope = json.load(f)
        seed = decrypt_seed(envelope, self._passphrase)     # raises on wrong pass
        stored_pub = envelope.get("public_key_hex")
        signer = LocalSigner(seed, identity)
        if stored_pub and stored_pub != signer.public_key_hex:
            raise ValueError(
                "key file public key does not match the decrypted seed - refusing")
        return signer


class EnvKeyStore(KeyStore):
    """Seeds from the environment (`BINGO_SEED_<IDENTITY>` hex) - for containers
    and CI where the orchestrator injects secrets. The key is exposed to anything
    that can read the process environment, so this is a step below a real KMS."""

    PREFIX = "BINGO_SEED_"

    def _var(self, identity: str) -> str:
        return self.PREFIX + "".join(
            c.upper() if c.isalnum() else "_" for c in identity)

    def has(self, identity: str) -> bool:
        return bool(os.environ.get(self._var(identity)))

    def signer(self, identity: str) -> Signer:
        raw = os.environ.get(self._var(identity))
        if not raw:
            raise KeyError(f"no key in environment for {identity!r} "
                           f"(expected ${self._var(identity)})")
        try:
            seed = bytes.fromhex(raw.strip())
        except ValueError:
            raise ValueError(f"${self._var(identity)} is not valid hex") from None
        return LocalSigner(seed, identity)


# -- test fixtures (explicit, never a default) ---------------------------------

def insecure_test_signer(identity: str) -> LocalSigner:
    """A DETERMINISTIC signer for tests and demos.

    **The private key is derived from the public identity string**, so anyone who
    reads a document signed this way can recompute the key and forge signatures.
    That is the point - reproducible fixtures - and it is why this is a loudly
    named function you have to reach for on purpose, rather than what you get by
    default. Never use it for anything that touches real value.
    """
    seed = hashlib.sha256(b"bingo/insecure-test-key/v1|" + identity.encode()).digest()
    return LocalSigner(seed, identity)
