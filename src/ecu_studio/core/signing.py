"""Ed25519 signatures for update packages (RFC 8032, pure Python).

The reference algorithm of RFC 8032 section 6, checked against the RFC test
vectors (tests/test_signing.py). Verification needs no third-party library, so
the portable package gains no dependency. Timing side channels do not matter
for verifying a public signature; signing only runs in the release workflow.

Signed message: ``ECU-Studio-AI update\\n<file name>\\n<sha256 hex>`` - binds the
signature to the exact file name (thus the version) and content.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

p = 2 ** 255 - 19
q = 2 ** 252 + 27742317777372353535851937790883648493
PUBLIC_KEY_FILE = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'update_signing_key.pub'


def _inv(x: int) -> int:
    return pow(x, p - 2, p)


d = -121665 * _inv(121666) % p
_SQRT_M1 = pow(2, (p - 1) // 4, p)


def _sha512(s: bytes) -> bytes:
    return hashlib.sha512(s).digest()


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % p, (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C, D = 2 * P[3] * Q[3] * d % p, 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F, G * H, F * G, E * H)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q) -> bool:
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recover_x(y: int, sign: int):
    if y >= p:
        return None
    x2 = (y * y - 1) * _inv(d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p:
        x = x * _SQRT_M1 % p
    if (x * x - x2) % p:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_GY = 4 * _inv(5) % p
_GX = _recover_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % p)


def _compress(P) -> bytes:
    zinv = _inv(P[2])
    x, y = P[0] * zinv % p, P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % p)


def _expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError('Geheimer Schlüssel muss 32 Byte lang sein')
    h = _sha512(secret)
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _modq(s: bytes) -> int:
    return int.from_bytes(_sha512(s), 'little') % q


def public_key(secret: bytes) -> bytes:
    a, _ = _expand(secret)
    return _compress(_mul(a, G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _compress(_mul(a, G))
    r = _modq(prefix + message)
    R = _compress(_mul(r, G))
    s = (r + _modq(R + A + message) * a) % q
    return R + int.to_bytes(s, 32, 'little')


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    R = _decompress(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= q:
        return False
    h = _modq(signature[:32] + public + message)
    return _equal(_mul(s, G), _add(R, _mul(h, A)))


def update_message(file_name: str, sha256_hex: str) -> bytes:
    return f'ECU-Studio-AI update\n{file_name}\n{sha256_hex.lower()}'.encode('ascii')


def trusted_key() -> bytes | None:
    """The maintainer's public key shipped with the app, or None (signatures then not required)."""
    try:
        text = PUBLIC_KEY_FILE.read_text(encoding='ascii').strip()
    except OSError:
        return None
    key = bytes.fromhex(text)
    if len(key) != 32:
        raise ValueError('update_signing_key.pub ist kein Ed25519-Schlüssel')
    return key
