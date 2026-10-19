"""Durable, atomic local writes with a retained previous version."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path


def atomic_write(path: str | Path, data: bytes, *, backup=False, protected=(), overwrite=True) -> None:
    target = Path(path).resolve()
    if target.parent.name=='.ecustudio-originals' and target.suffix=='.bin' and hashlib.sha256(data).hexdigest()!=target.stem:
        raise ValueError('Hashadressiertes Originalbackup darf nicht verändert werden')
    for original in protected:
        if original and (target == Path(original).resolve() or
                         (target.exists() and Path(original).exists() and os.path.samefile(target, original))):
            raise ValueError('Originaldatei darf nicht überschrieben werden')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+target.name+'.', suffix='.tmp', dir=target.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if hashlib.sha256(tmp.read_bytes()).digest() != hashlib.sha256(data).digest():
            raise OSError('Speicherverifikation fehlgeschlagen')
        if backup and target.exists():
            atomic_write(target.with_name(target.name+'.bak'), target.read_bytes(), protected=protected)
        if overwrite:
            os.replace(tmp, target)
        else:
            # Same-directory hard link is an atomic create-if-absent operation.
            # A racing writer cannot turn a new-output workflow into overwrite.
            os.link(tmp,target)
    finally:
        tmp.unlink(missing_ok=True)


def canonical_digest(payload: dict) -> str:
    obj = {k:v for k,v in payload.items() if k != 'integrity_sha256'}
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
