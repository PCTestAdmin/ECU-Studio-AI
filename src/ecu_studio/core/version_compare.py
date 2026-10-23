"""Compare two software versions of one ECU and adopt confirmed definitions.

The source version has definitions (XDF/A2L/project); the target is a related
version. Maps are placed with the anchor alignment of core/name_transfer, which
needs evidence at the new place - an equal address alone is never a match. Each
source map gets one class:

- ``exakt``          same bytes at the shifted place
- ``strukturell``    same stored header (counts and axes), values changed
- ``wahrscheinlich`` similar values or only the same surroundings
- ``mehrdeutig``     the target place is claimed by more than one source map, or
                     conflicts with a different definition already in the target
- ``nicht zuordenbar`` no evidence in the target

Adoption copies definitions only (the BIN is never written). Exact and structural
matches can be adopted; probable ones only with explicit confirmation; ambiguous
and unmatched ones never. Measured rates of the evidence classes: name_transfer.MEASURED.
"""
from __future__ import annotations
import bisect
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import numpy as np
from .model import BinaryImage, MapDefinition
from .name_transfer import transfer_names

CLASSES = ('exakt', 'strukturell', 'wahrscheinlich', 'mehrdeutig', 'nicht zuordenbar')
_FROM_EVIDENCE = {'identisch': 'exakt', 'gleicher Kopf': 'strukturell', 'ähnliche Werte': 'wahrscheinlich',
                  'gleiche Umgebung': 'wahrscheinlich'}
FILTERS = ('Alle', 'Geändert', 'Unverändert', 'Nicht zugeordnet', 'Mehrdeutig')


@dataclass
class VersionPair:
    source_index: int
    source: MapDefinition
    target: MapDefinition | None
    match: str
    evidence: str
    shift: int | None = None
    changed_cells: int = 0
    total_cells: int = 0
    max_abs_raw: float = 0.
    max_abs_physical: float = 0.
    max_relative_percent: float | None = None
    axes: str = 'unbekannt'          # 'gleich' | 'abweichend/ungeprüft' | 'unbekannt'
    conflict: str = ''               # a different target definition at the same place

    @property
    def changed(self) -> bool:
        return self.target is not None and self.changed_cells > 0

    @property
    def adoptable(self) -> bool:
        return self.target is not None and self.match in ('exakt', 'strukturell', 'wahrscheinlich') and not self.conflict

    @property
    def needs_confirmation(self) -> bool:
        return self.match == 'wahrscheinlich'


def _differences(source: BinaryImage, target: BinaryImage, a: MapDefinition, b: MapDefinition) -> dict:
    # Original bytes on both sides: edits in either project must not decide the comparison.
    src, dst = BinaryImage(source.original), BinaryImage(target.original)
    raw_a, raw_b = src.matrix(a).astype(float), dst.matrix(b).astype(float)
    phys_a, phys_b = src.matrix(a, physical=True), dst.matrix(b, physical=True)
    delta = phys_b - phys_a
    changed = int(np.count_nonzero(raw_a != raw_b))
    nonzero = np.abs(phys_a) > 1e-12
    relative = (float(np.max(np.abs(delta[nonzero] / phys_a[nonzero])) * 100) if changed and nonzero.any() else None)
    return {'changed_cells': changed, 'total_cells': int(raw_a.size),
            'max_abs_raw': float(np.max(np.abs(raw_b - raw_a))) if raw_a.size else 0.,
            'max_abs_physical': float(np.max(np.abs(delta))) if delta.size else 0.,
            'max_relative_percent': round(relative, 3) if relative is not None else None}


def _axes_state(a: MapDefinition, b: MapDefinition) -> str:
    stored = [(at, bt) for at, bt in ((a.axis_x_offset, b.axis_x_offset), (a.axis_y_offset, b.axis_y_offset))
              if at is not None]
    if not stored:
        return 'unbekannt'
    return 'gleich' if all(bt is not None for _, bt in stored) else 'abweichend/ungeprüft'


