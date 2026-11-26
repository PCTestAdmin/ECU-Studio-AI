"""Axis cell widths in the write check (1.21.0-rc2 release fix). Synthetic images only; no private firmware.

Before the fix the write check took every stored axis as 2 bytes per point: the upper half of a 32-bit or float
axis was not protected, and a technical clarification stored a cell width without using it. Now an axis covers
its largest point count x its cell width (stated by its users or the definition); an unknown width is protected
with the widest cell the program can represent (4 bytes), contradicting widths with the widest one and refused
for a shared axis. The value type of a table is never taken for its axes.
"""
import json
import random
import struct
from dataclasses import replace

import pytest

from ecu_studio.core import axis_refs as R
from ecu_studio.core.a2l import parse_a2l
from ecu_studio.core.edit_guard import (CLEARED, EditRefused, axis_range, conflicts, guarded, make_clearance,
                                        value_length)
from ecu_studio.core.map_pack import make_pack, parse_pack
from ecu_studio.core.model import BinaryImage, MapDefinition, load_project, save_project
from ecu_studio.core.storage import canonical_digest
from ecu_studio.core.xdf import read_xdf

AX = 0x100                     # stored axis address
ORIGIN = 'Adress- und Layoutprüfung im Programmcode: Aufrufe laden diese Achse mit 4 Punkten'


def image(size=0x1000):
    rnd = random.Random(size)                   # no period: equal bytes only where a test copies them
    return BinaryImage(bytes(rnd.randrange(256) for _ in range(size)))


def user(name, offset, dtype='', at=AX, cols=4, source='heuristic', **kw):
    """A 2 x cols u8 table reading its X axis (cols points) at ``at`` with axis cell type ``dtype``."""
    return MapDefinition(name=name, offset=offset, rows=2, cols=cols, dtype='u8', source=source,
                         axis_x_offset=at, axis_x_dtype=dtype, axis_x_type_source='Test' if dtype else '', **kw)


def axis_conflicts(maps, positions, data):
    return [c for c in conflicts(maps, None, positions, data) if c.kind == 'Achse']


@pytest.mark.parametrize('dtype, width', [('u8', 1), ('s8', 1), ('u16', 2), ('s16', 2), ('u32', 4), ('s32', 4),
                                          ('f32', 4)])
def test_every_cell_type_protects_exactly_its_stored_bytes(dtype, width):
    img = image()
    maps = [user('A', 0x400, dtype)]
    data = img.materialize()
    o = R.objects(maps, data=data)[0]
    assert (o.width, o.type_state) == (width, R.TYPE_STATED) and axis_range(o) == (AX, AX + 4 * width)
    assert axis_conflicts(maps, {AX + 4 * width - 1}, data)            # last byte of the last point
    assert not axis_conflicts(maps, {AX + 4 * width}, data)            # first byte behind the axis


def test_sixteen_bit_axis_protection_is_unchanged():
    img = image()
    maps = [user('A', 0x400, 'u16')]
    found = axis_conflicts(maps, {AX + 7}, img.materialize())
    assert [(c.start, c.end) for c in found] == [(AX, AX + 8)]


@pytest.mark.parametrize('dtype', ['u32', 's32', 'f32'])
def test_write_into_the_formerly_unprotected_upper_half_of_a_32_bit_axis_is_a_conflict(dtype):
    img = image()
    maps = [user('A', 0x400, dtype), user('B', 0x500, dtype)]       # shared, plausible
    policy = guarded(img, lambda: maps)
    for p in range(AX + 8, AX + 16):                                 # bytes 8..15: points 3 and 4
        with pytest.raises(EditRefused):
            img.write(p, b'\x00')                                    # no approval: refused
        approval, found = policy.approve(img, [], {p}, confirm=lambda f: False)
        assert approval is None and [c.kind for c in found] == ['Achse'] and found[0].end == AX + 16
    assert img.dirty_bytes == 0 and img.materialize() == img.original


