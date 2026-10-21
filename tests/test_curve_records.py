"""Curve records n, X[n], W[n]: accepted in record chains only, never from axis chains or swapped bytes."""
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.curve_records import scan_curve_records, CURVE_LAYOUT, MIN_RECORDS
from ecu_studio.core.confidence import evidence_class

X = [0, 400, 900, 1600, 2500, 3600]


def _curve(values, x=X, endian='<'):
    return np.array([len(x)] + list(x), endian + 'i2').tobytes() + np.asarray(values, endian + 'i2').tobytes()


def _records(n=MIN_RECORDS, endian='little', at=0x4000):
    """Stand-ins for accepted 2-D header records, giving the image's byte order."""
    return [MapDefinition('r', at + 0x100 * k + 20, 4, 4, 's16', endian, record_layout='candidate:nx,ny,x,y,z',
                          candidate_region_start=at + 0x100 * k) for k in range(n)]


def _image(*chunks, at=0x200):
    buf = bytearray(0x8000)
    pos = at
    for c in chunks:
        buf[pos:pos + len(c)] = c
        pos += len(c)
    return BinaryImage(bytes(buf))


def test_chained_curves_are_found_with_axis_and_values():
    # (A first value of n-1 followed by a rising run would read like a further counted
    # axis ending at the next record - an accepted ambiguity, avoided here.)
    a, b = _curve([50, 9, 14, 20, 27, 35]), _curve([-3, -1, 0, 2, 4, 9])
    image = _image(a, b)
    found = scan_curve_records(image, _records())
    values = sorted((m.offset, m.cols, m.dtype) for m in found if m.record_layout == CURVE_LAYOUT)
    assert values == [(0x200 + 2 + 12, 6, 'u16'), (0x200 + len(a) + 2 + 12, 6, 's16')]
    axes = {m.offset for m in found if m.record_layout != CURVE_LAYOUT}
    assert axes == {0x202, 0x200 + len(a) + 2}
    assert all(evidence_class(m) == 'curve:record' for m in found if m.record_layout == CURVE_LAYOUT)


def test_isolated_curve_is_not_enough():
    image = _image(_curve([5, 9, 14, 20, 27, 35]))
    assert scan_curve_records(image, _records()) == []


def test_axis_chain_is_not_read_as_curve():
    # n, X[n], n, Y[n], ...: the "values" of the first are the next counted axis.
    chain = b''.join(np.array([6] + [k + 100 * j for k in X], '<i2').tobytes() for j in range(4))
    found = [m for m in scan_curve_records(_image(chain), _records()) if m.record_layout == CURVE_LAYOUT]
    assert all(m.offset != 0x200 + 14 for m in found)


def test_curves_only_in_the_dominant_byte_order():
    a, b = _curve([5, 9, 14, 20, 27, 35]), _curve([-3, -1, 0, 2, 4, 9])
    image = _image(a, b)
    assert scan_curve_records(image, _records(endian='big')) == []        # image records are big-endian
    assert scan_curve_records(image, _records(n=MIN_RECORDS - 1)) == []   # no record convention
