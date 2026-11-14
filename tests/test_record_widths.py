"""Header records with mixed axis widths, signed byte values and widths fixed by the next header
(1.21.0, synthetic images only)."""
import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core import axis_records
from ecu_studio.core.axis_records import scan_axis_records, record_axes

X16 = [500, 1000, 1500, 2000, 3000, 4000]                 # 6 points, 16 bit
Y8 = [10, 20, 40, 60, 80]                                  # 5 points, 8 bit


def surface(rows, cols, base=40, dtype='u1'):
    y, x = np.mgrid[:rows, :cols]
    return (base + 7 * y + 4 * x + x * y).astype(dtype)


def record(x, y, xw, yw, z, align=1):
    """u8 counts, then X and Y in their own widths (little endian), then Z; padded to ``align``."""
    head = bytes([len(x), len(y)])
    ax = np.asarray(x, '<u2').tobytes() if xw == 2 else bytes(x)
    ay = np.asarray(y, '<u2').tobytes() if yw == 2 else bytes(y)
    raw = head + ax + ay + z.tobytes()
    return raw + bytes(-len(raw) % align)


def image(*records, at=0x100, size=0x2000):
    buf = bytearray(size)
    pos, starts = at, []
    for r in records:
        starts.append(pos)
        buf[pos:pos + len(r)] = r
        pos += len(r)
    return BinaryImage(bytes(buf)), starts


def test_mixed_axis_widths_are_read_with_their_own_widths():
    z = surface(5, 6, dtype='<u2') * 30
    img, (h,) = image(record(X16, Y8, 2, 1, z))
    data_at = h + 2 + 6 * 2 + 5
    found = [m for m in scan_axis_records(img, max_results=200) if m.offset == data_at]
    assert found, 'record with 16-bit X and 8-bit Y axis not found'
    m = found[0]
    assert (m.rows, m.cols, m.axes_x, m.axes_y) == (5, 6, X16, Y8)
    assert (m.axis_x_offset, m.axis_y_offset) == (h + 2, h + 2 + 12)
    axes = record_axes(img, m)
    assert [(a.offset, a.cols, a.dtype) for a in axes] == [(h + 2, 6, 'u16'), (h + 14, 5, 'u8')]


def test_signed_byte_values_are_read_signed():
    y, x = np.mgrid[:5, :6]
    z = (-40 + 12 * x + 6 * y).astype('i1')                         # -40 ... 44 around zero
    img, (h,) = image(record(X16, [100, 200, 300, 400, 500], 2, 2, z))
    data_at = h + 2 + 11 * 2
    found = [m for m in scan_axis_records(img, max_results=200) if m.offset == data_at and m.width == 1]
    assert found and found[0].dtype == 's8'


def test_next_header_decides_between_byte_and_word_values():
    """Byte values behind 16-bit axes also read as a word table; the next record header,
    after two alignment bytes, says bytes."""
    first = record(X16, [100, 200, 300, 400, 500], 2, 2, surface(5, 6, base=20), align=4)
    second = record(X16, [100, 200, 300, 400, 500], 2, 2, surface(5, 6, base=90), align=4)
    img, (h1, h2) = image(first, second)
    data_at = h1 + 2 + 11 * 2
    widths = {m.width for m in scan_axis_records(img, max_results=200) if m.offset == data_at}
    assert widths == {1}


def test_width_rule_keeps_the_width_closest_before_the_next_header():
    from ecu_studio.core.model import MapDefinition

    def rec(head, off, w):
        return (1., MapDefinition('', off, 4, 4, 'u8' if w == 1 else 'u16', 'little', candidate_region_start=head))
    nxt = rec(0x40 + 16 + 2, 0x80, 1)                       # next header 2 alignment bytes after 16 cells
    kept = axis_records._width_by_next_header([rec(0x30, 0x40, 1), rec(0x30, 0x40, 2), nxt])
    assert sorted(m.width for _, m in kept if m.offset == 0x40) == [1]
    both = axis_records._width_by_next_header([rec(0x30, 0x40, 1), rec(0x30, 0x40, 2)])   # no next header
    assert sorted(m.width for _, m in both) == [1, 2]


def test_flat_byte_values_behind_word_axes_need_the_next_header():
    flat = np.full((5, 6), 7, 'u1')
    alone, (h,) = image(record(X16, [100, 200, 300, 400, 500], 2, 2, flat, align=4))
    data_at = h + 2 + 11 * 2
    assert not [m for m in scan_axis_records(alone, max_results=200) if m.offset == data_at and m.width == 1]
    nxt = record(X16, [100, 200, 300, 400, 500], 2, 2, surface(5, 6, base=90), align=4)
    chained, (h, _) = image(record(X16, [100, 200, 300, 400, 500], 2, 2, flat, align=4), nxt)
    found = [m for m in scan_axis_records(chained, max_results=200) if m.offset == data_at and m.width == 1]
    assert found and found[0].dtype == 'u8' and 'nächste Datensatzkopf' in found[0].notes


def test_sign_rule_prefers_the_reading_without_wrapping_neighbours():
    from ecu_studio.core.precision import preferred_sign
    y, x = np.mgrid[:4, :6]
    around_zero = (-30 + 12 * x + 5 * y).astype('i1').tobytes()
    assert preferred_sign(around_zero, 4, 6, 1) == 's'
    high = (100 + 10 * x + 5 * y).astype('u1').tobytes()            # crosses 127/128 smoothly
    assert preferred_sign(high, 4, 6, 1) == 'u'
    assert preferred_sign(bytes(range(24)), 4, 6, 1) is None        # no top bit: both readings equal
    negative = np.full((4, 6), -50, 'i1') + (x + y).astype('i1')       # every cell >= 0x80: no wrap
    assert preferred_sign(negative.tobytes(), 4, 6, 1) is None
    modest = (-3 + 2 * x + y).astype('i1').tobytes()                    # one wrap, steps not 4x smaller
    assert preferred_sign(modest, 4, 6, 1) in ('s', 'u')
    # Known limit: 0/255 flag tables read as -1/0.
    sentinel = np.array([[0, 255, 0, 255, 0, 255]] * 4, 'u1').tobytes()
    assert preferred_sign(sentinel, 4, 6, 1) == 's'
