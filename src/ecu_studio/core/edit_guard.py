"""Edit guard: which other objects a byte edit would overwrite, and the write policy (quality phases 5 and 6).

ECU Studio never writes axis bytes as a side effect: an axis edit changes the definition of the one
selected table, and a cell edit writes only the cells of the selected table. A cell can still lie on
bytes that another object uses - the values of an overlapping table or a stored axis (a wrong or
uncertain detection, or a table whose record contains its own axis). Such an edit would silently
change the other object as well.

``conflicts`` lists every such foreign byte range with the affected tables and addresses, so the
caller shows them and asks before writing. ``refused`` names the conflicts that must not be written
at all: bytes of a stored axis whose shared identity is not established (core/axis_refs: identity
'unbekannt'), because then nobody can say which tables read these bytes.

Quality phase 6: the check no longer depends on each dialog. ``WritePolicy`` is attached to the image
(``BinaryImage.write_policy``); every transaction (``BinaryImage.commit``: cells, areas, batches, recipes,
transfers, version restores, checksum corrections, hex edits, scripts) is checked right before its bytes are
applied:

  * Without an ``Approval`` a transaction may only change bytes that belong to no table and no stored axis.
  * An ``Approval`` comes from ``WritePolicy.approve`` (shown to the user, confirmed where other objects are
    hit). It names the positions, the image revision and the conflicts the user confirmed. Right before writing
    the conflicts are computed again: new or changed conflicts, other positions or another revision refuse the
    write (the preview is stale).
  * A refused conflict (shared axis of unknown identity) is refused with or without approval; a second
    confirmation does not lift it. Only an ``AxisClearance`` does: a technical check the user records with the
    storage range, point count, cell width, users and origin of the axis. It is bound to the firmware (the
    original bytes) and to the layout of the axis users and is dropped as soon as one of them changes.

Undo/redo replay transactions that were checked when they were made; loading a project restores saved bytes.
Neither is checked again. A physical axis edit always changes the axis for every table that reads these
bytes; nothing is copied to other addresses.

The axis cell type is not part of a table definition, so an axis is taken as 2 bytes per point: an
8-bit axis is over-covered (a warning too many), a 16-bit one is exact. Nothing here writes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from .model import MapDefinition

AXIS_POINT_BYTES = 2
CLEARED = 'manuell geklärt'      # identity of an unknown shared axis with a valid AxisClearance
MIN_ORIGIN_CHARS = 20             # a clearance names its technical origin, not just "ok"
CONFIRM_LINES = 30                # conflicts listed in one confirmation (the rest is counted)
_GENERIC_ORIGINS = {'ok', 'passt', 'geprüft', 'stimmt', 'ja', 'yes', 'checked', 'egal', 'test'}


class EditRefused(ValueError):
    """A transaction the write policy does not allow (nothing was written)."""


@dataclass(frozen=True)
class Conflict:
    kind: str                 # 'Werte' | 'Achse'
    start: int                # byte range of the foreign object [start, end)
    end: int
    tables: tuple[str, ...]   # names of the tables using this object
    identity: str = ''        # shared axis: identity state from core/axis_refs ('' = not shared), or CLEARED
    hit: tuple[int, int] = (0, 0)   # first and last written byte inside the range
    unverified: int = 0       # users that are unchecked detections (their reading of these bytes is open)

    @property
    def refused(self) -> bool:
        from .axis_refs import UNKNOWN
        return self.kind == 'Achse' and self.identity == UNKNOWN

    @property
    def key(self) -> tuple:
        return (self.kind, self.start, self.end, self.identity, self.tables)

    def describe(self) -> str:
        names = ', '.join(self.tables[:5]) + (f' (+{len(self.tables) - 5})' if len(self.tables) > 5 else '')
        what = 'Werte von' if self.kind == 'Werte' else 'gespeicherte Achse von'
        state = f' – gemeinsame Achse, Identität: {self.identity}' if self.identity else ''
        open_ = f'; davon {self.unverified} ungeprüfte Erkennung(en)' if self.unverified else ''
        return (f'Bytes 0x{self.hit[0]:X}–0x{self.hit[1]:X} liegen in {what} {names} '
                f'(0x{self.start:X}–0x{self.end - 1:X}){state}{open_}')


def written_positions(m: MapDefinition, cells) -> set[int]:
    """Byte positions written when the given cells (row, col) of ``m`` are changed."""
    return {m.cell_offset(r, c) + j for r, c in cells for j in range(m.width)}


def update_positions(updates) -> set[int]:
    """Byte positions of (offset, payload) updates, e.g. BatchPreview.updates."""
    return {p + j for p, payload in updates for j in range(len(payload))}


def _own(m) -> list:
    if m is None:
        return []
    return list(m) if isinstance(m, (list, tuple, set)) else [m]


def conflicts(maps: list[MapDefinition], m, positions, data: bytes | None = None) -> list[Conflict]:
    """Foreign byte ranges hit by writing ``positions`` into table ``m`` (one table, several, or none).

    ``data``: the current image bytes, needed to tell a shared axis apart from value-equal copies; without
    them no code-named shared axis counts as established (core/axis_refs)."""
    from .project_store import DETECTED_SOURCES
    own = {id(x) for x in _own(m)}
    positions = sorted(set(positions))
    if not positions:
        return []
    lo, hi = positions[0], positions[-1]

    def hit(start, end):
        inside = [p for p in positions if start <= p < end] if start <= hi and end > lo else []
        return (inside[0], inside[-1]) if inside else None

    def unchecked(x):
        return x.source in DETECTED_SOURCES and not x.verified

    out = []
    for other in maps:
        if id(other) in own or other.offset > hi:      # cheap test first: ``length`` is computed
            continue
        h = hit(other.offset, other.offset + other.length)
        if h:
            out.append(Conflict('Werte', other.offset, other.offset + other.length, (other.name,), '', h,
                                int(unchecked(other))))
    from .axis_refs import objects
    for o in objects(maps, data=data, near=(lo, hi)):   # AXIS_POINT_BYTES <= axis_refs.NEAR_POINT_BYTES
        start, end = o.offset, o.offset + AXIS_POINT_BYTES * o.points
        h = hit(start, end)
        if h:
            names = tuple(maps[i].name for i in o.tables)
            out.append(Conflict('Achse', start, end, names, o.identity if o.shared else '', h,
                                sum(unchecked(maps[i]) for i in o.tables)))
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
    return ('Bearbeitung abgelehnt: Die Bytes liegen auf einer gespeicherten Achse, deren gemeinsame Identität '
            'nicht geklärt ist; welche Kennfelder diese Bytes lesen, lässt sich nicht sicher sagen. Eine weitere '
            'Bestätigung hebt das nicht auf; nur eine technische Klärung der Achse (Speicherbereich, Punktzahl, '
            'Zellbreite, Nutzer, Herkunft) oder eine passende geprüfte Definition.\n'
            + '\n'.join(c.describe() for c in found if c.refused))


def confirmation_text(found: list[Conflict]) -> str:
    """Question before an edit that also changes other objects, with every affected table and range."""
    axes = [c for c in found if c.kind == 'Achse']
    shared = ('\n\nEine gespeicherte Achse ist ein physischer Speicherbereich: Die Änderung gilt für jedes '
              'Kennfeld, das diese Bytes liest. Es wird nichts auf andere Adressen kopiert.') if axes else ''
    open_ = sum(c.unverified for c in found)
    unresolved = (f'\n{open_} der betroffenen Nutzer sind ungeprüfte Erkennungen; ob sie diese Bytes wirklich '
                  'lesen, ist offen.') if open_ else ''
    lines = [c.describe() for c in found[:CONFIRM_LINES]]
    if len(found) > CONFIRM_LINES:
        lines.append(f'… und {len(found) - CONFIRM_LINES} weitere Objekte')
    return ('Diese Bearbeitung ändert auch Bytes anderer Objekte:\n' + '\n'.join(lines)
            + shared + unresolved + '\n\nTrotzdem schreiben? Alle genannten Kennfelder ändern sich mit.')


@dataclass(frozen=True)
class Approval:
    """Permission for one transaction: these positions, this revision, these confirmed conflicts."""
    positions: frozenset
    revision: int
    own: tuple = ()           # the edited tables (objects); their own bytes are no conflict
    confirmed: frozenset = frozenset()   # Conflict.key of every conflict the user confirmed


@dataclass(frozen=True)
class AxisClearance:
    """A user's technical check of one stored axis whose shared identity the detection left unknown."""
    offset: int
    points: int
    width: int
    tables: tuple[str, ...]
    origin: str
    image_digest: str
    axis_digest: str          # SHA-256 of the axis bytes in the original file (record of what was checked)
    layout: tuple

    def holds(self, image_digest: str, maps: list[MapDefinition]) -> bool:
        """Still valid: same firmware (original bytes) and the same users of the axis with the same layout.
        Edits of the axis itself keep it (they are what the clearance permits)."""
        return image_digest == self.image_digest and _layout(maps, self.offset) == self.layout


