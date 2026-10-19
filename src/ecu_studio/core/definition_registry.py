"""Local ECU/XDF pairing registry, independent of ECU manufacturer.

A prior user-approved pair of exact file hashes may be reproduced automatically.
Hash equality proves byte identity, NOT semantic correctness of the XDF.
Unseen firmware or a modified definition always requires explicit review.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import tempfile

from .model import BinaryImage
from .profiles import identify_profile, xdf_match_status

MAX_RECORDS=250
MAX_BYTES=1_000_000


@dataclass(frozen=True)
class Pairing:
    path: Path
    bin_sha256: str
    xdf_sha256: str
    accepted_for_same_bytes: bool = True


def _hash_file(path: Path) -> str:
    sha=hashlib.sha256()
    with path.open('rb') as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def _default_path() -> Path:
    return Path.home()/'.ecu_studio_ai'/'approved_xdf_pairs.json'


def _load(db: Path) -> list[dict]:
    if not db.is_file():return []
    if db.stat().st_size>MAX_BYTES:raise ValueError('Definitionsdatenbank zu groß')
    parsed=json.loads(db.read_text(encoding='utf8'))
    if parsed.get('format')!=1 or not isinstance(parsed.get('pairs'),list):
        raise ValueError('Ungültige Definitionsdatenbank')
    return parsed['pairs'][:MAX_RECORDS]


def remember_pair(image: BinaryImage, xdf: str|Path, db_path: str|Path|None=None) -> None:
    source=Path(xdf).expanduser().resolve(strict=True)
    if source.suffix.lower()!='.xdf' or not source.is_file() or source.stat().st_size>25*1024*1024:
        raise ValueError('Nur lokale XDF-Dateien bis 25 MiB')
    db=Path(db_path) if db_path is not None else _default_path()
    profile=identify_profile(image)
    status,_=xdf_match_status(profile,str(source))
    if status=='rejected':raise ValueError('Bekannt unpassende XDF kann nicht gemerkt werden')
    digest=_hash_file(source)
    pairs=[p for p in _load(db) if p.get('bin_sha256')!=image.digest]
    pairs.append({'bin_sha256':image.digest,'bin_size':image.size,'xdf_sha256':digest,
                  'xdf_path':str(source),'status':'user-approved',
                  'note':'Exakt dieselbe BIN und unveränderte, zuvor freigegebene XDF. '
                         'Dies ist keine technische Validierung der Definition.'})
    db.parent.mkdir(parents=True,exist_ok=True)
    # Crash-safe replace; no user ECU binary or metadata is copied to the DB.
    fd,tmp=tempfile.mkstemp(prefix='.xdf-reg-',dir=str(db.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf8') as fp:
            json.dump({'format':1,'pairs':pairs[-MAX_RECORDS:]},fp,indent=2)
            fp.flush();os.fsync(fp.fileno())
        os.replace(tmp,db)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def lookup_pair(image: BinaryImage, db_path: str|Path|None=None) -> Pairing|None:
    db=Path(db_path) if db_path is not None else _default_path()
    for pair in reversed(_load(db)):
        if pair.get('bin_sha256')!=image.digest or pair.get('bin_size')!=image.size:
            continue
        if pair.get('status')!='user-approved':continue
        candidate=Path(pair.get('xdf_path',''))
        if not candidate.is_file() or candidate.suffix.lower()!='.xdf':continue
        if candidate.stat().st_size>25*1024*1024:continue
        if _hash_file(candidate)!=pair.get('xdf_sha256'):continue
        status,_=xdf_match_status(identify_profile(image),str(candidate))
        if status=='rejected':continue
        return Pairing(candidate, image.digest,pair['xdf_sha256'])
    return None


def search_local_xdfs(image: BinaryImage, directories: list[str|Path],
                      *, max_files:int=500) -> list[tuple[Path,str,str]]:
    """Locate local candidates; only profile-backed matches are promoted.

    Never invent map names or auto-apply on unknown/ambiguous identities.
    Results include status so the UI can distinguish plausible from unknown.
    """
    profile=identify_profile(image)
    seen=set();out=[];checked=0
    for directory in directories:
        root=Path(directory).expanduser()
        if not root.is_dir():continue
        for file in sorted(root.rglob('*')):
            if checked>=max_files:break
            if file.suffix.lower()!='.xdf' or file.is_symlink() or not file.is_file():continue
            checked+=1
            if file.stat().st_size>25*1024*1024:continue
            resolved=file.resolve()
            if resolved in seen:continue
            seen.add(resolved)
            status,reason=xdf_match_status(profile,str(file))
            if status=='rejected':continue
            out.append((file,status,reason))
        if checked>=max_files:break
    return sorted(out,key=lambda item:(0 if item[1]=='plausible' else 1,str(item[0]).lower()))
