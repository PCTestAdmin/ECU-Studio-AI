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

def test_value_width_stays_open_without_a_record_right_behind_the_16_bit_values(monkeypatch):
    """Quality phase 3: the last curve of a chain has no record behind its values; they may as well be 8 bit
    ("?"). The first curve is followed by the second record, so its 16-bit width is fixed by the structure."""
    from ecu_studio.core import curve_records
    from ecu_studio.core.confidence import type_doubts
    a, b = _curve([50, 9, 14, 20, 27, 35]), _curve([-3, -1, 0, 2, 4, 9])
    image = _image(a, b)

    def doubts():
        found = sorted((m for m in scan_curve_records(image, _records()) if m.record_layout == CURVE_LAYOUT),
                       key=lambda m: m.offset)
        return [(m.offset, m.cols, m.dtype, sorted(k for k, _ in type_doubts(m))) for m in found]
    now = doubts()
    assert 'width' not in now[0][3] and 'width' in now[1][3]
    monkeypatch.setattr(curve_records, 'CURVE_WIDTH_OPEN', False)
    old = doubts()
    assert [x[:3] for x in old] == [x[:3] for x in now] and not any('width' in x[3] for x in old)



def _found(image, layout=CURVE_LAYOUT):
    from ecu_studio.core.confidence import type_doubts
    return sorted(((m.offset, m.cols, m.dtype, sorted(k for k, _ in type_doubts(m)))
                   for m in scan_curve_records(image, _records()) if m.record_layout == layout))


def test_width_stays_open_when_a_record_also_begins_behind_the_8_bit_values(monkeypatch):
    """Quality phase 4: a record behind the 16-bit values, but also a record head right behind the 8-bit values.
    Both widths fit the structure: '?'. A mere count-prefixed axis there (bytes 4, 10, 20, 30, 40) is not enough:
    such byte runs are common in data (development: 18 wrong widths caught for 311 right ones marked)."""
    from ecu_studio.core import curve_records
    raw = bytes([50, 0, 9, 0, 14, 0]) + bytes([4, 10, 20, 30, 40, 0])
    a = np.array([len(X)] + X, '<i2').tobytes() + raw
    b = _curve([-3, -1, 0, 2, 4, 9])
    image = _image(a, b)
    values = 0x200 + 14

    def found(records):
        from ecu_studio.core.confidence import type_doubts
        return sorted(((m.offset, m.dtype, sorted(k for k, _ in type_doubts(m)))
                       for m in scan_curve_records(image, records) if m.record_layout == CURVE_LAYOUT))
    assert 'width' not in found(_records())[0][2]                       # only an axis behind the 8-bit values
    head = MapDefinition('r', values + 6 + 20, 4, 4, 's16', 'little', record_layout='candidate:nx,ny,x,y,z',
                         candidate_region_start=values + 6)
    first = found(_records() + [head])[0]
    assert first[:2] == (values, 'u16') and 'width' in first[2]
    monkeypatch.setattr(curve_records, 'WIDTH_BOTH_OPEN', False)
    assert 'width' not in found(_records() + [head])[0][2]


def test_16_bit_axis_whose_bytes_also_rise_keeps_its_width_open():
    rising = [0x0201, 0x0403, 0x0605, 0x0807, 0x0A09, 0x0C0B]          # bytes 1, 2, 3, ... rise one by one
    image = _image(_curve([50, 9, 14, 20, 27, 35], x=rising), _curve([-3, -1, 0, 2, 4, 9]))
    axes = _found(image, layout='candidate:record-axis')
    assert 'width' in axes[0][3] and 'width' not in axes[1][3]        # the second axis is X (0, 400, ...)


def test_8_bit_values_by_head_is_an_experiment_and_off_by_default(monkeypatch):
    """A record right behind the 8-bit values and none behind the 16-bit values: with CURVE_U8_BY_HEAD the
    values are read as 8 bit (marked as derived); without it they stay 16 bit with the width open."""
    from ecu_studio.core import curve_records
    lead = _curve([-30, -10, 0, 20, 40, 90])
    head = np.array([len(X)] + X, '<i2').tobytes()
    a = head + bytes([5, 7, 9, 11, 13, 15])                            # six 8-bit values, then the next record
    b = _curve([-3, -1, 0, 2, 4, 9])
    image = _image(lead, a, b, b)
    at = 0x200 + len(lead) + 14
    default = {o: rest for o, *rest in _found(image)}
    assert default[at][1] == 'u16' and 'width' in default[at][2]
    monkeypatch.setattr(curve_records, 'CURVE_U8_BY_HEAD', True)
    switched = {o: rest for o, *rest in _found(image)}
    assert switched[at][:2] == [6, 'u8'] and switched[at][2] == ['width-derived']
    # negative: with a record behind the 16-bit values nothing switches
    assert switched[0x200 + 14][1] in ('u16', 's16')
