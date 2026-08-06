"""Ed25519 signatures — pure Python, stdlib only (no dependencies).

The PoF evidence chain must be verifiable by ANYONE holding a node's public
key, not just the node that signed it (HMAC could only be checked by the
secret holder). This vendors the public-domain Ed25519 reference math
(Bernstein et al.), with modular exponentiation via the builtin `pow` for
speed. Signing a job's few dozen events is milliseconds.

RFC 8032 Ed25519. Verified in tests against the `cryptography` library's
Ed25519 (test-only cross-check; not a runtime dependency).

API:
    keypair(seed32) -> (seed32, public_key_32)   # seed is the private key
    sign(message, seed32, public_key_32) -> signature_64
    verify(message, signature_64, public_key_32) -> bool
"""

from __future__ import annotations

import hashlib
import os

b = 256
q = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
d = (-121665 * pow(121666, q - 2, q)) % q
I = pow(2, (q - 1) // 4, q)


def _H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _inv(x: int) -> int:
    return pow(x, q - 2, q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(d * y * y + 1)
    x = pow(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


_By = (4 * _inv(5)) % q
_Bx = _xrecover(_By)
B = (_Bx % q, _By % q)

# --- point arithmetic in extended twisted-Edwards coords (X,Y,Z,T), a=-1 ---
# No modular inverse per operation (the slow part); one inverse at the end.
# Formulas: add-2008-hwcd-3 / dbl-2008-hwcd (curve a=-1). Cross-checked
# byte-for-byte against the `cryptography` library in tests.
_d2 = (2 * d) % q


def _to_ext(P):
    x, y = P
    return (x, y, 1, (x * y) % q)


def _from_ext(P):
    X, Y, Z, _T = P
    zi = _inv(Z)
    return ((X * zi) % q, (Y * zi) % q)


def _ext_add(P, Q):
    X1, Y1, Z1, T1 = P
    X2, Y2, Z2, T2 = Q
    A = ((Y1 - X1) * (Y2 - X2)) % q
    Bb = ((Y1 + X1) * (Y2 + X2)) % q
    C = (T1 * _d2 * T2) % q
    D = (Z1 * 2 * Z2) % q
    E = (Bb - A) % q
    F = (D - C) % q
    G = (D + C) % q
    Hh = (Bb + A) % q
    return ((E * F) % q, (G * Hh) % q, (F * G) % q, (E * Hh) % q)


def _ext_dbl(P):
    X1, Y1, Z1, _T1 = P
    A = (X1 * X1) % q
    Bb = (Y1 * Y1) % q
    C = (2 * Z1 * Z1) % q
    D = (-A) % q
    E = ((X1 + Y1) * (X1 + Y1) - A - Bb) % q
    G = (D + Bb) % q
    F = (G - C) % q
    Hh = (D - Bb) % q
    return ((E * F) % q, (G * Hh) % q, (F * G) % q, (E * Hh) % q)


def _edwards(P, Q):
    """Affine add (used by decode/verify comparisons and kept for clarity)."""
    return _from_ext(_ext_add(_to_ext(P), _to_ext(Q)))


def _scalarmult(P, e: int):
    """Affine-in, affine-out double-and-add via extended coords."""
    R = (0, 1, 1, 0)                     # neutral element
    Pe = _to_ext(P)
    while e > 0:
        if e & 1:
            R = _ext_add(R, Pe)
        Pe = _ext_dbl(Pe)
        e >>= 1
    return _from_ext(R)


def _encodeint(y: int) -> bytes:
    return y.to_bytes(b // 8, "little")


def _encodepoint(P) -> bytes:
    x, y = P
    val = y | ((x & 1) << (b - 1))
    return val.to_bytes(b // 8, "little")


def _bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _decodeint(s: bytes) -> int:
    return int.from_bytes(s, "little")


def _decodepoint(s: bytes):
    y = int.from_bytes(s, "little") & ((1 << (b - 1)) - 1)
    x = _xrecover(y)
    if x & 1 != _bit(s, b - 1):
        x = q - x
    P = (x, y)
    if not _isoncurve(P):
        raise ValueError("point not on curve")
    return P


def _isoncurve(P) -> bool:
    x, y = P
    return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0


def _secret_scalar_and_prefix(seed: bytes):
    h = _H(seed)
    a = 2 ** (b - 2) + sum(2 ** i * _bit(h, i) for i in range(3, b - 2))
    return a, h[b // 8:b // 4]


def publickey(seed: bytes) -> bytes:
    a, _ = _secret_scalar_and_prefix(seed)
    return _encodepoint(_scalarmult(B, a))


def keypair(seed: bytes | None = None) -> tuple[bytes, bytes]:
    seed = seed or os.urandom(32)
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    return seed, publickey(seed)


def _Hint(m: bytes) -> int:
    return _decodeint(_H(m)) % (2 ** (2 * b))  # full 512-bit reduction happens mod L later


def sign(message: bytes, seed: bytes, pub: bytes) -> bytes:
    a, prefix = _secret_scalar_and_prefix(seed)
    r = int.from_bytes(_H(prefix + message), "little")
    R = _encodepoint(_scalarmult(B, r))
    k = int.from_bytes(_H(R + pub + message), "little")
    S = (r + k * a) % L
    return R + _encodeint(S)


def verify(message: bytes, signature: bytes, pub: bytes) -> bool:
    if len(signature) != 64 or len(pub) != 32:
        return False
    try:
        R = _decodepoint(signature[:32])
        A = _decodepoint(pub)
        # reject low-order / identity public keys: [8]A == neutral means A lives
        # in the small subgroup, under which signatures can be universally forged.
        if _scalarmult(A, 8) == (0, 1):
            return False
        S = _decodeint(signature[32:])
        if S >= L:
            return False
        k = int.from_bytes(_H(signature[:32] + pub + message), "little")
        # check [S]B == R + [k]A
        lhs = _scalarmult(B, S)
        rhs = _edwards(R, _scalarmult(A, k))
        return lhs == rhs
    except (ValueError, Exception):
        return False


if __name__ == "__main__":
    # self-test: round trip + tamper detection
    sk, pk = keypair(bytes(range(32)))
    msg = b"proof-of-fabrication event"
    sig = sign(msg, sk, pk)
    assert verify(msg, sig, pk), "valid signature must verify"
    assert not verify(msg + b"x", sig, pk), "tampered message must fail"
    assert not verify(msg, sig, publickey(bytes(range(1, 33)))), "wrong key must fail"
    print("ed25519 self-test OK:", pk.hex()[:16], "…")
