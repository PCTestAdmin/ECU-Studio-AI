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
from ecu_studio.core.structure_scan import scan_structures, CALL_LAYOUT
from ecu_studio.core.tricore_refs import (looks_like_tricore, call_sites, call_descriptors, cell_widths,
                                          MIN_CALLS)

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
    assert len(exact) >= 61      # 39 before TriCore calls (measured 2026-10-30)
    called = [m for m in maps if m.record_layout == CALL_LAYOUT]
    assert len(called) > 700
    for m in called:              # no call table contradicts the reference
        hit = [r for r in ref if r.offset < m.offset + m.length and m.offset < r.offset + r.length]
        # The XDF lists some data twice (a table and one of its rows): one exact reading suffices.
        assert not hit or any((r.offset, r.width) == (m.offset, m.width) and {r.rows, r.cols} == {m.rows, m.cols}
                              for r in hit)
