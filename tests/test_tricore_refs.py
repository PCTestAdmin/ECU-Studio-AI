"""TriCore interpolation calls: a4 = table data, a5/a6 = axis headers (Siemens MSD80 style).

Synthetic images use real TriCore encodings (movh.a, lea BOL, call, j16, ret);
an opt-in test re-measures one real MSD80 image against its community XDF.
"""
import hashlib
import os
import numpy as np
import pytest
from ecu_studio.core.confidence import evidence_class
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.structure_scan import scan_structures, CALL_LAYOUT, PRELOOKUP_ORIGIN, RECORD_ORIGIN
from ecu_studio.core import tricore_refs
from ecu_studio.core.tricore_refs import (looks_like_tricore, call_sites, call_descriptors, cell_widths,
                                          MIN_CALLS, cond_target, record_at)

SEG = 0xA0000000
RET = (0x9000).to_bytes(2, 'little')


def movh_a(reg, hi):
    return (0x91 | (hi & 0xFFFF) << 12 | reg << 28).to_bytes(4, 'little')


def lea(a, b, off):
    off &= 0xFFFF
    w = 0xD9 | a << 8 | b << 12 | (off & 0x3F) << 16 | ((off >> 10) & 0x3F) << 22 | ((off >> 6) & 0xF) << 28
    return w.to_bytes(4, 'little')


def load(reg, file_offset):
    """movh.a + lea materialising the uncached flash address of a file offset."""
    addr = SEG + file_offset
    hi = (addr + 0x8000) >> 16
    return movh_a(reg, hi) + lea(reg, reg, addr - (hi << 16))


