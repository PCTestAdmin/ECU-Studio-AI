"""Cryptographically committed OEM checksum validation evidence.

The checksum calculators can prove that a structure is internally consistent
with one original file.  That is not the same as OEM validation.  This module
keeps the second, stricter gate in a manifest keyed by the exact original
SHA-256. Every usable entry is signed by two distinct trusted Ed25519 keys over
the canonical claim and an evidence hash. An empty manifest is intentional
until lawful original firmware and an independent review are available. The
signatures protect integrity and signer identity; they cannot prove a human's
independence by themselves.
"""
from __future__ import annotations

import json
from pathlib import Path

from .signing import verify as verify_signature


MANIFEST = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'checksum_oem_validation.json'
TRUSTED_KEYS = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'checksum_validation_keys.json'


def attestation_message(entry: dict) -> bytes:
    """Canonical bytes signed by every independent validation reviewer."""
    fields = ('scheme', 'sha256', 'family', 'software', 'evidence_sha256', 'source',
              'validated', 'validated_at', 'independent_review')
    return json.dumps({key: entry[key] for key in fields}, ensure_ascii=False,
                      sort_keys=True, separators=(',', ':')).encode('utf-8')


def _trusted_keys(path: str | Path) -> dict[str, tuple[bytes, str]]:
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(obj, dict) or obj.get('format') != 1 or not isinstance(obj.get('keys'), dict):
        return {}
    out = {}
    for key_id, value in obj['keys'].items():
        if not isinstance(key_id, str) or not key_id.strip() or not isinstance(value, dict):
            continue
        encoded, group = value.get('public_key'), value.get('independence_group')
        if not isinstance(encoded, str) or not isinstance(group, str) or not group.strip():
            continue
        try:
            key = bytes.fromhex(encoded)
        except ValueError:
            continue
        if len(key) == 32:
            out[key_id] = (key, group)
    return out


def validation_record(image, scheme: str, path: str | Path | None = None,
                      keys_path: str | Path | None = None) -> dict | None:
    """Return a reviewed OEM record for ``image`` and ``scheme`` or ``None``.

    Records must carry at least two signatures from distinct trusted keys over
    the same canonical attestation. Merely setting ``validated`` never enables
    correction.
    Invalid manifests fail closed and are treated as no evidence.
    """
    path = MANIFEST if path is None else path
    keys_path = TRUSTED_KEYS if keys_path is None else keys_path
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or obj.get('format') != 2 or not isinstance(obj.get('entries'), list):
        return None
    trusted = _trusted_keys(keys_path)
    if len(trusted) < 2:
        return None
    for entry in obj['entries']:
        if not isinstance(entry, dict):
            continue
        if (entry.get('scheme') != scheme or entry.get('sha256') != image.digest or
                entry.get('validated') is not True or entry.get('independent_review') is not True or
                any(not isinstance(entry.get(key), str) or not entry[key].strip() for key in
                    ('sha256', 'family', 'software', 'evidence_sha256', 'source', 'validated_at')) or
                not isinstance(entry.get('signatures'), list) or len(entry['signatures']) < 2):
            continue
        if any(len(value) != 64 or any(ch not in '0123456789abcdefABCDEF' for ch in value)
               for value in (entry['sha256'], entry['evidence_sha256'])):
            continue
        message = attestation_message(entry)
        seen = set()
        groups = set()
        valid = 0
        for signature in entry['signatures']:
            if not isinstance(signature, dict):
                continue
            key_id, encoded = signature.get('key_id'), signature.get('signature')
            if key_id in seen or key_id not in trusted or not isinstance(encoded, str):
                continue
            try:
                raw = bytes.fromhex(encoded)
            except ValueError:
                continue
            public, group = trusted[key_id]
            if verify_signature(public, message, raw):
                seen.add(key_id)
                groups.add(group)
                valid += 1
        if valid >= 2 and len(groups) >= 2:
            record = dict(entry)
            record['verified_signatures'] = valid
            return record
    return None
