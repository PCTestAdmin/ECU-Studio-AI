"""One image, one byte order: records vote, coincidental readings in the other order go (1.21.0, synthetic)."""
import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core import axis_records
from ecu_studio.core.axis_records import scan_axis_records, _image_order, ORDER_MIN

X = [0, 500, 1000, 2000, 3000, 4500]
Y = [100, 200, 400, 800, 1600]


def wide_record(i):
    """16-bit counts and axes, little endian: fixes the byte order by itself."""
    yy, xx = np.mgrid[:len(Y), :len(X)]
    z = 300 + 50 * yy + 20 * xx + 7 * i + 3 * xx * yy
    return np.array([len(X), len(Y)] + X + [v + i for v in Y], '<u2').tobytes() + z.astype('<u2').tobytes()


def index_record():
    """8-bit counts, 16-bit index axes 0..7 / 0..5 (little endian), small 16-bit values."""
    yy, xx = np.mgrid[:6, :8]
    z = (20 + 9 * yy + 5 * xx).astype('<u2')
    return bytes([8, 6]) + np.arange(8, dtype='<u2').tobytes() + np.arange(6, dtype='<u2').tobytes() + z.tobytes()


def image(n_wide):
    parts = [wide_record(i) for i in range(n_wide)] + [index_record()]
    buf = bytearray(0x200)
    for p in parts:
        buf += p + bytes(8)
    buf += bytes(0x200)
    at = len(buf) - 0x200 - 8 - len(index_record())
    return BinaryImage(bytes(buf)), at + 2 + 2 * 14


def test_vote_needs_enough_records_and_a_clear_majority():
    assert _image_order(['little'] * ORDER_MIN) == 'little'
    assert _image_order(['little'] * (ORDER_MIN - 1)) is None
    assert _image_order(['big'] * 30 + ['little'] * 16) is None
    assert _image_order(['big'] * 40 + ['little'] * 20) == 'big'


def test_index_axes_are_read_in_the_image_byte_order():
    img, z = image(24)
    found = [m for m in scan_axis_records(img, max_results=200) if m.offset == z]
    assert found and all(m.endian == 'little' for m in found if m.width == 2)
    assert found[0].axes_x == list(range(8)) and found[0].axes_y == list(range(6))
    assert all(m.endian == 'little' for m in scan_axis_records(img, max_results=200) if m.width == 2)


def test_without_a_majority_the_old_readings_stay(monkeypatch):
    img, z = image(24)
    monkeypatch.setattr(axis_records, 'BYTE_ORDER', False)
    old = [m for m in scan_axis_records(img, max_results=200) if m.offset == z]
    # before 1.21.0 the index axes only passed byte-swapped (0, 256, 512 ...)
    assert old and old[0].axes_x == [256 * k for k in range(8)]
    monkeypatch.setattr(axis_records, 'BYTE_ORDER', True)
    img, z = image(4)                       # too few records to vote: unchanged
    few = [m for m in scan_axis_records(img, max_results=200) if m.offset == z]
    assert few and all(m.axes_x == [256 * k for k in range(8)] for m in few)


def test_sign_stays_open_after_the_byte_order_is_turned():
    """Phase 4: a record read in the other byte order gets the image order; the sign judged in the old order
    says nothing about the new one, so with a top bit set the other sign stays an open alternative."""
    yy, xx = np.mgrid[:6, :8]
    z_values = (0x8010 + 9 * yy + 5 * xx).astype('<u2')
    record = bytes([8, 6]) + np.arange(8, dtype='<u2').tobytes() + np.arange(6, dtype='<u2').tobytes() + z_values.tobytes()
    buf = bytearray(0x200)
    for p in [wide_record(i) for i in range(24)] + [record]:
        buf += p + bytes(8)
    buf += bytes(0x200)
    z = len(buf) - 0x200 - 8 - len(record) + 2 + 2 * 14
    img = BinaryImage(bytes(buf))

    def at_z():
        return [m for m in scan_axis_records(img, max_results=200) if m.offset == z]
    found = at_z()
    assert found and found[0].endian == 'little' and 'Mehrheit' in found[0].notes
    assert found[0].dtype_alternatives == ['u16' if found[0].dtype == 's16' else 's16']


def test_axes_read_against_the_majority_stay_open_when_both_readings_rise(monkeypatch):
    """Quality phase 3: a flat 8-bit record bounded by the next header is outside the byte-order vote; its 16-bit
    axes were read big (tried first) in a little-endian image although both readings rise. The order stays open
    ("?") on the record axes; values, addresses and shapes do not change."""
    from ecu_studio.core.axis_records import record_axes
    from ecu_studio.core.confidence import type_doubts

    def axis(n):
        return b''.join(bytes([k + 1, 2 * k + 1]) for k in range(n))      # rises read little and read big
    record = bytes([8, 6]) + axis(8) + axis(6) + bytes([40]) * 48
    buf = bytearray(0x200)
    for i in range(24):
        buf += wide_record(i) + bytes(8)
    z = len(buf) + 2 + 28
    buf += record + wide_record(99) + bytes(0x200)
    img = BinaryImage(bytes(buf))

    def at_z():
        return [m for m in scan_axis_records(img, max_results=300) if m.offset == z]
    found = at_z()
    assert found and axis_records.ENDIAN_OPEN_AXES in found[0].notes
    axes = record_axes(img, found[0])
    assert len(axes) == 2 and all(any(k == 'byte-order' for k, _ in type_doubts(a)) for a in axes)
    monkeypatch.setattr(axis_records, 'ENDIAN_AXES_OPEN', False)
    old = at_z()
    assert [(m.offset, m.rows, m.cols, m.dtype, m.endian, m.axes_x) for m in old] == \
           [(m.offset, m.rows, m.cols, m.dtype, m.endian, m.axes_x) for m in found]
    assert not any(k == 'byte-order' for a in record_axes(img, old[0]) for k, _ in type_doubts(a))