def test_unknown_width_is_protected_with_the_widest_cell_and_named():
    img = image()
    maps = [user('A', 0x400, '')]                                    # e.g. a project of an older version
    data = img.materialize()
    o = R.objects(maps, data=data)[0]
    assert o.type_state == R.TYPE_UNKNOWN and o.width == R.AXIS_MAX_CELL == 4 and o.end == AX + 16
    found = axis_conflicts(maps, {AX + 15}, data)
    assert found and 'Zellbreite der Achse unbekannt' in found[0].describe()
    assert 'Zelltyp nicht belegt' in o.describe()


def test_unknown_width_of_a_shared_axis_with_a_copy_is_refused_until_clarified():
    img = image()
    data = bytearray(img.original)
    data[0x200:0x210] = data[AX:AX + 16]                             # value-equal bytes elsewhere
    img = BinaryImage(bytes(data))
    maps = [user('A', 0x400), user('B', 0x500), user('C', 0x600, at=0x200)]
    policy = guarded(img, lambda: maps)
    approval, found = policy.approve(img, [], {AX + 12}, confirm=lambda f: True)
    assert approval is None and any(c.refused for c in found)       # a second confirmation does not help


def test_contradicting_widths_are_shown_protected_widely_and_never_cleared():
    img = image()
    maps = [user('A', 0x400, 'u16'), user('B', 0x500, 'u32')]
    data = img.materialize()
    o = R.objects(maps, data=data)[0]
    assert o.type_state == R.TYPE_CONTRADICTED and o.width == 4 and o.end == AX + 16
    assert o.identity == R.UNKNOWN and any('Zellbreiten widersprechen' in i for i in o.issues)
    policy = guarded(img, lambda: maps)
    approval, found = policy.approve(img, [], {AX + 12}, confirm=lambda f: True)
    assert approval is None and found[0].refused and 'widersprechen' in found[0].describe()
    for width in (2, 4):
        with pytest.raises(ValueError, match='Widerspruch'):
            policy.add_clearance(img, offset=AX, points=4, width=width, tables=['A', 'B'], origin=ORIGIN)
    assert policy.clearances == []


def test_contradicting_point_counts_protect_the_largest_one():
    img = image()
    maps = [user('A', 0x400, 'u16', cols=4), user('B', 0x500, 'u16', cols=6), user('C', 0x600, 'u16', cols=4)]
    o = R.objects(maps, data=img.materialize())[0]
    assert o.points == 4 and o.span_points == 6 and o.end == AX + 12   # majority 4, protection 6 points
    found = axis_conflicts(maps, {AX + 11}, img.materialize())
    assert found and found[0].refused


def test_shared_axis_lists_every_user():
    img = image()
    maps = [user(n, 0x400 + 0x40 * i, 'u32', source='a2l') for i, n in enumerate('ABCD')]
    found = axis_conflicts(maps, {AX + 13}, img.materialize())
    assert len(found) == 1 and found[0].tables == ('A', 'B', 'C', 'D') and found[0].identity == R.SURE


def test_value_equal_axes_at_different_addresses_stay_separate():
    data = bytearray(image().original)
    data[0x200:0x210] = data[AX:AX + 16]
    img = BinaryImage(bytes(data))
    maps = [user('A', 0x400, 'u32'), user('B', 0x500, 'u32', at=0x200)]
    objs = {o.offset: o for o in R.objects(maps, data=img.materialize())}
    assert set(objs) == {AX, 0x200} and all(not o.shared for o in objs.values())
    assert objs[AX].identity == R.VALUE_EQUAL and 0x200 in objs[AX].copies
    found = axis_conflicts(maps, {0x20C}, img.materialize())
    assert [c.tables for c in found] == [('B',)]                    # only B's own axis


