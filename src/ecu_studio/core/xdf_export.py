"""TunerPro XDF export for the part of the format this project can also read back.

Written as XML XDF 1.70 (``XDFFORMAT``) with file offsets (base offset 0):

- tables (rows x cols > 1) as ``XDFTABLE`` with z data in ``EMBEDDEDDATA``
  (address, element size 8/16/32 bit, row/column count, flags signed=0x01,
  little-endian=0x02, column-major=0x04, strides in bits),
- 1x1 definitions as ``XDFCONSTANT``,
- scaling as ``MATH`` equation: the definition's own formula, else ``X*f+b``,
- units, description (notes) and folder as category.

Axes are written as fixed ``LABEL`` values (the physical breakpoints the app
knows). The app does not store an axis's data type and scaling, so a linked,
address-based axis cannot be written correctly; the labels show the right
breakpoints but do not follow later changes of the axis bytes - the export
report says so.

Not exported (listed with the reason): 32-bit floats (the import side of this
project does not accept TunerPro's float flag, so the result could not be
verified) and definitions that do not validate against the image.
``verify_roundtrip`` reads the written file with the project's own XDF importer
and compares every exported field.
"""
from __future__ import annotations
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from .model import BinaryImage, MapDefinition

FLAG_SIGNED, FLAG_LITTLE, FLAG_COLUMN_MAJOR = 0x01, 0x02, 0x04


@dataclass
class ExportReport:
    path: str = ''
    exported: int = 0
    tables: int = 0
    constants: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)     # (name, reason)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f'{self.exported} Definitionen exportiert ({self.tables} Tabellen, {self.constants} Konstanten).']
        if self.skipped:
            lines.append(f'{len(self.skipped)} nicht exportiert:')
            lines += [f'  • {name}: {reason}' for name, reason in self.skipped[:30]]
            if len(self.skipped) > 30:
                lines.append(f'  … und {len(self.skipped) - 30} weitere')
        lines += self.notes
        return '\n'.join(lines)


def _number(value: float) -> str:
    text = repr(float(value))
    return text[:-2] if text.endswith('.0') else text


def equation(m: MapDefinition) -> str:
    """TunerPro equation of the definition (own formula or affine X*f+b)."""
    if m.equation:
        return m.equation
    text = 'X' if m.factor == 1 else f'X*{_number(m.factor)}'
    if m.bias:
        text += f'+{_number(m.bias)}' if m.bias > 0 else f'-{_number(-m.bias)}'
    return text


def _flags(m: MapDefinition) -> int:
    return ((FLAG_SIGNED if m.dtype.startswith('s') else 0) | (FLAG_LITTLE if m.endian == 'little' else 0)
            | (FLAG_COLUMN_MAJOR if m.storage_order == 'column-major' else 0))


def _embedded(parent, m: MapDefinition, *, table: bool):
    attrs = {'mmedaddress': f'0x{m.offset:X}', 'mmedelementsizebits': str(m.width * 8),
             'mmedtypeflags': f'0x{_flags(m):02X}'}
    if table:
        attrs.update(mmedrowcount=str(m.rows), mmedcolcount=str(m.cols))
    if m.major_stride_bits:
        attrs['mmedmajorstridebits'] = str(m.major_stride_bits)
    if m.minor_stride_bits:
        attrs['mmedminorstridebits'] = str(m.minor_stride_bits)
    ET.SubElement(parent, 'EMBEDDEDDATA', attrs)


def _math(parent, text: str):
    node = ET.SubElement(parent, 'MATH', equation=text)
    ET.SubElement(node, 'VAR', id='X')


def _axis(table, axis_id: str, count: int, values: list[float], unit: str):
    axis = ET.SubElement(table, 'XDFAXIS', id=axis_id, uniqueid='0x0')
    ET.SubElement(axis, 'units').text = unit or ''
    ET.SubElement(axis, 'indexcount').text = str(count)
    ET.SubElement(axis, 'outputtype').text = '1'
    # Only known breakpoints become labels; an unknown axis stays an index
    # axis instead of inventing 0, 1, 2 ... as "values".
    if len(values) == count:
        for i, value in enumerate(values):
            ET.SubElement(axis, 'LABEL', index=str(i), value=_number(value))
    _math(axis, 'X')


