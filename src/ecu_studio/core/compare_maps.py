"""Read-only ORI/MOD comparison with byte and logical cell attribution.

The map list is tied to the *opened* firmware; comparisons to other variants
must NOT be treated as validated semantic matches.
"""
from __future__ import annotations
import csv
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import struct
import math
import numpy as np
from .model import BinaryImage, MapDefinition, FORMATS
from .profiles import identify_profile


@dataclass
class MapDifference:
    name: str
    offset: int
    dimensions: str
    kind: str
    provenance: str
    changed_cells: int
    total_cells: int
    changed_bytes: int
    max_abs_raw_delta: int | float
    max_abs_physical_delta: float
    max_relative_percent: float | None
    status: str


def _spans(a: bytes, b: bytes) -> list[tuple[int,int]]:
    blocks=[]
    begin=None
    for i,(x,y) in enumerate(zip(a,b)):
        if x!=y and begin is None:begin=i
        elif x==y and begin is not None:
            blocks.append((begin,i-begin));begin=None
    if begin is not None:blocks.append((begin,len(a)-begin))
    return blocks


def compare_images(original: bytes|BinaryImage, modified: bytes|BinaryImage,
                   maps: list[MapDefinition] = ()) -> dict:
    """Exact common offset comparison; never modifies either input.

    A different-length file is rejected; no silent truncation. All changed bytes,
    not just the first 250, are counted. Map cells respect XDF strides/endianness.
    """
    a=original.materialize() if isinstance(original,BinaryImage) else bytes(original)
    b=modified.materialize() if isinstance(modified,BinaryImage) else bytes(modified)
    if len(a)!=len(b):raise ValueError('ORI und MOD haben unterschiedliche Länge; automatischer Offsetvergleich gesperrt')
    if len(a)>128*1024*1024:raise ValueError('Datei größer als 128 MiB')
    base=BinaryImage(a)
    # Deliberately don't treat a modified byte pattern as a brand/vehicle proof.
    old=identify_profile(base)
    new=identify_profile(BinaryImage(b))
    compatible=(old.identified and new.identified and
                old.family==new.family and
                (old.software_version or old.calibration_id)==(new.software_version or new.calibration_id))
    conflict=(old.identified and new.identified and not compatible)
    changed_mask=np.frombuffer(a,dtype=np.uint8)!=np.frombuffer(b,dtype=np.uint8)
    total_changed=int(np.count_nonzero(changed_mask))
    n_ranges=int(bool(len(changed_mask) and changed_mask[0])) + int(np.count_nonzero(changed_mask[1:] & ~changed_mask[:-1]))
    changes=[]
    if n_ranges and n_ranges<=25000:
        begin=np.flatnonzero(changed_mask & np.r_[True,~changed_mask[:-1]])
        end=np.flatnonzero(changed_mask & np.r_[~changed_mask[1:],True])
        changes=[(int(start),int(stop-start+1)) for start,stop in zip(begin,end)]
    # Avoid multi-million entry Python lists for highly fragmented files.
    range_list_capped=n_ranges>25000
    # At most the changed positions need ownership lookup; storing all map bytes
    # would waste RAM on firmware images with long padded strides.
    covered_changed=np.zeros(len(a),dtype=np.bool_)
    rows=[]
    cell_changes=[]
    capped=False
    max_logged_cells=20000
    for m in maps:
        m.validate(len(a))
        changed_cells=0; local_changed=set(); max_raw=0; max_physical=0.; max_relative=None
        code=('>' if m.endian=='big' else '<') + FORMATS[m.dtype][0]
        for row in range(m.rows):
            for col in range(m.cols):
                pos=m.cell_offset(row,col)
                original_bytes=a[pos:pos+m.width]
                modified_bytes=b[pos:pos+m.width]
                if original_bytes==modified_bytes:continue
                changed_cells+=1
                local_changed.update(x for x in range(pos,pos+m.width) if a[x]!=b[x])
                v1=struct.unpack(code,original_bytes)[0]
                v2=struct.unpack(code,modified_bytes)[0]
                if len(cell_changes)<max_logged_cells:
                    try:
                        physical_before=m.scale_raw(v1)
                        physical_after=m.scale_raw(v2)
                        if not (math.isfinite(physical_before) and math.isfinite(physical_after)):
                            physical_before=physical_after=None
                    except (ValueError,OverflowError,ZeroDivisionError):
                        physical_before=physical_after=None
                    cell_changes.append({'map_name':m.name,'map_offset':f'0x{m.offset:08X}',
                        'cell_offset':f'0x{pos:08X}','row':row,'col':col,
                        'raw_before':v1 if math.isfinite(v1) else None,'raw_after':v2 if math.isfinite(v2) else None,
                        'physical_before':physical_before,'physical_after':physical_after,
                        'unit':m.unit,'source':m.label_origin or m.source})
                else:capped=True
                if math.isfinite(v1) and math.isfinite(v2):max_raw=max(max_raw,abs(v2-v1))
                try:
                    p1=m.scale_raw(v1);p2=m.scale_raw(v2)
                    delta=abs(p2-p1)
                    if delta!=delta or delta==float('inf'):continue
                    max_physical=max(max_physical,delta)
                    if abs(p1)>1e-10:
                        rel=100*delta/abs(p1)
                        if rel!=float('inf'):
                            max_relative=max(max_relative or 0.,rel)
                except (ValueError,ZeroDivisionError,OverflowError):pass
        for x in local_changed:covered_changed[x]=True
        rows.append(MapDifference(m.name,m.offset,f'{m.rows}x{m.cols}',m.kind,
                    m.label_origin or m.source,changed_cells,m.rows*m.cols,len(local_changed),
                    max_raw,round(max_physical,5),round(max_relative,4) if max_relative is not None else None,
                    'GEÄNDERT' if changed_cells else 'GLEICH'))
    return {'original_sha256':hashlib.sha256(a).hexdigest(),
            'modified_sha256':hashlib.sha256(b).hexdigest(),
            'file_size':len(a),'changed_bytes':total_changed,
            'changed_ranges':changes,'changed_ranges_count':n_ranges,
            'changed_ranges_truncated':range_list_capped,
            'changed_bytes_outside_maps':int(np.count_nonzero(changed_mask & ~covered_changed)),
            'maps_changed':sum(m.changed_cells>0 for m in rows),
            'maps_total':len(rows),'identity_consistent':compatible,
            'identity_warning':('Abweichende ECU-/Softwaremarker: Kennfeldzuordnung für den Vergleich NICHT validiert.'
                                if conflict else 'Mindestens eine Firmware ohne überprüften ECU-Fingerprint: '
                                'Softwaregleichheit unbekannt; Kennfeldadressen NICHT bestätigt.'
                                if not compatible else 'ECU-Softwaremarker stimmen überein; '
                                'Kartenlayout/Checksumme weiterhin nicht bestätigt.'),
            'maps':[asdict(m) for m in rows],
            'cell_changes':cell_changes,'cell_changes_truncated':capped}


def export_map_comparison_csv(report: dict,path: str|Path) -> None:
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        fields=list(MapDifference.__dataclass_fields__)
        writer=csv.DictWriter(f,fieldnames=fields,delimiter=';')
        writer.writeheader();writer.writerows(report['maps'])


def export_cell_comparison_csv(report: dict,path: str|Path) -> None:
    """Export row/column-level changes for inspectable mapped cells.

    The report can be bounded to 20,000 entries. Never silently export partial
    content while claiming the CSV contains every changed cell.
    """
    if report['cell_changes_truncated']:
        raise ValueError('Zellprotokoll abgeschnitten; Export nicht vollständig. Vergleiche kleinere Bereiche.')
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        fields=['map_name','map_offset','cell_offset','row','col','raw_before','raw_after',
                'physical_before','physical_after','unit','source']
        writer=csv.DictWriter(f,fieldnames=fields,delimiter=';')
        writer.writeheader();writer.writerows(report['cell_changes'])
