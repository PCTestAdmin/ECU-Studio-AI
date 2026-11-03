"""Review checklist: which detected maps a person should check first, and why.

Every unconfirmed detection (code/structure or data pattern) gets reasons and a
score; definitions only appear when the fusion check found a contradiction or a
plausibility warning for them. Higher score = a human decision matters more:

  contradiction with a definition      5   (detection or definition is wrong)
  definition plausibility warning      4
  sign not proven by code              3   (other reading listed)
  axes missing / changing direction    2
  data pattern only, no code/structure 2   (evidence level "Datenmuster-Vermutung")
  experimental evidence (TriCore code) 1
  size (up to 1 for 256 cells)         ≤1
  shares an axis with other maps       .5  (one check informs the linked maps)

Data-pattern guesses without a contradiction form their own group
(``ReviewItem.group``) after the evidenced finds; the dialog shows it
expanded and marked as guesses (on MS42/MS45 most exact finds are there) and
lets the user collapse it. Nothing is removed: the maps stay in the project
and the catalogue.

Decisions are explicit: confirming marks a map as checked by the user
(``verified``); rejecting removes it and records the rejection in the project's
review log, so a new scan does not offer the same table again. Every decision
can be withdrawn (``zurückgenommen``); the latest entry per table counts.

A rejection is bound to the firmware it was made on (SHA-256 of the original
file) and to the evidence layer of the rejected detection: it never applies to
another file, and a later detection with stronger evidence (code/structure
after a rejected data pattern) is offered again, marked as previously rejected.
Nothing here is sent anywhere or used for training: confirmed maps only become
local references when the user adds them to the local library.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime
import math
from .confidence import DATA_PATTERN, evidence_level, is_experimental
from .fusion import layer_of
from .model import MapDefinition

DECISIONS = ('bestätigt', 'abgelehnt', 'zurückgenommen')
GUESSES = 'Datenmuster-Vermutungen'
LEVELS = ((5., 'hoch'), (2., 'mittel'), (0., 'niedrig'))


@dataclass
class ReviewItem:
    map: MapDefinition
    score: float
    reasons: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    group: str = ''                  # GUESSES: data pattern only, shown collapsed

    @property
    def priority(self) -> str:
        return next(name for limit, name in LEVELS if self.score >= limit)


def _monotone(axis) -> bool:
    """No reversal of direction (repeated padding breakpoints are allowed, as in fusion.definition_check)."""
    steps = [b - a for a, b in zip(axis, axis[1:])]
    return all(d >= 0 for d in steps) or all(d <= 0 for d in steps)


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
                reasons.append('Achse nicht monoton')
            if evidence_level(m) == DATA_PATTERN:
                score += 2
                reasons.append('Datenmuster-Vermutung: weder Programmcode noch gespeicherte Struktur belegt die Tabelle')
            elif is_experimental(m):
                score += 1
                reasons.append('Beleg aus TriCore-Programmcode: experimentell, nicht unabhängig validiert')
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
        guess = evidence_level(m) == DATA_PATTERN and not hits and not warnings
        items.append(ReviewItem(m, round(score, 2), reasons, links, GUESSES if guess else ''))
    items.sort(key=lambda i: (-i.score, i.map.offset))
    return items


def decision(m: MapDefinition, verdict: str, reason: str = '', image_sha256: str | None = None) -> dict:
    """A review log entry (stored in the project, never the firmware).

    ``image_sha256`` binds the entry to the original file it was made on; ``layer``
    records the evidence layer of the decided map (1 definition/user, 2 code/structure,
    3 data pattern).
    """
    if verdict not in DECISIONS:
        raise ValueError(f'Unbekannte Entscheidung: {verdict}')
    entry = {'offset': m.offset, 'rows': m.rows, 'cols': m.cols, 'dtype': m.dtype, 'endian': m.endian,
             'name': m.name, 'source': m.source, 'layer': layer_of(m), 'decision': verdict,
             'reason': reason.strip(), 'at': datetime.datetime.now().isoformat(timespec='seconds')}
    if image_sha256:
        entry['image_sha256'] = image_sha256
    return entry


def entry_key(e: dict) -> tuple:
    width = MapDefinition('x', 0, rows=1, cols=1, dtype=e['dtype']).width
    return e['offset'], tuple(sorted((e['rows'], e['cols']))), width


def latest(log: list[dict], image_sha256: str | None = None) -> dict[tuple, dict]:
    """The latest decision per table; entries made on another file are ignored."""
    state = {}
    for e in log:
        if image_sha256 and e.get('image_sha256') not in (None, image_sha256):
            continue
        state[entry_key(e)] = e
    return state


def validate_log(log) -> list[dict]:
    if not isinstance(log, list):
        raise ValueError('Ungültiges Prüfprotokoll im Projekt')
    out = []
    for e in log:
        if (not isinstance(e, dict) or e.get('decision') not in DECISIONS
                or not all(isinstance(e.get(k), int) and e[k] >= 0 for k in ('offset', 'rows', 'cols'))
                or not isinstance(e.get('dtype'), str)
                or e.get('layer', 3) not in (1, 2, 3)
                or not isinstance(e.get('image_sha256', ''), str)):
            raise ValueError('Ungültiger Eintrag im Prüfprotokoll')
        out.append(dict(e))
    return out


def rejected_keys(log: list[dict], image_sha256: str | None = None) -> dict[tuple, int]:
    """{table: evidence layer of the rejected detection} for tables whose latest decision is a rejection.

    With ``image_sha256`` only decisions made on that file count (entries without a
    hash come from projects, which are bound to their file anyway).
    """
    return {k: e.get('layer', 3) for k, e in latest(log, image_sha256).items() if e['decision'] == 'abgelehnt'}


def is_rejected(m: MapDefinition, keys: dict[tuple, int]) -> bool:
    """Rejected, and the new detection is not stronger than the rejected one."""
    layer = keys.get(table_key(m))
    return layer is not None and layer_of(m) >= layer


def rejected_before(m: MapDefinition, keys: dict[tuple, int]) -> bool:
    """Rejected once, but now found with stronger evidence: offer again with a note."""
    layer = keys.get(table_key(m))
    return layer is not None and layer_of(m) < layer
