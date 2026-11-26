"""Evidence levels: what kind of evidence produced a candidate, not a probability.

Each automatic candidate belongs to an evidence class (code reference with
axes, code reference only, count-prefixed axis, smoothness only, ...) and,
through it, to one of three levels:

  Code-Beleg              the program code addresses the table (code/pointer layouts)
  Strukturbeleg           a stored record structure (header, axis record, count axis)
  Datenmuster-Vermutung   only the values look like a table (smoothness, row pitch)

The same layers decide the fusion with definitions (core/fusion.layer_of).
Definitions and maps confirmed by the user are not candidates and carry no
level here.

Until 1.18.2 each class showed a hit rate measured on reference firmware
(confidence_calibration.json). Several of those files have no documented
provenance or clearance, and the rates do not carry over to other ECU families,
so no percentage is shown any more; the historical table is kept in
docs/MODELLKARTE.md. No level is independently validated; program-code
evidence on TriCore (code calls) is experimental.
"""
from __future__ import annotations
import re
from pathlib import Path
from .model import MapDefinition
from .project_store import DETECTED_SOURCES

# Where tools/calibrate_confidence.py used to write; the application no longer reads it.
DATA = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'confidence_calibration.json'

CODE, STRUCTURE, DATA_PATTERN = 'Code-Beleg', 'Strukturbeleg', 'Datenmuster-Vermutung'
LEVELS = (CODE, STRUCTURE, DATA_PATTERN)
EXPERIMENTAL_CLASSES = ('code:call:', 'code:call-pre:', 'code:generic')
NOT_VALIDATED = 'Art des Belegs, keine Wahrscheinlichkeit; nicht unabhängig validiert.'
EXPERIMENTAL = 'TriCore-Codeerkennung experimentell.'


def evidence_class(m: MapDefinition) -> str:
    """Stable key describing what evidence produced a candidate."""
    layout = m.record_layout or 'raster'
    one_d = min(m.rows, m.cols) == 1
    if layout == 'candidate:code-reference':
        axes = 'axes2' if m.axes_x and m.axes_y else 'axis1' if m.axes_x else 'noaxes'
        return f"code:{'1d' if one_d else '2d'}:{axes}"
    if layout == 'candidate:code-call':
        # Own class: rates measured for C16x code references do not carry over.
        # Axes linked through earlier axis searches are weaker than axes in a5/a6.
        from .structure_scan import PRELOOKUP_ORIGIN
        kind = 'call-pre' if (m.label_origin or '').startswith(PRELOOKUP_ORIGIN) else 'call'
        return f"code:{kind}:{'1d' if one_d else '2d'}"
    if layout == 'candidate:code-reference-generic':
        return 'code:generic'
    if layout == 'candidate:pointer-descriptor':
        return 'pointer:descriptor'
    if layout == 'candidate:record-axis':
        return 'axis:record'
    if layout == 'candidate:curve-record':
        return 'curve:record'
    if layout == 'candidate:count-axis':
        return 'axis:count'
    if layout == 'candidate:nx,ny,x,y,z':
        from .axis_records import SHAPE_ONLY_ORIGIN
        return 'header:nxny:shape' if (m.label_origin or '').startswith(SHAPE_ONLY_ORIGIN) else 'header:nxny'
    if layout == 'candidate:row-pitch':
        return 'pitch'
    return 'raster'


def evidence_level(m: MapDefinition) -> str:
    """Level of an automatic candidate ('' for definitions, proposals and user-confirmed maps)."""
    if m.source != 'heuristic' or m.verified:
        return ''
    cls = evidence_class(m)
    if cls.startswith(('code:', 'pointer:')):
        return CODE
    if cls in ('pitch', 'raster'):
        return DATA_PATTERN
    return STRUCTURE


def is_experimental(m: MapDefinition) -> bool:
    return m.source == 'heuristic' and evidence_class(m).startswith(EXPERIMENTAL_CLASSES)


# Notes the record scan writes when the value width was not read from a smooth surface.
_WIDTH_GUESSED = ('Wertebreite = Achsenbreite (ungeprüft)', 'Wertebreite 1 Byte: hinter der 8-Bit-Lesart',
                  'weil der nächste Datensatzkopf genau danach beginnt (ungeprüft)')


