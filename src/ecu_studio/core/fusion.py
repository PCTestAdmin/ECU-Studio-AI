"""Three recognition layers combined: definition, code/structure, data pattern/ML.

Layer 1 – definitions (XDF, A2L, CSV, RomRaider, bundled, manual, verified maps)
  are kept as they are. Each is checked against the firmware (bounds, readable
  axes, not erased). A detected table at exactly the same place, size and cell
  width confirms it independently ("bestätigt durch Programmcode/Struktur").
Layer 2 – code and structure evidence (interpolation calls, code references,
  header records, axis arrays, descriptors) fills gaps the definitions leave.
Layer 3 – data patterns and model proposals (row pitch, raster, ML/transfer
  proposals) only fill gaps; they never replace a layer 1 or layer 2 result.

Overlaps are never resolved silently: a lower layer that disagrees with a
higher one is dropped, and the disagreement is listed as a conflict with its
kind (start, size, cell width, sign, byte order). Candidates of the same
detection layer were already deduplicated by the scanner (a table and its
axes may share a record) and are kept as they are. Nothing is marked verified.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
from .model import BinaryImage, MapDefinition

DEFINITION_SOURCES = ('xdf', 'a2l', 'csv', 'romraider', 'bundled-definition', 'exact-reference', 'pack',
                      'manual', 'xdf-preview')
STRUCTURE_LAYOUTS = ('candidate:code-call', 'candidate:code-reference', 'candidate:code-reference-generic',
                     'candidate:pointer-descriptor', 'candidate:nx,ny,x,y,z', 'candidate:record-axis',
                     'candidate:curve-record', 'candidate:count-axis')
LAYER_NAMES = {1: 'Definition', 2: 'Code/Struktur', 3: 'Datenmuster/KI'}


def layer_of(m: MapDefinition) -> int:
    """1 = definition or confirmed by the user, 2 = code/structure evidence, 3 = data pattern or proposal."""
    if m.verified or m.source in DEFINITION_SOURCES or (m.label_origin or '').startswith('Manuelle'):
        return 1
    if m.source == 'heuristic' and m.record_layout in STRUCTURE_LAYOUTS:
        return 2
    return 3


@dataclass
class Conflict:
    offset: int
    kind: str              # 'Start', 'Größe', 'Zellbreite', 'Vorzeichen', 'Byte-Reihenfolge'
    kept: str              # name of the kept map
    kept_layer: int
    dropped: str           # description of the dropped reading
    dropped_layer: int
    detail: str

    def text(self) -> str:
        return (f'0x{self.offset:X}: {self.kind} – behalten {LAYER_NAMES[self.kept_layer]} „{self.kept}“, '
                f'verworfen {LAYER_NAMES[self.dropped_layer]} ({self.dropped}). {self.detail}')


@dataclass
class FusionResult:
    maps: list[MapDefinition]
    conflicts: list[Conflict] = field(default_factory=list)
    confirmed: list[MapDefinition] = field(default_factory=list)   # layer 1 maps found again by detection
    definition_warnings: dict[int, list[str]] = field(default_factory=dict)   # id(map) -> warnings
    counts: dict[str, int] = field(default_factory=dict)


def _span(m: MapDefinition) -> tuple[int, int]:
    """Cell data only: a record header or count prefix may hold the axis of the same table."""
    return m.offset, m.offset + m.length


def _overlap(a: MapDefinition, b: MapDefinition) -> bool:
    (s1, e1), (s2, e2) = _span(a), _span(b)
    return s1 < e2 and s2 < e1


def _same_table(a: MapDefinition, b: MapDefinition) -> bool:
    return a.offset == b.offset and a.width == b.width and {a.rows, a.cols} == {b.rows, b.cols}


def disagreement(kept: MapDefinition, other: MapDefinition) -> str:
    """The first property in which two overlapping readings differ."""
    if kept.offset != other.offset:
        return 'Start'
    if {kept.rows, kept.cols} != {other.rows, other.cols}:
        return 'Größe'
    if kept.width != other.width:
        return 'Zellbreite'
    if kept.width > 1 and kept.endian != other.endian:
        return 'Byte-Reihenfolge'
    if kept.dtype[:1] != other.dtype[:1]:
        return 'Vorzeichen'
    return 'Überlappung'


def sign_matters(image: BinaryImage, m: MapDefinition) -> bool:
    """True when the signed and unsigned readings of the cells differ (some cell has its top bit set)."""
    if m.dtype[1:] not in ('8', '16') or m.major_stride_bits or m.minor_stride_bits:
        return False
    raw = image.read(m.offset, m.length)
    top = raw if m.width == 1 else raw[1::2] if m.endian == 'little' else raw[0::2]
    return any(b & 0x80 for b in top)


def sign_proven(m: MapDefinition) -> bool:
    """Only the load instructions of an interpolation routine prove a sign; no alternative was left open."""
    return m.record_layout == 'candidate:code-call' and not m.dtype_alternatives


def definition_check(image: BinaryImage, m: MapDefinition) -> list[str]:
    """Plausibility of a definition against this firmware (layer 1 is kept regardless).

    Detects definitions for another software version: outside the file, axes
    changing direction, or table bytes erased (0xFF) / empty (0x00).
    """
    warnings = []
    try:
        m.validate(image.size)
    except (ValueError, IndexError) as exc:
        return [f'passt nicht zur Datei: {exc}']
    for name, axis, n in (('X', m.axes_x, m.cols), ('Y', m.axes_y, m.rows)):
        # A constant axis is an undefined one (XDF "autogen" axes are all zeros), not a wrong version.
        if n > 1 and axis and len(axis) == n and all(math.isfinite(v) for v in axis) and len(set(axis)) > 1:
            # Repeated breakpoints (padding of unused points) are common; a reversal is not.
            steps = [b - a for a, b in zip(axis, axis[1:])]
            if not (all(d >= 0 for d in steps) or all(d <= 0 for d in steps)):
                warnings.append(f'{name}-Achse nicht monoton')
    if m.length >= 8 and not (m.major_stride_bits or m.minor_stride_bits):
        raw = image.read(m.offset, m.length)
        if raw.count(0xFF) == len(raw):
            warnings.append('Tabellenbereich gelöscht (nur 0xFF)')
        elif raw.count(0) == len(raw):
            warnings.append('Tabellenbereich leer (nur 0x00)')
    return warnings


def fuse(image: BinaryImage, definitions: list[MapDefinition], detected: list[MapDefinition]) -> FusionResult:
    """Combine layer 1 definitions with detected candidates (layers 2 and 3).

    ``definitions`` stay unchanged and complete. ``detected`` candidates are
    taken in layer order (code/structure before data patterns), each only where
    nothing of a higher or equal earlier layer lies. Detected tables that equal
    a definition confirm it; all other overlaps become conflicts.
    """
    result = FusionResult(maps=list(definitions))
    for m in definitions:
        warnings = definition_check(image, m)
        if warnings:
            result.definition_warnings[id(m)] = warnings
    kept: list[tuple[int, MapDefinition]] = [(layer_of(m), m) for m in definitions]
    confirmed_ids = set()
    order = sorted(detected, key=lambda m: (layer_of(m), m.offset))
    for m in order:
        layer = layer_of(m)
        hits = [(lk, k) for lk, k in kept if lk < layer and _overlap(m, k)]
        if not hits:
            kept.append((layer, m))
            result.maps.append(m)
            continue
        for lk, k in hits:
            if lk == 1 and layer > 1 and _same_table(m, k):
                if id(k) not in confirmed_ids:
                    confirmed_ids.add(id(k))
                    result.confirmed.append(k)
                # Same table, other cell type: a sign disagrees only when proven by code and visible in the values.
                kind = ('Byte-Reihenfolge' if k.width > 1 and k.endian != m.endian else
                        'Vorzeichen' if (k.dtype[:1] != m.dtype[:1] and sign_proven(m)
                                         and sign_matters(image, k)) else None)
                if kind:
                    result.conflicts.append(Conflict(
                        offset=k.offset, kind=kind, kept=k.name, kept_layer=lk,
                        dropped=f'{m.dtype} {m.endian}, {m.label_origin or m.source}', dropped_layer=layer,
                        detail=(f'Belegt: {k.dtype} {k.endian}. Lage und Größe stimmen überein; die Erkennung '
                                'widerspricht der Definition beim Datentyp: Definition und Firmware prüfen.')))
                continue
            kind = disagreement(k, m)
            result.conflicts.append(Conflict(
                offset=min(k.offset, m.offset), kind=kind, kept=k.name, kept_layer=lk,
                dropped=f'{m.rows}×{m.cols} {m.dtype} {m.endian} @ 0x{m.offset:X}, {m.label_origin or m.source}',
                dropped_layer=layer,
                detail=(f'Belegt: {k.rows}×{k.cols} {k.dtype} {k.endian} @ 0x{k.offset:X}.'
                        + (' Die Erkennung widerspricht der Definition: Definition und Firmware prüfen.'
                           if lk == 1 else ''))))
    by_layer = {1: 0, 2: 0, 3: 0}
    for m in result.maps:
        by_layer[layer_of(m)] += 1
    result.counts = {'definition': by_layer[1], 'structure': by_layer[2], 'pattern': by_layer[3],
                     'confirmed': len(result.confirmed), 'conflicts': len(result.conflicts),
                     'definition_warnings': len(result.definition_warnings)}
    return result


def annotate(result: FusionResult) -> None:
    """Write confirmations and definition warnings into the maps' notes (never sets ``verified``)."""
    for m in result.confirmed:
        note = 'Unabhängig bestätigt: Erkennung ohne Definition findet dieselbe Tabelle (Start, Größe, Zellbreite).'
        if note not in m.notes:
            m.notes = (m.notes + ' ' + note).strip()
    for m in result.maps:
        warnings = result.definition_warnings.get(id(m))
        if warnings:
            note = 'Definitionsprüfung: ' + '; '.join(warnings) + '.'
            if note not in m.notes:
                m.notes = (m.notes + ' ' + note).strip()
