"""Table -> axis reference -> axis object: shared only by storage address, never by look-alike values
(quality phase 3, synthetic)."""
from ecu_studio.core import axis_refs as R
from ecu_studio.core.function_id import AXIS, identify, relations
from ecu_studio.core.model import MapDefinition


def table(name, offset, rows=4, cols=4, source='a2l', x=None, y=None, axes_x=(), function='', **kw):
    return MapDefinition(name=name, offset=offset, rows=rows, cols=cols, dtype='u8', source=source,
                         axis_x_offset=x, axis_y_offset=y, axes_x=list(axes_x), function=function, **kw)


def test_one_axis_used_by_several_tables_is_one_object():
    maps = [table('A', 0x100, x=0x900), table('B', 0x200, x=0x900), table('C', 0x300, x=0x900, y=0x940)]
    objs = R.objects(maps)
    shared = [o for o in objs if o.offset == 0x900]
    assert len(shared) == 1 and shared[0].shared and shared[0].tables == [0, 1, 2]
    assert not shared[0].contradictory
    assert [o.offset for o in objs] == [0x900, 0x940]
    assert R.index(objs)[2] == objs


def test_equal_points_at_different_addresses_stay_two_objects():
    pts = [0, 10, 20, 30]
    maps = [table('A', 0x100, x=0x900, axes_x=pts), table('B', 0x200, x=0xA00, axes_x=pts)]
    objs = R.objects(maps)
    assert len(objs) == 2 and not any(o.shared for o in objs)
    assert not [r for r in relations(maps) if r.kind == AXIS]


def test_different_lengths_or_cell_types_at_one_address_are_contradictions():
    maps = [table('A', 0x100, cols=4, x=0x900), table('B', 0x200, cols=8, x=0x900)]
    obj = R.objects(maps)[0]
    assert obj.contradictory and 'Punktzahlen' in obj.issues[0]
    defs = [MapDefinition(name='AX', offset=0x900, rows=1, cols=4, dtype='u8', source='a2l'),
            MapDefinition(name='AX', offset=0x900, rows=1, cols=4, dtype='s16', source='a2l')]
    obj2 = R.objects(maps[:1] + [table('C', 0x300, x=0x900)], defs)[0]
    assert any('Zelltypen' in t for t in obj2.issues) and obj2.dtype == ''


def test_cell_type_of_the_axis_comes_from_its_definition():
    maps = [table('A', 0x100, x=0x900), table('B', 0x200, x=0x900)]
    defs = [MapDefinition(name='AX', offset=0x900, rows=1, cols=4, dtype='s16', endian='little', source='a2l')]
    obj = R.objects(maps, defs)[0]
    assert (obj.dtype, obj.endian) == ('s16', 'little')
    assert 's16 little' in obj.describe()


def test_tricore_aliases_name_the_same_object():
    maps = [table('A', 0x100, x=0x1900), table('B', 0x200, x=0x1900)]
    obj = R.objects(maps, ecu_base=0x80000000)[0]
    assert obj.aliases == (0x80001900, 0xA0001900)
    assert len(R.objects(maps, ecu_base=0xA0000000)) == 1


def test_fixed_and_unresolved_axes_are_not_guessed():
    fixed = table('F', 0x100, axes_x=[0, 1, 2, 3], axes_y=[0, 5, 9, 12])   # definition, points, no address
    open_ = table('O', 0x200, source='heuristic', axes_x=[0, 1, 2, 3])  # found by pattern, no address
    refs = R.references([fixed, open_])
    assert {(r.table, r.status) for r in refs} >= {(0, R.FIXED), (1, R.OPEN)}
    assert R.objects([fixed, open_]) == []
    assert 'ungeklärt' in [r for r in refs if r.table == 1][0].describe()
    counts = R.summary([fixed, open_])
    assert counts[R.FIXED] == 2 and counts[R.OPEN] == 2 and counts['objects'] == 0


def test_axis_inside_a_users_values_is_reported():
    maps = [table('A', 0x100, x=0x104), table('B', 0x200, x=0x104)]
    assert any('Wertebereich' in t for t in R.objects(maps)[0].issues)


def test_a_wrongly_shared_axis_does_not_spread_a_function():
    """Users disagree on the axis length: the axis is no evidence that both tables share a function."""
    maps = [table('A', 0x100, cols=4, x=0x900, function='FN_A', verified=True),
            table('B', 0x200, cols=8, x=0x900, source='heuristic')]
    h = identify(maps, relations(maps))[1]
    assert h.function == '' and h.contradictions


def test_shared_unapplied_axis_is_marked_not_hidden():
    """Quality phase 4: an axis whose points are all equal (unapplied) exists as value-equal copies; a common
    address stays a shared object, but it is marked as weaker evidence."""
    blank = [0, 0, 0, 0]
    maps = [table('A', 0x100, x=0x900, axes_x=blank), table('B', 0x200, x=0x900, axes_x=blank),
            table('C', 0x300, x=0x940, axes_x=[0, 10, 20, 30]), table('D', 0x400, x=0x940, axes_x=[0, 10, 20, 30])]
    objs = {o.offset: o for o in R.objects(maps)}
    assert objs[0x900].shared and objs[0x900].unapplied and 'nicht bedatet' in objs[0x900].describe()
    assert objs[0x940].shared and not objs[0x940].unapplied and 'nicht bedatet' not in objs[0x940].describe()
    assert R.summary(maps)['shared_unapplied'] == 1
    # no values known for a user: not called unapplied
    assert not R.objects([table('E', 0x100, x=0x900), table('F', 0x200, x=0x900, axes_x=blank)])[0].unapplied
