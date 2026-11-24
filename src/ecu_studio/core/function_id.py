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

Abstention (quality phase 3): a relation names a function only where the evidence can carry it.

  memory layout   the calibration is laid out by software module: a function that rests on ONE evidence family
                  (would be "Vermutet") must occur among the LOCAL_ANCHORS nearest anchors on each side (by
                  address); otherwise the layout speaks against it and the table stays "Unbekannt"
  contradictions  an axis whose users disagree on the number of points does not vote
  self-check      (ablation switch, off: no net benefit measured) how far a kind of relation (shared axis,
                  neighbour, caller, ...) agrees with the function differs between software lines and files.
                  Each file checks it on its own anchors (leave one out: does the kind name exactly one
                  function, the anchor's own, from the OTHER anchors?). A kind that agrees in less than
                  RELIABLE_SHARE of at least MIN_CHECKS checks does not vote in this file; the reason names the
                  count. A kind with fewer checks is untested: UNTESTED decides ('vote', 'local' = only with the
                  memory-layout check, 'none').

Held-back functions stay visible as candidates with the reason (``Hypothesis.candidates``, ``reasons``);
``missing`` names the evidence that would raise the status. No probability is claimed.
"""
from __future__ import annotations

import bisect
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
# Abstention rules (switches for ablations). Set on development data of one line (MEVD17.2, tools/
# function_benchmark: table, block and function splits) and checked on the other (MSD80); see
# docs/ENTWICKLUNG_NEXTGEN.md § 8.
# Rejected (kept as an ablation switch, 0 = off): a shared axis / routine / result variable votes only when this
# share of its other tables are anchors of the function. Set on MEVD17.2 it cut wrong assignments there, but on
# MSD80 (where shared axes agree with the function) it removed most right ones (1 % anchors: 14 373 -> 617 right).
HUB_MIN_SHARE = 0
# Self-check of relation kinds (see above): measured, not adopted. With it the development data lost more right
# than wrong assignments (MEVD17.2, 10 % anchors, with the layout check: 906 right for 34 wrong); off = PR #30.
SELF_CHECK = False
RELIABLE_SHARE = .9     # agreeing checks a kind needs to vote
MIN_CHECKS = 10         # fewer checks: the kind is untested in this file
UNTESTED = 'local'      # untested kinds: 'vote', 'local' (vote only if the memory layout agrees), 'none'
LOCAL_ANCHORS = 2       # nearest anchors on each side (by address); one of them must carry the function
# Memory-layout check: True every vote, 'single' only votes of one evidence family (Vermutet), False only where
# UNTESTED == 'local' asks for it. Set on MEVD17.2 (10 % anchors, one salt: wrong 354 -> 76, right unchanged),
# checked on MSD80 (wrong 893 -> 397, right 21 051 -> 16 962); 'single' keeps the same wrong and more right
# assignments than True on MSD80. Figures: docs/ENTWICKLUNG_NEXTGEN.md § 8.
LOCAL_CHECK = 'single'
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
    hub: tuple | None = None  # the shared source (axis address, routine, result variable), if any
    doubt: str = ''           # why this relation does not vote (e.g. users of the axis disagree)


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
    reasons: list[str] = field(default_factory=list)      # why no function / why only this status
    candidates: list[str] = field(default_factory=list)   # functions considered and held back (with reason)
    missing: list[str] = field(default_factory=list)      # evidence that would raise the status

    def describe(self) -> str:
        head = f'Funktion: {self.function} ({self.status})' if self.function else 'Funktion unbekannt'
        lines = [head] + ['  Grund: ' + r for r in self.reasons]
        lines += ['  Beleg: ' + e.text + (f' [{e.source}]' if e.source else '') for e in self.evidence]
        lines += ['  Zurückgehalten: ' + c for c in self.candidates]
        lines += ['  Widerspruch: ' + c for c in self.contradictions]
        lines += ['  Fehlender Beleg: ' + m for m in self.missing]
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
    points: dict[int, set[int]] = defaultdict(set)
    for i, m in enumerate(maps):
        for axis, n in ((m.axis_x_offset, m.cols), (m.axis_y_offset, m.rows)):
            if axis is not None:
                if i not in by_axis[axis]:
                    by_axis[axis].append(i)
                points[axis].add(n)
    # An axis inside a table's own record is used by that table only; shared means several users.
    own = frozenset(a for a, members in by_axis.items() if len(members) == 1)
    for axis, members in sorted(by_axis.items()):
        # One stored axis has one length: users that disagree read it wrongly (or share no axis).
        doubt = (f'Nutzer der Achse bei 0x{axis:X} uneinig über die Punktzahl ('
                 + ', '.join(map(str, sorted(points[axis]))) + ')') if len(points[axis]) > 1 else ''
        for k, a in enumerate(members):
            for b in members[k + 1:]:
                out.append(Relation(a, b, AXIS, f'Achse bei 0x{axis:X}', hub=('axis', axis), doubt=doubt))
    for g in (graph or {}).get('groups', ()):
        members = sorted(g.members)
        for k, a in enumerate(members):
            for b in members[k + 1:]:
                out.append(Relation(a, b, ROUTINE, f'Routine 0x{g.routine_start:X}',
                                    hub=('routine', g.routine_start)))
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
        hub = (r.kind, r.source_address) if r.kind in (CALLER, SAME_RESULT) else None
        out.append(Relation(min(a, b), max(a, b), r.kind, detail, r, hub))
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


FAMILY_NAMES = ('Achse', 'Speicherlage', 'Programmcode')


def _local(order: list[int], offsets: list[int], anchors: dict[int, str], i: int, offset: int) -> set[str]:
    """Functions of the LOCAL_ANCHORS nearest anchors on each side of ``offset`` (by address)."""
    k = bisect.bisect_left(offsets, offset)
    left = [order[x] for x in range(k - 1, -1, -1) if order[x] != i][:LOCAL_ANCHORS]
    right = [order[x] for x in range(k, len(order)) if order[x] != i][:LOCAL_ANCHORS]
    return {anchors[j] for j in left + right}


def _enclosed(mine, anchors: dict[int, str]) -> str | None:
    """Function of the anchors on BOTH sides of a table (direct neighbours), None otherwise."""
    sides = {j for j, r in mine if r.kind == NEIGHBOUR}
    found = {anchors.get(j) for j in sides}
    return next(iter(found)) if len(sides) == 2 and len(found) == 1 else None


def reliability(maps: list[MapDefinition], rels: list[Relation]) -> dict[str, tuple[int, int]]:
    """Self-check of each voting relation kind on the anchors of this file: kind -> (agreeing, checks).

    Leave one out: for each anchor, the functions the kind would name from the OTHER anchors (same rules
    as in identify: no doubted relations, a neighbour only when anchors of one function enclose the table).
    Only checks where the kind names exactly ONE function count (several functions end as a contradiction in
    identify, never as a wrong name); a check agrees when that function is the anchor's own. Only the file's own
    definitions are used, no reference data."""
    own = [_own(m) for m in maps]
    anchors = {i: o[0] for i, o in enumerate(own) if o and o[1] in (CONFIRMED, STRONG)}
    linked: dict[int, list[tuple[int, Relation]]] = defaultdict(list)
    for r in rels:
        if r.a in anchors and r.b in anchors:
            linked[r.a].append((r.b, r))
            linked[r.b].append((r.a, r))
    out: dict[str, list[int]] = {k: [0, 0] for k in VOTING}
    for i, mine in linked.items():
        named: dict[str, set[str]] = defaultdict(set)
        enclosed = _enclosed(mine, anchors)
        for j, r in mine:
            if r.kind not in VOTING or r.doubt:
                continue
            if r.kind == NEIGHBOUR and NEIGHBOUR_BOTH_SIDES and enclosed is None:
                continue
            named[r.kind].add(anchors[j])
        for kind, fs in named.items():
            if len(fs) == 1:
                out[kind][1] += 1
                out[kind][0] += fs == {anchors[i]}
    return {k: (a, n) for k, (a, n) in out.items()}


def identify(maps: list[MapDefinition], rels: list[Relation] | None = None, graph: dict | None = None
             ) -> list[Hypothesis]:
    """One hypothesis per table (same order as ``maps``)."""
    rels = relations(maps, graph) if rels is None else rels
    own = [_own(m) for m in maps]
    anchors = {i: o[0] for i, o in enumerate(own) if o and o[1] in (CONFIRMED, STRONG)}
    checked = reliability(maps, rels) if SELF_CHECK else {}
    unreliable = {k for k, (a, n) in checked.items() if n >= MIN_CHECKS and a < RELIABLE_SHARE * n}
    untested = {k for k, (a, n) in checked.items() if n < MIN_CHECKS}
    linked: dict[int, list[tuple[int, Relation]]] = defaultdict(list)
    hubs: dict[tuple, set[int]] = defaultdict(set)
    for r in rels:
        linked[r.a].append((r.b, r))
        linked[r.b].append((r.a, r))
        if r.hub is not None:
            hubs[r.hub].update((r.a, r.b))
    hub_functions: dict[tuple, dict[str, int]] = {}
    for hub, members in hubs.items():
        c: dict[str, int] = defaultdict(int)
        for j in members:
            if j in anchors:
                c[anchors[j]] += 1
        hub_functions[hub] = c
    order = sorted(anchors, key=lambda j: (maps[j].offset, j))
    offsets = [maps[j].offset for j in order]
    out = []
    for i, m in enumerate(maps):
        votes: dict[str, set[str]] = defaultdict(set)
        evidence: dict[str, list[Evidence]] = defaultdict(list)
        held: dict[str, list[str]] = defaultdict(list)       # function -> why a relation did not vote
        layout: set[str] = set()                              # functions whose votes need the layout check
        doubts: list[str] = []
        mine = linked.get(i, ())
        enclosed = _enclosed(mine, anchors)
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
            if r.doubt:
                if r.doubt not in doubts:
                    doubts.append(r.doubt)
                continue
            if r.hub is not None and HUB_MIN_SHARE:
                others = len(hubs[r.hub]) - 1
                agree = hub_functions[r.hub].get(f, 0) - (anchors.get(i) == f)
                if agree < HUB_MIN_SHARE * others:
                    why = (f'{RELATION_LABELS[r.kind]}: nur {agree} von {others} weiteren Kennfeldern dieser Quelle '
                           f'mit bekannter Funktion {f} (gemeinsame Größe, kein Funktionsbeleg)')
                    if why not in held[f]:
                        held[f].append(why)
                    continue
            if r.kind in unreliable:
                a, n = checked[r.kind]
                why = (f'{RELATION_LABELS[r.kind]}: in dieser Datei nur bei {a} von {n} Kennfeldern mit bekannter '
                       'Funktion dieselbe Funktion (Beziehungsart hier unzuverlässig)')
                if why not in held[f]:
                    held[f].append(why)
                continue
            if r.kind in untested and UNTESTED != 'vote':
                if UNTESTED == 'none':
                    why = (f'{RELATION_LABELS[r.kind]}: in dieser Datei nicht prüfbar (zu wenige Kennfelder mit '
                           'bekannter Funktion)')
                    if why not in held[f]:
                        held[f].append(why)
                    continue
                layout.add(f)
            votes[f].add(FAMILY[r.kind])
            evidence[f].append(Evidence(r.kind, f'{RELATION_LABELS[r.kind]} wie „{maps[j].name}“ ({f})',
                                        r.detail, f))
        if own[i] and own[i][1] in (CONFIRMED, STRONG):
            f, status, ev = own[i]
            others = sorted(set(votes) - {f})
            contra = [f'{k}-Beziehung mit Tabellen der Funktion {g}' for g in others for k in sorted(votes[g])]
            out.append(Hypothesis(i, f, status, [ev] + evidence.get(f, []), contra + doubts))
            continue
        candidates = [f'{g} – {w}' for g in sorted(held) if g not in votes for w in held[g]]
        if len(votes) > 1:
            contra = [f'{g}: ' + ', '.join(sorted(kinds)) for g, kinds in sorted(votes.items())]
            ev = [e for f in sorted(evidence) for e in evidence[f]]
            if own[i]:
                ev.insert(0, own[i][2])
            out.append(Hypothesis(i, '', UNKNOWN, ev, ['Beziehungen zu Tabellen verschiedener Funktionen'] + contra
                                  + doubts, ['Belege führen zu verschiedenen Funktionen'],
                                  [f'{g} ({", ".join(sorted(k))})' for g, k in sorted(votes.items())] + candidates))
            continue
        if votes:
            f, kinds = next(iter(votes.items()))
            layout_check = LOCAL_CHECK is True or (LOCAL_CHECK == 'single' and len(kinds) < 2) or f in layout
            if (layout_check and own[i] is None
                    and f not in _local(order, offsets, anchors, i, m.offset)):
                out.append(Hypothesis(i, '', UNKNOWN, evidence[f], doubts,
                                      [f'{f} kommt unter den nächstgelegenen Kennfeldern mit bekannter Funktion nicht '
                                       'vor (Speicherlage spricht dagegen)'],
                                      [f'{f} ({", ".join(sorted(kinds))}) – Speicherlage widerspricht'] + candidates,
                                      ['ein Kennfeld derselben Funktion in der Nähe oder ein Beleg, der die '
                                       'Speicherlage erklärt']))
                continue
            status = STRONG if len(kinds) >= 2 else SUSPECTED
            ev = evidence[f]
            contra = list(doubts)
            reasons, missing = [], []
            if status == SUSPECTED:
                reasons.append('nur eine Belegfamilie (' + ', '.join(sorted(kinds)) + ')')
                missing.append('zweiter unabhängiger Beleg: ' + ', '.join(n for n in FAMILY_NAMES if n not in kinds))
            if own[i]:
                ev = [own[i][2]] + ev
                if own[i][0] != f:
                    contra.insert(0, f'übernommener Name gehört zu {own[i][0]}, Beziehungen zu {f}')
                    status, f = UNKNOWN, ''
                    reasons, missing = ['übernommener Name und Beziehungen widersprechen sich'], []
            out.append(Hypothesis(i, f, status, ev, contra, reasons, candidates, missing))
            continue
        if own[i]:
            f, status, ev = own[i]
            out.append(Hypothesis(i, f, status, [ev], doubts, ['nur der übernommene Name (ungeprüft)'], candidates,
                                  ['Beziehung zu einem Kennfeld mit bekannter Funktion']))
            continue
        if candidates or doubts:
            reasons = ['die Beziehungen reichen für keine Funktion']
        elif mine:
            reasons = ['keine Beziehung zu einem Kennfeld mit bekannter Funktion']
        else:
            reasons = []
        out.append(Hypothesis(i, '', UNKNOWN, [], doubts, reasons, candidates))
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
           'FunctionGroup', 'relations', 'code_links', 'reliability', 'identify', 'groups', 'function_groups', 'counts']
