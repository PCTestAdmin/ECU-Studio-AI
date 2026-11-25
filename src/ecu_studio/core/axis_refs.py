"""Table -> axis reference -> stored axis object (quality phase 3, after 1.21.0-rc1).

Every table with an axis of more than one point has one reference per axis (X, Y). A reference
either names a stored axis object by its storage address, or it stays open:

  gespeichert   the axis points are read from a storage address (a definition, the program code
                or the table's own record header names it)
  fest          a definition gives the points but no storage address (A2L FIX_AXIS, computed axes):
                nothing is stored, nothing can be shared
  ungeklärt     the table has an axis but no source names its storage (e.g. a value block found by
                its data pattern alone): the reference stays open, it is never guessed from values

Several tables that name the same storage address use ONE axis object (a shared axis). Two axes
with identical points at different addresses are two objects: identical values do not prove
common storage (core/axis_groups.axis_value_hints lists them as hints only). Addresses are file
offsets; CPU addresses of the same bytes (e.g. TriCore cached/uncached flash) are aliases of one
object and are listed with it.

An object records what is known about its storage (point count, cell type and byte order where a
definition gives them), where each statement comes from, and the contradictions between its users
(different point counts, different cell types). A contradicted object is no evidence for a common
function (core/function_id). Nothing here changes a table.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from .confidence import CODE as CODE_LEVEL, evidence_level
from .model import MapDefinition

STORED, FIXED, OPEN = 'gespeichert', 'fest', 'ungeklärt'
UNAPPLIED_NOTE = (' · nicht bedatet (alle Stützstellen gleich): gemeinsam nur über die Speicheradresse; '
                  'wertgleiche Kopien an anderen Adressen sind möglich')
DEFINITION, CODE, STRUCTURE = 'Definition', 'Programmcode', 'Datenstruktur'
DEFINITION_SOURCES = ('a2l', 'xdf', 'romraider', 'csv', 'definition', 'pack', 'exact-reference')
TRICORE_ALIASES = (0x80000000, 0xA0000000)   # cached / uncached view of the same flash


def _source(m: MapDefinition) -> str:
    if m.verified or m.source.lower().startswith(DEFINITION_SOURCES):
        return DEFINITION
    if evidence_level(m) == CODE_LEVEL:
        return CODE
    return STRUCTURE


@dataclass(frozen=True)
class AxisRef:
    table: int
    axis: str                 # 'X' or 'Y'
    points: int
    status: str               # STORED / FIXED / OPEN
    offset: int | None
    source: str               # DEFINITION / CODE / STRUCTURE
    name: str = ''            # name of the axis object in the definition (A2L AXIS_PTS), if any

    def describe(self) -> str:
        if self.status == STORED:
            name = f' {self.name}' if self.name else ''
            return f'{self.axis}-Achse{name} @ 0x{self.offset:X}, {self.points} Punkte ({self.source})'
        if self.status == FIXED:
            return f'{self.axis}-Achse: {self.points} Punkte, nicht gespeichert (feste oder berechnete Achse)'
        return f'{self.axis}-Achse: {self.points} Punkte, Achsenreferenz ungeklärt (keine Speicheradresse belegt)'


@dataclass
class AxisObject:
    offset: int
    points: int
    users: list[tuple[int, str]]                      # (table index, 'X' | 'Y')
    sources: tuple[str, ...]
    name: str = ''
    dtype: str = ''                                   # from a definition of the axis object ('' unknown)
    endian: str = ''
    aliases: tuple[int, ...] = ()                     # CPU addresses that name these bytes
    issues: list[str] = field(default_factory=list)
    # All users read equal points (an unapplied axis, e.g. all zero; quality phase 4): such axes exist as
    # value-equal copies at many addresses, so a common address from code is weaker evidence of sharing.
    unapplied: bool = False

    @property
    def tables(self) -> list[int]:
        return sorted({i for i, _ in self.users})

    @property
    def shared(self) -> bool:
        return len(self.tables) >= 2

    @property
    def contradictory(self) -> bool:
        return bool(self.issues)

    def describe(self) -> str:
        name = f' {self.name}' if self.name else ''
        cell = f', {self.dtype} {self.endian}'.rstrip() if self.dtype else ', Zelltyp nicht belegt'
        alias = (' · Adressen ' + ', '.join(f'0x{a:X}' for a in self.aliases)) if len(self.aliases) > 1 else ''
        users = f'{len(self.tables)} Kennfelder' if self.shared else '1 Kennfeld'
        state = ('Widerspruch: ' + '; '.join(self.issues)) if self.issues else 'widerspruchsfrei'
        return (f'Achse{name} @ 0x{self.offset:X}: {self.points} Punkte{cell}, {users}, '
                f'Beleg: {", ".join(self.sources)}{alias} – {state}' + (UNAPPLIED_NOTE if self.unapplied else ''))


def references(maps: list[MapDefinition]) -> list[AxisRef]:
    """One reference per axis with more than one point, in table order."""
    out = []
    for i, m in enumerate(maps):
        src = _source(m)
        for axis, at, n, ref, values in (('X', m.axis_x_offset, m.cols, m.axis_x_ref, m.axes_x),
                                         ('Y', m.axis_y_offset, m.rows, m.axis_y_ref, m.axes_y)):
            if n <= 1:
                continue
            if at is not None:
                out.append(AxisRef(i, axis, n, STORED, at, src, ref))
            elif src == DEFINITION and values:
                out.append(AxisRef(i, axis, n, FIXED, None, src, ref))
            else:
                out.append(AxisRef(i, axis, n, OPEN, None, src, ref))
    return out


def objects(maps: list[MapDefinition], axis_definitions: list[MapDefinition] = (), *,
            ecu_base: int | None = None) -> list[AxisObject]:
    """Stored axis objects by storage address (file offset), with their users, sources and contradictions.

    ``axis_definitions``: axis objects of a definition (e.g. A2LLinkResult.axis_objects) giving the
    cell type and byte order of the stored points. ``ecu_base``: CPU address of file offset 0, to list
    the TriCore cached/uncached aliases of each object.
    """
    by_offset: dict[int, list[AxisRef]] = defaultdict(list)
    for r in references(maps):
        if r.status == STORED:
            by_offset[r.offset].append(r)
    defs: dict[int, list[MapDefinition]] = defaultdict(list)
    for d in axis_definitions:
        defs[d.offset].append(d)
    out = []
    for at in sorted(by_offset):
        refs = by_offset[at]
        counts: dict[int, int] = defaultdict(int)
        for r in refs:
            counts[r.points] += 1
        points = max(counts, key=lambda c: (counts[c], c))
        names = sorted({r.name for r in refs if r.name})
        types = sorted({(d.dtype, d.endian) for d in defs.get(at, ())})
        issues = []
        if len(counts) > 1:
            issues.append('Punktzahlen widersprechen sich (' + ', '.join(f'{c}×{n}' for c, n in sorted(counts.items()))
                          + ')')
        if len(names) > 1:
            issues.append('verschiedene Achsnamen an einer Adresse (' + ', '.join(names) + ')')
        if len(types) > 1:
            issues.append('Definitionen nennen verschiedene Zelltypen (' +
                          ', '.join(f'{t} {e}' for t, e in types) + ')')
        inside = sorted({maps[i].name for i in range(len(maps))
                         if maps[i].offset <= at < maps[i].offset + maps[i].length
                         and any(r.table == i for r in refs)})
        if inside:
            issues.append('Achse liegt im Wertebereich von ' + ', '.join(inside[:3]))
        aliases = ()
        if ecu_base is not None and (ecu_base & 0xE0000000) in TRICORE_ALIASES:
            low = (ecu_base + at) & 0x1FFFFFFF
            aliases = tuple(seg + low for seg in TRICORE_ALIASES)
        sources = tuple(s for s in (DEFINITION, CODE, STRUCTURE) if any(r.source == s for r in refs))
        dtype, endian = types[0] if len(types) == 1 else ('', '')
        values = [maps[r.table].axes_x if r.axis == 'X' else maps[r.table].axes_y for r in refs]
        unapplied = all(v and len(set(v)) == 1 for v in values)
        out.append(AxisObject(at, points, sorted((r.table, r.axis) for r in refs), sources,
                              names[0] if len(names) == 1 else '', dtype, endian, aliases, issues, unapplied))
    return out


def index(objs: list[AxisObject]) -> dict[int, list[AxisObject]]:
    """Table index -> the axis objects it uses."""
    out: dict[int, list[AxisObject]] = defaultdict(list)
    for o in objs:
        for i in o.tables:
            out[i].append(o)
    return dict(out)


def summary(maps: list[MapDefinition], objs: list[AxisObject] | None = None) -> dict[str, int]:
    """Counts for reports and the GUI: references by status, objects, shared and contradicted objects."""
    refs = references(maps)
    objs = objects(maps) if objs is None else objs
    out = {'references': len(refs), STORED: 0, FIXED: 0, OPEN: 0}
    for r in refs:
        out[r.status] += 1
    out['objects'] = len(objs)
    out['shared'] = sum(o.shared for o in objs)
    out['shared_unapplied'] = sum(o.shared and o.unapplied for o in objs)
    out['contradictory'] = sum(o.contradictory for o in objs)
    return out


__all__ = ['STORED', 'FIXED', 'OPEN', 'DEFINITION', 'CODE', 'STRUCTURE', 'AxisRef', 'AxisObject', 'references',
           'objects', 'index', 'summary']
