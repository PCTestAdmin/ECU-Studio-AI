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

Identity of a shared object (quality phase 5), given the image bytes:

  eindeutig gemeinsam   every user comes from a definition that places the axis at this address
  plausibel gemeinsam   the address comes from program code or data structure, the axis is applied
                        (not all points equal) and no other stored axis holds the same bytes
  wertgleich            (an object, shared or not, related to another address only by equal bytes):
                        never one object; listed in ``copies``
  unbekannt             contradicted, unapplied, a value-equal copy exists at another axis address,
                        or the bytes were not checked

Development data (MSD80 detections after quality phase 4, A2L for evaluation only): of the shared axes
from code with an applied axis and no value-equal copy 1892 of 1892 were right, with a copy 669 of 683,
unapplied 132 of 152. Only the first class is called plausible; precision and coverage are measured
separately (docs/ENTWICKLUNG_NEXTGEN.md).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from .confidence import CODE as CODE_LEVEL, evidence_level
from .model import FORMATS, MapDefinition

STORED, FIXED, OPEN = 'gespeichert', 'fest', 'ungeklärt'
UNAPPLIED_NOTE = (' · nicht bedatet (alle Stützstellen gleich): gemeinsam nur über die Speicheradresse; '
                  'wertgleiche Kopien an anderen Adressen sind möglich')
DEFINITION, CODE, STRUCTURE = 'Definition', 'Programmcode', 'Datenstruktur'
DEFINITION_SOURCES = ('a2l', 'xdf', 'romraider', 'csv', 'definition', 'pack', 'exact-reference')
TRICORE_ALIASES = (0x80000000, 0xA0000000)   # cached / uncached view of the same flash
SURE, PLAUSIBLE, VALUE_EQUAL, UNKNOWN = 'eindeutig gemeinsam', 'plausibel gemeinsam', 'wertgleich', 'unbekannt'
IDENTITIES = (SURE, PLAUSIBLE, VALUE_EQUAL, UNKNOWN)
# Count keys in summary() (plain identifiers: the tester report allows no spaces in field names)
IDENTITY_KEYS = {SURE: 'identity_sure', PLAUSIBLE: 'identity_plausible', VALUE_EQUAL: 'identity_value_equal',
                 UNKNOWN: 'identity_unknown'}
# Cell width of a stored axis (1.21.0-rc2). The value type of a table is never taken for its axes; the width comes
# from what the users and the definition's axis objects state (MapDefinition.axis_x_dtype / axis_y_dtype):
#
#   bestätigt        one width, stated by users that are all checked definitions
#   belegt           one width, stated by a definition or a detector that read the axis with it
#   unbekannt        nobody states a width (e.g. a project of an older version): the write check protects the
#                    widest cell the program can represent (AXIS_MAX_CELL bytes per point)
#   widersprüchlich  users or definitions state different widths: the widest is protected, the object is
#                    contradicted (a shared one gets identity 'unbekannt' and is refused by the write check)
#
# The protected range uses the largest point count any user reads, not the majority.
TYPE_CONFIRMED, TYPE_STATED, TYPE_UNKNOWN, TYPE_CONTRADICTED = 'bestätigt', 'belegt', 'unbekannt', 'widersprüchlich'
AXIS_MAX_CELL = max(spec[1] for spec in FORMATS.values())
NEAR_POINT_BYTES = AXIS_MAX_CELL   # objects(near=...): no object whose protected range touches a write is left out
COPY_UNKNOWN_BYTES = 1             # copy search of an axis of unknown width: compare 1 byte per point (finds every
                                   # copy of any width, so the identity stays 'unbekannt' rather than 'plausibel')


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
    # Identity (quality phase 5): SURE / PLAUSIBLE / UNKNOWN for a shared object, VALUE_EQUAL for an unshared one
    # with copies, '' otherwise; ``copies`` = other stored axis addresses holding the same bytes (at most COPIES_LISTED).
    identity: str = ''
    identity_reason: str = ''
    copies: tuple[int, ...] = ()
    # Cell width (1.21.0-rc2): bytes per point the write check protects, its state (TYPE_*), where the stated
    # types come from, and the largest point count a user reads.
    width: int = AXIS_MAX_CELL
    type_state: str = TYPE_UNKNOWN
    type_sources: tuple[str, ...] = ()
    span_points: int = 0
    step: int = 0                                     # bytes between two points where stated (0 = packed)

    @property
    def end(self) -> int:
        """End (exclusive) of the protected byte range: up to the last point of the largest point count, plus
        one cell (packed: points x width)."""
        n = max(self.span_points, self.points)
        return self.offset + (n - 1) * max(self.step, self.width) + self.width

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
        if self.type_state == TYPE_UNKNOWN:
            cell += f' (geschützt: {self.width} Byte je Punkt)'
        else:
            cell += f', Zellbreite {self.width} Byte ({self.type_state}'
            cell += (': ' + '; '.join(self.type_sources[:2]) + ')') if self.type_sources else ')'
        alias = (' · Adressen ' + ', '.join(f'0x{a:X}' for a in self.aliases)) if len(self.aliases) > 1 else ''
        users = f'{len(self.tables)} Kennfelder' if self.shared else '1 Kennfeld'
        state = ('Widerspruch: ' + '; '.join(self.issues)) if self.issues else 'widerspruchsfrei'
        ident = ''
        if self.identity:
            ident = f' · Identität: {self.identity}' + (f' ({self.identity_reason})' if self.identity_reason else '')
        return (f'Achse{name} @ 0x{self.offset:X}: {self.points} Punkte{cell}, {users}, '
                f'Beleg: {", ".join(self.sources)}{alias} – {state}' + (UNAPPLIED_NOTE if self.unapplied else '')
                + ident)


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


