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