def _digest(data: bytes, offset: int, points: int, width: int) -> str:
    end = offset + points * width
    return hashlib.sha256(data[offset:end]).hexdigest() if 0 <= offset and end <= len(data) else ''


def _layout(maps: list[MapDefinition], offset: int) -> tuple:
    """Users of the stored axis at ``offset`` with everything that decides how they read it."""
    out = []
    for m in maps:
        for axis, at, n in (('X', m.axis_x_offset, m.cols), ('Y', m.axis_y_offset, m.rows)):
            if at == offset and n > 1:
                out.append((m.name, m.offset, m.rows, m.cols, m.dtype, m.endian, axis, n))
    return tuple(sorted(out))


def make_clearance(maps: list[MapDefinition], data: bytes, image_digest: str, *, offset: int, points: int,
                   width: int, tables, origin: str, original: bytes | None = None) -> AxisClearance:
    """Record a technical check of the stored axis at ``offset``; every statement must match the image.

    Raises ValueError when the range, point count, cell width or users do not match what the tables read, or
    the origin is missing or generic: a clearance is never a blanket switch."""
    from .axis_refs import objects
    obj = next((o for o in objects(maps, data=data) if o.offset == offset), None)
    if obj is None:
        raise ValueError(f'Keine gespeicherte Achse bei 0x{offset:X}')
    if points != obj.points:
        raise ValueError(f'Punktzahl {points} passt nicht: die Nutzer lesen {obj.points} Punkte')
    if width not in (1, 2, 4):
        raise ValueError('Zellbreite muss 1, 2 oder 4 Byte sein')
    if offset + points * width > len(data):
        raise ValueError('Achse reicht über das Abbild hinaus')
    names = tuple(sorted(maps[i].name for i in obj.tables))
    if tuple(sorted(set(tables))) != names:
        raise ValueError('Zuordnung passt nicht: Nutzer dieser Achse sind ' + ', '.join(names))
    text = ' '.join(str(origin or '').split())
    if len(text) < MIN_ORIGIN_CHARS or text.lower().strip('.! ') in _GENERIC_ORIGINS:
        raise ValueError(f'Herkunft der Prüfung fehlt (mindestens {MIN_ORIGIN_CHARS} Zeichen, z. B. '
                         'geprüfte Definition, Adress- und Layoutprüfung im Programmcode)')
    return AxisClearance(offset, points, width, names, text, image_digest,
                         _digest(original if original is not None else data, offset, points, width),
                         _layout(maps, offset))