def axis_type(m: MapDefinition, axis: str) -> tuple[str, str]:
    """(cell type, source) the table states for its X or Y axis; ('', '') = not known."""
    dtype = m.axis_x_dtype if axis == 'X' else m.axis_y_dtype
    source = m.axis_x_type_source if axis == 'X' else m.axis_y_type_source
    return (dtype, source or m.source) if dtype in FORMATS else ('', '')


def _cell(refs, maps, defs, cleared: int | None) -> tuple[int, int, str, tuple[str, ...], list[str]]:
    """(width, step, state, sources, issues) of one stored axis from its users' and definitions' stated types.
    ``step``: bytes between two points where a user states one (0 = packed). ``cleared``: width of a valid
    technical clarification; it only applies where no width is stated."""
    stated: dict[int, set[str]] = defaultdict(set)
    steps: set[int] = set()
    confirmed = True
    for r in refs:
        m = maps[r.table]
        dtype, source = axis_type(m, r.axis)
        if dtype:
            stated[FORMATS[dtype][1]].add(f'{source} ({dtype})')
            steps.add(m.axis_x_step if r.axis == 'X' else m.axis_y_step)
            confirmed &= m.verified and r.source == DEFINITION
    for d in defs:
        if d.dtype in FORMATS:
            stated[FORMATS[d.dtype][1]].add(f'{d.source or "Definition"} ({d.dtype})')
            steps.add(0)
            confirmed = False
    sources = tuple(sorted(s for group in stated.values() for s in group))
    if not stated:
        if cleared:
            return cleared, 0, TYPE_STATED, ('technische Klärung',), []
        return AXIS_MAX_CELL, 0, TYPE_UNKNOWN, (), []
    issues = []
    if len(stated) > 1:
        issues.append('Zellbreiten widersprechen sich (' + ', '.join(f'{w} Byte' for w in sorted(stated)) + ')')
    if len(steps) > 1:
        issues.append('Abstände der Stützstellen widersprechen sich (' +
                      ', '.join('gepackt' if s == 0 else f'{s} Byte' for s in sorted(steps)) + ')')
    state = TYPE_CONTRADICTED if issues else TYPE_CONFIRMED if confirmed else TYPE_STATED
    return max(stated), max(steps), state, sources, issues


