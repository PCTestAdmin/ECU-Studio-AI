"""Status of manufacturer (OEM) signatures inside ECU firmware.

Three kinds of signature are kept strictly apart and never stand in for one another:

  * OEM firmware signatures   - inside the ECU image, made by the vehicle/ECU manufacturer (this module);
  * Authenticode              - on the Windows program files of ECU Studio AI (not checked by the program);
  * GitHub build attestations - provenance of the release assets (``gh attestation verify``, release workflow).

Every firmware signature ends in exactly one of six states:

  gueltig             cryptographically verified with a TRUSTED key: the signed bytes are exactly the signed ones
  ungueltig           cryptographically checked with a trusted key: the signature does not match these bytes
  erkannt             structure recognised (location, scheme), not verified - no trusted key for it
  erwartet            the ECU family usually carries a signature, it was not located in this file
  nicht_unterstuetzt  a signature is present, but its scheme has no verifier in this program
  unbekannt           nothing is known about a signature

Trust comes only from a trust store the user configures explicitly (``load_trust_store``), never from the analysed
file: a public key found in the firmware is no trust anchor, because whoever changes the firmware can replace the
key as well. "gueltig" says nothing about checksums, emissions, road legality or flashing; there is no flash
approval. This module only verifies: it has no function that creates, changes, removes or bypasses a signature in
firmware.

Verifiers (pure Python, no third-party library):
  ed25519               RFC 8032 (core/signing.py, checked against the RFC test vectors)
  rsa-pkcs1v15-sha256   RSASSA-PKCS1-v1_5 with SHA-256 (RFC 8017, section 8.2.2), modulus of at least 2048 bit
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import signing

GUELTIG, UNGUELTIG, ERKANNT, ERWARTET, NICHT_UNTERSTUETZT, UNBEKANNT = (
    'gueltig', 'ungueltig', 'erkannt', 'erwartet', 'nicht_unterstuetzt', 'unbekannt')
STATES = (GUELTIG, UNGUELTIG, ERKANNT, ERWARTET, NICHT_UNTERSTUETZT, UNBEKANNT)
STATE_TEXT = {
    GUELTIG: 'gültig – mit vertrauenswürdigem Schlüssel kryptographisch geprüft',
    UNGUELTIG: 'ungültig – mit vertrauenswürdigem Schlüssel geprüft, Daten oder Signatur verändert',
    ERKANNT: 'Struktur erkannt – nicht geprüft',
    ERWARTET: 'erwartet, aber nicht gefunden – nicht geprüft',
    NICHT_UNTERSTUETZT: 'Verfahren nicht unterstützt – nicht geprüft',
    UNBEKANNT: 'unbekannt – nicht geprüft',
}
SCHEMES = ('ed25519', 'rsa-pkcs1v15-sha256')
MIN_RSA_BITS = 2048
# DER prefix of DigestInfo for SHA-256 (RFC 8017, section 9.2, note 1)
_SHA256_DIGEST_INFO = bytes.fromhex('3031300d060960864801650304020105000420')


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    scheme: str
    public: bytes | tuple[int, int]          # Ed25519: 32 bytes; RSA: (n, e)
    source: str                               # where the user got the key from (documentation, never checked)

    @property
    def fingerprint(self) -> str:
        raw = self.public if isinstance(self.public, bytes) else (
            self.public[0].to_bytes((self.public[0].bit_length() + 7) // 8, 'big') + self.public[1].to_bytes(4, 'big'))
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignatureCandidate:
    """A signature located in a firmware image. ``ranges`` are the signed bytes (inclusive file offsets)."""
    kind: str
    scheme: str
    ranges: tuple[tuple[int, int], ...]
    signature: bytes
    location: int
    key_id: str | None = None


@dataclass(frozen=True)
class SignatureResult:
    kind: str
    state: str
    detail: str = ''
    key_id: str | None = None
    location: int | None = None
    domain: str = 'oem-firmware'
    meta: dict = field(default_factory=dict, compare=False)

    @property
    def text(self) -> str:
        return STATE_TEXT[self.state]


def rsa_pkcs1v15_sha256_verify(n: int, e: int, message: bytes, signature: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 verification with SHA-256 (RFC 8017 8.2.2); fails closed on every malformed input."""
    if not (isinstance(n, int) and isinstance(e, int)) or n.bit_length() < MIN_RSA_BITS or e < 3 or not e & 1:
        return False
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, 'big')
    if s >= n:
        return False
    em = pow(s, e, n).to_bytes(k, 'big')
    t = _SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    if k < len(t) + 11:
        return False
    expected = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return hmac.compare_digest(em, expected)