def call(at, target):
    disp = ((target - at) // 2) & 0xFFFFFF
    return (0x6D | (disp >> 16) << 8 | (disp & 0xFFFF) << 16).to_bytes(4, 'little')


def j16(at, target):
    return (0x3C | (((target - at) // 2) & 0xFF) << 8).to_bytes(2, 'little')


def u8_axis(values):
    return bytes([len(values)]) + bytes(values)


def u16_axis(values):
    return np.array([len(values)] + list(values), '<u2').tobytes()


def build(n_u8=12, n_u16=12, *, alternative=True, extra_code=b'', fill=True, bad_axis=False):
    """64 KiB image: code at 0, routines at 0x7000/0x7100, tables from 0x8000, axes from 0xC000."""
    img = bytearray(0x10000)
    tables, pos = [], 0x8000
    y, x = np.mgrid[:5, :6]
    for i in range(n_u8 + n_u16):
        w = 1 if i < n_u8 else 2
        z = (10 + 3 * y + 2 * x + i).astype('<u2' if w == 2 else 'u1') * (40 if w == 2 else 1)
        raw = z.astype('<u2' if w == 2 else 'u1').tobytes()
        img[pos:pos + len(raw)] = raw
        tables.append((pos, w))
        pos += len(raw)
    ax = 0xC000
    x_hdr = ax
    xa = u8_axis([5, 9, 20, 40, 60, 90])                         # 6 columns
    img[ax:ax + len(xa)] = xa
    ax += len(xa) + (len(xa) & 1)
    y_hdr = ax
    ya = u16_axis([500, 1000, 2000, 3000, 4000]) if not bad_axis else u16_axis([5, 4, 3, 2, 1])
    img[ax:ax + len(ya)] = ya
    code, at = bytearray(), 0
    for i, (t, w) in enumerate(tables):
        routine = 0x7000 if w == 1 else 0x7100
        if alternative and i == len(tables) - 2:
            # if (...) a4 = table i else a4 = table i+1; then shared axes and call
            block = load(4, t)
            jpos = at + len(block)
            alt = load(4, tables[i + 1][0])
            join = jpos + 2 + len(alt)
            block += j16(jpos, join) + alt
        elif alternative and i == len(tables) - 1:
            continue
        else:
            block = load(4, t)
        block += load(5, x_hdr) + load(6, y_hdr)
        block += call(at + len(block), routine) + RET
        code += block
        at += len(block)
    code += extra_code
    if fill:   # ordinary code density: unrelated address loads and returns
        while len(code) < 0x6000:
            code += movh_a(12, 0xD000) + RET + RET
    img[:len(code)] = code
    img[0x7000:0x7002] = RET
    img[0x7100:0x7102] = RET
    return bytes(img), tables, x_hdr, y_hdr


def test_gate_rejects_images_without_tricore_code():
    rng = np.random.default_rng(1)
    assert not looks_like_tricore(rng.integers(0, 256, 0x40000, dtype=np.uint8).tobytes())
    assert not looks_like_tricore(bytes(0x40000))
    assert not looks_like_tricore(bytes([0x91, 0x00, 0x00, 0x90]) * 1000)   # too small
    data, *_ = build()
    assert looks_like_tricore(data)
    assert call_descriptors(bytes(0x40000)) == {}


def test_calls_name_data_and_both_axis_headers():
    data, tables, x_hdr, y_hdr = build()
    desc = call_descriptors(data)
    assert set(desc) == {t for t, _ in tables}
    for d in desc.values():
        assert (d.x_axis.header, d.x_axis.count, d.x_axis.width) == (x_hdr, 6, 1)
        assert (d.y_axis.header, d.y_axis.count, d.y_axis.width) == (y_hdr, 5, 2)
        assert d.y_axis.values == (500, 1000, 2000, 3000, 4000)


def test_branch_variants_before_shared_axis_loads_are_both_named():
    data, tables, *_ = build()
    sites = call_sites(data)
    last_two = {tables[-2][0], tables[-1][0]}
    shared = [c for c in sites if c.data in last_two]
    assert {c.data for c in shared} == last_two and len({c.site for c in shared}) == 1


def test_cell_width_from_next_object_and_routine_vote():
    data, tables, x_hdr, y_hdr = build()
    desc = call_descriptors(data)
    widths = cell_widths(desc, list(desc) + [x_hdr, y_hdr])
    assert widths == {t: w for t, w in tables}
    # The last table has no exactly fitting successor (gap to the axis pool):
    # its routine's unambiguous calls decide.
    last, w = tables[-1]
    assert (0xC000 - last) > 2 * 30 * w


def test_unparsable_axes_and_conflicting_readings_give_no_descriptor():
    data, *_ = build(bad_axis=True)
    assert all(d.y_axis is None for d in call_descriptors(data).values())   # decreasing Y: not an axis
    data, tables, x_hdr, y_hdr = build()
    # A second call names the first table with other axes: not one table.
    t0 = tables[0][0]
    extra = load(4, t0) + load(5, y_hdr) + load(6, x_hdr)
    data2, *_ = build(extra_code=extra + call(0, 0) + RET)
    assert t0 not in call_descriptors(data2) and tables[1][0] in call_descriptors(data2)


def test_too_few_calls_are_not_evidence():
    data, *_ = build(n_u8=MIN_CALLS // 2 - 2, n_u16=MIN_CALLS // 2 - 2)
    assert looks_like_tricore(data) and call_descriptors(data) == {}


def test_scan_reports_exact_call_tables_as_own_uncalibrated_class():
    data, tables, *_ = build()
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = {(m.offset, m.rows, m.cols, m.width): m for m in maps if m.record_layout == CALL_LAYOUT}
    assert set(called) == {(t, 5, 6, w) for t, w in tables}
    m = called[(tables[0][0], 5, 6, 1)]
    assert m.endian == 'little' and m.axis_x_offset == 0xC001 and m.axes_y == [500, 1000, 2000, 3000, 4000]
    assert evidence_class(m) == 'code:call:2d' and m.evidence_tier == 'nicht kalibriert'
    assert 'TriCore' in m.label_evidence and not m.verified


def test_call_tables_do_not_use_up_the_smoothness_budget():
    data, tables, *_ = build()
    found = scan_structures(BinaryImage(data), 0x8000, 0x10000, max_results=1)
    assert len([m for m in found if m.record_layout == CALL_LAYOUT]) == len(tables)


# --- Stack slots and split (prelookup) interpolation -------------------------------------------

def sub_sp(n):
    return (0x20 | (n & 0xFF) << 8).to_bytes(2, 'little')          # sub.a sp,#n


def st_a15_sp(off):
    return (0xF8 | (off // 4) << 8).to_bytes(2, 'little')          # st.a [sp]off,a15


def ld_a_sp(a, off):                                                # ld.a a,[sp]off10 (BO)
    w = 0x09 | a << 8 | 10 << 12 | (off & 0x3F) << 16 | 0x26 << 22 | ((off >> 6) & 0xF) << 28
    return w.to_bytes(4, 'little')


def mov_aa(a, b):
    return (0x40 | a << 8 | b << 12).to_bytes(2, 'little')


def bo_load(op2, d, b, off=0):                                      # ld.* d,[b]off10 (BO, base+offset)
    w = 0x09 | d << 8 | b << 12 | (off & 0x3F) << 16 | op2 << 22 | ((off >> 6) & 0xF) << 28
    return w.to_bytes(4, 'little')


LD_B, LD_BU, LD_H, LD_HU = 0x20, 0x21, 0x22, 0x23


def reader(*op2s):
    """Interpolation routine body: a2 = a4 (table), then the given loads through a2, ret."""
    return mov_aa(2, 4) + b''.join(bo_load(op2, 2 + i, 2, i) for i, op2 in enumerate(op2s)) + RET


def image_with(make_code, n_tables=24, routines=None):
    """64 KiB image: u8 5x6 tables from 0x8000, X (6 pts, u8) at 0xC000, X2 (4 pts) at 0xC008,
    Y (5 pts, u16) at 0xC010; routines at 0x7000.. (ret); code from make_code(tables) at 0x100."""
    img = bytearray(0x10000)
    y, x = np.mgrid[:5, :6]
    tables = []
    for i in range(n_tables):
        t = 0x8000 + i * 30
        img[t:t + 30] = (10 + 3 * y + 2 * x + i).astype('u1').tobytes()
        tables.append(t)
    for off, raw in ((0xC000, u8_axis([5, 9, 20, 40, 60, 90])), (0xC008, u8_axis([1, 2, 3, 4])),
                     (0xC010, u16_axis([500, 1000, 2000, 3000, 4000]))):
        img[off:off + len(raw)] = raw
    for r in (0x7000, 0x7100, 0x7200, 0x7300):
        body = (routines or {}).get(r, RET)
        img[r:r + len(body)] = body
    code = bytearray(make_code(tables, 0x100))
    while len(code) < 0x6000:
        code += movh_a(12, 0xD000) + RET + RET
    img[0x100:0x100 + len(code)] = code[:0x6F00]
    return bytes(img), tables


def stack_function(tables, base, *, escape=False, two_frames=False, reassign_from=None):
    """call F; F: sub.a sp; X and Y header pointers into [sp]4/[sp]20; per table: an unrelated
    call (clobbers a2-a7), a4 = table, a5/a6 reloaded from the stack, call routine."""
    entry = base + 4 + 2
    code = bytearray(call(base, entry) + RET)
    code += sub_sp(24)
    if two_frames:
        code += sub_sp(8)
    code += load(15, 0xC000) + st_a15_sp(4) + load(15, 0xC010) + st_a15_sp(20)
    if escape:
        code += lea(2, 10, 4)                     # slot address handed out: a callee may write it
    for i, t in enumerate(tables):
        if reassign_from is not None and i == reassign_from:
            code += load(15, 0xC008) + st_a15_sp(4)
        at = base + len(code)
        code += call(at, 0x7200)
        code += load(4, t) + ld_a_sp(5, 4) + ld_a_sp(6, 20)
        code += call(base + len(code), 0x7000)
    return bytes(code + RET)


def test_axis_pointers_reloaded_from_stack_slots():
    data, tables = image_with(stack_function)
    assert call_descriptors(data) != {}
    desc = call_descriptors(data)
    assert set(desc) == set(tables)
    assert all((d.x_axis.header, d.y_axis.header, d.prelookup) == (0xC000, 0xC010, False) for d in desc.values())
    assert all(c.x_header is None for c in call_sites(data, stack=False) if c.data in tables)


def test_stack_reload_takes_the_nearest_preceding_store():
    data, tables = image_with(lambda t, b: stack_function(t, b, reassign_from=12))
    desc = call_descriptors(data)
    assert {desc[t].x_axis.header for t in tables[:12]} == {0xC000}
    assert {desc[t].x_axis.header for t in tables[12:]} == {0xC008}


@pytest.mark.parametrize('kw', [{'escape': True}, {'two_frames': True}])
def test_stack_slots_are_not_trusted_when_sp_moves_twice_or_a_slot_address_escapes(kw):
    data, tables = image_with(lambda t, b: stack_function(t, b, **kw))
    assert looks_like_tricore(data)
    assert not any(c.x_header for c in call_sites(data) if c.data in tables)
    assert call_descriptors(data) == {}


def prelookup_code(tables, base, *, single=False):
    """Per table: a4 = X header -> call P1, a4 = Y header -> call P2, a4 = table -> call M."""
    code = bytearray()
    for t in tables:
        code += load(4, 0xC000) + call(base + len(code) + 8, 0x7100)
        if not single:
            code += load(4, 0xC010) + call(base + len(code) + 8, 0x7200)
        code += load(4, t) + call(base + len(code) + 8, 0x7300) + RET
    return bytes(code)


U8_TABLE = {0x7300: reader(LD_BU, LD_BU)}     # table routine M reads unsigned bytes through a4


def test_split_interpolation_takes_axes_from_the_two_prelookups_on_the_path():
    data, tables = image_with(prelookup_code, routines=U8_TABLE)
    desc = call_descriptors(data)
    assert set(desc) == set(tables)
    assert all((d.x_axis.header, d.y_axis.header, d.prelookup) == (0xC000, 0xC010, True) for d in desc.values())
    widths = cell_widths(desc, list(desc) + [0xC000, 0xC010])
    # Exactly filled gaps give the width; the last table (gap to the axis pool) stays open.
    assert widths == {t: 1 for t in tables[:-1]}
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = [m for m in maps if m.record_layout == CALL_LAYOUT]
    assert {(m.offset, m.rows, m.cols) for m in called} == {(t, 5, 6) for t in tables[:-1]}
    assert all(m.label_origin.startswith(PRELOOKUP_ORIGIN) and evidence_class(m) == 'code:call-pre:2d'
               and m.evidence_tier == 'nicht kalibriert' for m in called)


def test_one_prelookup_is_not_enough_for_a_table():
    data, tables = image_with(lambda t, b: prelookup_code(t, b, single=True), routines=U8_TABLE)
    assert call_descriptors(data) == {}


def test_table_routine_without_table_loads_loses_its_role():
    data, tables = image_with(prelookup_code)          # M is a bare ret: no evidence it reads a table
    assert call_descriptors(data) == {}


@pytest.mark.parametrize('loads, width, signed, dtype', [
    ((LD_BU, LD_BU), 1, False, 'u8'), ((LD_B, LD_B), 1, True, 's8'),
    ((LD_BU, LD_B), 1, None, None), ((LD_BU,), None, None, None)])
def test_cell_width_and_sign_come_from_the_table_loads_of_the_routine(loads, width, signed, dtype):
    data, tables = image_with(stack_function, routines={0x7000: reader(*loads)})
    desc = call_descriptors(data)
    assert set(desc) == set(tables)
    assert {(d.cell_width, d.cell_signed) for d in desc.values()} == {(width, signed)}
    if dtype:
        maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
        called = [m for m in maps if m.record_layout == CALL_LAYOUT]
        assert called and {m.dtype for m in called} == {dtype}
        assert all('Ladebefehlen der Interpolationsroutine' in m.label_evidence for m in called)


def test_loads_overrule_a_gap_that_two_equal_byte_tables_fill_exactly():
    # Only every other u8 table is named: the gap is exactly twice the table (one u16 reading),
    # but the routine reads bytes.
    data, tables = image_with(lambda t, b: stack_function(t[::2], b), n_tables=48,
                              routines={0x7000: reader(LD_BU, LD_BU)})
    desc = call_descriptors(data)
    widths = cell_widths(desc, list(desc) + [0xC000, 0xC010])
    assert set(widths.values()) == {1}
    data2, _ = image_with(lambda t, b: stack_function(t[::2], b), n_tables=48)   # no loads: the gap decides
    desc2 = call_descriptors(data2)
    assert set(cell_widths(desc2, list(desc2) + [0xC000, 0xC010]).values()) == {2}


def thirds_code(tables, base):
    """Tables i % 3 < 2 after two prelookups; tables i % 3 == 2 passed in a4 without any."""
    code = bytearray()
    for i, t in enumerate(tables):
        if i % 3 < 2:
            code += load(4, 0xC000) + call(base + len(code) + 8, 0x7100)
            code += load(4, 0xC010) + call(base + len(code) + 8, 0x7200)
        code += load(4, t) + call(base + len(code) + 8, 0x7300) + RET
    return bytes(code)


def test_neighbours_named_without_axes_still_bound_a_prelookup_table():
    data, tables = image_with(thirds_code, n_tables=36, routines=U8_TABLE)
    desc = call_descriptors(data)
    middle = [t for i, t in enumerate(tables) if i % 3 == 1]
    assert set(middle) <= set(desc) and all(tables[i] not in desc for i in range(2, 36, 3))
    bounds = list(desc) + [0xC000, 0xC010]
    assert not any(t in cell_widths(desc, bounds) for t in middle)          # gap = two tables
    assert all(cell_widths(desc, bounds + list(desc.named)).get(t) == 1 for t in middle)


@pytest.mark.parametrize('cut', [0x10000 - 1, 0x6F03, 0x200])
def test_truncated_and_damaged_images_do_not_fail(cut):
    data, _ = image_with(prelookup_code, routines=U8_TABLE)
    call_descriptors(data[:cut])
    damaged = bytearray(data)
    damaged[0x1000:0x1400] = bytes(range(256)) * 4      # garbage inside the code
    desc = call_descriptors(bytes(damaged))
    assert all(0x8000 <= d < 0xC000 for d in desc)


MSD80_SHA = 'c53ff0d4da3aafb0aee93b2a4df165b4f98229752b2bc2ea694a2699bc396b38'


@pytest.fixture(scope='module')
def msd80():
    path, xdf = os.environ.get('ECU_STUDIO_MSD80_REGRESSION_BIN'), os.environ.get('ECU_STUDIO_MSD80_REGRESSION_XDF')
    if not path or not xdf:
        pytest.skip('Opt-in private real BIN + community XDF; never bundled')
    data = open(path, 'rb').read()
    assert hashlib.sha256(data).hexdigest() == MSD80_SHA
    return data, xdf


def test_real_msd80_calls_find_reference_tables_without_conflicts(msd80):
    from ecu_studio.core.xdf import read_xdf
    data, xdf = msd80
    image = BinaryImage(data)
    ref = read_xdf(xdf, image, include_constants=True).maps
    maps = scan_calibration_candidates(image)
    exact = {(r.offset, r.width) for r in ref if min(r.rows, r.cols) >= 4 and any(
        m.offset == r.offset and m.width == r.width and {m.rows, m.cols} == {r.rows, r.cols} for m in maps)}
    # 39 before TriCore calls, 61 with a5/a6, 71 with stack + prelookup, 73 with named neighbours,
    # 74 with conditional branches, 84 with record headers (1.19 development)
    assert len(exact) >= 84
    called = [m for m in maps if m.record_layout == CALL_LAYOUT]
    assert len(called) > 700
    scalars = set()
    for m in called:              # no call table contradicts a reference table or curve
        hit = [r for r in ref if r.offset < m.offset + m.length and m.offset < r.offset + r.length]
        # The XDF lists some data twice (a table and one of its rows): one exact reading suffices.
        if not hit or any((r.offset, r.width) == (m.offset, m.width) and {r.rows, r.cols} == {m.rows, m.cols}
                          for r in hit):
            continue
        assert all(r.rows == r.cols == 1 for r in hit), (hex(m.offset), [r.name for r in hit])
        scalars |= {r.offset for r in hit}
    # One known case: the XDF puts a scalar inside a 6 x 9 s8 record (counts, axes, exactly
    # bounded by the next record header) that routine 0x1E5870 reads; not resolvable without an A2L.
    assert scalars <= {0x63F30}


def jz16(at, target):                                               # jz d15,disp8 (SB)
    return (0x6E | (((target - at) // 2) & 0xFF) << 8).to_bytes(2, 'little')


def test_conditional_branch_targets():
    assert cond_target(0x100, 2, 0x6E | 0x05 << 8) == 0x10A          # jz d15,+5 halfwords
    assert cond_target(0x100, 2, 0x6E | 0xFE << 8) == 0xFC           # backward
    assert cond_target(0x100, 2, 0x76 | 0x3 << 8 | 0xF << 12) == 0x106   # jz d15? no: jz d[b],disp4
    w = 0xDF | (0x10 << 16)                                          # jeq d,const4,+16 halfwords
    assert cond_target(0x200, 4, w) == 0x220
    assert cond_target(0x200, 4, 0x6D) is None and cond_target(0x200, 2, 0x9000) is None


def branch_code(tables, base):
    """Per table: a4 = table, conditional jump over a ret to the shared axis loads and the call."""
    code = bytearray()
    for t in tables:
        code += load(4, t)
        at = base + len(code)
        code += jz16(at, at + 4) + RET
        code += load(5, 0xC000) + load(6, 0xC010) + call(base + len(code) + 16, 0x7000) + RET
    return bytes(code)


def test_register_state_reaches_conditional_branch_targets(monkeypatch):
    data, tables = image_with(branch_code)
    assert set(call_descriptors(data)) == set(tables)
    monkeypatch.setattr(tricore_refs, 'FOLLOW_BRANCHES', False)
    assert call_descriptors(data) == {}         # after the ret only the branch carries a4


def u16(*v):
    return np.array(v, '<u2').tobytes()


def record(z, x, y, *, xw=2, yw=1, cw=1, dtype='<i2'):
    """Self-describing record: counts (cw bytes each), X (xw bytes), Y (yw bytes), then Z row-major."""
    counts = (len(x).to_bytes(cw, 'little') + len(y).to_bytes(cw, 'little'))
    ax = (u16(*x) if xw == 2 else bytes(x)) + (u16(*y) if yw == 2 else bytes(y))
    return counts + ax + np.asarray(z, dtype).tobytes()


def test_record_header_reading_with_mixed_axis_widths():
    z = 900 - np.arange(48).reshape(6, 8) * 3           # falling: cannot extend the Y axis
    raw = bytes(2) + record(z, [100, 200, 300, 400, 500, 600, 700, 800], [1, 2, 3, 4, 5, 6])
    (x, y), = record_at(raw, 2)
    assert (x.header, x.offset, x.count, x.width) == (2, 4, 8, 2)
    assert (y.header, y.offset, y.count, y.width) == (3, 20, 6, 1)
    assert y.end == 26 and x.values[0] == 100
    flat = bytes(2) + bytes([4, 4]) + u16(5, 5, 5, 5) + bytes([1, 2, 3, 4]) + bytes(32)
    assert record_at(flat, 2) == []                                # non-increasing axis
    assert record_at(bytes([40, 2, 1, 2]), 0) == []                # count beyond 32
    assert record_at(bytes([4]), 0) == []                             # truncated
    rising = bytes(2) + record(np.arange(48).reshape(6, 8) * 50 - 2000, [100, 200, 300, 400, 500, 600, 700, 800],
                               [1, 2, 3, 4, 5, 6])
    assert len(record_at(rising, 2)) == 2                          # u8 Y + data also reads as a u16 Y


def record_image(n=24, loads=(LD_BU, LD_BU) + (LD_H,) * 10, dtype='<i2'):
    """Records from 0x8000; one routine at 0x7000 receives a4 = record header."""
    img = bytearray(0x10000)
    y, x = np.mgrid[:6, :8]
    headers, starts, pos = [], [], 0x8000
    for i in range(n):
        z = (3 * y + 2 * x + i) * 50 - 300 if dtype == '<i2' else (3 * y + 2 * x + i) * 50
        raw = record(z, [100, 200, 300, 400, 500, 600, 700, 800], [1, 2, 3, 4, 5, 6], dtype=dtype)
        img[pos:pos + len(raw)] = raw
        headers.append(pos)
        starts.append(pos + 2 + 16 + 6)
        pos += len(raw)
    body = reader(*loads)
    img[0x7000:0x7000 + len(body)] = body
    code = bytearray()
    for h in headers:
        code += load(4, h) + call(0x100 + len(code) + 8, 0x7000) + RET
    while len(code) < 0x6000:
        code += movh_a(12, 0xD000) + RET + RET
    img[0x100:0x100 + len(code)] = code[:0x6F00]
    return bytes(img), headers, starts


def test_record_routine_names_data_after_counts_and_axes():
    data, headers, starts = record_image()
    assert len(record_at(data, headers[0])) == 2                   # ambiguous on its own ...
    desc = call_descriptors(data)
    assert set(desc) == set(starts)                                # ... the routine's layout decides
    d = desc[starts[0]]
    assert d.record and (d.x_axis.count, d.x_axis.width, d.y_axis.count, d.y_axis.width) == (8, 2, 6, 1)
    # Two count loads are left out; the ten signed halfword loads give the cell type.
    assert (d.cell_width, d.cell_signed) == (2, True)
    assert set(desc.named) >= set(headers)                         # headers bound the tables before them
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = {m.offset: m for m in maps if m.record_layout == CALL_LAYOUT}
    assert set(called) == set(starts)
    m = called[starts[3]]
    assert (m.rows, m.cols, m.dtype, m.endian) == (6, 8, 's16', 'little')
    assert m.label_origin.startswith(RECORD_ORIGIN) and 'Datensatzkopf' in m.label_evidence
    assert m.axes_x == [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]
    assert (m.axis_x_offset, m.axis_y_offset) == (headers[3] + 2, headers[3] + 18)


def test_record_routine_without_cell_loads_leaves_the_type_open():
    data, headers, starts = record_image(loads=(LD_BU, LD_BU), dtype='<u2')
    desc = call_descriptors(data)
    assert set(desc) == set(starts)
    assert {(d.cell_width, d.cell_signed) for d in desc.values()} == {(None, None)}
    # Width from the gap to the next header (exact), sign unchecked.
    widths = cell_widths(desc, list(desc) + list(desc.named))
    assert all(widths[s] == 2 for s in starts[:-1])
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = [m for m in maps if m.record_layout == CALL_LAYOUT]
    assert called and all('Vorzeichen aus der glatteren Lesart (ungeprüft)' in m.label_evidence for m in called)


def test_mixed_loads_give_no_record_cell_type():
    data, _, starts = record_image(loads=(LD_BU, LD_BU) + (LD_H,) * 5 + (LD_HU,) * 5)
    assert {(d.cell_width, d.cell_signed) for d in call_descriptors(data).values()} == {(None, None)}


def test_record_role_needs_most_calls_to_parse(monkeypatch):
    data, headers, starts = record_image()
    damaged = bytearray(data)
    for h in headers[:20]:                                          # 20 of 24 headers no longer parse
        damaged[h:h + 2] = bytes([0xFF, 0xFF])
    assert call_descriptors(bytes(damaged)) == {}
    monkeypatch.setattr(tricore_refs, 'FIND_RECORDS', False)
    assert call_descriptors(data) == {}


def other_register_code(tables, base):
    """Another calling convention: data in a2, X header in a3, Y header in a7."""
    code = bytearray()
    for t in tables:
        code += load(2, t) + load(3, 0xC000) + load(7, 0xC010)
        code += call(base + len(code), 0x7000) + RET
    return bytes(code)


def reader_from(reg, *op2s):
    return mov_aa(12, reg) + b''.join(bo_load(op2, 2 + i, 12, i) for i, op2 in enumerate(op2s)) + RET


def test_register_roles_are_learned_from_call_behaviour(monkeypatch):
    data, tables = image_with(other_register_code, routines={0x7000: reader_from(2, LD_BU, LD_BU)})
    desc = call_descriptors(data)
    assert set(desc) == set(tables)
    d = desc[tables[0]]
    assert d.registers == (2, (3, 7))
    assert (d.x_axis.header, d.y_axis.header) == (0xC000, 0xC010)
    assert (d.cell_width, d.cell_signed) == (1, False)              # loads through a2, not a4
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = [m for m in maps if m.record_layout == CALL_LAYOUT]
    assert called and all('Daten in a2, Achsköpfe in a3/a7' in m.label_evidence for m in called)
    monkeypatch.setattr(tricore_refs, 'LEARN_ROLES', False)
    assert call_descriptors(data) == {}


def test_msd80_convention_is_not_relearned():
    data, tables = image_with(stack_function)
    assert {d.registers for d in call_descriptors(data).values()} == {(4, (5, 6))}


def test_sign_alternatives_only_where_the_bytes_decide():
    from ecu_studio.core.structure_scan import sign_alternatives
    low = np.array([1, 2, 300, 4], '<u2').tobytes()
    high = np.array([1, 2, 0x8001, 4], '<u2').tobytes()
    assert sign_alternatives(low, 0, 4, 2, 'u16') == []
    assert sign_alternatives(high, 0, 4, 2, 'u16') == ['s16']
    assert sign_alternatives(high, 0, 4, 2, 's16', 'little') == ['u16']
    assert sign_alternatives(np.array([0x0180], '>u2').tobytes(), 0, 1, 2, 'u16', 'big') == []
    assert sign_alternatives(bytes([5, 0x90]), 0, 2, 1, 's8') == ['u8']


def test_code_proven_sign_has_no_alternative_and_survives_a_project_round_trip():
    from ecu_studio.core.model import map_from_record
    data, headers, starts = record_image()
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = [m for m in maps if m.record_layout == CALL_LAYOUT]
    assert called and all(m.dtype == 's16' and m.dtype_alternatives == [] for m in called)
    m = called[0]
    m.dtype_alternatives = ['u16']
    assert map_from_record(m.asdict(), set()).dtype_alternatives == ['u16']
