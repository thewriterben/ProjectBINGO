# Key custody, rotation, revocation, and recovery

_Status: implemented (`bingo/keys.py`, `bingo/keydir.py`), 34/34 suites. Written
2026-08-11, immediately after the Tier-1 payout rail became real._

## Why this exists

BINGO proves things with signatures. A node's proof-of-fabrication chain releases
its settlement; an operator's `EARN` event distributes revenue to investors; a
rancher's attestation is what makes a cut worth $65/lb. Every one of those is the
same sentence: **this key signed this, therefore pay.**

The kernel has been hardened for ten red-team rounds on the second half of that
sentence - that the signature is sound, binds the right bytes, and fails closed.
This spec is about the first half: *whose key, kept how, and what happens when it
is lost or stolen.* A signature is only worth the secrecy of the key behind it,
and until now there was nothing here at all.

The trigger was Tier 1. While the money rails were `NotImplementedError` stubs,
demo-grade keys were a survivable inconsistency. The moment a real rail could move
real dollars, the keys authorizing those payouts became the weakest link in the
system.

## The vulnerability this closed

`Actor.create` - the identity primitive used by **all five** provenance verticals
(passport, token, transport, coin, machine-RWA) - defaulted the private seed to a
deterministic function of the actor's own `actor_id`:

```python
seed = seed if seed is not None else (actor_id.encode() + b"\x00" * 32)[:32]
```

`actor_id` is not a secret. It is published in the clear as the `signer` of every
event in every document the system ships. So:

```
attacker reads a passport  ->  sees signer id "rancher-sadu"
derives seed from it       ->  holds that rancher's PRIVATE KEY
signs anything             ->  forged attestations verify as the real rancher
```

Confirmed by running it: a forged passport claiming fabricated provenance verified
as the genuine signer. `Trainer.create` in the training-royalty vertical had the
identical defect.

**Why ten rounds of red-team missed it.** Every round pointed attackers at the
*verifiers* - forge a signature, break a chain, bypass a gate - and every round the
attackers were *handed* constructed documents with keys already in them. Nobody
attacked key *generation*. The campaign tested the locks exhaustively and never
looked at the key-cutting machine. Worth remembering: an adversarial exercise only
covers the surface you point it at, and "we ran a red-team" is not the same claim
as "we red-teamed everything."

**The fix.** `create()` with no key now mints `os.urandom(32)` and nothing else.
Reproducible fixtures moved to `Actor.for_testing()` / `Trainer.for_testing()`,
which are deliberately loud about deriving a forgeable key from the public id.
Cost of the safe default: exactly two test call sites that genuinely needed
determinism. The rule, stated flatly:

> **A private key is never a function of anything public.** If it can be derived
> from a name, an id, a timestamp, or anything else that appears in a document,
> it is not a private key.

## The three layers

### 1. `Signer` - the seam (`bingo/keys.py`)

A signer exposes `public_key()` and `sign()`, and nothing else. That shape is the
whole point: a `LocalSigner` holds the seed in memory, but an HSM/KMS signer never
has the private key at all - it ships bytes out to hardware and gets a signature
back. Code that accepts a `Signer` works with both, so moving to hardware is a
construction change rather than a rewrite. Anything that demands raw seed bytes
forecloses that option, which is why `Actor` and `Trainer` now accept `signer=`.

`ExternalKmsSigner` is the fail-closed seam for real hardware: unconfigured, it
refuses to sign rather than falling back to something weaker.

### 1b. The signing path itself

A seam is only worth as much as what sits behind it. `bingo/crypto.py` is a
correct RFC 8032 Ed25519, but **Python big-integer arithmetic is variable-time by
construction** - how long it runs depends on the secret scalar - so the
pure-Python *signing* path leaks key material to anyone who can measure it, and
nothing written in pure Python fixes that.

The asymmetry that makes this tractable:

| | input | leaks? | implementation |
|---|---|---|---|
| **signing** | the private key | yes, via timing | audited constant-time library, when installed |
| **verification** | message, signature, public key - all public | nothing to leak | pure-Python, always |

