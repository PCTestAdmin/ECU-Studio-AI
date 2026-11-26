"""Quality phase 6: the write check builds only the axis objects near a write (objects(near=...)). Those objects
must be exactly the ones of the full list (same users, issues, identity and copies), and none that the write
touches may be missing. Synthetic tables only."""
import random

from ecu_studio.core import axis_refs as R
from ecu_studio.core.edit_guard import conflicts
from ecu_studio.core.model import MapDefinition


def _fields(o):
    return (o.offset, o.points, o.users, o.sources, o.name, o.dtype, o.endian, o.aliases, o.issues, o.unapplied,
            o.identity, o.identity_reason, o.copies, o.width, o.type_state, o.type_sources, o.span_points, o.step)


def _world(seed):
    rnd = random.Random(seed)
    data = bytearray(rnd.randrange(256) for _ in range(0x4000))
    axes = [0x100 + 0x20 * k for k in range(40)]
    for k in range(0, 40, 4):                       # value-equal copies at several addresses
        data[axes[k]:axes[k] + 16] = data[axes[0]:axes[0] + 16]
    maps = []
    for i in range(120):
        rows, cols = rnd.choice([(1, 8), (4, 8), (8, 8), (6, 4)])
        at_x = rnd.choice(axes + [None])
        at_y = rnd.choice(axes + [None]) if rows > 1 else None
        source = rnd.choice(['definition', 'scanner', 'tricore-code'])
        maps.append(MapDefinition(f'T{i}', 0x1000 + 0x40 * i, rows, cols, dtype='u16',
                                  axis_x_offset=at_x, axis_y_offset=at_y,
                                  axes_x=[rnd.choice([0, 1])] * cols if rnd.random() < .1 else list(range(cols)),
                                  axes_y=list(range(rows)), source=source, verified=source == 'definition'))
    maps.append(MapDefinition('Innen', 0x100, 4, 8, dtype='u16', axis_x_offset=0x100, source='scanner'))
    return maps, bytes(data)


def test_near_objects_equal_the_full_list():
    for seed in range(5):
        maps, data = _world(seed)
        full = R.objects(maps, data=data)
        rnd = random.Random(100 + seed)
        for _ in range(40):
            lo = rnd.randrange(0, 0x700)
            hi = lo + rnd.randrange(0, 0x40)
            near = R.objects(maps, data=data, near=(lo, hi))
            by_offset = {o.offset: o for o in full}
            assert all(_fields(o) == _fields(by_offset[o.offset]) for o in near)
            touched = {o.offset for o in full if o.offset <= hi and o.end > lo}
            assert touched <= {o.offset for o in near}


def test_objects_users_match_references():
    maps, data = _world(7)
    stored = sorted((r.offset, r.table, r.axis) for r in R.references(maps) if r.status == R.STORED)
    assert stored == sorted((o.offset, t, a) for o in R.objects(maps, data=data) for t, a in o.users)


def test_write_conflicts_unchanged_by_the_window():
    """conflicts() with the window gives what a full rebuild gives for the same write."""
    maps, data = _world(3)
    full = R.objects(maps, data=data)
    for o in full[:15]:
        positions = {o.offset + 1}
        got = [(c.kind, c.start, c.end, c.identity) for c in conflicts(maps, None, positions, data) if c.kind == 'Achse']
        want = [('Achse', x.offset, x.end, x.identity if x.shared else '')
                for x in full if x.offset <= o.offset + 1 < x.end]
        assert got == want


def test_large_equal_groups_list_a_bounded_number_of_copies():
    data = bytearray(0x10000)
    maps = [MapDefinition(f'T{i}', 0x8000 + 0x40 * i, 4, 4, dtype='u16', axis_x_offset=0x100 + 0x10 * i,
                          axes_x=[0, 1, 2, 3], source='scanner') for i in range(50)]
    objs = R.objects(maps, data=bytes(data))
    assert all(len(o.copies) == R.COPIES_LISTED and o.offset not in o.copies for o in objs)
    assert all(o.identity == R.VALUE_EQUAL for o in objs)


def test_value_conflicts_equal_a_brute_force_check_also_with_strides():
    """The cheap pre-test in conflicts() (rows x cols x widest cell) must never skip a hit table; tables with
    strides are longer than that and always take the exact length."""
    from dataclasses import replace
    maps, data = _world(11)
    strided = [replace(maps[k], name=f'S{k}', offset=0x1000 + 0x40 * k, major_stride_bits=64 * 8,
                       axis_x_offset=None, axis_y_offset=None) for k in range(0, 40, 5)]
    maps = maps + strided
    rnd = random.Random(5)
    for _ in range(300):
        lo = rnd.randrange(0x1000, 0x3000)
        positions = {lo, lo + rnd.randrange(0, 3)}
        got = sorted((c.start, c.end) for c in conflicts(maps, None, positions, data) if c.kind == 'Werte')
        want = sorted((m.offset, m.offset + m.length) for m in maps
                      if any(m.offset <= p < m.offset + m.length for p in positions))
        assert got == want
    assert any(m.length > m.rows * m.cols * 8 for m in strided)