def objects(maps: list[MapDefinition], axis_definitions: list[MapDefinition] = (), *,
            ecu_base: int | None = None, data: bytes | None = None,
            near: tuple[int, int] | None = None, cleared: dict[int, int] | None = None) -> list[AxisObject]:
    """Stored axis objects by storage address (file offset), with their users, sources and contradictions.

    ``axis_definitions``: axis objects of a definition (e.g. A2LLinkResult.axis_objects) giving the
    cell type and byte order of the stored points. ``ecu_base``: CPU address of file offset 0, to list
    the TriCore cached/uncached aliases of each object. ``data``: the image bytes, to find value-equal
    copies; without them no shared axis from code or structure is plausible (identity 'unbekannt').
    ``near``: (first, last) byte position of a write; only objects whose points (up to NEAR_POINT_BYTES each)
    touch that range are returned, with the same identity as in the full list (copies are still searched
    among all stored axes). The write check uses this so a cell edit does not rebuild every axis object.
    ``cleared``: address -> cell width of valid technical clarifications (core/edit_guard.AxisClearance); used
    only for an axis whose width nobody states.
    """
    cleared = cleared or {}
    # Stored references as plain tuples (table, axis, points); AxisRef objects (the same ones references()
    # gives) are made only for the objects built, so objects(near=...) stays cheap with many tables.
    stored: dict[int, list[tuple[int, str, int]]] = defaultdict(list)
    steps: dict[int, int] = {}                        # address -> largest stated distance between points
    for i, m in enumerate(maps):
        for axis, at, n, step in (('X', m.axis_x_offset, m.cols, m.axis_x_step),
                                  ('Y', m.axis_y_offset, m.rows, m.axis_y_step)):
            if n > 1 and at is not None:
                stored[at].append((i, axis, n))
                if step:
                    steps[at] = max(step, steps.get(at, 0))
    defs: dict[int, list[MapDefinition]] = defaultdict(list)
    for d in axis_definitions:
        defs[d.offset].append(d)
    addresses = sorted(stored)
    if near is not None:
        lo, hi = near
        # The protected range is at most the largest point count x the widest cell (or the stated point distance).
        build = [at for at in addresses if at <= hi and
                 at + max(NEAR_POINT_BYTES, steps.get(at, 0)) * max(n for _, _, n in stored[at]) > lo]
    else:
        build = addresses
    out = []
    for at in build:
        refs = [AxisRef(i, axis, n, STORED, at, _source(maps[i]),
                        maps[i].axis_x_ref if axis == 'X' else maps[i].axis_y_ref) for i, axis, n in stored[at]]
        points, counts = _points(r.points for r in refs)
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
        width, step, type_state, type_sources, width_issues = _cell(refs, maps, defs.get(at, ()), cleared.get(at))
        issues += width_issues
        # Only users of this axis count; looping over them (not over all tables) keeps this linear.
        inside = sorted({maps[i].name for i in {r.table for r in refs}
                         if maps[i].offset <= at < maps[i].offset + maps[i].length})
        if inside:
            issues.append('Achse liegt im Wertebereich von ' + ', '.join(inside[:3]))
        aliases = ()
        if ecu_base is not None and (ecu_base & 0xE0000000) in TRICORE_ALIASES:
            low = (ecu_base + at) & 0x1FFFFFFF
            aliases = tuple(seg + low for seg in TRICORE_ALIASES)
        sources = tuple(s for s in (DEFINITION, CODE, STRUCTURE) if any(r.source == s for r in refs))
        dtype, endian = types[0] if len(types) == 1 else ('', '')
        if not dtype:
            user_types = {axis_type(maps[r.table], r.axis)[0] for r in refs} - {''}
            dtype = next(iter(user_types)) if len(user_types) == 1 else ''
        values = [maps[r.table].axes_x if r.axis == 'X' else maps[r.table].axes_y for r in refs]
        unapplied = all(v and len(set(v)) == 1 for v in values)
        out.append(AxisObject(at, points, sorted((r.table, r.axis) for r in refs), sources,
                              names[0] if len(names) == 1 else '', dtype, endian, aliases, issues, unapplied,
                              width=width, type_state=type_state, type_sources=type_sources,
                              span_points=max(counts), step=step))
    # Candidates for value-equal copies: stored axes whose bytes can equal those of a judged object, i.e. with
    # the same point count (the compared length is the object's cell width x points). Only needed with image bytes.
    wanted = {o.points for o in out} if data is not None else set()
    pool = [(at, n) for at in addresses if any(k in wanted for _, _, k in stored[at])
            for n in (_majority(stored[at]),) if n in wanted]
    _identities(out, data, pool)
    return out


def _copy_width(o: AxisObject) -> int:
    """Bytes per point compared in the copy search: the stated width; 1 byte when none is stated (more copies
    found, so the identity stays open) and the widest stated one when they contradict."""
    return COPY_UNKNOWN_BYTES if o.type_state == TYPE_UNKNOWN or o.step else o.width