`AuditedSigner` signs through `cryptography`'s Ed25519 when it is available, and
`best_local_signer()` picks it automatically - both keystores hand it out, so a
node that has the library never signs in pure Python by accident. It also derives
the *public key* through the audited library, because `crypto.publickey()` is a
second variable-time operation **on the secret seed**; the point is that no
secret-dependent pure-Python math runs at all.

The drop-in claim is checkable rather than hopeful: RFC 8032 signatures are
deterministic, so the two implementations must produce **byte-identical** output
for the same seed and message. `tests/test_signing_path.py` checks that over 150
random seeds/messages, checks the public keys agree, and cross-verifies in both
directions. Measured on the cloud host: ~4 ms/op pure-Python vs ~38 us/op audited,
about 105x - the security fix is also the performance fix.

Without the library, `AuditedSigner` **refuses to construct** rather than silently
degrading; the equivalence checks *skip and say so*, because a skipped check must
never read as a passed one. `signing_path_report()` states in one line whether
this host is safe to hold a real key. Note that the reference node's own machine
does **not** currently have the library, so it is signing in pure Python today.

Verification stays pure-Python everywhere and always. That is deliberate: it is
what keeps "a stranger can verify this document with nothing installed" true, and
it costs nothing, because there is no secret in it.

### 2. `KeyStore` - custody at rest

| Backend | Use | Exposure |
|---|---|---|
| `EncryptedFileKeyStore` | a node on its own machine | passphrase-encrypted, `0600` |
| `EnvKeyStore` | containers / CI | anything that can read the environment |
| `ExternalKmsSigner` | real value | key never enters the process |

This replaces `out/node_identity.json`, which stored `seed_hex` in plaintext next
to a comment asking the operator not to share it. That is not custody; it is a
note. Onboarding now encrypts under `$BINGO_KEY_PASSPHRASE`, and **with no
passphrase set it mints an ephemeral key and says so rather than ever writing a
private key to disk in the clear.** An existing plaintext file is flagged as
compromised with instructions to rotate.

**Honest note on file permissions.** Key files are created `0600`, but POSIX mode
bits are a no-op on Windows: `os.open(..., 0o600)` is ignored and the file
inherits the directory ACL. **On Windows the passphrase encryption is doing all
the work, with no OS-level access control behind it** - setting a proper Windows
ACL is not implemented. That matters here because the reference node runs on
Windows. Use a strong passphrase, keep the volume encrypted (BitLocker), and
prefer the KMS seam.

**Honest note on the encryption.** The kernel is stdlib-only and the standard
library ships no AEAD, so `EncryptedFileKeyStore` uses a construction assembled
from stdlib primitives: PBKDF2-HMAC-SHA256 (600k iterations), an HMAC-SHA256
counter-mode keystream, encrypt-then-MAC, constant-time tag compare. That is a
sound conventional construction and vastly better than the plaintext it replaces -
but it is hand-rolled and unaudited, and it cannot protect a key from an attacker
who already has code execution as you. For real value, use an HSM or KMS. That is
what the seam is for.

### 3. The key directory - rotation, revocation, recovery (`bingo/keydir.py`)

Which key an identity may sign with has to be answerable the way BINGO answers
everything else: from a signed, hash-chained document a stranger can verify
offline. A mutable server-side table would not survive the threat model. Same
kernel - `sha256_hex`, `canonical_json`, Ed25519 - no new crypto.

| Event | Meaning | Who must sign |
|---|---|---|
| `GENESIS` | first key + commitment to a recovery key | the genesis key |
| `ROTATE` | move to a new key | the **outgoing** key |
| `REVOKE` | declare a key compromised | active **or** recovery key |
| `RECOVER` | adopt a new key without the old one | the **committed recovery** key |

Three properties worth stating explicitly:

- **Rotation is a continuity proof, not a claim.** `ROTATE` must be signed by the
  key being retired, so every link chains back to `GENESIS` through keys the
  attacker never had. Someone who steals today's key cannot rewrite history to
  show they held the identity all along.
- **Rotation does not invalidate the past.** `active_key_at(seq)` resolves the key
  authoritative at a given directory position, so a settlement signed last month
  by last month's key still verifies. A rotation protocol that orphaned history
  would make rotation something operators avoid, which defeats it.
