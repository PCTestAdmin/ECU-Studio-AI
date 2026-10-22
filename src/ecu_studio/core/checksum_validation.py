"""Committed OEM checksum validation evidence.

The checksum calculators can prove that a structure is internally consistent
with one original file.  That is not the same as OEM validation.  This module
keeps the second, stricter gate in a small reviewed manifest keyed by the exact
original SHA-256.  An empty manifest is intentional until lawful original
firmware and an independent review are available.
"""
from __future__ import annotations

import json
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'checksum_oem_validation.json'


def validation_record(image, scheme: str, path: str | Path | None = None) -> dict | None:
    """Return a reviewed OEM record for ``image`` and ``scheme`` or ``None``.

    Records must be committed by a reviewer.  Merely naming a family or setting
    ``validated`` without source and reviewer fields never enables correction.
    Invalid manifests fail closed and are treated as no evidence.
    """
    path = MANIFEST if path is None else path
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or obj.get('format') != 1 or not isinstance(obj.get('entries'), list):
        return None
    for entry in obj['entries']:
        if not isinstance(entry, dict):
            continue
        if (entry.get('scheme') != scheme or entry.get('sha256') != image.digest or
                entry.get('validated') is not True or
                not isinstance(entry.get('source'), str) or not entry['source'].strip() or
                not isinstance(entry.get('reviewer'), str) or not entry['reviewer'].strip()):
            continue
        return dict(entry)
    return None
