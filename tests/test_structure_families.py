"""Family-specific evidence of structure_scan: ME7 base/records, 68k operands, Denso descriptors."""
import struct
import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.cpu_refs import m68k_targets
from ecu_studio.core.structure_scan import (c16x_base, inline_records, gap_curve, pointer_descriptors,
                                            scan_structures, _runs_forward, POINTER_LAYOUT)


def _noise(n, seed=11):
    return bytearray(np.random.default_rng(seed).integers(0, 256, n, dtype=np.uint8).tobytes())


def test_c16x_base_is_voted_by_lookup_calls_with_valid_axes():
    data = _noise(0x10000)
    base = 0x800000
    for k in range(6):
        table, axis = 0x2000 + 0x100 * k, 0x8000 + 0x40 * k
        data[axis:axis + 6] = bytes([5, 10, 20, 30, 40, 50])
        a, d = table + base, axis + base
        data[0x400 + 16 * k:0x410 + 16 * k] = (b'\xE6\xFC' + struct.pack('<H', a & 0x3FFF) + b'\xE6\xFD' + struct.pack('<H', a >> 14)
                                              + b'\xE6\xFE' + struct.pack('<H', d & 0x3FFF) + b'\xE6\xFF' + struct.pack('<H', d >> 14))
    assert c16x_base(bytes(data)) == base
    assert c16x_base(bytes(_noise(0x10000, seed=3))) == 0


def test_inline_record_reads_counts_axes_and_data():
    data = _noise(0x400)
    z = np.add.outer(np.arange(5) * 12, np.arange(4) * 3).astype(np.uint8) + 40
    rec = bytes([4, 5, 10, 20, 30, 40, 1, 2, 3, 4, 5]) + z.tobytes()
    data[0x100:0x100 + len(rec)] = rec
    hits = [r for r in inline_records(bytes(data), 0x100, 0x200) if r[2] > 1]
    cost, off, rows, cols, w, endian, dtype, x, y = min(hits, key=lambda r: r[0])
    assert (off, rows, cols, w) == (0x10B, 5, 4, 1)
    assert x.values == (10, 20, 30, 40) and y.values == (1, 2, 3, 4, 5)


def test_gap_curve_fills_gap_between_references_and_rejects_noise():
    data = _noise(0x200)
    data[0x80:0x90] = bytes(range(20, 180, 10))
    cost, n, w, endian, dtype = gap_curve(bytes(data), 0x80, 0x90)
    assert n * w == 16 and cost <= .25
    assert gap_curve(bytes(data), 0x100, 0x110) is None


def test_m68k_abs_long_operand_targets_respect_base():
    data = bytearray(0x2000)
    data[0x10:0x16] = struct.pack('>HI', 0x2039, 0x401234)     # MOVE.L (0x401234).L,D0
    assert 0x1234 in m68k_targets(bytes(data), 0x400000)
    assert 0x1234 not in m68k_targets(bytes(data), 0)


def _denso_image(n_tables=6):
    data = bytearray(0x4000)
    for k in range(n_tables):
        x_ptr = 0x1000 + 0x200 * k
        y_ptr = x_ptr + 4 * 4
        z_ptr = y_ptr + 5 * 4
        data[x_ptr:y_ptr] = struct.pack('>4f', 0, 1000, 2000, 3000)
        data[y_ptr:z_ptr] = struct.pack('>5f', 10, 20, 40, 80, 160)
        z = np.add.outer(np.arange(5) * 300, np.arange(4) * 70).astype('>u2') + 100 * k
        data[z_ptr:z_ptr + z.nbytes] = z.tobytes()
        d = 0x200 + 0x20 * k
        data[d:d + 24] = struct.pack('>HHIIIBxxxf', 4, 5, x_ptr, y_ptr, z_ptr, 0x08, 1.)
    return bytes(data)


def test_pointer_descriptors_name_start_shape_type_and_axes():
    found = pointer_descriptors(_denso_image())
    assert len(found) == 6
    rows, cols, dtype, w, x, y = found[0x1000 + 9 * 4]
    assert (rows, cols, dtype, w) == (5, 4, 'u16', 2)
    assert x.values == (0., 1000., 2000., 3000.) and y.count == 5


def test_few_descriptors_are_ignored_and_scan_reports_descriptor_tables():
    assert pointer_descriptors(_denso_image(3)) == {}
    found = {m.offset: m for m in scan_structures(BinaryImage(_denso_image()))}
    m = found[0x1000 + 9 * 4]
    assert (m.rows, m.cols, m.dtype, m.endian, m.record_layout) == (5, 4, 'u16', 'big', POINTER_LAYOUT)
    assert m.axes_x == [0., 1000., 2000., 3000.] and len(m.axes_y) == 5