def compare_versions(source: BinaryImage, source_maps: list[MapDefinition], target: BinaryImage,
                     target_maps: list[MapDefinition] = (), *, cancelled=None) -> dict:
    """Pairs for every source map plus the target maps no source map reaches."""
    transfers = transfer_names(source, target, source_maps, cancelled=cancelled)
    if cancelled and cancelled():
        return {'pairs': [], 'target_only': [], 'cancelled': True}
    by_source = {id(t.source): t for t in transfers}
    claims: dict[int, list[int]] = {}
    for i, m in enumerate(source_maps):
        t = by_source.get(id(m))
        if t is not None:
            claims.setdefault(t.target.offset, []).append(i)
    existing: dict[int, list[int]] = {}
    for j, m in enumerate(target_maps):
        existing.setdefault(m.offset, []).append(j)
    pairs, reached = [], set()
    for i, m in enumerate(source_maps):
        t = by_source.get(id(m))
        if t is None:
            pairs.append(VersionPair(i, m, None, 'nicht zuordenbar', 'Kein Beleg am Zielort'))
            continue
        moved = t.target
        match, evidence = _FROM_EVIDENCE[t.evidence], f'{t.evidence}, Verschiebung {t.shift:+d} Byte'
        if len(claims[moved.offset]) > 1:
            others = ', '.join(source_maps[k].name for k in claims[moved.offset] if k != i)
            match, evidence = 'mehrdeutig', evidence + f'; Zielort auch beansprucht von {others}'
        conflict = ''
        for j in existing.get(moved.offset, ()):
            reached.add(j)
            other = target_maps[j]
            if (other.rows, other.cols, other.dtype, other.endian) != (moved.rows, moved.cols, moved.dtype, moved.endian):
                conflict = (f'Zieldefinition {other.name}: {other.rows}×{other.cols} {other.dtype} {other.endian} '
                            f'statt {moved.rows}×{moved.cols} {moved.dtype} {moved.endian}')
                match = 'mehrdeutig'
        pair = VersionPair(i, m, moved, match, evidence, t.shift, axes=_axes_state(m, moved), conflict=conflict)
        try:
            for key, value in _differences(source, target, m, moved).items():
                setattr(pair, key, value)
        except (ValueError, IndexError) as exc:
            pair.conflict = pair.conflict or f'Werte nicht vergleichbar: {exc}'
        pairs.append(pair)
    # Target maps whose bytes no source map covers exist only in the target version.
    spans = sorted((p.target.offset, p.target.offset + p.target.length) for p in pairs if p.target is not None)
    starts = [s for s, _ in spans]
    target_only = []
    for j, m in enumerate(target_maps):
        if j in reached:
            continue
        k = bisect.bisect_right(starts, m.offset) - 1
        covered = any(spans[q][0] < m.offset + m.length and m.offset < spans[q][1] for q in (k, k + 1)
                      if 0 <= q < len(spans))
        if not covered:
            target_only.append(j)
    return {'pairs': pairs, 'target_only': target_only, 'cancelled': False,
            'counts': {c: sum(p.match == c for p in pairs) for c in CLASSES}}


def filter_pairs(pairs: list[VersionPair], choice: str) -> list[VersionPair]:
    if choice == 'Geändert':
        return [p for p in pairs if p.changed]
    if choice == 'Unverändert':
        return [p for p in pairs if p.target is not None and not p.changed and p.match != 'mehrdeutig']
    if choice == 'Nicht zugeordnet':
        return [p for p in pairs if p.match == 'nicht zuordenbar']
    if choice == 'Mehrdeutig':
        return [p for p in pairs if p.match == 'mehrdeutig']
    return list(pairs)


def adopt_definitions(pairs: list[VersionPair], target_maps: list[MapDefinition], *, source_label: str,
                      confirm_probable: bool = False) -> tuple[list[MapDefinition], list[dict]]:
    """New target definitions for the selected pairs, and one protocol line each.

    Raises before returning anything if one pair may not be adopted, so a
    selection is applied completely or not at all.
    """
    for p in pairs:
        if p.target is None or p.match in ('mehrdeutig', 'nicht zuordenbar'):
            raise ValueError(f'{p.source.name}: {p.match} – keine Übernahme')
        if p.conflict:
            raise ValueError(f'{p.source.name}: {p.conflict}')
        if p.needs_confirmation and not confirm_probable:
            raise ValueError(f'{p.source.name}: nur wahrscheinlich zugeordnet – ausdrückliche Bestätigung nötig')
    if len({p.target.offset for p in pairs}) != len(pairs):
        raise ValueError('Ein Zielort ist mehrfach ausgewählt')
    present = {(m.offset, m.rows, m.cols, m.dtype) for m in target_maps}
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    added, protocol = [], []
    for p in pairs:
        t = p.target
        if (t.offset, t.rows, t.cols, t.dtype) in present:
            continue
        note = (f'Aus Softwarestand {source_label} übernommen ({p.match}: {p.evidence}). '
                'Ungeprüft: Funktion und Skalierung am Zielstand bestätigen.')
        new = replace(t, source='transfer-proposed', verified=False, label_origin=f'Softwarestand-Abgleich · {p.match}',
                      label_evidence=note, notes=(p.source.notes + ' ' + note).strip())
        added.append(new)
        protocol.append({'utc': stamp, 'action': 'definition-adopted', 'name': t.name, 'source_label': source_label,
                         'source_offset': p.source.offset, 'target_offset': t.offset, 'match': p.match,
                         'evidence': p.evidence, 'changed_cells': p.changed_cells})
    return added, protocol
