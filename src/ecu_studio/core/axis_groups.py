"""Shared-axis groups: maps whose X or Y breakpoints are read from the same stored axis.

A group is formed ONLY by a common axis storage address (``axis_x_offset`` /
``axis_y_offset``), never by look-alike values. Evidence classes, strongest first:

- ``definition``: every member comes from a definition (A2L/XDF) that places the
  axis at this address - for A2L COM_AXIS the shared AXIS_PTS object itself.
- ``structure``: at least one member is a detector candidate whose axis was read
  from this address (header record, code reference); structurally plausible,
  unverified.

A group whose members disagree on the number of points is kept but marked
``uncertain`` with the reason: one stored axis has one length.

Identical axis VALUES at different addresses are not a group. ``axis_value_hints``
lists them separately as hypotheses for the reviewer.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .model import BinaryImage, MapDefinition

DEFINITION_SOURCES = ('a2l', 'xdf', 'romraider', 'csv', 'definition', 'pack', 'exact-reference')
MIN_HINT_POINTS = 4   # shorter axes (0,1,2,3 ...) repeat everywhere by chance


@dataclass
class AxisGroup:
    axis_offset: int
    points: int                      # majority point count of the members
    members: list[tuple[int, str]]   # (map index, 'X' | 'Y')
    evidence: str                    # 'definition' | 'structure'
    reference: str = ''              # shared axis object name, if a definition names one
    issues: list[str] = field(default_factory=list)

    @property
    def uncertain(self) -> bool:
        return bool(self.issues)

    @property
    def indices(self) -> list[int]:
        return sorted({i for i, _ in self.members})

    def describe(self) -> str:
        name = f' {self.reference}' if self.reference else ''
        status = 'unsicher: ' + '; '.join(self.issues) if self.issues else (
            'aus Definition' if self.evidence == 'definition' else 'strukturell, ungeprüft')
        return (f'Gemeinsame Achse{name} @ 0x{self.axis_offset:X} ({self.points} Punkte), '
                f'{len(self.indices)} Kennfelder – {status}')


def _from_definition(m: MapDefinition) -> bool:
    src = m.source.lower()
    return any(src.startswith(s) for s in DEFINITION_SOURCES)


def axis_slots(m: MapDefinition):
    """(axis name, storage offset, point count, reference name) of the map's stored axes."""
    for name, at, count, ref in (('X', m.axis_x_offset, m.cols, m.axis_x_ref),
                                 ('Y', m.axis_y_offset, m.rows, m.axis_y_ref)):
        if at is not None and count > 1:
            yield name, at, count, ref


def shared_axis_groups(maps: list[MapDefinition]) -> list[AxisGroup]:
    """Groups of >= 2 distinct maps reading one axis from the same address, by address."""
    by_address: dict[int, list[tuple[int, str, int, str]]] = {}
    for i, m in enumerate(maps):
        for name, at, count, ref in axis_slots(m):
            by_address.setdefault(at, []).append((i, name, count, ref))
    groups = []
    for at in sorted(by_address):
        entries = by_address[at]
        if len({i for i, *_ in entries}) < 2:
            continue
        counts: dict[int, int] = {}
        for _, _, count, _ in entries:
            counts[count] = counts.get(count, 0) + 1
        points = max(counts, key=lambda c: (counts[c], c))
        refs = sorted({ref for *_, ref in entries if ref})
        evidence = 'definition' if all(_from_definition(maps[i]) for i, *_ in entries) else 'structure'
        issues = []
        if len(counts) > 1:
            issues.append('Punktzahlen widersprechen sich (' +
                          ', '.join(f'{c}×{n}' for c, n in sorted(counts.items())) + ')')
        if len(refs) > 1:
            issues.append('verschiedene Achsnamen an einer Adresse (' + ', '.join(refs) + ')')
        overlapping = [maps[i].name for i, *_ in entries if maps[i].offset <= at < maps[i].offset + maps[i].length]
        if overlapping:
            issues.append('Achse liegt im Wertebereich von ' + ', '.join(sorted(set(overlapping))[:3]))
        groups.append(AxisGroup(at, points, sorted((i, n) for i, n, _, _ in entries), evidence,
                                refs[0] if len(refs) == 1 else '', issues))
    return groups


