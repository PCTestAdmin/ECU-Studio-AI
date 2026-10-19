"""Explicit, validated Intel HEX / S-record -> BIN workflow.

This is a conversion, not an ECU checksum or memory-layout verifier.
Sparse holes are never filled without an explicit choice; a sidecar records
which portions were present and which were synthetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

from .records import MemoryImage, read_memory_file
from ..core.addressing import AddressSegment, validate_segments


@dataclass(frozen=True)
class ImportResult:
    destination: Path
    manifest: Path
    size: int
    sha256: str
    gap_bytes: int
    base_address: int


def describe_memory_image(image: MemoryImage) -> dict:
    return {
        'format': image.format,
        'base_address': image.start,
        'end_exclusive': image.end,
        'payload_bytes': image.payload_bytes,
        'gap_bytes': image.gap_bytes,
        'segments': [{'ecu_start': a, 'ecu_end_exclusive': b,
                      'binary_offset': a-image.start} for a,b in image.segments],
        'entry_address': image.entry_address,
    }


def convert_to_binary(source: str | Path, destination: str | Path, *, fill: int | None = None) -> ImportResult:
    src, dst = Path(source), Path(destination)
    if src.resolve() == dst.resolve():
        raise ValueError('Quell- und Zieldatei dürfen nicht identisch sein')
    img = read_memory_file(str(src))
    data = img.to_binary(fill=fill)
    if not dst.parent.is_dir():
        raise ValueError('Zielordner existiert nicht')
    manifest = dst.with_name(dst.name + '.memory.json')
    if dst.exists() or manifest.exists():
        raise FileExistsError('Ziel-BIN oder Speichersegment-Protokoll existiert bereits')
    details = describe_memory_image(img)
    details.update({
        'source_name': src.name,
        'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
        'binary_sha256': hashlib.sha256(data).hexdigest(),
        'filler': fill if img.gap_bytes else None,
        'notice': 'Gefüllte Speicherlücken enthalten keine originalen ECU-Daten. Nicht flash-validiert.',
    })
    created_dst=False
    created_manifest=False
    try:
        with dst.open('xb') as fp:
            created_dst=True
            fp.write(data)
        if dst.read_bytes() != data:
            raise IOError('Verifikation der importierten BIN fehlgeschlagen')
        with manifest.open('x', encoding='utf-8') as fp:
            created_manifest=True
            json.dump(details,fp,ensure_ascii=False,indent=2)
    except Exception:
        if created_dst:dst.unlink(missing_ok=True)
        if created_manifest:manifest.unlink(missing_ok=True)
        raise
    return ImportResult(dst,manifest,len(data),details['binary_sha256'],img.gap_bytes,img.start)


def read_import_segments(binary_path: str | Path) -> list[AddressSegment]:
    """Load only a same-BIN-SHA-256 mapping created by our converter.

    Never infer an ECU layout from an unverified or mismatched sidecar.
    The returned segments are still unverified against actual ECU software.
    """
    path=Path(binary_path)
    manifest=path.with_name(path.name+'.memory.json')
    if not manifest.is_file():return []
    if manifest.stat().st_size > 1024*1024:
        raise ValueError('Speicherprotokoll zu groß')
    payload=json.loads(manifest.read_text(encoding='utf-8'))
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if payload.get('binary_sha256')!=actual:
        raise ValueError('Speicherprotokoll gehört nicht zu dieser BIN (SHA-256)')
    if payload.get('base_address') is None or not isinstance(payload.get('segments'),list):
        raise ValueError('Speicherprotokoll unvollständig')
    base=payload['base_address']
    if type(base) is not int or not 0<=base<=0xFFFFFFFF:
        raise ValueError('Ungültige ECU-Basisadresse')
    result=[]
    for entry in payload['segments']:
        if not isinstance(entry,dict):raise ValueError('Ungültige Segmentbeschreibung')
        a,b,start=entry.get('ecu_start'),entry.get('ecu_end_exclusive'),entry.get('binary_offset')
        if any(type(v) is not int for v in (a,b,start)) or a<base or b<=a or b>0x100000000:
            raise ValueError('Ungültiger Speichersegmentbereich')
        if start != a-base:
            raise ValueError('Inkonsistenter Speichersegment-Offset')
        result.append(AddressSegment(a,b-1,start))
    validate_segments(result,path.stat().st_size)
    return result