- **The recovery key is committed at `GENESIS` and cannot be changed by the
  signing key.** Otherwise an attacker who stole the signing key would simply
  install their own recovery key and own the identity permanently. It is meant to
  live offline - paper, a safe, an HSM in a drawer - and never touch the signing
  host.

## Backdating: the limit, and how it was closed

`verify_as_identity()` defaults to evaluating against the directory HEAD, so **a
revoked key is refused.**

The hard case is a signature made *before* a key was revoked. Originally the only
option was to let the caller assert a historical position - and that assertion
costs an attacker holding the stolen key exactly nothing, because they control
every byte of the document they hand you, including any position or timestamp it
claims. A self-contained artifact cannot prove its own age. This was documented
here as an open limitation, needing an **external ordering witness**.

**That witness now exists** (`bingo/anchor.py`, `specs/EXTERNAL-ANCHOR.md`), so
the assertion path is gone. Accepting a revoked key's signature now requires an
`anchor` proof that the signature was recorded in an append-only Merkle log
*before* the revocation was:

```python
verify_as_identity(msg, sig, directory_doc, anchor={
    "log_pubkey": ..., "revoked_payload": ...,
    "receipt": {...},              # inclusion proof for the signature
    "revocation_receipt": {...},   # inclusion proof for the revocation
    "witness_keys": {...}, "quorum": 2,
})
```

Both halves must verify, they must come from the same log, and the signature's
index must be strictly lower. Logging the forgery *after* the revocation yields a
perfectly valid inclusion proof and is still refused, because order is the claim.

What this converts, honestly: "trust whatever the document says about when it was
signed" becomes "trust that the log operator and a quorum of independent witnesses
are not all colluding." That is a real trust assumption, not a proof - but it is
a bounded one that a relying party chooses, and it is enormously better than a
claim the attacker writes themselves.

## Operator runbook

**Set up a node identity**

```bash
export BINGO_KEY_PASSPHRASE='...'        # back this up; losing it means recovery
python -m bingo.node.onboard --name "Dana's X1C" --operator acct:dana
```

**Open a directory with an offline recovery key.** Generate the recovery key on a
machine that is not the signing host, and keep it offline.

```python
from bingo import keys
from bingo.keydir import KeyDirectory

store    = keys.EncryptedFileKeyStore("out/keys")     # $BINGO_KEY_PASSPHRASE
signing  = store.signer("n-dana")
recovery = keys.LocalSigner.generate("n-dana/recovery")   # export, store OFFLINE
directory = KeyDirectory.genesis("n-dana", signing, recovery.public_key())
```

**Routine rotation** (no compromise - rotate on a schedule):

```python
new = store.create("n-dana-2026q4")
directory.rotate(signing, new.public_key())
```

**Suspected compromise** - revoke first, then re-key. Revoke with the recovery key
if the signing key is the one that leaked:

```python
directory.revoke(recovery, signing.public_key(), reason="laptop stolen")
directory.recover(recovery, store.create("n-dana-new").public_key())
```

**Lost key** (no compromise, just gone): `directory.recover(recovery, new_pub)`.

**Lost recovery key too:** the identity cannot be rescued. Open a new identity and
re-establish reputation. This is deliberate - a back door that rescues an operator
who lost everything is a back door an attacker can walk through.

Publish `directory.to_dict()` wherever relying parties can fetch it; they call
`verify_as_identity(message, sig, directory_doc)` instead of checking a raw key.

## What is still open

- ~~**No external anchor**~~ **CLOSED** (`bingo/anchor.py`) - and the same
  primitive is now available to close the `provenance/coin.py` rollback
  limitation, which has not yet been wired up.
- **The file encryption is hand-rolled and unaudited.** Use the KMS seam for real
  value.
- **`ExternalKmsSigner` is a seam, not an integration** - it fails closed and is
  marked `TODO(real)`, exactly like the payout rails were before Tier 1.
- **Directory distribution is unspecified.** The document verifies offline, but
  how a relying party *learns the current head* is the unsolved half, and it is
  the same problem as the external anchor.
- **No OS-level file protection on Windows** (above) - the encryption is the
  only barrier there.
- **Nothing here has had an independent cryptographic review.**
