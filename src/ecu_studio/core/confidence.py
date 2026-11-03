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