def load_trust_store(path: str | Path) -> dict[str, TrustedKey]:
    """Keys from an explicitly configured JSON file; anything malformed is skipped (fail closed).

    {"format": 1, "keys": {"<id>": {"scheme": "ed25519", "public_key": "<64 hex>", "source": "..."},
                           "<id>": {"scheme": "rsa-pkcs1v15-sha256", "n": "<hex>", "e": 65537, "source": "..."}}}
    """
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(obj, dict) or obj.get('format') != 1 or not isinstance(obj.get('keys'), dict):
        return {}
    store = {}
    for key_id, value in obj['keys'].items():
        if not isinstance(key_id, str) or not key_id.strip() or not isinstance(value, dict):
            continue
        source = value.get('source')
        if not isinstance(source, str) or not source.strip():
            continue                                   # a key without a stated origin is not trusted
        try:
            if value.get('scheme') == 'ed25519':
                public = bytes.fromhex(value['public_key'])
                if len(public) != 32:
                    continue
                store[key_id] = TrustedKey(key_id, 'ed25519', public, source)
            elif value.get('scheme') == 'rsa-pkcs1v15-sha256':
                n, e = int(value['n'], 16), value['e']
                if not isinstance(e, int) or n.bit_length() < MIN_RSA_BITS or e < 3 or not e & 1:
                    continue
                store[key_id] = TrustedKey(key_id, 'rsa-pkcs1v15-sha256', (n, e), source)
        except (KeyError, TypeError, ValueError):
            continue
    return store


def signed_bytes(data: bytes, ranges) -> bytes | None:
    """The signed message: the ranges in the given order; None if a range is empty, reversed or outside the file."""
    parts = []
    for start, end in ranges:
        if not (0 <= start <= end < len(data)):
            return None
        parts.append(data[start:end + 1])
    return b''.join(parts) if parts else None


def verify_candidate(data: bytes, candidate: SignatureCandidate,
                     trust: dict[str, TrustedKey] | None) -> SignatureResult:
    """Verify one located signature against the trust store; only a trusted key can give gueltig/ungueltig."""
    def result(state, detail, key_id=None):
        return SignatureResult(candidate.kind, state, detail, key_id, candidate.location)

    if candidate.scheme not in SCHEMES:
        return result(NICHT_UNTERSTUETZT, f'Verfahren {candidate.scheme} wird nicht geprüft')
    key = (trust or {}).get(candidate.key_id) if candidate.key_id else None
    if key is None:
        return result(ERKANNT, 'kein vertrauenswürdiger Schlüssel für diese Signatur')
    if key.scheme != candidate.scheme:
        return result(ERKANNT, f'Schlüssel {key.key_id} gehört zu einem anderen Verfahren')
    message = signed_bytes(data, candidate.ranges)
    if message is None:
        return result(ERKANNT, 'signierter Bereich liegt nicht vollständig in der Datei', key.key_id)
    if key.scheme == 'ed25519':
        ok = signing.verify(key.public, message, candidate.signature)
    else:
        ok = rsa_pkcs1v15_sha256_verify(*key.public, message, candidate.signature)
    if ok:
        return result(GUELTIG, f'Schlüssel {key.key_id} ({key.fingerprint[:16]}…)', key.key_id)
    return result(UNGUELTIG, f'Signatur passt nicht zu den Daten (Schlüssel {key.key_id})', key.key_id)
