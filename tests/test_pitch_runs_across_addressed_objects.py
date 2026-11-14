"""Smooth runs across objects the code addresses one by one are not one table (1.21.0, synthetic)."""
import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.structure_scan import scan_structures, PITCH_LAYOUT
from ecu_studio.core.tricore_refs import Descriptors


def smooth_image():
    rng = np.random.default_rng(7)
    data = bytearray(rng.integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    y, x = np.mgrid[:12, :16]
    z = (1000 + 40 * y + 25 * x + 3 * x * y).astype('<u2').tobytes()
    data[0x1000:0x1000 + len(z)] = z
    return BinaryImage(bytes(data))


def pitch(found):
    return [m for m in found if m.record_layout == PITCH_LAYOUT and m.offset <= 0x1000 + 0x100 < m.offset + m.length]


def test_smooth_run_is_found_without_code_evidence():
    assert pitch(scan_structures(smooth_image(), calls=Descriptors()))


def test_run_across_an_addressed_object_is_dropped():
    calls = Descriptors()
    calls.addressed = frozenset({0x1000 + 0x100})     # the code reads an object inside the run
    found = scan_structures(smooth_image(), calls=calls)
    assert not pitch(found)
    # a reading of the rows in front of the object may remain; none crosses it
    assert all(m.offset + m.length <= 0x1100 or m.offset >= 0x1100 for m in found if m.record_layout == PITCH_LAYOUT)


def test_addressed_object_at_the_start_does_not_drop_the_run():
    calls = Descriptors()
    calls.addressed = frozenset({0x1000})
    found = [m for m in scan_structures(smooth_image(), calls=calls) if m.record_layout == PITCH_LAYOUT]
    assert any(m.offset == 0x1000 for m in found)
