"""Conservative ASAP2/A2L catalogue reader and explicitly anchored ECU-to-file linker.

This is deliberately a documented *subset*, not a full standards-conformant parser.
Unsupported layouts/conversions stay unlinked; never silently invent storage layout.
No evaluation of formulas, includes, or executable input.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterable

from .model import MapDefinition
from .intelligence import classify_metadata
from .addressing import AddressSegment, validate_segments, locate_range

TOKEN = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[^\s]+', re.DOTALL)
STORAGE = {'UBYTE': 'u8', 'SBYTE': 's8', 'UWORD': 'u16', 'SWORD': 's16',
           'ULONG': 'u32', 'SLONG': 's32'}
CAL_TYPES = {'VALUE', 'CURVE', 'MAP', 'CUBOID', 'VAL_BLK', 'ASCII', 'CUBE_4', 'CUBE_5'}


@dataclass
class Block:
    tag: str
    head: list[str] = field(default_factory=list)
    children: list['Block'] = field(default_factory=list)

    def first(self, tag: str) -> 'Block | None':
        return next((c for c in self.children if c.tag == tag), None)

    def each(self, tag: str) -> list['Block']:
        return [c for c in self.children if c.tag == tag]


def scan_blocks(source: str) -> Block:
    """Parse nested ASAP2 blocks without recursion or external file inclusions."""
    root = Block('__ROOT__')
    stack = [root]
    lex = (m.group(0) for m in TOKEN.finditer(source))
    count = 0
    for token in lex:
        if token.startswith('/*') or token.startswith('//'):
            continue
        count += 1
        if count > 3_000_000:
            raise ValueError('A2L überschreitet die Token-Grenze (3 Mio.)')
        if token == '/begin':
            try:
                name = next(lex)
            except StopIteration as exc:
                raise ValueError('A2L unvollständiger /begin-Block') from exc
            name = name.upper()
            if len(stack) >= 64:
                raise ValueError('A2L-Blöcke zu tief verschachtelt')
            sub = Block(name)
            stack[-1].children.append(sub)
            stack.append(sub)
        elif token == '/end':
            try:
                name = next(lex).upper()
            except StopIteration as exc:
                raise ValueError('A2L unvollständiger /end-Block') from exc
            if len(stack) < 2 or stack[-1].tag != name:
                raise ValueError(f'A2L /end {name} stimmt nicht mit /begin überein')
            stack.pop()
        else:
            stack[-1].head.append(token)
    if len(stack) != 1:
        raise ValueError('A2L enthält nicht geschlossene Blöcke')
    return root


def unquote(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        # Do not accidentally re-decode UTF-8 bytes as Latin-1 (umlauts in DAMOS).
        return re.sub(r'\\(["\\])', r'\1', value[1:-1])
    return value


def attr(block: Block, keyword: str, count: int = 1) -> list[str]:
    """Read ASAP2 item keywords, normally inline rather than nested /begin."""
    if keyword in block.head:
        i = block.head.index(keyword)
        return block.head[i+1:i+1+count]
    child = block.first(keyword)
    return child.head[:count] if child else []


def parse_num(value: str) -> int:
    return int(value, 0) if value.lower().startswith('0x') else int(value, 10)


def descendants(root: Block, tag: str) -> Iterable[Block]:
    pending = [root]
    while pending:
        parent = pending.pop()
        if parent.tag == tag:
            yield parent
        pending.extend(reversed(parent.children))


@dataclass
class Characteristic:
    name: str
    description: str
    cal_type: str
    address: int
    layout: str
    conversion: str
    dims: tuple[int, int]
    axes: list[tuple[str, str, int]] = field(default_factory=list)
    axis_descriptors: list[Block] = field(default_factory=list)


@dataclass
class LinkResult:
    maps: list[MapDefinition] = field(default_factory=list)
    total: int = 0
    unsupported: list[str] = field(default_factory=list)
    out_of_range: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unlinked: list[str] = field(default_factory=list)


@dataclass
class A2LCatalog:
    characteristics: list[Characteristic]
    layouts: dict[str, Block]
    conversions: dict[str, Block]
    byte_order: str = 'MSB_FIRST'
    warnings: list[str] = field(default_factory=list)

    def link(self, *, file_size: int, ecu_anchor: int = 0, file_anchor: int = 0,
             source: str = 'a2l', segments: list[AddressSegment] | None = None) -> LinkResult:
        """Map ECU addresses to file offsets using explicitly supplied anchor.

        file_offset = ecu_address - ecu_anchor + file_anchor
        This simple affine address rule MUST be reviewed for multi-segment images.
        """
        if file_size <= 0 or ecu_anchor < 0 or not 0 <= file_anchor < file_size:
            raise ValueError('Ungültiger BIN-Bereich oder Anker')
        if segments is not None:
            validate_segments(segments, file_size)
        result = LinkResult(total=len(self.characteristics))
        if self.byte_order not in ('MSB_FIRST', 'MSB_LAST'):
            raise ValueError(f'Byte-Reihenfolge {self.byte_order!r} nicht unterstützt – keine sichere Abbildung')
        endian = 'big' if self.byte_order == 'MSB_FIRST' else 'little'
        for ch in self.characteristics:
            prefix = f'{ch.name} (ECU 0x{ch.address:X})'
            layout = self.layouts.get(ch.layout)
            if layout is None:
                result.unsupported.append(prefix + ': RECORD_LAYOUT fehlt')
                continue
            value = attr(layout, 'FNC_VALUES', 4)
            if len(value) < 4 or value[1] not in STORAGE:
                result.unsupported.append(prefix + ': FNC_VALUES fehlt oder Datentyp nicht unterstützt')
                continue
            if any(a[0] == 'STD_AXIS' for a in ch.axes):
                result.unsupported.append(prefix + ': STD_AXIS (Speicherlayout ungeklärt)')
                continue
            # Require explicit row-major storage at the record start. Column-major,
            # embedded identification/reserved bytes and direct/indirect variants
            # need a dedicated layout engine; never invent element offsets.
            try:
                first_position = parse_num(value[0])
            except ValueError:
                first_position = -1
            if first_position != 1 or value[2] != 'ROW_DIR' or value[3] != 'DIRECT':
                result.unsupported.append(prefix + ': FNC_VALUES nicht direkt/zeilenweise ab Position 1')
                continue
            # Only unambiguous contiguous value arrays: inline axis storage, offsets,
            # dynamic counts and interleaved fields need a complete RECORD_LAYOUT engine.
            forbidden = ('NO_AXIS_PTS_X', 'NO_AXIS_PTS_Y', 'AXIS_PTS_X', 'AXIS_PTS_Y',
                         'OFFSET_X', 'OFFSET_Y', 'DIST_OP_X', 'DIST_OP_Y', 'IDENTIFICATION')
            unsupported_fields = [x for x in forbidden if x in layout.head or layout.first(x)]
            unsupported_fields += [c.tag for c in layout.children
                                   if c.tag not in {'FNC_VALUES', 'FIX_NO_AXIS_PTS_X', 'FIX_NO_AXIS_PTS_Y'}]
            if any(a[0] == 'STD_AXIS' for a in ch.axes):
                unsupported_fields.append('STD_AXIS (Speicherlayout ungeklärt)')
            if unsupported_fields:
                result.unsupported.append(prefix + ': Layout mit Inline-/variablen Feldern (' +
                                          ', '.join(sorted(set(unsupported_fields))) + ')')
                continue
            # This initial linker does not support interleaved/non-contiguous data.
            if any(x in value[2:] for x in ('COLUMN_DIR', 'ALTERNATE_WITH_X', 'ALTERNATE_WITH_Y', 'INCR')):
                result.unsupported.append(prefix + ': nicht-kontiguierliche Anordnung')
                continue
            dims = ch.dims
            if dims[0] < 1 or dims[1] < 1 or dims[0] > 512 or dims[1] > 512:
                result.unsupported.append(prefix + ': Dimensionen außerhalb 1–512')
                continue
            factor, bias, unit, convert_error = self._conversion(ch.conversion)
            if convert_error:
                result.unsupported.append(prefix + ': Umrechnung nicht unterstützt (' + convert_error + ')')
                continue
            required = dims[0] * dims[1] * {'u8': 1, 's8': 1, 'u16': 2, 's16': 2,
                                              'u32': 4, 's32': 4}[STORAGE[value[1]]]
            offset = (locate_range(ch.address, required, segments) if segments is not None
                      else ch.address - ecu_anchor + file_anchor)
            if offset is None:
                result.unlinked.append(prefix + ': liegt nicht vollständig in einem ECU-Segment')
                continue
            axes_x, axes_y = [], []
            for ax_i, descriptor in enumerate(ch.axis_descriptors[:2]):
                values, axis_issue = self._fixed_axis(descriptor)
                if axis_issue:
                    result.warnings.append(prefix + f': Achse {ax_i+1}: ' + axis_issue)
                else:
                    expected = dims[1] if ax_i == 0 else dims[0]
                    if len(values) == expected:
                        if ax_i == 0: axes_x = values
                        else: axes_y = values
                    else:
                        result.warnings.append(prefix + f': Achsenlänge {len(values)} statt {expected}')
            prediction = classify_metadata(ch.name, ch.description, unit,
                                           ' '.join(a[1] for a in ch.axes))
            m = MapDefinition(name=ch.name, offset=offset, rows=dims[0], cols=dims[1],
                              dtype=STORAGE[value[1]], endian=endian,
                              factor=factor, bias=bias, unit=unit,
                              kind=prediction.kind,
                              source=source, verified=False,
                              label_origin=prediction.origin,
                              label_evidence=prediction.evidence,
                              type_score=prediction.score,
                              type_alternatives=list(prediction.alternatives),
                              notes=f'A2L: {ch.description}; ECU 0x{ch.address:X}; '
                                    f'RECORD_LAYOUT {ch.layout}. ANKER prüfen!',
                              ecu_address=ch.address, record_layout=ch.layout,
                              axes_info=' | '.join(f'{a}:{b}({n})' for a,b,n in ch.axes),
                              axes_x=axes_x, axes_y=axes_y)
            try:
                m.validate(file_size)
            except ValueError:
                result.out_of_range.append(prefix + f': Dateioffset 0x{offset:X} außerhalb BIN')
                continue
            result.maps.append(m)
        return result

    def _fixed_axis(self, descriptor: Block) -> tuple[list[float], str]:
        """Safely interpret explicitly fixed ASAP2 axes, not stored/live axes.

        FIX_AXIS_PAR_DIST Offset Distance Count and FIX_AXIS_PAR Offset Shift
        Count. All other layouts return an explanation and no fabricated axis.
        """
        if len(descriptor.head) < 4 or descriptor.head[0] != 'FIX_AXIS':
            return [], 'Keine konstante FIX_AXIS'
        try:
            count = parse_num(descriptor.head[3])
        except ValueError:
            return [], 'Ungültige Achsenlänge'
        if not 1 <= count <= 512:
            return [], 'Achsenlänge nicht unterstützt'
        conversion = descriptor.head[2]
        factor, bias, _, issue = self._conversion(conversion)
        if issue:
            return [], 'Achsen-Umrechnung nicht unterstützt: ' + issue
        dist = attr(descriptor, 'FIX_AXIS_PAR_DIST', 3)
        shift = attr(descriptor, 'FIX_AXIS_PAR', 3)
        try:
            if len(dist) == 3:
                start, step, elements = (parse_num(x) for x in dist)
            elif len(shift) == 3:
                start, exponent, elements = (parse_num(x) for x in shift)
                if not 0 <= exponent <= 30:
                    return [], 'Shift außerhalb des unterstützten Bereichs'
                step = 1 << exponent
            else:
                return [], 'FIX_AXIS_PAR(_DIST) fehlt'
            if elements != count:
                return [], 'Deklarierte Achsenlänge ist widersprüchlich'
            return [float((start + i*step)*factor+bias) for i in range(count)], ''
        except (ValueError, OverflowError):
            return [], 'Ungültige feste Achse'

    def _conversion(self, name: str) -> tuple[float, float, str, str]:
        if not name or name == 'NO_COMPU_METHOD':
            return (1, 0, '', '')
        block = self.conversions.get(name)
        if block is None or len(block.head) < 5:
            return (1, 0, '', 'COMPU_METHOD unbekannt')
        unit = unquote(block.head[4])
        method = block.head[2]
        if method == 'IDENTICAL':
            return 1, 0, unit, ''
        if method == 'LINEAR':
            coeff = block.first('COEFFS_LINEAR')
            # In ASAP2, COEFFS_LINEAR often appears as a keyword in plain head tokens,
            # not a /begin block. Find both syntactic representations.
            if coeff and len(coeff.head) >= 2:
                raw = coeff.head[:2]
            else:
                try:
                    ix = block.head.index('COEFFS_LINEAR')
                    raw = block.head[ix+1:ix+3]
                except ValueError:
                    raw = []
            if len(raw) == 2:
                try:
                    scale, bias = float(raw[0]), float(raw[1])
                    if scale != 0 and all(abs(x) < 1e100 for x in (scale,bias)):
                        return scale, bias, unit, ''
                except ValueError:
                    pass
            return 1, 0, unit, 'ungültige COEFFS_LINEAR'
        return 1, 0, unit, method


# Labels are solely inferred from *explicit A2L symbol names and descriptions*.
# Raw values are never used to claim function names.
CATEGORIES = {
    'Ladedruck / Boost': ('boost', 'ladedruck', 'charge pressure', 'pcr_', 'plsol', 'intake manifold pressure'),
    'AGR / EGR': ('egr', 'agr', 'exhaust gas recirculation', 'abgasrueckfuehr', 'abgasrückführ'),
    'Drehmoment': ('torque', 'drehmoment', 'momentenbegrenz', 'kfmirl', 'kfmio'),
    'Einspritzung': ('injection', 'einspritz', 'duration', 'injekt'),
    'Zündung': ('ignition', 'zuend', 'zünd', 'spark angle'),
    'Luftmasse / Lambda': ('lambda', 'air mass', 'luftmasse', 'maf', 'afr'),
    'Turbo / VTG': ('wastegate', 'vtg', 'vnt', 'turbocharger', 'turbolader'),
    'Drehzahl / Leerlauf': ('idle speed', 'leerlauf', 'rpm limit', 'drehzahlbegrenz'),
    'Temperatur / Schutz': ('temperature', 'temperatur', 'thermal', 'schutz', 'protection'),
    'Kraftstoff / Druck': ('fuel pressure', 'kraftstoffdruck', 'railpressure'),
    'Diagnose': ('diagnostic', 'diagnose', 'dtc', 'fault code'),
    'Abgasnachbehandlung': ('scr', 'nox', 'particulate', 'dpf', 'partikelfilter'),
    'Fahrerwunsch / Pedal': ('fahrerwunsch', 'pedal', 'driver wish', 'accelerator position'),
    'Rauchbegrenzung': ('smoke limiter', 'smoke limitation', 'rauchbegrenz', 'lambda limiter'),
    'Raildruck / Railregelung': ('rail setpoint', 'rail pressure', 'raildruck', 'railregler'),
    'Einspritzbeginn / SOI': ('start of injection', 'einspritzbeginn', 'injection timing', 'soi_'),
    'Nockenwellenverstellung': ('camshaft', 'nockenwell', 'valve timing', 'vvt_'),
    'Drosselklappe': ('throttle', 'drosselklappe', 'wdk_'),
    'Klopfregelung': ('knock control', 'klopfregel', 'knock threshold'),
    'Geschwindigkeitsregelung': ('speed limiter', 'vehicle speed', 'geschwindigkeitsbegrenz'),
    'Regelung / PID': ('pid_', 'controller gain', 'reglerparameter', 'integral gain'),
    'Sensorik / Kennlinie': ('sensor characteristic', 'sensor curve', 'kennlinie', 'linearization'),
}


def classify_name(description: str) -> str:
    s = description.casefold()
    return classify_metadata(description).kind


def read_a2l(path: str) -> A2LCatalog:
    source = Path(path)
    if source.stat().st_size > 45 * 1024 * 1024:
        raise ValueError('A2L-Dateien über 45 MiB in Version 0.2 nicht unterstützt')
    payload = source.read_bytes()
    if payload.startswith(b'\xef\xbb\xbf'):
        text = payload.decode('utf-8-sig')
    else:
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError:
            text = payload.decode('cp1252')
    return parse_a2l(text)


def parse_a2l(source: str) -> A2LCatalog:
    root = scan_blocks(source)
    layouts = {c.head[0]: c for c in descendants(root, 'RECORD_LAYOUT') if c.head}
    conversions = {c.head[0]: c for c in descendants(root, 'COMPU_METHOD') if c.head}
    common = next(iter(descendants(root, 'MOD_COMMON')), None)
    byte_order = 'MSB_FIRST'
    if common and 'BYTE_ORDER' in common.head:
        idx = common.head.index('BYTE_ORDER')
        if idx+1 < len(common.head): byte_order = common.head[idx+1]
    chars = []
    warnings = []
    for block in descendants(root, 'CHARACTERISTIC'):
        h = block.head
        if len(h) < 8:
            warnings.append('CHARACTERISTIC mit unvollständigen Stammdaten übersprungen')
            continue
        try:
            name, desc, form, address, layout, conversion = (
                h[0], unquote(h[1]), h[2], parse_num(h[3]), h[4], h[6])
            if form not in CAL_TYPES:
                continue
            axes = []
            axis_descriptors = block.each('AXIS_DESCR')
            for item in axis_descriptors:
                if len(item.head) >= 4:
                    axes.append((item.head[0], item.head[2], parse_num(item.head[3])))
            matrix = attr(block, 'MATRIX_DIM', 3)
            if matrix:
                # MATRIX_DIM is stored inline: stop before the next keyword
                dims_raw = [parse_num(s) for s in matrix if re.fullmatch(r'(?:0[xX][0-9A-Fa-f]+|[0-9]+)', s)]
                if len(dims_raw) > 2 and dims_raw[2] != 1:
                    warnings.append(f'{name}: Mehrdimensionale Daten nicht unterstützt')
                    continue
                xdim = dims_raw[0]
                ydim = dims_raw[1] if len(dims_raw) > 1 else 1
            elif form == 'VALUE':
                xdim, ydim = 1, 1
            elif form == 'CURVE' and axes:
                xdim, ydim = axes[0][2], 1
            elif form == 'MAP' and len(axes) >= 2:
                xdim, ydim = axes[0][2], axes[1][2]
            else:
                warnings.append(f'{name}: Ohne eindeutige Dimensionen')
                continue
            if len(chars) >= 100_000:
                raise ValueError('Mehr als 100.000 CHARACTERISTIC-Einträge')
            chars.append(Characteristic(name, desc, form, address, layout, conversion,
                                        (ydim, xdim), axes, axis_descriptors))
        except (ValueError, IndexError) as exc:
            warnings.append(f'{h[0] if h else "?"}: {exc}')
    return A2LCatalog(chars, layouts, conversions, byte_order, warnings)
