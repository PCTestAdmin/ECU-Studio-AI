"""Change-impact and catalogue-health helpers for real calibration workflows.

Structural change counts and value deltas do NOT indicate engine safety.
"""
from __future__ import annotations
from dataclasses import dataclass
import csv
from pathlib import Path
import struct
from .model import BinaryImage, MapDefinition, FORMATS


@dataclass(frozen=True)
class MapImpact:
    name: str
    kind: str
    file_offset: int
    source: str
    verified: bool
    cells_changed: int
    bytes_changed: int
    max_abs_delta: float
    mean_abs_delta: float
    unit: str
    status: str


def measure_map_impact(image: BinaryImage, definition: MapDefinition) -> MapImpact:
    """Compare the current image against original values using each map's scale.

    Works for VALUE/CURVE/MAP represented as 1x1, 1xN, MxN contiguous arrays.
    """
    definition.validate(image.size)
    m = definition
    fmt, width, _, _ = FORMATS[m.dtype]
    pat = ('>' if m.endian == 'big' else '<') + fmt
    cells = differing = 0
    max_delta = sum_delta = 0.0
    modified_offsets: set[int] = set()
    for row in range(m.rows):
        for col in range(m.cols):
            pos = m.cell_offset(row,col)
            before_data = image.original[pos:pos+width]
            after_data = image.read(pos,width)
            if before_data == after_data:
                continue
            cells += 1
            modified_offsets.update(pos+i for i in range(width)
                                    if before_data[i] != after_data[i])
            before = struct.unpack(pat,before_data)[0]
            after = struct.unpack(pat,after_data)[0]
            delta = abs(m.scale_raw(after)-m.scale_raw(before))
            sum_delta += delta
            max_delta = max(max_delta,delta)
    differing = len(modified_offsets)
    if not cells:
        return MapImpact(m.name, m.kind, m.offset, m.source, m.verified,
                         0,0,0.0,0.0,m.unit,'unverändert')
    return MapImpact(m.name, m.kind, m.offset, m.source, m.verified,
                     cells, differing, max_delta, sum_delta/cells, m.unit,
                     'ungeprüft' if not m.verified else 'manuell verifiziert')


def measure_catalogue(image: BinaryImage, maps: list[MapDefinition],
                      *, limit: int = 30_000) -> list[MapImpact]:
    if len(maps) > limit:
        raise ValueError('Zu viele Kennfelder für synchronen Vergleich')
    return [measure_map_impact(image, m) for m in maps]


def uncovered_patches(image: BinaryImage, maps: list[MapDefinition]) -> tuple[int, int]:
    """Count edited bytes not used by *actual* map cells, excluding XDF padding."""
    ranges=[]
    sparse=set()
    for m in maps:
        if m.major_stride_bits in (0,m.width*8) and m.minor_stride_bits in (0,m.width*8):
            ranges.append((m.offset,m.offset+m.length))
        else:
            for r in range(m.rows):
                for c in range(m.cols):
                    p=m.cell_offset(r,c)
                    sparse.update(range(p,p+m.width))
    merged=[]
    for a,b in sorted(ranges):
        if merged and a<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else:merged.append((a,b))
    outside=idx=0
    for offset in sorted(image._patches):
        while idx<len(merged) and offset>=merged[idx][1]:idx+=1
        within=idx<len(merged) and offset>=merged[idx][0]
        if not within and offset not in sparse:outside+=1
    return outside,image.dirty_bytes


def export_impact_csv(path: str, rows: list[MapImpact]) -> None:
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Kennfeld', 'Typ', 'Dateioffset', 'Quelle', 'Manuell_geprüft',
                         'Geänderte_Zellen', 'Geänderte_Bytes', 'Max_Abweichung_phys',
                         'Mittel_Abweichung_phys', 'Einheit', 'Status'])
        for m in rows:
            writer.writerow([m.name,m.kind,f'0x{m.file_offset:X}',m.source,int(m.verified),
                             m.cells_changed,m.bytes_changed,f'{m.max_abs_delta:g}',
                             f'{m.mean_abs_delta:g}',m.unit,m.status])
