#!/usr/bin/env python3
"""Generate DGD's issuer key OFFLINE, on a machine DGD controls.

Run this on an offline/air-gapped computer (unplug the network first if you want
the belt-and-suspenders guarantee). It creates an Ed25519 keypair using the
audited `cryptography` library, and — if this repo is present — cross-checks that
the key verifies under Project BINGO's own crypto, so you KNOW it's compatible
before you commit to it.

    pip install cryptography          # if not already installed
    python3 generate_issuer_key.py

Output:
  * DGD_ISSUER_SEED  — the SECRET. Put it in the environment of the machine that
    mints coins / runs the validation server. Never publish, never commit.
  * ISSUER_PUBKEY    — safe to share; this is what goes on digitalgold.co.

Store the seed in offline DGD custody (password manager / hardware). Whoever has
it can mint valid $25 coins.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as _s

_k = Ed25519PrivateKey.generate()
seed = _k.private_bytes(_s.Encoding.Raw, _s.PrivateFormat.Raw, _s.NoEncryption())
pub = _k.public_key().public_bytes(_s.Encoding.Raw, _s.PublicFormat.Raw)

# compatibility self-check against Project BINGO's crypto, if importable
compat = "not checked (run from the repo to verify)"
try:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "v3"))
    from bingo import crypto  # noqa
    assert crypto.publickey(seed) == pub, "pubkey mismatch"
    msg = b"dgd issuer key offline self-test"
    assert crypto.verify(msg, crypto.sign(msg, seed, pub), pub), "verify failed"
    compat = "OK — verifies under bingo.crypto (compatible with coins & the page)"
except Exception as e:  # pragma: no cover
    compat = f"self-check skipped/failed: {e}"

print("DGD issuer key (generated locally):\n")
print("  DGD_ISSUER_SEED=" + seed.hex())
print("  ISSUER_PUBKEY=" + pub.hex())
print("\ncompatibility:", compat)
print("\nKeep the SEED secret and offline. Share only the PUBKEY.")
