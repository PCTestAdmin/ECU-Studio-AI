"""Function membership of tables: evidence, relations, hypotheses with status (after 1.21.0-rc1, prototype).

A table's ECU function (e.g. the A2L FUNCTION that defines it) is never derived from values and
never invented. It comes only from

  - a definition: A2L FUNCTION / DEF_CHARACTERISTIC (``MapDefinition.function``) or the user;
  - a relation to tables whose function is known (anchors): the same stored axis, the same code
    routine, or direct neighbourhood in the calibration (no other object in between).

Status of a hypothesis (one per table, never a probability):

  Bestätigt       the table's own definition names the function and the table is checked
                  (user-verified definition or map)
  Stark gestützt  the table's own definition names the function, but its link to this file is
                  not checked; or at least two independent kinds of relation lead to anchors of
                  the same function and no relation leads to an anchor of another function
  Vermutet        one kind of relation leads to anchors of one function, none to another; or the
                  function came with a transferred name (transferred names stay unchecked)
  Unbekannt       no evidence, or relations lead to anchors of different functions (listed as
                  contradictions)

Only Bestätigt and Stark gestützt tables serve as anchors, so a hypothesis never feeds another
hypothesis. Each hypothesis lists its evidence with its source (provenance).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from .model import MapDefinition

CONFIRMED, STRONG, SUSPECTED, UNKNOWN = 'Bestätigt', 'Stark gestützt', 'Vermutet', 'Unbekannt'
STATUSES = (CONFIRMED, STRONG, SUSPECTED, UNKNOWN)
AXIS, ROUTINE, NEIGHBOUR = 'axis', 'routine', 'neighbour'
RELATION_LABELS = {AXIS: 'gleiche gespeicherte Achse', ROUTINE: 'gleiche Coderoutine',
                   NEIGHBOUR: 'direkter Nachbar im Speicher'}
NEIGHBOUR_GAP = 16      # bytes between two objects that still count as direct neighbours (alignment, counts)
AXIS_WINDOW = 1024      # an axis this close in front of the values belongs to the table's own record
TRANSFER_ORIGIN = 'Namensübertragung'   # label_origin of name_transfer proposals


@dataclass(frozen=True)
class Relation:
    a: int
    b: int
    kind: str
    detail: str = ''


@dataclass(frozen=True)
class Evidence:
    kind: str          # 'definition', 'transfer', or a relation kind
    text: str
    source: str        # where it comes from (definition file, code routine, axis address, ...)
    function: str = ''


@dataclass
class Hypothesis:
    index: int
    function: str
    status: str
    evidence: list[Evidence] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)

    def describe(self) -> str:
        head = f'Funktion: {self.function or "unbekannt"} ({self.status})'
        lines = [head] + ['  Beleg: ' + e.text + (f' [{e.source}]' if e.source else '') for e in self.evidence]
        lines += ['  Widerspruch: ' + c for c in self.contradictions]
        return '\n'.join(lines)


def _span(m: MapDefinition, own_axes=frozenset()) -> tuple[int, int]:
    """Bytes of the table's record: values plus header and axes stored right in front (``own_axes``:
    axis addresses no other table uses)."""
    start = m.offset if m.candidate_region_start is None else min(m.offset, m.candidate_region_start)
    for axis in (m.axis_x_offset, m.axis_y_offset):
        if axis is not None and axis in own_axes and m.offset - AXIS_WINDOW <= axis < m.offset:
            start = min(start, axis)
    return start, m.offset + m.length


def relations(maps: list[MapDefinition], graph: dict | None = None) -> list[Relation]:
    """Relations between tables: shared stored axis, same code routine (``graph`` from
    function_graph.build_function_graph), direct neighbours without another object in between."""
    out: list[Relation] = []
    by_axis: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(maps):
        for axis in {m.axis_x_offset, m.axis_y_offset} - {None}:
            by_axis[axis].append(i)
    # An axis inside a table's own record is used by that table only; shared means several users.
    own = frozenset(a for a, members in by_axis.items() if len(members) == 1)
    for axis, members in sorted(by_axis.items()):
        for k, a in enumerate(members):
            for b in members[k + 1:]:
                out.append(Relation(a, b, AXIS, f'Achse bei 0x{axis:X}'))
    for g in (graph or {}).get('groups', ()):
        members = sorted(g.members)
        for k, a in enumerate(members):
            for b in members[k + 1:]:
                out.append(Relation(a, b, ROUTINE, f'Routine 0x{g.routine_start:X}'))
    spans = sorted((*_span(m, own), i) for i, m in enumerate(maps))
    for (s1, e1, a), (s2, e2, b) in zip(spans, spans[1:]):
        if e1 <= s2 <= e1 + NEIGHBOUR_GAP:
            out.append(Relation(min(a, b), max(a, b), NEIGHBOUR, f'Abstand {s2 - e1} Byte'))
    return out


def _own(m: MapDefinition) -> tuple[str, str, Evidence] | None:
    """(function, status, evidence) from the table's own definition or transferred name."""
    if not m.function:
        return None
    source = m.function_source or m.source
    if (m.label_origin or '').startswith(TRANSFER_ORIGIN) or m.source.startswith('transfer'):
        return m.function, SUSPECTED, Evidence('transfer', 'mit dem übernommenen Namen übertragen (ungeprüft)',
                                               source, m.function)
    if m.verified:
        return m.function, CONFIRMED, Evidence('definition', 'eigene Definition, Tabelle geprüft', source, m.function)
    return m.function, STRONG, Evidence('definition', 'eigene Definition, Zuordnung zur Datei ungeprüft', source,
                                        m.function)