def _majority(users: list[tuple[int, str, int]]) -> int:
    """_points(...)[0] for stored tuples; most addresses have users that agree, which needs no counting."""
    first = users[0][2]
    if all(n == first for _, _, n in users):
        return first
    return _points(n for _, _, n in users)[0]


def _points(points) -> tuple[int, dict[int, int]]:
    """Point count most users read (ties: the larger), and the count per point count."""
    counts: dict[int, int] = defaultdict(int)
    for n in points:
        counts[n] += 1
    return max(counts, key=lambda c: (counts[c], c)), counts


# ``copies`` lists at most this many other addresses (messages show three); empty means: no copy.
COPIES_LISTED = 8


def _stored_bytes(data: bytes, offset: int, length: int) -> bytes | None:
    end = offset + length
    return data[offset:end] if end <= len(data) else None


def _identities(objs: list[AxisObject], data: bytes | None, pool: list[tuple[int, int]]) -> None:
    """Identity state of each object (see module doc). Equal bytes never join two objects.
    ``pool``: (address, points) of the stored axes that can be value-equal copies of ``objs``; a candidate has the
    same point count and the same bytes over the object's compared length (copy width x points)."""
    by_bytes: dict[tuple[int, bytes], list[int]] = defaultdict(list)
    keys = []
    if data is not None:
        widths: dict[int, set[int]] = defaultdict(set)      # points -> compared widths needed
        for o in objs:
            widths[o.points].add(_copy_width(o))
        for at, n in pool:
            for w in widths.get(n, ()):
                key = _stored_bytes(data, at, w * n)
                if key is not None:
                    by_bytes[(w, key)].append(at)
        for o in objs:
            w = _copy_width(o)
            key = _stored_bytes(data, o.offset, w * o.points)
            keys.append((w, key) if key is not None else None)
    else:
        keys = [None] * len(objs)
    for o, key in zip(objs, keys):
        # Bounded: listing every member of a large equal-bytes group made this quadratic (quality phase 6:
        # 600 ms per cell edit with 3,000 tables). One object per address, so the first COPIES_LISTED + 1
        # members always hold COPIES_LISTED others when the group is that large.
        group = by_bytes.get(key, ()) if key is not None else ()
        o.copies = tuple(a for a in group[:COPIES_LISTED + 1] if a != o.offset)[:COPIES_LISTED]
        if not o.shared:
            o.identity = VALUE_EQUAL if o.copies else ''
            o.identity_reason = ('gleiche Bytes bei ' + ', '.join(f'0x{a:X}' for a in o.copies[:3])) if o.copies else ''
            continue
        if o.issues:
            o.identity, o.identity_reason = UNKNOWN, 'Nutzer widersprechen sich'
        elif o.sources == (DEFINITION,):
            o.identity, o.identity_reason = SURE, 'Adresse aus der Definition'
        elif o.unapplied:
            o.identity, o.identity_reason = UNKNOWN, 'nicht bedatet'
        elif data is None:
            o.identity, o.identity_reason = UNKNOWN, 'Achsbytes nicht geprüft'
        elif o.copies:
            o.identity, o.identity_reason = UNKNOWN, ('wertgleiche Kopie bei ' +
                                                      ', '.join(f'0x{a:X}' for a in o.copies[:3]))
        else:
            o.identity, o.identity_reason = PLAUSIBLE, 'gemeinsame Adresse aus ' + ', '.join(o.sources)


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
    for state in IDENTITIES:
        out[IDENTITY_KEYS[state]] = sum(o.identity == state for o in objs)
    return out


__all__ = ['STORED', 'FIXED', 'OPEN', 'DEFINITION', 'CODE', 'STRUCTURE', 'SURE', 'PLAUSIBLE', 'VALUE_EQUAL',
           'UNKNOWN', 'IDENTITIES', 'IDENTITY_KEYS', 'TYPE_CONFIRMED', 'TYPE_STATED', 'TYPE_UNKNOWN',
           'TYPE_CONTRADICTED', 'AXIS_MAX_CELL', 'AxisRef', 'AxisObject', 'axis_type', 'references', 'objects',
           'index', 'summary']