def test_copy_search_compares_the_whole_cell_width():
    data = bytearray(image().original)
    data[0x200:0x208] = data[AX:AX + 8]                              # equal first half only
    img = BinaryImage(bytes(data))
    maps = [user('A', 0x400, 'u32'), user('B', 0x500, 'u32'), user('C', 0x600, 'u32', at=0x200)]
    o = {x.offset: x for x in R.objects(maps, data=img.materialize())}[AX]
    assert o.copies == () and o.identity == R.PLAUSIBLE              # 16 bytes compared, not 8


def test_a_stated_width_cannot_be_narrowed_by_a_clarification():
    data = bytearray(image().original)
    data[0x200:0x210] = data[AX:AX + 16]
    img = BinaryImage(bytes(data))
    maps = [user('A', 0x400, 'u32'), user('B', 0x500, 'u32'), user('C', 0x600, 'u32', at=0x200)]
    policy = guarded(img, lambda: maps)
    with pytest.raises(ValueError, match='belegten Zellbreite 4'):
        policy.add_clearance(img, offset=AX, points=4, width=2, tables=['A', 'B'], origin=ORIGIN)
    policy.add_clearance(img, offset=AX, points=4, width=4, tables=['A', 'B'], origin=ORIGIN)
    approval, found = policy.approve(img, [], {AX + 14}, confirm=lambda f: True)
    assert approval and found[0].identity == CLEARED and (found[0].start, found[0].end) == (AX, AX + 16)


def test_a_clarified_unknown_width_must_not_reach_into_the_users_values():
    img = image()
    # A reads its axis right in front of its own values: 4 points x 2 bytes end exactly at 0x108
    maps = [user('A', AX + 8), user('B', 0x500)]
    data = bytearray(img.original)
    data[0x300:0x310] = data[AX:AX + 16]
    img = BinaryImage(bytes(data))
    maps.append(user('C', 0x600, at=0x300))
    policy = guarded(img, lambda: maps)
    with pytest.raises(ValueError, match='reicht die Achse in die Werte von A'):
        policy.add_clearance(img, offset=AX, points=4, width=4, tables=['A', 'B'], origin=ORIGIN)
    clearance = policy.add_clearance(img, offset=AX, points=4, width=2, tables=['A', 'B'], origin=ORIGIN)
    assert clearance.end == AX + 8
    # the clarified width is used by the range check: the axis now covers exactly 8 bytes
    found = policy.conflicts(img, [], {AX + 7})
    assert [(c.start, c.end, c.identity) for c in found if c.kind == 'Achse'] == [(AX, AX + 8, CLEARED)]
    assert not [c for c in policy.conflicts(img, [maps[0]], {AX + 8}) if c.kind == 'Achse']


def test_clarification_expires_with_layout_width_or_firmware():
    def setup():
        data = bytearray(image().original)
        data[0x300:0x310] = data[AX:AX + 16]
        img = BinaryImage(bytes(data))
        maps = [user('A', 0x400), user('B', 0x500), user('C', 0x600, at=0x300)]
        policy = guarded(img, lambda: maps)
        policy.add_clearance(img, offset=AX, points=4, width=2, tables=['A', 'B'], origin=ORIGIN)
        return img, maps, policy

    img, maps, policy = setup()
    maps[1].rows = 3                                                  # layout of a user changed
    assert any(c.refused for c in policy.conflicts(img, [], {AX + 2})) and policy.clearances == []
    img, maps, policy = setup()
    maps[0].axis_x_dtype, maps[0].axis_x_type_source = 'u32', 'Definition'   # axis cell width changed
    found = policy.conflicts(img, [], {AX + 2})
    assert policy.clearances == [] and found and all(c.identity != CLEARED for c in found)
    img, maps, policy = setup()
    clearance = policy.clearances[0]
    other = BinaryImage(img.original[:-1] + b'\x01')                  # other firmware
    assert clearance.holds(img.digest, maps) and not clearance.holds(other.digest, maps)


