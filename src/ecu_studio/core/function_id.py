"""Function membership of tables: evidence, relations, hypotheses with status (after 1.21.0-rc1, prototype).

A table's ECU function (e.g. the A2L FUNCTION that defines it) is never derived from values and
never invented. It comes only from

  - a definition: A2L FUNCTION / DEF_CHARACTERISTIC (``MapDefinition.function``) or the user;
  - a relation to tables whose function is known (anchors): the same stored axis, the same code
    routine, or direct neighbourhood in the calibration (no other object in between); from the
    program code (core/code_flow, TriCore): looked up by the same calling routine, the result of one
    table feeds the other, or both results go to the same RAM variable. Reading the same input
    variable is listed but never counts: tables of different functions share operating points.

Status of a hypothesis (one per table, never a probability):

  Bestätigt       the table's own definition names the function and the table is checked
                  (user-verified definition or map)
  Stark gestützt  the table's own definition names the function, but its link to this file is
                  not checked; or relations of at least two independent families (stored axis,
                  memory layout, program code) lead to anchors of the same function and no relation
                  leads to an anchor of another function
  Vermutet        relations of one family lead to anchors of one function, none to another; or the
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
CALLER, FLOW, SAME_RESULT, SHARED_INPUT = 'same-caller', 'flow', 'same-result', 'shared-input'   # core/code_flow
RELATION_LABELS = {AXIS: 'gleiche gespeicherte Achse', ROUTINE: 'gleiche Coderoutine',
                   NEIGHBOUR: 'direkter Nachbar im Speicher', CALLER: 'gleiche aufrufende Coderoutine',
                   FLOW: 'Ergebnis fließt in die andere Tabelle', SAME_RESULT: 'Ergebnis in derselben Variablen',
                   SHARED_INPUT: 'gleiche Eingangsgröße'}
# Independent sources of evidence: two relations of one family (e.g. same caller and same result
# variable, both from the same code) are one argument, not two.
FAMILY = {AXIS: 'Achse', NEIGHBOUR: 'Speicherlage', ROUTINE: 'Programmcode', CALLER: 'Programmcode',
          FLOW: 'Programmcode', SAME_RESULT: 'Programmcode'}
CODE_EVIDENCE = (ROUTINE, CALLER, FLOW, SAME_RESULT)
# SHARED_INPUT never votes: development data, same A2L function for 166 of 538 such pairs (MSD80).
# FLOW is shown and groups, but does not vote (Schutzregel): same A2L function in 128 of 195 pairs (66 %),
# against 92 % for the same caller (development data, two full images per line).
VOTING = tuple(k for k in FAMILY if k != FLOW)
GROUPING = (AXIS, ROUTINE, CALLER, FLOW, SAME_RESULT)
# A direct neighbour shares the A2L function in 62 % of the pairs (MSD80) and caused almost all wrong
# assignments under hard splits (tools/function_benchmark, development data, 3 salts: MSD80 whole functions
# hidden at 50 %: 84 216 of 86 108 wrong). It votes only when anchors of ONE function enclose the table on
# both sides: wrong 86 108 -> 6 763 (function split), table split 50 %: precision 73.7 % -> 96.4 % (MSD80),
# 95.4 % -> 99.8 % (MEVD17.2); about half of the right assignments become "Unbekannt".
NEIGHBOUR_BOTH_SIDES = True
# A shared axis with at least two anchors of the function: no measured benefit (ablation), so not required.
AXIS_MIN_ANCHORS = 1
NEIGHBOUR_GAP = 16      # bytes between two objects that still count as direct neighbours (alignment, counts)
AXIS_WINDOW = 1024      # an axis this close in front of the values belongs to the table's own record
TRANSFER_ORIGIN = 'Namensübertragung'   # label_origin of name_transfer proposals


@dataclass(frozen=True)
class Relation:
    a: int
    b: int
    kind: str
    detail: str = ''
    evidence: object = None   # code_flow.CodeRelation for code relations (addresses, method, open points)


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


def code_links(maps: list[MapDefinition], code_relations) -> list[Relation]:
    """Code relations (core/code_flow.CodeRelation, between table offsets) as relations between ``maps``."""
    index: dict[int, int] = {}
    for i, m in enumerate(maps):
        index.setdefault(m.offset, i)
    out = []
    for r in code_relations:
        a, b = index.get(r.a), index.get(r.b)
        if a is None or b is None or a == b:
            continue
        detail = r.evidence + (f' – offen: {r.uncertainty}' if r.uncertainty else '')
        out.append(Relation(min(a, b), max(a, b), r.kind, detail, r))
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
        mine = linked.get(i, ())
        sides = {j for j, r in mine if r.kind == NEIGHBOUR}
        enclosed = (anchors.get(next(iter(sides))) if len(sides) == 2 and
                    len({anchors.get(j) for j in sides}) == 1 else None)
        axis_anchors: dict[str, set[int]] = defaultdict(set)
        for j, r in mine:
            if r.kind == AXIS and anchors.get(j):
                axis_anchors[anchors[j]].add(j)
        for j, r in mine:
            f = anchors.get(j)
            if not f or r.kind not in VOTING:
                continue
            if r.kind == NEIGHBOUR and NEIGHBOUR_BOTH_SIDES and enclosed != f:
                continue
            if r.kind == AXIS and len(axis_anchors[f]) < AXIS_MIN_ANCHORS:
                continue
            votes[f].add(FAMILY[r.kind])
            evidence[f].append(Evidence(r.kind, f'{RELATION_LABELS[r.kind]} wie „{maps[j].name}“ ({f})',
                                        r.detail, f))
        if own[i] and own[i][1] in (CONFIRMED, STRONG):
            f, status, ev = own[i]
            others = sorted(set(votes) - {f})
            contra = [f'{k}-Beziehung mit Tabellen der Funktion {g}' for g in others for k in sorted(votes[g])]
            out.append(Hypothesis(i, f, status, [ev] + evidence.get(f, []), contra))
            continue
        if len(votes) > 1:
            contra = [f'{g}: ' + ', '.join(sorted(kinds)) for g, kinds in sorted(votes.items())]
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
        if r.kind in GROUPING:
            parent[find(r.a)] = find(r.b)
    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(maps)):
        members[find(i)].append(i)
    return sorted((v for v in members.values() if len(v) > 1), key=lambda v: (-len(v), v[0]))


@dataclass
class FunctionGroup:
    """Tables linked by technical relations (shared axis, code). Named only by a number: the group is a
    structural fact. ``functions`` are the definitions its members already have; with exactly one the
    group is a proposal for the other members (status from identify, never more)."""
    number: int
    members: list[int]
    kinds: dict[str, int]                 # relation kind -> number of relations inside the group
    functions: dict[str, int]             # known function -> members that declare it
    relations: list[Relation] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f'Unbekannte Funktionsgruppe {self.number}'

    @property
    def contradictory(self) -> bool:
        return len(self.functions) > 1

    @property
    def code_backed(self) -> bool:
        return any(k in CODE_EVIDENCE for k in self.kinds)


def function_groups(maps: list[MapDefinition], rels: list[Relation]) -> list[FunctionGroup]:
    """groups() with their relations, relation kinds and known functions; numbered from 1, largest first."""
    out = []
    for n, members in enumerate(groups(maps, rels), 1):
        inside = set(members)
        mine = [r for r in rels if r.kind in GROUPING and r.a in inside and r.b in inside]
        kinds: dict[str, int] = defaultdict(int)
        for r in mine:
            kinds[r.kind] += 1
        functions: dict[str, int] = defaultdict(int)
        for i in members:
            own = _own(maps[i])
            if own and own[1] in (CONFIRMED, STRONG):
                functions[own[0]] += 1
        out.append(FunctionGroup(n, members, dict(kinds), dict(functions), mine))
    return out


def counts(hypotheses: list[Hypothesis]) -> dict[str, int]:
    out = dict.fromkeys(STATUSES, 0)
    for h in hypotheses:
        out[h.status] += 1
    return out


__all__ = ['CONFIRMED', 'STRONG', 'SUSPECTED', 'UNKNOWN', 'STATUSES', 'AXIS', 'ROUTINE', 'NEIGHBOUR', 'CALLER',
           'FLOW', 'SAME_RESULT', 'SHARED_INPUT', 'FAMILY', 'VOTING', 'Relation', 'Evidence', 'Hypothesis',
           'FunctionGroup', 'relations', 'code_links', 'identify', 'groups', 'function_groups', 'counts']
