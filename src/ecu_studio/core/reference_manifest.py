"""Local, hash-locked reference pairs. No input paths are copied into reports."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re

from .storage import atomic_write


def load_manifest(path: str | Path) -> list[dict]:
    path = Path(path).resolve()
    if path.stat().st_size > 2 * 1024**2:
        raise ValueError('Reference manifest exceeds 2 MiB')
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or obj.get('schema') != 1:
        raise ValueError('Expected locked reference manifest schema 1')
    pairs = obj.get('pairs')
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 100:
        raise ValueError('Expected 1..100 reference pairs')
    entries, names, roles = [], set(), {}
    for i, item in enumerate(pairs):
        if not isinstance(item, dict):
            raise ValueError(f'Pair {i}: expected object')
        name = item.get('name', '')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name) or name in names:
            raise ValueError(f'Pair {i}: use a unique public alias without paths')
        names.add(name)
        for key in ('family', 'software', 'source', 'license'):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 160 or any(c in value for c in '\\/:\n\r'):
                raise ValueError(f'{name}: {key} must be a public label, not a file path or URL')
        role = item.get('role')
        if role not in ('training', 'development', 'test') or type(item.get('complete')) is not bool:
            raise ValueError(f'{name}: explicit role and complete boolean required')
        if item.get('data_kind') not in ('synthetic', 'real'):
            raise ValueError(f'{name}: data_kind must be synthetic or real')
        if os.environ.get('CI') and item['data_kind'] != 'synthetic':
            raise ValueError('Real reference data must stay on the local development machine')
        entry = dict(item)
        for key, digest_key, limit in (('bin', 'sha256', 128 * 1024**2),
                                        ('reference', 'reference_sha256', 128 * 1024**2)):
            expected = item.get(digest_key, '')
            if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError(f'{name}: {digest_key} required')
            try:
                file = (path.parent / item[key]).resolve()
                if file.stat().st_size > limit:
                    raise ValueError(f'{name}: input size limit exceeded')
                actual = hashlib.sha256(file.read_bytes()).hexdigest()
            except (OSError, KeyError, TypeError):
                raise ValueError(f'{name}: local {key} unavailable') from None
            if actual != expected:
                raise ValueError(f'{name}: {digest_key} mismatch')
            entry[key] = str(file)
        # A declared independence group is bound to the data, not its alias.
        group = item.get('group')
        if not isinstance(group, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', group):
            raise ValueError(f'{name}: public independence group required')
        for identity in (('hash', item['sha256']), ('group', group)):
            if identity in roles and roles[identity] != role:
                raise ValueError(f'{name}: training/development/test leakage')
            roles[identity] = role
        entries.append(entry)
    return entries


def write_report(path, text: str, entries: list[dict], *, protected=()):
    """Reports must never overwrite a manifest, a reference or an original."""
    inputs = [e[k] for e in entries for k in ('bin', 'reference')]
    atomic_write(path, text.encode('utf-8'), protected=(*inputs, *protected))
