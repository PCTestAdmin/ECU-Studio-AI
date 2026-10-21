"""Scans on several CPU cores return exactly what the single-core scan returns."""
import numpy as np
import pytest
from ecu_studio.core import parallel
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates, PARALLEL_MIN_BYTES


def _image():
    rng = np.random.default_rng(5)
    buf = bytearray(rng.integers(0, 256, PARALLEL_MIN_BYTES + 0x10000, dtype=np.uint8).tobytes())
    y, x = np.mgrid[:12, :16]
    for k in range(6):                                   # smooth tables between random bytes
        off = 0x2000 + k * 0x9000
        t = (300 + 40 * y + 25 * x + (x * y) % 7 + 100 * k).astype('<u2')
        buf[off:off + t.nbytes] = t.tobytes()
    head = np.array([6, 5, 0, 500, 1000, 2000, 3000, 4500, 100, 200, 400, 800, 1600], '<i2').tobytes()
    buf[0x30000:0x30000 + len(head) + 60] = head + np.full(30, 7, '<i2').tobytes()   # flat header record
    return BinaryImage(bytes(buf))


def _key(found):
    return [(m.offset, m.rows, m.cols, m.dtype, m.endian, m.record_layout, m.calibrated_rate) for m in found]


def test_parallel_scan_equals_sequential(monkeypatch):
    image = _image()
    parallel.enable(False)
    sequential = _key(scan_calibration_candidates(image, use_definitions=False))
    monkeypatch.setenv('ECU_STUDIO_WORKERS', '2')
    parallel.enable()
    try:
        assert parallel.worker_count() == 2
        assert _key(scan_calibration_candidates(image, use_definitions=False)) == sequential
        assert parallel._pool is not None    # the worker processes were really used
    finally:
        parallel.enable(False)
    assert sequential                       # the image does contain candidates


def test_parallel_is_off_unless_an_entry_point_enables_it(monkeypatch):
    parallel.enable(False)
    monkeypatch.setenv('ECU_STUDIO_WORKERS', '4')
    assert parallel.worker_count() == 1      # library use never spawns processes by itself


def test_cancel_returns_nothing():
    parallel.enable(False)
    assert scan_calibration_candidates(_image(), use_definitions=False, cancelled=lambda: True) == []


def test_ordered_map_keeps_order_without_pool():
    assert parallel.ordered_map(pow, [(2, 3), (3, 2), (5, 0)], parallel=False) == [8, 9, 1]