WIDTH_OPEN = 'Wertebreite offen: auch eine 8-Bit-Tabelle'
ROUTINE_WIDTH = 'nur aus der Kennlinienroutine abgeleitet'
SIGN_FOLLOWS_BYTE_ORDER = True   # quality phase 5: an open byte order leaves the sign open as well (switch)
# Keys of the open questions about a data type, in the order they are shown (1.21.0).
WIDTH, SIGN, BYTE_ORDER, PATTERN, WIDTH_DERIVED = 'width', 'sign', 'byte-order', 'pattern', 'width-derived'

# What evidence would settle each open question (shown as "Fehlender Beleg"). Facts about the
# evidence, never a probability.
MISSING_EVIDENCE = {
    WIDTH: 'Wertebreite: ein Datensatzkopf direkt hinter der Tabelle, Programmcode mit Zugriffsbreite '
           'oder eine Definition (A2L/XDF) legt 8 oder 16 Bit fest.',
    SIGN: 'Vorzeichen: Programmcode, der die Werte vorzeichenbehaftet liest, oder eine Definition. Die Werte '
          'selbst entscheiden es nicht, weil das oberste Bit gesetzt ist und beide Lesarten zusammenhängende '
          'Werte ergeben.',
    BYTE_ORDER: 'Byte-Reihenfolge: eine klare Mehrheit der Datensätze dieses Abbilds, ein 16-Bit-Zähler im '
                'eigenen Datensatzkopf oder eine Definition.',
    PATTERN: 'Lage und Datentyp: weder Programmcode noch ein gespeicherter Datensatzkopf belegen die Tabelle; '
             'nur der Werteverlauf spricht dafür.',
    WIDTH_DERIVED: 'Wertebreite: nur aus dem Aufbau des Datensatzes abgeleitet; ein glatter Werteverlauf in dieser '
                   'Breite, Programmcode oder eine Definition fehlen.',
}


def type_doubts(m: MapDefinition) -> list[tuple[str, str]]:
    """Open questions about the data type of an unchecked candidate as (key, text), most important first.

    Definitions and checked maps carry none. Several can apply at once (e.g. sign and byte order).
    """
    if m.source != 'heuristic' or m.verified:
        return []
    from .axis_records import ENDIAN_OPEN, ENDIAN_OPEN_AXES
    notes = m.notes or ''
    out = []
    if WIDTH_OPEN in notes:
        out.append((WIDTH, 'Wertebreite nicht belegt (auch möglich: 8-Bit-Tabelle gleicher Form)'))
    if m.dtype_alternatives:
        out.append((SIGN, 'Vorzeichen nicht belegt (auch möglich: ' + ', '.join(m.dtype_alternatives) + ')'))
    if ENDIAN_OPEN in notes and m.width > 1:
        why = ('gegen die Mehrheit der Datensätze gelesen, beide Lesarten steigen' if ENDIAN_OPEN_AXES in notes
               else 'Datensätze dieses Abbilds uneinig')
        out.append((BYTE_ORDER, f'Byte-Reihenfolge nicht belegt ({why}; auch möglich: '
                    + ('little' if m.endian == 'big' else 'big') + ')'))
        if SIGN_FOLLOWS_BYTE_ORDER and SIGN not in {k for k, _ in out} and not m.dtype.startswith('f'):
            # Quality phase 5: which bit is the sign bit depends on the byte order; with the byte order open the
            # sign is open too (development data: 9 wrong signs newly marked for 13 right ones).
            out.append((SIGN, 'Vorzeichen nicht belegt (hängt von der offenen Byte-Reihenfolge ab)'))
    if evidence_level(m) == DATA_PATTERN:
        out.append((PATTERN, 'Datentyp nur aus der Glätte der Werte geschätzt'))
    elif not out and any(text in notes for text in _WIDTH_GUESSED):
        out.append((WIDTH_DERIVED, 'Wertebreite nur aus dem Datensatzaufbau abgeleitet'))
    if ROUTINE_WIDTH in notes and WIDTH not in {k for k, _ in out}:
        # Quality phase 5: the width of a code curve whose own values do not fill the gap to the next named
        # object comes from the curve routine only; shown even when the sign is open too.
        out.append((WIDTH_DERIVED, 'Wertebreite nur aus der Kennlinienroutine abgeleitet'))
    return out