def test_vectorised_runs_match_naive_count():
    good = np.random.default_rng(5).random(503) > .3
    for c in (4, 7, 16):
        run = _runs_forward(good, c)
        for p in range(len(good)):
            k = 0
            while p + k * c < len(good) and good[p + k * c]:
                k += 1
            assert run[p] == k


def test_descriptor_axes_must_really_increase_for_unsigned_widths():
    # Regression: np.diff on unsigned arrays wraps (5 - 10 = 251 for u8,
    # 0x0005 - 0x000A = 65531 for u16), so falling axes passed as increasing.
    from ecu_studio.core.structure_scan import _increasing_axis
    for width, fmt in ((1, 'B'), (2, '>H')):
        size = struct.calcsize(fmt)
        def pack(*vals):
            return b''.join(struct.pack(fmt, v) for v in vals)
        assert _increasing_axis(pack(1, 2, 3, 4), 0, 4, size) is not None
        assert _increasing_axis(pack(10, 5, 20, 30), 0, 4, size) is None      # falls once
        assert _increasing_axis(pack(40, 30, 20, 10), 0, 4, size) is None     # falling
        assert _increasing_axis(pack(3, 3, 4, 5), 0, 4, size) is None         # repeated
    assert _increasing_axis(struct.pack('>4f', 1, 2, float('nan'), 4), 0, 4, 4) is None
    assert _increasing_axis(struct.pack('>2H', 1, 2), 0, 4, 2) is None        # truncated


def test_descriptor_with_falling_u16_axis_is_rejected():
    data = bytearray(_denso_image())
    # Make the X axis of every table fall: no descriptor may survive.
    for k in range(6):
        x_ptr = 0x1000 + 0x200 * k
        data[x_ptr:x_ptr + 16] = struct.pack('>4f', 3000, 2000, 1000, 0)
    assert pointer_descriptors(bytes(data)) == {}


def test_fast_window_statistics_and_overlap_match_brute_force():
    from numpy.lib.stride_tricks import sliding_window_view
    from ecu_studio.core.structure_scan import _sliding_extreme, _window_sums
    from ecu_studio.core.scoped_scan import _merged, _overlaps_any
    rng = np.random.default_rng(2)
    x = rng.integers(0, 65536, 997).astype(np.float64)
    for k in (2, 8, 13, 32):
        win = sliding_window_view(x, k)
        assert np.array_equal(_sliding_extreme(x, k, np.maximum), win.max(1))
        assert np.array_equal(_sliding_extreme(x, k, np.minimum), win.min(1))
        assert np.array_equal(_window_sums(x.astype(np.int64), k), win.sum(1).astype(np.int64))
    spans = [(int(a), int(a + b)) for a, b in zip(rng.integers(0, 5000, 60), rng.integers(1, 80, 60))]
    merged = _merged(spans)
    for lo in range(0, 5100, 7):
        hi = lo + 5
        assert _overlaps_any(lo, hi, merged) == any(lo < e and s < hi for s, e in spans)


def test_vectorised_axis_search_matches_reference_rule():
    from ecu_studio.core.axis_arrays import _raw_arrays, _increasing
    data = bytes(np.random.default_rng(8).integers(0, 256, 20000, dtype=np.uint8))
    data += bytes([5, 1, 2, 3, 4, 9]) + bytes([3, 0, 1, 0, 5, 0, 9, 0])
    found = {(a.header, a.width): a for a in _raw_arrays(data, 0, len(data))}
    b = np.frombuffer(data, np.uint8)
    for width in (1, 2):
        for h in range(0, len(data) - width, width):
            n = int(b[h]) if width == 1 else int(b[h]) | int(b[h + 1]) << 8
            if not 2 <= n <= 32 or h + width + n * width > len(data):
                continue
            v = (b[h + width:h + width + n] if width == 1 else
                 np.frombuffer(data[h + width:h + width + 2 * n], '<u2')).astype(np.int64)
            assert ((h, width) in found) == _increasing(v)


def test_empty_data_region_list_searches_nothing():
    # Regression: an empty region list fell back to a pitch search over the whole file.
    data = bytearray(_noise(0x4000))
    t = np.add.outer(np.arange(8) * 9, np.arange(8) * 4).astype(np.uint8) + 10
    data[0x800:0x840] = t.tobytes()
    image = BinaryImage(bytes(data))
    assert any(m.offset == 0x800 for m in scan_structures(image, regions=None))
    assert not any(m.offset == 0x800 for m in scan_structures(image, regions=[]))