def test_fixed_axis_without_address_claims_no_bytes():
    img = image()
    fixed = MapDefinition(name='F', offset=0x400, rows=2, cols=4, dtype='u8', source='a2l', axes_x=[1, 2, 3, 4])
    assert [r.status for r in R.references([fixed]) if r.axis == 'X'] == [R.FIXED] and R.objects([fixed]) == []
    assert not axis_conflicts([fixed], set(range(0, 0x400)), img.materialize())


def test_axis_at_the_end_of_the_image():
    img = image(0x200)
    ok = user('A', 0x10, 'u32', at=0x200 - 16)
    ok.validate(img.size)
    found = axis_conflicts([ok], {img.size - 1}, img.materialize())
    assert found and found[0].end == img.size
    with pytest.raises(ValueError, match='über das Ende'):
        user('B', 0x10, 'u32', at=0x200 - 12).validate(img.size)      # 4 x 4 bytes do not fit
    unknown = user('C', 0x10, at=0x200 - 8)                           # unknown width: still checked, no crash
    unknown.validate(img.size)
    assert axis_conflicts([unknown], {img.size - 1}, img.materialize())


@pytest.mark.parametrize('changes', [dict(axis_x_offset=-1), dict(axis_x_offset=0x1000),
                                     dict(axis_x_dtype='u64'), dict(axis_x_dtype='f64'), dict(axis_x_step=-2),
                                     dict(axis_x_dtype='u32', axis_x_step=2)])
def test_invalid_axis_address_type_or_step_is_refused(changes):
    with pytest.raises(ValueError):
        replace(user('A', 0x400, 'u16'), **changes).validate(0x1000)


def test_invalid_clarification_statements_are_refused():
    img = image()
    data = bytearray(img.original)
    data[0x300:0x310] = data[AX:AX + 16]
    img = BinaryImage(bytes(data))
    maps = [user('A', 0x400), user('B', 0x500), user('C', 0x600, at=0x300)]
    policy = guarded(img, lambda: maps)
    for bad in (dict(points=5), dict(points=0), dict(width=3), dict(width=8), dict(offset=AX + 1),
                dict(offset=img.size + 4), dict(tables=['A']), dict(origin='ok'), dict(points='4')):
        args = dict(offset=AX, points=4, width=2, tables=['A', 'B'], origin=ORIGIN) | bad
        with pytest.raises(ValueError):
            policy.add_clearance(img, **args)
    assert policy.clearances == []


def test_overlapping_axis_and_table_are_both_reported():
    img = image()
    maps = [user('A', 0x400, 'u32'), MapDefinition('T', AX + 12, 1, 4, 'u8')]
    found = conflicts(maps, None, {AX + 13}, img.materialize())
    assert sorted(c.kind for c in found) == ['Achse', 'Werte']


def test_open_wider_value_type_of_a_table_is_protected():
    m = MapDefinition('W', 0x400, 1, 4, 'u16', dtype_alternatives=['u32', 's16'])
    assert value_length(m) == 16
    assert conflicts([m], None, {0x40F}, image().materialize())


def test_transaction_with_one_unprotected_part_writes_nothing_and_undo_redo_is_exact():
    img = image()
    maps = [user('A', 0x400, 'u32'), user('B', 0x500, 'u32')]
    policy = guarded(img, lambda: maps)
    approval, _ = policy.approve(img, [maps[0]], {0x400}, confirm=lambda f: True)
    mixed = [(0x400, img.byte(0x400), 1), (AX + 12, img.byte(AX + 12), 1)]     # second part: upper axis half
    with pytest.raises(EditRefused):
        img.commit(mixed, approval=approval)
    assert img.dirty_bytes == 0
    edits = {AX + 12: 0x11, AX + 13: 0x22}
    approval, found = policy.approve(img, [], set(edits), confirm=lambda f: True)
    assert approval and found[0].end == AX + 16
    img.commit([(p, img.byte(p), v) for p, v in edits.items()], approval=approval)
    after = img.materialize()
    assert img.undo() and img.materialize() == img.original and img.dirty_bytes == 0
    assert img.redo() and img.materialize() == after
    assert img.original == image().original                           # the original never changes