def dtype_doubt(m: MapDefinition) -> str:
    """Why the data type of an unchecked candidate is not established ('' when it is).

    Shown next to the type in the list (1.21.0): a tuner must not edit a table in a
    width, sign or byte order the evidence does not fix. Definitions and checked maps carry no doubt.
    """
    return '; '.join(text for _, text in type_doubts(m))


def missing_evidence(m: MapDefinition) -> list[str]:
    """Which technical evidence would settle each open question of ``m`` (empty when nothing is open)."""
    return [MISSING_EVIDENCE[key] for key, _ in type_doubts(m)]


def overlapping(maps: list[MapDefinition]) -> dict[int, int]:
    """{index: number of other entries sharing bytes with it}, one sweep over the sorted spans (1.21.0)."""
    spans = sorted((m.offset, m.offset + max(m.length, 1), i) for i, m in enumerate(maps))
    counts: dict[int, int] = {}
    active: list[tuple[int, int]] = []          # (end, index) of spans still open
    for start, end, i in spans:
        active = [(e, j) for e, j in active if e > start]
        for _, j in active:
            counts[i] = counts.get(i, 0) + 1
            counts[j] = counts.get(j, 0) + 1
        active.append((end, i))
    return counts


def overlap_note(m: MapDefinition, maps: list[MapDefinition], limit: int = 5) -> str:
    """Which other entries share bytes with ``m`` (1.21.0): only one reading of these bytes can be right.

    Shown in the details so a tuner sees competing readings instead of one silently winning.
    """
    end = m.offset + m.length
    hits = [x for x in maps if x is not m and x.offset < end and m.offset < x.offset + x.length]
    if not hits:
        return ''
    def state(x):
        return 'ungeprüfter Vorschlag' if x.source in DETECTED_SOURCES and not x.verified else 'Definition/geprüft'
    names = ', '.join(f'{x.name} @0x{x.offset:X} ({state(x)})' for x in hits[:limit])
    more = f' (+{len(hits) - limit})' if len(hits) > limit else ''
    return (f'Überschneidung mit {len(hits)} weiteren Einträgen: {names}{more}. '
            'Nur eine Lesart dieser Bytes kann stimmen; vor Änderungen klären.')


def describe(m: MapDefinition) -> str:
    """One line for tooltips and notes, never a percentage."""
    level = evidence_level(m)
    if not level:
        return ''
    return (f'{level} (Beweisart {evidence_class(m)}): {NOT_VALIDATED}'
            + (' ' + EXPERIMENTAL if is_experimental(m) else ''))


# Notes written by 1.15.0-1.18.2 into candidates and saved with projects.
HISTORIC_RATE_NOTES = re.compile(
    r'\s*(Evidenzklasse \S+?: \d+% Treffer \(n=\d+, gemessen: [^)]*\) – [^.]+\.'
    r'|Lernmodell \(familienübergreifend geprüft\): Score [0-9.]+, gemessene Trefferquote dieses Score-Bereichs \d+%\.)')


def strip_historic_rates(text: str) -> str:
    return HISTORIC_RATE_NOTES.sub('', text or '').strip()


def apply_confidence(maps: list[MapDefinition], table: dict | None = None,
                     family: str | None = None) -> list[MapDefinition]:
    """Annotate automatic candidates with their evidence level (in place). ``table`` and ``family`` are accepted
    for compatibility with 1.18 callers and ignored: no measured rate is attached any more."""
    for m in maps:
        if m.source != 'heuristic':
            continue
        m.evidence_tier, m.calibrated_rate = evidence_level(m), None
        note = describe(m)
        m.notes = strip_historic_rates(m.notes)
        if note and note not in m.notes:
            m.notes = (m.notes + ' ' + note).strip()
    return maps
