"""Time-saving map catalogue and safe, atomic batch processing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import struct

from .model import BinaryImage, MapDefinition, FORMATS


@dataclass
class BatchPreview:
    before_min: float
    before_max: float
    after_min: float
    after_max: float
    changed_cells: int
    changed_bytes: int
    updates: list[tuple[int, bytes]]
    source_digest: str = ''
    revision: int | None = None
    before_bytes: tuple[tuple[int, bytes], ...] = ()


def plan_map_transform(image: BinaryImage, m: MapDefinition, *, mode: str, amount: float,
                       row_range: tuple[int, int] | None = None,
                       col_range: tuple[int, int] | None = None) -> BatchPreview:
    """Preview and validate *all* cells prior to making any change.

    mode 'add' uses physical units, 'percent' scales physical values, 'set' sets
    physical values. None is allowed to keep existing cells; no saturating writes.
    """
    m.validate(image.size)
    if mode not in ('add', 'percent', 'set') or not math.isfinite(amount):
        raise ValueError('Unbekannte Transformation oder ungültiger Betrag')
    r0, r1 = row_range or (0, m.rows)
    c0, c1 = col_range or (0, m.cols)
    if not (0 <= r0 < r1 <= m.rows and 0 <= c0 < c1 <= m.cols):
        raise ValueError('Ungültiger Ausschnitt')
    fmt, width, lower, upper = FORMATS[m.dtype]
    prefix = '>' if m.endian == 'big' else '<'
    updates = []
    before, after = [], []
    byte_changes = 0
    for r in range(r0, r1):
        for c in range(c0, c1):
            if m.equation:
                raise ValueError("Batch-Bearbeitung nichtlinearer XDF-Kennfelder gesperrt")
            physical = image.physical_value(m, r, c)
            next_physical = (physical + amount if mode == 'add' else
                             physical * (1+amount/100) if mode == 'percent' else amount)
            raw = m.raw_from_physical(next_physical)
            if not lower <= raw <= upper:
                raise ValueError(f'Zelle ({r},{c}): Rohwert {raw} liegt außerhalb {lower}..{upper}')
            offset = m.cell_offset(r,c)
            payload = struct.pack(prefix+fmt, raw)
            original = image.read(offset, width)
            if payload != original:
                byte_changes += sum(a != b for a, b in zip(original,payload))
                updates.append((offset,payload))
            before.append(physical)
            after.append(struct.unpack(prefix+fmt,payload)[0]*m.factor+m.bias)
    return BatchPreview(min(before),max(before),min(after),max(after),len(updates),byte_changes,updates,
                        image.digest, image.revision, tuple((p,image.read(p,len(b))) for p,b in updates))


def apply_batch(image: BinaryImage, preview: BatchPreview) -> None:
    """All-or-nothing batch write, represented by ONE undo record."""
    changes=[]
    if preview.source_digest and preview.source_digest != image.digest:
        raise ValueError('Vorschau gehört zu einer anderen Originaldatei')
    if preview.revision is not None and preview.revision != image.revision:
        raise ValueError('Vorschau ist veraltet – erneut berechnen')
    for pos, data in preview.before_bytes:
        if image.read(pos,len(data)) != data:
            raise ValueError('Vorschau ist veraltet – erneut berechnen')
    touched=set()
    for offset, payload in preview.updates:
        if offset < 0 or offset+len(payload) > image.size:
            raise ValueError('Batch-Eintrag außerhalb der Datei')
        for j, value in enumerate(payload):
            index=offset+j
            if index in touched:raise ValueError('Überlappende Batch-Edits')
            touched.add(index)
            prior=image.byte(index)
            if prior != value: changes.append((index,prior,value))
    if not changes:return
    image.commit(changes, label='Bereichsbearbeitung', expected_revision=preview.revision)


def catalogue_check(maps: list[MapDefinition], file_size: int) -> dict:
    """Identify definition conflicts and duplicate offsets without modifying input."""
    invalid=[]
    duplicates=[]
    overlaps=[]
    seen={}
    spans=[]
    for m in maps:
        try:m.validate(file_size)
        except ValueError as exc:
            invalid.append((m.name,str(exc)))
            continue
        key=(m.offset,m.rows,m.cols,m.dtype,m.endian)
        if key in seen:
            duplicates.append((seen[key],m.name))
        else:seen[key]=m.name
        spans.append((m.offset,m.offset+m.length,m.name))
    spans.sort()
    active=[]
    for start,end,name in spans:
        active=[(e,n) for e,n in active if e>start]
        for stop,other in active[:25]:
            if len(overlaps)<500:
                overlaps.append((other,name,start))
        active.append((end,name))
    return {'invalid':invalid,'duplicates':duplicates,'overlaps':overlaps}


def export_map_pack(path: str, maps: list[MapDefinition], image: BinaryImage) -> None:
    """Portable *own* JSON catalogue format, not proprietary WinOLS .kp format."""
    from .map_pack import make_pack, write_pack
    write_pack(path, make_pack(image, maps), protected=(image.path,))


def import_map_pack(path: str, *, image: BinaryImage, allow_mismatch: bool = False) -> tuple[list[MapDefinition],str]:
    from .map_pack import read_pack, preview_pack
    preview = preview_pack(read_pack(path), image, [])
    if preview.conflicts:
        raise ValueError('; '.join(preview.conflicts))
    return [MapDefinition(**r) for r in preview.records], 'Exakt gleicher Originalstand; ungeprüfte Definitionen'