def test_batch_area_and_hex_paths_use_the_same_range():
    from ecu_studio.core.editing import plan_surface_edit
    from ecu_studio.core.workflows import apply_batch
    img = image()
    table = MapDefinition('T', AX + 8, 1, 4, 'u16', source='a2l', verified=True)   # values on the upper half
    maps = [user('A', 0x400, 'u32'), table]
    policy = guarded(img, lambda: maps)
    preview = plan_surface_edit(img, table, 'set', cells=[[0, 0]], amount=7)
    with pytest.raises(EditRefused):
        apply_batch(img, preview)                                     # area/batch path without approval
    with pytest.raises(EditRefused):
        img.write(AX + 9, b'\x00')                                    # hex path without approval
    approval, found = policy.approve(img, [table], {AX + 8, AX + 9}, confirm=lambda f: True)
    assert approval and [c.kind for c in found] == ['Achse']
    apply_batch(img, preview, approval=approval)
    assert struct.unpack('>H', img.read(AX + 8, 2))[0] == 7


def test_projects_and_map_packs_without_axis_type_load_as_unknown(tmp_path):
    img = image()
    maps = [user('A', 0x400, 'u16'), user('B', 0x500, 'u16')]
    target = tmp_path / 'alt.ecustudio'
    save_project(str(target), img, maps, [], '')
    payload = json.loads(target.read_text(encoding='utf-8'))
    for record in payload['maps']:                                    # as written by 1.21.0-rc1 or older
        for key in ('axis_x_dtype', 'axis_y_dtype', 'axis_x_type_source', 'axis_y_type_source',
                    'axis_x_step', 'axis_y_step'):
            record.pop(key)
    payload.pop('integrity_sha256')
    target.write_text(json.dumps(payload), encoding='utf-8')
    _, loaded, _, _ = load_project(str(target))
    assert [(m.axis_x_dtype, m.axis_x_offset) for m in loaded] == [('', AX), ('', AX)]
    o = R.objects(loaded, data=img.materialize())[0]
    assert o.type_state == R.TYPE_UNKNOWN and o.end == AX + 16       # not taken as 16 bit

    doc = make_pack(img, maps).document
    for record in doc['maps']:
        for key in ('axis_x_dtype', 'axis_y_dtype', 'axis_x_type_source', 'axis_y_type_source',
                    'axis_x_step', 'axis_y_step'):
            record.pop(key)
    doc.pop('integrity_sha256')
    doc['integrity_sha256'] = canonical_digest(doc)
    old = parse_pack(doc)
    assert old.unknown_fields == () and all(m.axis_x_dtype == '' for m in old.maps())
    new = make_pack(img, maps)
    assert [m.axis_x_dtype for m in new.maps()] == ['u16', 'u16']     # round trip keeps the type


A2L = '''/begin PROJECT P "" /begin MODULE M ""
/begin MOD_COMMON "" BYTE_ORDER MSB_FIRST ALIGNMENT_BYTE 1 ALIGNMENT_WORD 1 ALIGNMENT_LONG 1
  ALIGNMENT_FLOAT32_IEEE 1 /end MOD_COMMON
/begin RECORD_LAYOUT SstUl NO_AXIS_PTS_X 1 UBYTE AXIS_PTS_X 2 ULONG INDEX_INCR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT SstF NO_AXIS_PTS_X 1 UBYTE AXIS_PTS_X 2 FLOAT32_IEEE INDEX_INCR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT GKfUb FNC_VALUES 1 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT KfUw NO_AXIS_PTS_X 1 UBYTE NO_AXIS_PTS_Y 2 UBYTE AXIS_PTS_X 3 UBYTE INDEX_INCR DIRECT
  AXIS_PTS_Y 4 UWORD INDEX_INCR DIRECT FNC_VALUES 5 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT
/begin AXIS_PTS SNM "" 0x800100 nmot SstUl 0 NO_COMPU_METHOD 8 0 100000 /end AXIS_PTS
/begin AXIS_PTS SRL "" 0x800120 rl SstF 0 NO_COMPU_METHOD 8 0 1000 /end AXIS_PTS
/begin CHARACTERISTIC GKF_A "a" MAP 0x800200 GKfUb 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR COM_AXIS nmot NO_COMPU_METHOD 8 0 100000 AXIS_PTS_REF SNM /end AXIS_DESCR
  /begin AXIS_DESCR COM_AXIS rl NO_COMPU_METHOD 8 0 1000 AXIS_PTS_REF SRL /end AXIS_DESCR /end CHARACTERISTIC
/begin CHARACTERISTIC KF_OWN "own" MAP 0x800300 KfUw 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR STD_AXIS nmot NO_COMPU_METHOD 8 0 255 /end AXIS_DESCR
  /begin AXIS_DESCR STD_AXIS rl NO_COMPU_METHOD 8 0 65535 /end AXIS_DESCR /end CHARACTERISTIC
/end MODULE /end PROJECT'''


