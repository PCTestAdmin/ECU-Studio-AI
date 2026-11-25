"""Edit guard: which other objects an edit of a table's cells would overwrite (quality phase 5).

ECU Studio never writes axis bytes as a side effect: an axis edit changes the definition of the one
selected table, and a cell edit writes only the cells of the selected table. A cell can still lie on
bytes that another object uses - the values of an overlapping table or a stored axis (a wrong or
uncertain detection, or a table whose record contains its own axis). Such an edit would silently
change the other object as well.

``conflicts`` lists every such foreign byte range with the affected tables and addresses, so the
caller shows them and asks before writing. ``refused`` names the conflicts that must not be written
at all: bytes of a stored axis whose shared identity is not established (core/axis_refs: identity
'unbekannt'), because then nobody can say which tables read these bytes.

The axis cell type is not part of a table definition, so an axis is taken as 2 bytes per point: an
8-bit axis is over-covered (a warning too many), a 16-bit one is exact. Nothing here writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from .model import MapDefinition

AXIS_POINT_BYTES = 2


@dataclass(frozen=True)
class Conflict:
    kind: str                 # 'Werte' | 'Achse'
    start: int                # byte range of the foreign object [start, end)
    end: int
    tables: tuple[str, ...]   # names of the tables using this object
    identity: str = ''        # shared axis: identity state from core/axis_refs ('' = not shared)
    hit: tuple[int, int] = (0, 0)   # first and last written byte inside the range

    @property
    def refused(self) -> bool:
        from .axis_refs import UNKNOWN
        return self.kind == 'Achse' and self.identity == UNKNOWN

    def describe(self) -> str:
        names = ', '.join(self.tables[:5]) + (f' (+{len(self.tables) - 5})' if len(self.tables) > 5 else '')
        what = 'Werte von' if self.kind == 'Werte' else 'gespeicherte Achse von'
        state = f' – gemeinsame Achse, Identität: {self.identity}' if self.identity else ''
        return (f'Bytes 0x{self.hit[0]:X}–0x{self.hit[1]:X} liegen in {what} {names} '
                f'(0x{self.start:X}–0x{self.end - 1:X}){state}')


def written_positions(m: MapDefinition, cells) -> set[int]:
    """Byte positions written when the given cells (row, col) of ``m`` are changed."""
    return {m.cell_offset(r, c) + j for r, c in cells for j in range(m.width)}


def update_positions(updates) -> set[int]:
    """Byte positions of (offset, payload) updates, e.g. BatchPreview.updates."""
    return {p + j for p, payload in updates for j in range(len(payload))}


def conflicts(maps: list[MapDefinition], m, positions, data: bytes | None = None) -> list[Conflict]:
    """Foreign byte ranges hit by writing ``positions`` into table ``m`` (one table or several, by object).

    ``data``: the current image bytes, needed to tell a shared axis apart from value-equal copies; without
    them no code-named shared axis counts as established (core/axis_refs)."""
    own = {id(x) for x in (m if isinstance(m, (list, tuple, set)) else [m])}
    positions = sorted(set(positions))
    if not positions:
        return []
    lo, hi = positions[0], positions[-1]

    def hit(start, end):
        inside = [p for p in positions if start <= p < end] if start <= hi and end > lo else []
        return (inside[0], inside[-1]) if inside else None

    out = []
    for other in maps:
        if id(other) in own:
            continue
        h = hit(other.offset, other.offset + other.length)
        if h:
            out.append(Conflict('Werte', other.offset, other.offset + other.length, (other.name,), '', h))
    from .axis_refs import objects
    for o in objects(maps, data=data):
        start, end = o.offset, o.offset + AXIS_POINT_BYTES * o.points
        h = hit(start, end)
        if h:
            names = tuple(maps[i].name for i in o.tables)
            out.append(Conflict('Achse', start, end, names, o.identity if o.shared else '', h))
    return out


def allowed(found: list[Conflict], confirm) -> bool:
    """Whether an edit with these conflicts may be written: no conflict -> yes; a refused one -> no (the
    user is not asked); otherwise ``confirm(found)`` decides (it shows every affected table and range)."""
    if not found:
        return True
    if any(c.refused for c in found):
        return False
    return bool(confirm(found))


def refusal_text(found: list[Conflict]) -> str:
    """Why an edit is refused, with the affected tables and ranges."""
    return ('Bearbeitung abgelehnt: Die Zellen liegen auf einer gespeicherten Achse, deren gemeinsame Identität '
            'nicht geklärt ist; welche Kennfelder diese Bytes lesen, lässt sich nicht sicher sagen.\n'
            + '\n'.join(c.describe() for c in found if c.refused))


def confirmation_text(found: list[Conflict]) -> str:
    """Question before an edit that also changes other objects, with every affected table and range."""
    return ('Diese Bearbeitung ändert auch Bytes anderer Objekte:\n' + '\n'.join(c.describe() for c in found)
            + '\n\nTrotzdem schreiben? Alle genannten Kennfelder ändern sich mit.')


__all__ = ['AXIS_POINT_BYTES', 'Conflict', 'allowed', 'conflicts', 'confirmation_text', 'refusal_text',
           'update_positions', 'written_positions']