def group_index(groups: list[AxisGroup]) -> dict[int, list[AxisGroup]]:
    """Map index -> the shared-axis groups it belongs to."""
    out: dict[int, list[AxisGroup]] = {}
    for g in groups:
        for i in g.indices:
            out.setdefault(i, []).append(g)
    return out


def axis_value_hints(maps: list[MapDefinition], groups: list[AxisGroup] | None = None) -> list[list[int]]:
    """Hypotheses only: maps with identical axis values but no common axis address.

    Pairs already in an address group are left out. Short or constant axes are
    ignored: equal values there are coincidence, not a relation.
    """
    grouped = {frozenset(g.indices) for g in (groups if groups is not None else shared_axis_groups(maps))}
    linked = {(i, j) for g in grouped for i in g for j in g}
    by_values: dict[tuple, list[int]] = {}
    for i, m in enumerate(maps):
        if min(m.rows, m.cols) < 2:
            continue
        for values in (m.axes_x, m.axes_y):
            if len(values) >= MIN_HINT_POINTS and len(set(values)) >= MIN_HINT_POINTS:
                by_values.setdefault(tuple(values), []).append(i)
    hints = []
    for members in by_values.values():
        members = sorted(set(members))
        if len(members) >= 2 and not all((a, b) in linked for a in members for b in members if a != b):
            if members not in hints:
                hints.append(members)
    return sorted(hints)


def relocated_axis(source: BinaryImage, target: BinaryImage, at: int | None, count: int,
                   shift: int) -> int | None:
    """Axis offset after moving a map by ``shift``; None unless the target confirms the bytes.

    The axis width is not stored, so 2 bytes per point are compared: conservative
    for 8-bit axes (more bytes must agree), exact for 16-bit ones.
    """
    if at is None:
        return None
    n, new = 2 * count, at + shift
    if at + n > source.size or new < 0 or new + n > target.size:
        return None
    return new if source.read(at, n) == target.read(new, n) else None


def _pairs(groups: list[AxisGroup], keep: set[int] | None = None) -> set[frozenset]:
    out = set()
    for g in groups:
        ids = [i for i in g.indices if keep is None or i in keep]
        out |= {frozenset((a, b)) for k, a in enumerate(ids) for b in ids[k + 1:]}
    return out


def compare_with_reference(found: list[MapDefinition], reference: list[MapDefinition]) -> dict:
    """How well detected axis addresses and groups agree with a definition.

    Only maps matched exactly (same start, width and size) are compared, so the
    numbers measure axis assignment, not map detection. ``axis_*`` counts stored
    axes of matched maps; ``pairs_*`` counts map pairs sharing an axis.
    """
    ref_key = {}
    for j, r in enumerate(reference):
        ref_key.setdefault((r.offset, r.width), []).append(j)
    match: dict[int, int] = {}
    for i, m in enumerate(found):
        for j in ref_key.get((m.offset, m.width), ()):
            r = reference[j]
            if {m.rows, m.cols} == {r.rows, r.cols}:
                match[i] = j
                break
    with_axes = correct = 0
    for i, j in match.items():
        m, r = found[i], reference[j]
        ref_at = {r.axis_x_offset, r.axis_y_offset} - {None}
        for at in (m.axis_x_offset, m.axis_y_offset):
            if at is None or not ref_at:
                continue
            with_axes += 1
            correct += at in ref_at
    # Group pairs restricted to matched maps, expressed in reference indices.
    found_pairs = {frozenset(match[i] for i in p) for p in _pairs(shared_axis_groups(found), set(match))}
    ref_pairs = _pairs(shared_axis_groups(reference), set(match.values()))
    agree = len(found_pairs & ref_pairs)
    return {'matched_maps': len(match), 'axis_with_address': with_axes, 'axis_address_correct': correct,
            'pairs_found': len(found_pairs), 'pairs_reference': len(ref_pairs), 'pairs_agree': agree,
            'pair_precision': round(agree / len(found_pairs), 4) if found_pairs else None,
            'pair_recall': round(agree / len(ref_pairs), 4) if ref_pairs else None}