def test_a2l_axis_cell_type_comes_from_the_axis_record_layout_not_the_values():
    d = bytearray(0x1000)
    d[0x100] = 4
    d[0x101:0x111] = struct.pack('>4I', 1000, 2000, 3000, 70000)        # SNM: 4 x ULONG
    d[0x120] = 3
    d[0x121:0x12D] = struct.pack('>3f', 0.5, 1.0, 1.5)                  # SRL: 3 x FLOAT32
    d[0x200:0x20C] = bytes(range(12))                                   # 3 x 4 UBYTE values
    d[0x300:0x302] = bytes([2, 2])
    d[0x302:0x304] = bytes([10, 20])                                    # X: UBYTE
    d[0x304:0x308] = struct.pack('>2H', 300, 600)                       # Y: UWORD
    d[0x308:0x30C] = bytes([1, 2, 3, 4])
    data = bytes(d)
    maps = {m.name: m for m in parse_a2l(A2L).link(file_size=len(data), ecu_anchor=0x800000, data=data).maps}
    a, own = maps['GKF_A'], maps['KF_OWN']
    assert (a.dtype, a.axis_x_dtype, a.axis_y_dtype) == ('u8', 'u32', 'f32')
    assert 'AXIS_PTS SNM' in a.axis_x_type_source and 'SstUl' in a.axis_x_type_source
    assert (own.axis_x_dtype, own.axis_y_dtype) == ('u8', 'u16') and 'RECORD_LAYOUT KfUw' in own.axis_y_type_source
    objs = {o.offset: o for o in R.objects(list(maps.values()), data=data)}
    assert objs[0x101].end == 0x111 and objs[0x121].end == 0x12D and objs[0x304].end == 0x308
    assert objs[0x101].type_state == R.TYPE_STATED


XDF = '''<?xml version="1.0"?><XDFFORMAT version="1.60">
<XDFHEADER><deftitle>Synthetic</deftitle><BASEOFFSET offset="0" subtract="0"/></XDFHEADER>
<XDFTABLE uniqueid="0x1"><title>Wide axes</title>
<XDFAXIS id="x"><EMBEDDEDDATA mmedaddress="0x100" mmedelementsizebits="32"/><indexcount>2</indexcount></XDFAXIS>
<XDFAXIS id="y"><EMBEDDEDDATA mmedaddress="0x140" mmedelementsizebits="8" mmedmajorstridebits="64"/>
<indexcount>3</indexcount></XDFAXIS>
<XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x200" mmedelementsizebits="8" mmedrowcount="3" mmedcolcount="2"/>
</XDFAXIS></XDFTABLE></XDFFORMAT>'''


