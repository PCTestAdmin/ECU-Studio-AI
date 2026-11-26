"""Shared-axis identity states and edit safety (quality phase 5, synthetic only).

Identity: a common storage address named by a definition is 'eindeutig gemeinsam'; one named by code or
data structure is 'plausibel gemeinsam' only when the axis is applied and no other stored axis holds the
same bytes; equal bytes at another address are 'wertgleich' (never one object); everything else is
'unbekannt'. Equal values never make a shared identity.

Editing: a cell edit writes only the selected cells of the selected table; bytes of other objects it
would hit are listed with all users and need a confirmation, bytes of an axis of unknown identity are
refused; undo/redo restore exactly; the original stays unchanged.
"""
import struct

from ecu_studio.core import axis_refs as R
from ecu_studio.core.edit_guard import Conflict, allowed, conflicts, written_positions
from ecu_studio.core.editing import plan_surface_edit
from ecu_studio.core.map_pack import make_pack, parse_pack
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.workflows import apply_batch

AXIS = [0, 500, 1000, 2000]


def image_with(*axes):
    data = bytearray(range(256)) * 16
    for at, values in axes:
        data[at:at + 2 * len(values)] = struct.pack(f'<{len(values)}H', *values)
    return bytes(data)


def table(name, offset, x=None, source='heuristic', axes_x=AXIS, **kw):
    return MapDefinition(name=name, offset=offset, rows=4, cols=4, dtype='u8', source=source,
                         axis_x_offset=x, axes_x=list(axes_x), **kw)


def obj(objs, at):
    return next(o for o in objs if o.offset == at)


def test_definition_address_is_unique_identity():
    data = image_with((0x900, AXIS))
    maps = [table('A', 0x100, 0x900, 'a2l'), table('B', 0x200, 0x900, 'a2l')]
    assert obj(R.objects(maps, data=data), 0x900).identity == R.SURE


def test_code_address_with_unique_applied_axis_is_plausible():
    data = image_with((0x900, AXIS))
    maps = [table('A', 0x100, 0x900), table('B', 0x200, 0x900)]
    o = obj(R.objects(maps, data=data), 0x900)
    assert o.identity == R.PLAUSIBLE and o.copies == ()
    assert R.PLAUSIBLE in o.describe()


def test_value_equal_copy_makes_a_code_group_unknown_and_never_merges():
    data = image_with((0x900, AXIS), (0xA00, AXIS))
    maps = [table('A', 0x100, 0x900), table('B', 0x200, 0x900), table('C', 0x300, 0xA00)]
    objs = R.objects(maps, data=data)
    shared, single = obj(objs, 0x900), obj(objs, 0xA00)
    assert shared.identity == R.UNKNOWN and shared.copies == (0xA00,)
    assert 'wertgleiche Kopie' in shared.identity_reason
    # equal bytes elsewhere: two objects, related only as value-equal
    assert single.identity == R.VALUE_EQUAL and single.tables == [2] and not single.shared


def test_unapplied_or_contradicted_axis_is_unknown():
    blank = [7, 7, 7, 7]
    data = image_with((0x900, blank))
    maps = [table('A', 0x100, 0x900, axes_x=blank), table('B', 0x200, 0x900, axes_x=blank)]
    assert obj(R.objects(maps, data=data), 0x900).identity == R.UNKNOWN
    bad = [table('A', 0x100, 0x900), MapDefinition(name='B', offset=0x200, rows=1, cols=8, dtype='u8',
                                                    source='heuristic', axis_x_offset=0x900)]
    assert obj(R.objects(bad, data=image_with((0x900, AXIS))), 0x900).identity == R.UNKNOWN


def test_without_bytes_a_code_group_is_not_called_plausible():
    maps = [table('A', 0x100, 0x900), table('B', 0x200, 0x900)]
    assert obj(R.objects(maps), 0x900).identity == R.UNKNOWN
    counts = R.summary(maps, R.objects(maps, data=image_with((0x900, AXIS))))
    assert counts['identity_plausible'] == 1 and counts['identity_unknown'] == 0