def identify(maps: list[MapDefinition], rels: list[Relation] | None = None, graph: dict | None = None
             ) -> list[Hypothesis]:
    """One hypothesis per table (same order as ``maps``)."""
    rels = relations(maps, graph) if rels is None else rels
    own = [_own(m) for m in maps]
    anchors = {i: o[0] for i, o in enumerate(own) if o and o[1] in (CONFIRMED, STRONG)}
    linked: dict[int, list[tuple[int, Relation]]] = defaultdict(list)
    for r in rels:
        linked[r.a].append((r.b, r))
        linked[r.b].append((r.a, r))
    out = []
    for i, m in enumerate(maps):
        votes: dict[str, set[str]] = defaultdict(set)
        evidence: dict[str, list[Evidence]] = defaultdict(list)
        for j, r in linked.get(i, ()):
            f = anchors.get(j)
            if not f:
                continue
            votes[f].add(r.kind)
            evidence[f].append(Evidence(r.kind, f'{RELATION_LABELS[r.kind]} wie „{maps[j].name}“ ({f})',
                                        r.detail, f))
        if own[i] and own[i][1] in (CONFIRMED, STRONG):
            f, status, ev = own[i]
            others = sorted(set(votes) - {f})
            contra = [f'{RELATION_LABELS[k]} mit Tabellen der Funktion {g}' for g in others for k in sorted(votes[g])]
            out.append(Hypothesis(i, f, status, [ev] + evidence.get(f, []), contra))
            continue
        if len(votes) > 1:
            contra = [f'{g}: ' + ', '.join(RELATION_LABELS[k] for k in sorted(kinds)) for g, kinds in sorted(votes.items())]
            ev = [e for f in sorted(evidence) for e in evidence[f]]
            if own[i]:
                ev.insert(0, own[i][2])
            out.append(Hypothesis(i, '', UNKNOWN, ev, ['Beziehungen zu Tabellen verschiedener Funktionen'] + contra))
            continue
        if votes:
            f, kinds = next(iter(votes.items()))
            status = STRONG if len(kinds) >= 2 else SUSPECTED
            ev = evidence[f]
            contra = []
            if own[i]:
                ev = [own[i][2]] + ev
                if own[i][0] != f:
                    contra = [f'übernommener Name gehört zu {own[i][0]}, Beziehungen zu {f}']
                    status, f = UNKNOWN, ''
            out.append(Hypothesis(i, f, status, ev, contra))
            continue
        if own[i]:
            f, status, ev = own[i]
            out.append(Hypothesis(i, f, status, [ev]))
            continue
        out.append(Hypothesis(i, '', UNKNOWN))
    return out


def groups(maps: list[MapDefinition], rels: list[Relation]) -> list[list[int]]:
    """Connected groups of related tables (relation graph), largest first; single tables left out.

    A group is a structural fact (shared axes, routine, neighbourhood), not a function: tables of
    different functions share axes. Shown as "related tables", never with a function name.
    """
    parent = list(range(len(maps)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in rels:
        if r.kind in (AXIS, ROUTINE):
            parent[find(r.a)] = find(r.b)
    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(maps)):
        members[find(i)].append(i)
    return sorted((v for v in members.values() if len(v) > 1), key=lambda v: (-len(v), v[0]))


def counts(hypotheses: list[Hypothesis]) -> dict[str, int]:
    out = dict.fromkeys(STATUSES, 0)
    for h in hypotheses:
        out[h.status] += 1
    return out


__all__ = ['CONFIRMED', 'STRONG', 'SUSPECTED', 'UNKNOWN', 'STATUSES', 'AXIS', 'ROUTINE', 'NEIGHBOUR', 'Relation',
           'Evidence', 'Hypothesis', 'relations', 'identify', 'groups', 'counts']
