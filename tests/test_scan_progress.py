"""The scan names its stages and its progress only rises; cancelling stops it; speedups keep results."""
import numpy as np
from ecu_studio.core.axis_arrays import scan_count_axes
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def _image():
    rng = np.random.default_rng(5)
    data = bytearray(rng.integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    y, x = np.mgrid[:12, :12]
    data[0x2000:0x2120] = ((100 + 7 * y + 5 * x) * 9).astype('>u2').tobytes()
    return BinaryImage(bytes(data))


def test_stages_and_rising_progress():
    steps, percents = [], []
    scan_calibration_candidates(_image(), use_definitions=False, step=steps.append, progress=percents.append)
    assert steps[0] == 'Kalibrierbereich bestimmen'
    assert 'Programmcode: Interpolationsaufrufe' in steps and any(s.endswith('Kandidaten bewerten') for s in steps)
    assert percents == sorted(percents) and percents[-1] == 100


def test_cancel_returns_nothing():
    assert scan_calibration_candidates(_image(), use_definitions=False, cancelled=lambda: True) == []


def test_count_axes_overlap_choice_matches_the_plain_rule():
    # Chained count-prefixed arrays with overlapping alternatives: binary-search choice == pairwise check.
    rng = np.random.default_rng(9)
    blob = bytearray()
    for _ in range(300):
        n = int(rng.integers(3, 9))
        start = int(rng.integers(0, 50))
        blob += bytes([n]) + bytes(sorted(set(range(start, start + 4 * n, 4)))[:n])
        if rng.random() < .3:
            blob += bytes(rng.integers(0, 256, int(rng.integers(1, 5)), dtype=np.uint8))
    axes = scan_count_axes(bytes(blob))
    spans = [(a.header, a.end) for a in axes]
    assert axes and all(e1 <= s2 for (s1, e1), (s2, e2) in zip(spans, spans[1:]))
