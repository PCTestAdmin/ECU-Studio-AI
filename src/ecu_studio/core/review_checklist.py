"""Review checklist: which detected maps a person should check first, and why.

Every unconfirmed detection (code/structure or data pattern) gets reasons and a
score; definitions only appear when the fusion check found a contradiction or a
plausibility warning for them. Higher score = a human decision matters more:

  contradiction with a definition      5   (detection or definition is wrong)
  definition plausibility warning      4
  sign not proven by code              3   (other reading listed)
  axes missing / not monotone          2
  measured hit rate below 60 %         2   (evidence class "Vermutung")
  hit rate of the evidence not measured 1
  size (up to 1 for 256 cells)         ≤1
  shares an axis with other maps       .5  (one check informs the linked maps)

Decisions are explicit: confirming marks a map as checked by the user
(``verified``); rejecting removes it and records the rejection in the project's
review log, so a new scan does not offer the same table again. Nothing here is
sent anywhere or used for training: confirmed maps only become local references
when the user adds them to the local library.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime
import math
from .fusion import layer_of
from .model import MapDefinition

DECISIONS = ('bestätigt', 'abgelehnt')
LEVELS = ((5., 'hoch'), (2., 'mittel'), (0., 'niedrig'))


@dataclass
class ReviewItem:
    map: MapDefinition
    score: float
    reasons: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    @property
    def priority(self) -> str:
        return next(name for limit, name in LEVELS if self.score >= limit)


def _monotone(axis) -> bool:
    steps = [b - a for a, b in zip(axis, axis[1:])]
    return all(d > 0 for d in steps) or all(d < 0 for d in steps)


def table_key(m: MapDefinition) -> tuple:
    """Same table regardless of orientation: start, cell count per side, cell width."""
    return m.offset, tuple(sorted((m.rows, m.cols))), m.width


def checklist(maps: list[MapDefinition], *, conflicts: dict[int, list[str]] | None = None,
              definition_warnings: dict[str, list[str]] | None = None) -> list[ReviewItem]:
    """Prioritised review items, highest score first.

    ``conflicts``: offset -> conflict texts (fusion report). ``definition_warnings``:
    map name -> warnings (fusion report).
    """
    conflicts = conflicts or {}
    definition_warnings = definition_warnings or {}
    shared: dict[int, list[MapDefinition]] = {}
    for m in maps:
        for off in {m.axis_x_offset, m.axis_y_offset} - {None}:
            shared.setdefault(off, []).append(m)
    items = []
    for m in maps:
        if m.verified:
            continue
        layer = layer_of(m)
        reasons, score = [], 0.
        hits = [t for off, texts in conflicts.items() if m.offset <= off < m.offset + m.length for t in texts]
        if hits:
            score += 5
            reasons.append('Widerspruch zwischen Erkennung und Definition: ' + hits[0]
                           + (f' (+{len(hits) - 1} weitere)' if len(hits) > 1 else ''))
        warnings = definition_warnings.get(m.name, [])
        if warnings:
            score += 4
            reasons.append('Definitionsprüfung: ' + '; '.join(warnings))
        if layer == 1 and not reasons:
            continue                     # unremarkable definitions are not part of the checklist
        if m.dtype_alternatives:
            score += 3
            reasons.append(f'Datentyp nicht belegt: {m.dtype} ist die glattere Lesart, ebenfalls möglich: '
                           + ', '.join(m.dtype_alternatives))
        if layer > 1:
            two_d = m.rows > 1 and m.cols > 1
            if not m.axes_x or (two_d and not m.axes_y):
                score += 2
                reasons.append('Achsen fehlen' if not m.axes_x else 'Y-Achse fehlt')
            elif any(len(a) > 1 and all(map(math.isfinite, a)) and not _monotone(a) for a in (m.axes_x, m.axes_y)):
                score += 2
                reasons.append('Achse nicht streng monoton')
            if m.calibrated_rate is None:
                score += 1
                reasons.append('Trefferquote dieser Beweisart nicht gemessen')
            elif m.calibrated_rate < .6:
                score += 2
                reasons.append(f'Vermutung: gemessene Trefferquote {m.calibrated_rate:.0%}')
            if not reasons:
                reasons.append('Automatisch erkannt, noch nicht geprüft')
        score += min(1., m.rows * m.cols / 256)
        links = []
        for name, off in (('X', m.axis_x_offset), ('Y', m.axis_y_offset)):
            others = [o for o in shared.get(off, []) if o is not m]
            if others:
                score += .5
                links.append(f'{name}-Achse @ 0x{off:X} gemeinsam mit {len(others)} weiteren: '
                             + ', '.join(o.name for o in others[:3]) + (' …' if len(others) > 3 else ''))
        items.append(ReviewItem(m, round(score, 2), reasons, links))
    items.sort(key=lambda i: (-i.score, i.map.offset))
    return items


def decision(m: MapDefinition, verdict: str, reason: str = '') -> dict:
    """A review log entry (stored in the project, never the firmware)."""
    if verdict not in DECISIONS:
        raise ValueError(f'Unbekannte Entscheidung: {verdict}')
    return {'offset': m.offset, 'rows': m.rows, 'cols': m.cols, 'dtype': m.dtype, 'endian': m.endian,
            'name': m.name, 'source': m.source, 'decision': verdict, 'reason': reason.strip(),
            'at': datetime.datetime.now().isoformat(timespec='seconds')}


def validate_log(log) -> list[dict]:
    if not isinstance(log, list):
        raise ValueError('Ungültiges Prüfprotokoll im Projekt')
    out = []
    for e in log:
        if (not isinstance(e, dict) or e.get('decision') not in DECISIONS
                or not all(isinstance(e.get(k), int) and e[k] >= 0 for k in ('offset', 'rows', 'cols'))
                or not isinstance(e.get('dtype'), str)):
            raise ValueError('Ungültiger Eintrag im Prüfprotokoll')
        out.append(dict(e))
    return out


def rejected_keys(log: list[dict]) -> set[tuple]:
    """Tables the user rejected; the latest decision per table counts."""
    state = {}
    for e in log:
        width = MapDefinition('x', 0, rows=1, cols=1, dtype=e['dtype']).width
        state[(e['offset'], tuple(sorted((e['rows'], e['cols']))), width)] = e['decision']
    return {k for k, v in state.items() if v == 'abgelehnt'}


def is_rejected(m: MapDefinition, keys: set[tuple]) -> bool:
    return table_key(m) in keys