@dataclass
class WritePolicy:
    """Checks every transaction of one image (``BinaryImage.write_policy``) against the current tables."""
    maps_provider: object                      # callable returning the current list of tables
    clearances: list = field(default_factory=list)

    def maps(self) -> list[MapDefinition]:
        return list(self.maps_provider() or [])

    def conflicts(self, image, own, positions) -> list[Conflict]:
        """Conflicts of writing ``positions`` (tables ``own`` edited), with valid clearances applied."""
        maps = self.maps()
        data = image.materialize()
        found = conflicts(maps, own, positions, data)
        valid = [c for c in self.clearances if c.holds(image.digest, maps)]
        self.clearances[:] = valid             # a clearance that no longer holds is discarded
        cleared = {c.offset for c in valid}
        return [replace(c, identity=CLEARED) if c.refused and c.start in cleared else c for c in found]

    def approve(self, image, own, positions, confirm=None) -> tuple[Approval | None, list[Conflict]]:
        """(approval, conflicts) for writing ``positions``. Refused conflicts give no approval; other conflicts
        need ``confirm(conflicts)`` to return true."""
        found = self.conflicts(image, own, positions)
        if any(c.refused for c in found):
            return None, found
        if found and not (confirm and confirm(found)):
            return None, found
        return Approval(frozenset(positions), image.revision, tuple(_own(own)),
                        frozenset(c.key for c in found)), found

    def add_clearance(self, image, *, offset, points, width, tables, origin) -> AxisClearance:
        c = make_clearance(self.maps(), image.materialize(), image.digest, offset=offset, points=points,
                           width=width, tables=tables, origin=origin, original=image.original)
        self.clearances[:] = [x for x in self.clearances if x.offset != offset] + [c]
        return c

    def check(self, image, positions, approval: Approval | None) -> None:
        """Called by ``BinaryImage.commit`` right before the bytes are applied; raises EditRefused."""
        positions = set(positions)
        if approval is None:
            found = self.conflicts(image, None, positions)
            if found:
                raise EditRefused('Schreiben ohne Freigabe abgelehnt: ' + '; '.join(c.describe() for c in found[:3])
                                  + (f' (+{len(found) - 3})' if len(found) > 3 else ''))
            return
        if approval.revision != image.revision:
            raise EditRefused('Freigabe veraltet: das Abbild wurde seit der Vorschau geändert – erneut prüfen')
        if not positions <= approval.positions:
            raise EditRefused('Freigabe gilt nicht für alle zu schreibenden Bytes – erneut prüfen')
        found = self.conflicts(image, approval.own, positions)
        if any(c.refused for c in found):
            raise EditRefused(refusal_text(found))
        new = [c for c in found if c.key not in approval.confirmed]
        if new:
            raise EditRefused('Freigabe veraltet: betroffene Objekte haben sich seit der Bestätigung geändert – '
                              + '; '.join(c.describe() for c in new[:3]))


def silent_approval(image, own, positions) -> Approval | None:
    """Approval where no question can be asked (a dialog or model without a guard): only when no other object
    is affected. None also when the image has no policy - ``commit`` then has nothing to check; otherwise
    ``commit`` refuses the write without approval."""
    policy = getattr(image, 'write_policy', None)
    if policy is None:
        return None
    return policy.approve(image, own, positions)[0]


def guarded(image, maps_provider) -> WritePolicy:
    """Attach a write policy to ``image`` (scripts and tools that know the tables use this too)."""
    policy = WritePolicy(maps_provider)
    image.write_policy = policy
    return policy


__all__ = ['AXIS_POINT_BYTES', 'Approval', 'AxisClearance', 'CLEARED', 'Conflict', 'EditRefused', 'WritePolicy',
           'allowed', 'conflicts', 'confirmation_text', 'guarded', 'make_clearance', 'refusal_text', 'silent_approval',
           'update_positions', 'written_positions']