def export_xdf(path: str | Path, image: BinaryImage, maps: list[MapDefinition], *, title: str = '') -> ExportReport:
    """Write ``maps`` as an XDF for ``image``; returns what was exported and what not (with reasons)."""
    report = ExportReport(path=str(path))
    root = ET.Element('XDFFORMAT', version='1.70')
    header = ET.SubElement(root, 'XDFHEADER')
    ET.SubElement(header, 'flags').text = '0x1'
    ET.SubElement(header, 'deftitle').text = title or 'ECU Studio AI Export'
    ET.SubElement(header, 'description').text = ('Exportiert aus ECU Studio AI. Adressen sind Dateioffsets '
                                                 '(Basis 0). Nur geprüfte Definitionen sind fachlich bestätigt.')
    ET.SubElement(header, 'BASEOFFSET', offset='0', subtract='0')
    ET.SubElement(header, 'DEFAULTS', datasizeinbits='8', sigdigits='4', outputtype='1', signed='0',
                  lsbfirst='0', float='0')
    ET.SubElement(header, 'REGION', type='0xFFFFFFFF', startaddress='0x0', size=f'0x{image.size:X}',
                  regionflags='0x0', name='Binary File', desc='Gesamte Datei')
    folders = sorted({m.folder for m in maps if m.folder})
    for i, name in enumerate(folders):
        ET.SubElement(header, 'CATEGORY', index=f'0x{i:X}', name=name)
    category = {name: i for i, name in enumerate(folders)}
    uid = 0x1000
    for m in maps:
        if m.dtype == 'f32':
            report.skipped.append((m.name, '32-Bit-Gleitkomma wird nicht exportiert (Rückimport nicht prüfbar)'))
            continue
        try:
            m.validate(image.size)
        except ValueError as exc:
            report.skipped.append((m.name, f'Definition ungültig: {exc}'))
            continue
        table = m.rows * m.cols > 1
        entry = ET.SubElement(root, 'XDFTABLE' if table else 'XDFCONSTANT', uniqueid=f'0x{uid:X}', flags='0x0')
        uid += 1
        ET.SubElement(entry, 'title').text = m.name
        if m.notes:
            ET.SubElement(entry, 'description').text = m.notes[:2000]
        if m.folder:
            # CATEGORYMEM is one-based in TunerPro XDFs (see the importer).
            ET.SubElement(entry, 'CATEGORYMEM', index='0', category=str(category[m.folder] + 1))
        if table:
            _axis(entry, 'x', m.cols, m.axes_x, m.axis_x_unit)
            _axis(entry, 'y', m.rows, m.axes_y, m.axis_y_unit)
            z = ET.SubElement(entry, 'XDFAXIS', id='z')
            _embedded(z, m, table=True)
            ET.SubElement(z, 'units').text = m.unit or ''
            ET.SubElement(z, 'outputtype').text = '1'
            _math(z, equation(m))
            report.tables += 1
        else:
            _embedded(entry, m, table=False)
            ET.SubElement(entry, 'units').text = m.unit or ''
            ET.SubElement(entry, 'outputtype').text = '1'
            _math(entry, equation(m))
            report.constants += 1
        report.exported += 1
    if report.tables:
        report.notes.append('Achsen als feste Stützstellen-Werte (LABEL): richtig für die aktuelle Datei, folgen '
                            'aber keiner späteren Änderung der Achsenbytes.')
    if any(not m.verified for m in maps):
        report.notes.append('Ungeprüfte Definitionen bleiben ungeprüft – der Export bestätigt nichts fachlich.')
    ET.indent(root)
    Path(path).write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8'))
    return report


COMPARED = ('offset', 'rows', 'cols', 'dtype', 'endian', 'unit', 'storage_order', 'major_stride_bits',
            'minor_stride_bits', 'axis_x_unit', 'axis_y_unit', 'folder')


def verify_roundtrip(path: str | Path, image: BinaryImage, maps: list[MapDefinition]) -> list[str]:
    """Differences between ``maps`` and the file read back by the project's XDF importer (empty = identical)."""
    from .xdf import read_xdf
    back = read_xdf(str(path), image)
    expected = [m for m in maps if m.dtype != 'f32']
    problems = []
    if len(back.maps) != len(expected):
        problems.append(f'{len(expected)} exportiert, {len(back.maps)} wieder eingelesen')
    for a, b in zip(expected, back.maps):
        if a.name != b.name:
            problems.append(f'{a.name}: Name eingelesen als {b.name!r}')
            continue
        for key in COMPARED:
            if getattr(a, key) != getattr(b, key):
                problems.append(f'{a.name}: {key} {getattr(a, key)!r} ≠ {getattr(b, key)!r}')
        if a.equation:
            if b.equation != a.equation:
                problems.append(f'{a.name}: Formel {a.equation!r} ≠ {b.equation!r}')
        elif not (math.isclose(a.factor, b.factor, rel_tol=1e-12) and math.isclose(a.bias, b.bias, abs_tol=1e-12)):
            problems.append(f'{a.name}: Skalierung {a.factor}/{a.bias} ≠ {b.factor}/{b.bias}')
        for which, count in (('x', a.cols), ('y', a.rows)):
            mine = getattr(a, f'axes_{which}')
            theirs = getattr(b, f'axes_{which}')
            if a.rows * a.cols > 1 and len(mine) == count and [round(v, 6) for v in mine] != [round(v, 6) for v in theirs]:
                problems.append(f'{a.name}: {which.upper()}-Achse weicht ab')
    return problems
