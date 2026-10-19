"""Read-only integrity/definition audit for ECU calibration maps.

Proves internal decoding consistency; never claims a map is semantically or
physically correct without a firmware-matched external reference.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import csv
import math
from pathlib import Path

from .model import BinaryImage, MapDefinition
from .profiles import identify_profile


@dataclass
class MapQuality:
    name: str
    offset: str
    source: str
    dtype: str
    endian: str
    dimensions: str
    type_label: str
    evidence: str
    decoded_cells: int
    samples_checked: int
    decode_mismatches: int
    axes_x: str
    axes_y: str
    min_value: float | None
    max_value: float | None
    warnings: list[str]

    @property
    def status(self) -> str:
        return 'REJECT' if self.decode_mismatches else ('REVIEW' if self.warnings else 'DECODE_OK')


def _axis_status(axis: list[float], n: int) -> str:
    if not axis:
        return 'nicht vorhanden'
    if len(axis) != n or not all(math.isfinite(v) for v in axis):
        return 'ungültig/unvollständig'
    if len(axis) == 1:
        return '1 Wert'
    if any(axis[i] > axis[i+1] for i in range(len(axis)-1)):
        return 'nicht monoton (prüfen)'
    return 'vollständig'


def audit_map(image: BinaryImage, m: MapDefinition, *, sample_limit: int = 128) -> MapQuality:
    """Check raw layout independently via int.from_bytes.

    Explicitly does *not* prove map function or XDF variant validity.
    """
    if sample_limit < 2:
        raise ValueError('sample_limit muss mindestens 2 sein')
    m.validate(image.size)
    profile = identify_profile(image)
    warnings: list[str] = []
    if m.source in ('heuristic','manual','reference-shape') or m.kind in ('Unbekannt','Boost-Verdacht','AGR-Verdacht'):
        warnings.append('Kennfeldfunktion nicht durch eine passende Definition belegt')
    if m.equation:
        warnings.append('Nichtlineare Umrechnung: Darstellung schreibgeschützt; Werte fachlich gegen Referenz prüfen')
    if m.source == 'xdf':
        warnings.append('XDF-Software-/Patchvariante nicht kryptografisch mit BIN verifiziert')
    if m.source == 'a2l':
        warnings.append('A2L-Adresszuordnung muss zum Softwarestand passen')
    ax_x = _axis_status(m.axes_x, m.cols)
    ax_y = _axis_status(m.axes_y, m.rows)
    if m.cols > 1 and ax_x != 'vollständig':
        warnings.append('X-Achse: ' + ax_x)
    if m.rows > 1 and ax_y != 'vollständig':
        warnings.append('Y-Achse: ' + ax_y)
    if profile.identified and profile.cal_start is not None and profile.cal_end is not None:
        if not (profile.cal_start <= m.offset and m.offset+m.length <= profile.cal_end):
            warnings.append('Kennfeld außerhalb bekannten Kalibrierfensters')
    cells = m.rows*m.cols
    # Deterministic positions across the entire table, including corners.
    n = min(sample_limit, cells)
    indices = [0] if cells == 1 else sorted(set([0, cells-1, cells//2] +
              [round(i*(cells-1)/(n-1)) for i in range(n)]))
    mismatches = 0
    values=[]
    for index in indices:
        row, col = divmod(index, m.cols)
        start=m.cell_offset(row,col)
        payload=image.read(start,m.width)
        if m.dtype=='f32':
            import numpy as np
            independent=float(np.frombuffer(payload,dtype='>f4' if m.endian=='big' else '<f4')[0])
        else:
            independent=int.from_bytes(payload,byteorder=m.endian,signed=m.dtype.startswith('s'))
        actual=image.raw_value(m,row,col)
        physical=image.physical_value(m,row,col)
        expected=m.scale_raw(independent)
        if independent!=actual or not math.isclose(physical,expected,abs_tol=1e-8,rel_tol=1e-12):
            mismatches+=1
        if not math.isfinite(physical):
            mismatches+=1
        else:
            values.append(physical)
    return MapQuality(name=m.name,offset=f'0x{m.offset:08X}',source=m.source,
                      dtype=m.dtype,endian=m.endian,
                      dimensions=f'{m.rows}x{m.cols}',type_label=m.kind,
                      evidence=m.label_evidence[:220],decoded_cells=cells,
                      samples_checked=len(indices),decode_mismatches=mismatches,
                      axes_x=ax_x,axes_y=ax_y,
                      min_value=min(values) if values else None,
                      max_value=max(values) if values else None,
                      warnings=warnings)


def audit_catalog(image: BinaryImage, maps: list[MapDefinition], *, sample_limit: int=128) -> list[MapQuality]:
    result=[]
    for m in maps:
        try:
            result.append(audit_map(image,m,sample_limit=sample_limit))
        except (ValueError,IndexError,OverflowError) as exc:
            result.append(MapQuality(m.name,f'0x{m.offset:08X}',m.source,m.dtype,
                m.endian,f'{m.rows}x{m.cols}',m.kind,m.label_evidence[:220],
                m.rows*m.cols,0,1,'unbekannt','unbekannt',None,None,
                ['Definition nicht lesbar: '+str(exc)]))
    return result


def write_quality_csv(path: str | Path, reports: list[MapQuality]) -> None:
    columns=['name','offset','source','dtype','endian','dimensions','type_label',
             'evidence','status','decoded_cells','samples_checked',
             'decode_mismatches','axes_x','axes_y','min_value','max_value','warnings']
    with Path(path).open('w',encoding='utf-8-sig',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=columns,delimiter=';')
        writer.writeheader()
        for r in reports:
            row=asdict(r)
            row['status']=r.status
            row['warnings']=' | '.join(r.warnings)
            writer.writerow(row)