def test_edit_of_own_cells_has_no_foreign_conflict_and_writes_only_them():
    data = image_with((0x900, AXIS))
    maps = [table('A', 0x100, 0x900), table('B', 0x200, 0x900)]
    image = BinaryImage(data)
    cells = [(0, 0), (1, 2)]
    assert conflicts(maps, maps[0], written_positions(maps[0], cells), data) == []
    preview = plan_surface_edit(image, maps[0], 'add', cells=cells, amount=3)
    apply_batch(image, preview)
    changed = {i for i in range(image.size) if image.byte(i) != data[i]}
    assert changed and changed <= written_positions(maps[0], cells)
    assert image.original == data                        # original untouched
    assert image.read(0x900, 8) == data[0x900:0x908]     # shared axis untouched
    assert image.undo() and image.materialize() == data
    assert image.redo() and {i for i in range(image.size) if image.byte(i) != data[i]} == changed


def test_overlapping_table_lists_the_other_table_and_needs_confirmation():
    data = image_with()
    maps = [table('A', 0x100), table('B', 0x108)]
    found = conflicts(maps, maps[0], written_positions(maps[0], [(2, 1)]), data)
    assert [(c.kind, c.tables) for c in found] == [('Werte', ('B',))]
    assert '0x109' in found[0].describe() and not found[0].refused
    asked = []
    assert allowed(found, lambda c: asked.append(c) or False) is False and asked == [found]
    assert allowed(found, lambda c: True) is True


def test_cells_on_a_shared_axis_show_all_users_and_refuse_unknown_identity():
    # a (wrongly placed) table A whose last row lies on the axis that B and C read at 0x10C
    data = image_with((0x10C, AXIS))
    maps = [table('A', 0x100), table('B', 0x200, 0x10C), table('C', 0x300, 0x10C)]
    found = [c for c in conflicts(maps, maps[0], written_positions(maps[0], [(0, 0), (0, 1), (0, 2), (3, 0)]), data)
             if c.kind == 'Achse']
    assert len(found) == 1 and found[0].tables == ('B', 'C') and found[0].identity == R.PLAUSIBLE
    assert found[0].hit == (0x10C, 0x10C) and not found[0].refused
    assert 'B, C' in found[0].describe() and '0x10C' in found[0].describe()
    # the same layout with a value-equal copy elsewhere: identity unknown -> refused, confirm never asked
    data2 = image_with((0x10C, AXIS), (0xA00, AXIS))
    maps.append(table('D', 0x400, 0xA00))   # another table reads the same bytes at another address
    found2 = conflicts(maps, maps[0], written_positions(maps[0], [(0, 0), (0, 1), (0, 2), (3, 0)]), data2)
    axis = [c for c in found2 if c.kind == 'Achse'][0]
    assert axis.refused
    assert allowed(found2, lambda c: (_ for _ in ()).throw(AssertionError('asked'))) is False


def test_axis_definition_edit_changes_only_the_selected_table():
    data = image_with((0x900, AXIS))
    maps = [table('A', 0x100, 0x900), table('B', 0x200, 0x900)]
    image = BinaryImage(data)
    maps[0].axes_x = [1, 2, 3, 4]       # what the axis dialog stores: definition only
    assert maps[1].axes_x == AXIS and image.materialize() == data and image.dirty_bytes == 0


def test_map_pack_round_trip_keeps_shared_axes_and_groups():
    data = image_with((0x900, AXIS))
    maps = [table('A', 0x100, 0x900, 'a2l'), table('B', 0x200, 0x900, 'a2l'), table('C', 0x300, 0xA00, 'a2l')]
    pack = make_pack(BinaryImage(data), maps)
    again = parse_pack(pack.document).maps()
    assert [(m.name, m.axis_x_offset) for m in again] == [(m.name, m.axis_x_offset) for m in maps]
    assert pack.document['axis_groups'] == parse_pack(pack.document).document['axis_groups']
    assert [g['axis_offset'] for g in pack.document['axis_groups']] == [0x900]


def test_table_cell_edit_asks_the_guard_before_writing():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ecu_studio.ui.views import MapTableModel
    data = image_with()
    image, m = BinaryImage(data), table('A', 0x100)
    model = MapTableModel()
    model.set_map(image, m)
    asked = []
    model.guard = lambda t, pos: asked.append((t, sorted(pos))) or False
    assert model.setData(model.index(1, 2), '9') is False
    assert image.dirty_bytes == 0 and asked == [(m, [0x106])]
    model.guard = lambda t, pos: True
    assert model.setData(model.index(1, 2), '9') and image.byte(0x106) == 9 and image.original == data


def test_conflict_record_is_plain_data():
    c = Conflict('Werte', 0x10, 0x20, ('X',), '', (0x12, 0x13))
    assert not c.refused and 'X' in c.describe()
