"""Code relations between tables: a small, processor-independent data-flow model (after 1.21.0-rc1).

A processor module (e.g. core/tricore_flow) decodes the instructions around each call of an
interpolation routine and reports one ``TableUse`` per call: which RAM variables feed the call's
input registers, where the result is stored (as a copy or after local arithmetic) and which code
routine contains the call. This module turns those uses into relations between tables. It never
decodes instructions itself.

Relation kinds (each with addresses, evidence, method and open points):

  flow           the result of table A is stored in a RAM variable the call of table B loads as input
  same-result    the results of A and B are stored in the same RAM variable (selection, limitation)
  same-caller    A and B are looked up by the same code routine
  shared-input   A and B read the same input variable (e.g. the same breakpoint quantity): a common
                 operating point, not a common function; listed, never used to name a function

A relation is a technical fact about the code; it does not say that two tables belong to the same
ECU function. core/function_id decides what counts as evidence for a function, per kind, from
measurements (docs/ENTWICKLUNG_NEXTGEN.md).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

RAM, CONST, COMPUTED, OPEN, RESULT = 'ram', 'const', 'computed', 'open', 'call-result'
COPY, DERIVED = 'copy', 'derived'
FLOW, SAME_RESULT, SAME_CALLER, SHARED_INPUT = 'flow', 'same-result', 'same-caller', 'shared-input'
CODE_KINDS = (FLOW, SAME_RESULT, SAME_CALLER, SHARED_INPUT)
MAX_SHARED = 12     # a variable read or written by more tables is a common quantity, not a link


@dataclass(frozen=True)
class Operand:
    kind: str                 # RAM / CONST / COMPUTED / OPEN / RESULT (address: the producing call)
    address: int | None = None
    reason: str = ''          # why the value stays open (undecoded instruction, branch target, call, ...)


@dataclass(frozen=True)
class Store:
    address: int
    how: str                  # COPY (the result itself) or DERIVED (after local arithmetic)
    width: int = 0
    at: int = 0               # file offset of the store instruction


@dataclass
class TableUse:
    table: int                # file offset of the table data
    site: int                 # file offset of the call instruction
    routine: int              # file offset of the interpolation routine
    caller: int | None        # entry of the code routine containing the call (None: unknown)
    inputs: dict[str, Operand] = field(default_factory=dict)   # input register -> operand
    stores: list[Store] = field(default_factory=list)
    open: list[str] = field(default_factory=list)              # open points of this use
    method: str = ''


@dataclass(frozen=True)
class CodeRelation:
    a: int                    # table offsets (a < b, except FLOW: a feeds b)
    b: int
    kind: str
    evidence: str
    source_address: int       # instruction or variable that proves it (file offset or RAM address)
    target_address: int
    method: str
    uncertainty: str = ''


def relations(uses: list[TableUse]) -> list[CodeRelation]:
    """Relations between the tables of ``uses`` (see module doc). Deterministic order."""
    out: dict[tuple, CodeRelation] = {}
    writers: dict[int, list[tuple[TableUse, Store]]] = defaultdict(list)
    readers: dict[int, list[tuple[TableUse, str]]] = defaultdict(list)
    callers: dict[int, list[TableUse]] = defaultdict(list)
    for u in uses:
        for s in u.stores:
            writers[s.address].append((u, s))
        for reg, op in u.inputs.items():
            if op.kind == RAM and op.address is not None:
                readers[op.address].append((u, reg))
        if u.caller is not None:
            callers[u.caller].append(u)

    def add(rel: CodeRelation):
        out.setdefault((rel.a, rel.b, rel.kind), rel)

    by_site = {u.site: u for u in uses}
    for v in uses:
        for reg, op in v.inputs.items():
            u = by_site.get(op.address) if op.kind == RESULT else None
            if u is not None and u.table != v.table:
                add(CodeRelation(u.table, v.table, FLOW, f'Ergebnis des Aufrufs direkt als Eingang {reg} übergeben',
                                 u.site, v.site, v.method))

    for var, ws in writers.items():
        tables_w = {u.table for u, _ in ws}
        tables_r = {u.table for u, _ in readers.get(var, ())}
        if len(tables_w) > MAX_SHARED or len(tables_r) > MAX_SHARED:
            continue
        for u, s in ws:
            for v, reg in readers.get(var, ()):
                if v.table == u.table:
                    continue
                how = 'direkt' if s.how == COPY else 'nach Rechnung'
                add(CodeRelation(u.table, v.table, FLOW,
                                 f'Ergebnis ({how}) gespeichert bei 0x{var:X}, als Eingang {reg} geladen',
                                 s.at, v.site, u.method or v.method,
                                 '' if s.how == COPY else 'Ergebnis vor dem Speichern verrechnet'))
        tables = sorted(tables_w)
        for i, a in enumerate(tables):
            for b in tables[i + 1:]:
                add(CodeRelation(a, b, SAME_RESULT, f'beide Ergebnisse gespeichert bei 0x{var:X}', var, var,
                                 ws[0][0].method))
    for var, rs in readers.items():
        tables = sorted({u.table for u, _ in rs})
        if len(tables) > MAX_SHARED:
            continue
        for i, a in enumerate(tables):
            for b in tables[i + 1:]:
                add(CodeRelation(a, b, SHARED_INPUT, f'gleiche Eingangsgröße bei 0x{var:X}', var, var,
                                 rs[0][0].method, 'gemeinsamer Betriebspunkt, keine gemeinsame Funktion'))
    for entry, us in callers.items():
        tables = sorted({u.table for u in us})
        if len(tables) > MAX_SHARED:
            continue
        for i, a in enumerate(tables):
            for b in tables[i + 1:]:
                add(CodeRelation(a, b, SAME_CALLER, f'beide in der Coderoutine bei 0x{entry:X} gelesen', entry, entry,
                                 us[0].method, 'Routinegrenze aus Aufrufzielen (keine vollständige Zerlegung)'))
    return sorted(out.values(), key=lambda r: (r.kind, r.a, r.b))


def summary(uses: list[TableUse]) -> dict:
    """Counts for reports: uses, resolved inputs, uses with a stored result, open reasons."""
    out = defaultdict(int)
    for u in uses:
        out['uses'] += 1
        out['inputs_ram'] += sum(op.kind == RAM for op in u.inputs.values())
        out['inputs_open'] += sum(op.kind == OPEN for op in u.inputs.values())
        out['with_result'] += bool(u.stores)
        for reason in u.open:
            out['open: ' + reason] += 1
    return dict(out)


__all__ = ['Operand', 'Store', 'TableUse', 'CodeRelation', 'relations', 'summary', 'FLOW', 'SAME_RESULT',
           'SAME_CALLER', 'SHARED_INPUT', 'CODE_KINDS', 'RAM', 'CONST', 'COMPUTED', 'OPEN', 'RESULT', 'COPY',
           'DERIVED']