def test_xdf_axis_cell_type_and_point_distance(tmp_path):
    d = bytearray(0x400)
    d[0x100:0x108] = struct.pack('>2I', 100, 200)
    d[0x140], d[0x148], d[0x150] = 1, 2, 3                              # 8-bit points, every 8th byte
    xdf = tmp_path / 's.xdf'
    xdf.write_text(XDF, encoding='utf-8')
    img = BinaryImage(bytes(d))
    m = read_xdf(str(xdf), img).maps[0]
    assert (m.axis_x_dtype, m.axis_x_step, m.axis_y_dtype, m.axis_y_step) == ('u32', 0, 'u8', 8)
    assert m.axes_x == [100, 200] and m.axes_y == [1, 2, 3]
    objs = {o.offset: o for o in R.objects([m], data=img.materialize())}
    assert objs[0x100].end == 0x108
    assert objs[0x140].end == 0x151                                     # last point 0x150 + 1 byte
    assert axis_conflicts([m], {0x150}, img.materialize()) and not axis_conflicts([m], {0x151}, img.materialize())


def _random_world(seed):
    rnd = random.Random(seed)
    data = bytearray(rnd.randrange(256) for _ in range(0x6000))
    axes = [0x100 + 0x40 * k for k in range(60)]
    for k in range(0, 60, 6):
        data[axes[k]:axes[k] + 32] = data[axes[0]:axes[0] + 32]
    maps = []
    for i in range(160):
        n = rnd.choice([2, 4, 6, 8])
        dtype = rnd.choice(['', '', 'u8', 'u16', 'u16', 's16', 'u32', 'f32'])
        step = rnd.choice([0, 0, 0, 8]) if dtype else 0
        maps.append(MapDefinition(f'T{i}', 0x2000 + 0x40 * i, rnd.choice([1, 2, 4]), n, 'u8',
                                  source=rnd.choice(['a2l', 'heuristic', 'tricore-code']),
                                  axis_x_offset=rnd.choice(axes), axis_x_dtype=dtype, axis_x_step=step,
                                  axes_x=list(range(n))))
    return maps, bytes(data)


def test_optimised_check_equals_a_brute_force_range_check_with_mixed_widths():
    """objects(near=...) and conflicts() never leave out a stored axis whose real range is hit."""
    for seed in range(4):
        maps, data = _random_world(seed)
        full = R.objects(maps, data=data)
        rnd = random.Random(seed + 50)
        for _ in range(150):
            lo = rnd.randrange(0x100, 0x1000)
            positions = {lo, lo + rnd.randrange(0, 4)}
            got = sorted((c.start, c.end) for c in axis_conflicts(maps, positions, data))
            want = sorted((o.offset, o.end) for o in full if any(o.offset <= p < o.end for p in positions))
            assert got == want
        # the brute force range itself is the real stored range: points x width, or with a step
        for o in full:
            if o.type_state == R.TYPE_STATED:
                n = o.span_points
                assert o.end == o.offset + ((n - 1) * o.step + o.width if o.step else n * o.width)


def test_an_approval_does_not_survive_a_changed_axis_width():
    img = image()
    maps = [user('A', 0x400, 'u16'), user('B', 0x500, 'u16'), MapDefinition('T', 0x700, 1, 4, 'u8')]
    policy = guarded(img, lambda: maps)
    approval, found = policy.approve(img, [], {AX + 4}, confirm=lambda f: True)
    assert approval and (found[0].start, found[0].end) == (AX, AX + 8)
    for m in maps[:2]:                                   # the definitions now state 32-bit cells
        m.axis_x_dtype = 'u32'
    with pytest.raises(EditRefused, match='veraltet'):
        img.commit([(AX + 4, img.byte(AX + 4), img.byte(AX + 4) ^ 1)], approval=approval)
    before = [m.asdict() for m in maps]
    after = [replace(m) for m in maps]
    img.commit_metadata(maps, maps[:], after, label='Definition')     # an undoable definition change
    with pytest.raises(EditRefused, match='veraltet'):
        img.commit([(AX + 4, img.byte(AX + 4), img.byte(AX + 4) ^ 1)], approval=approval)
    assert img.dirty_bytes == 0 and [m.asdict() for m in maps] == before
