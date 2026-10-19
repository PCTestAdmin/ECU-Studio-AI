import struct
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.raw_trace import raw_trace


def test_raw_without_any_map():
    image = BinaryImage(bytes([0, 1, 0, 2, 0, 3]))
    trace = raw_trace(image, 0, 40, 'u16')
    assert trace.points == ((0, 1), (2, 2), (4, 3))
    assert (trace.start, trace.end, trace.low, trace.high) == (0, 6, 1, 3)


def test_endian_and_signed_and_32_bit():
    image = BinaryImage(bytes([0xff, 0xff, 0, 1]))
    assert raw_trace(image, 0, 2, 's16', 'big').points == ((0, -1), (2, 1))
    assert raw_trace(image, 0, 2, 'u16', 'little').points[0] == (0, 65535)
    assert raw_trace(image, 0, 1, 's32', 'big').points == ((0, -65535),)


def test_offset_aligned_and_clamped_to_eof():
    trace = raw_trace(BinaryImage(b'\x01\x02\x03\x04\x05'), 3, 65536, 'u16')
    assert trace.start == 2 and trace.end == 4
    assert trace.points == ((2, 0x0304),)


def test_edits_visible_but_source_unchanged():
    image = BinaryImage(b'\x00\x00\x00\x00')
    image.write(2, b'\x00\x0a')
    assert raw_trace(image, 0, 2, 'u16').points[-1] == (2, 10)
    assert image.original == b'\x00\x00\x00\x00'


def test_downsampling_preserves_peak_and_edges():
    a = [2] * 2000
    a[701] = 60000
    a[702] = 0
    data = struct.pack('>' + 'H' * len(a), *a)
    trace = raw_trace(BinaryImage(data), 0, 2000, 'u16', max_points=100)
    assert len(trace.points) <= 104
    assert (1402, 60000) in trace.points
    assert (1404, 0) in trace.points
    assert trace.points[0][0] == 0
    assert trace.points[-1][0] == (len(a) - 1) * 2


def test_invalid_and_empty():
    assert raw_trace(BinaryImage(b''), 0, 200).points == ()
    with pytest.raises(ValueError): raw_trace(BinaryImage(b'1234'), 0, 2, 'f32')
    with pytest.raises(ValueError): raw_trace(BinaryImage(b'1234'), 0, 2, 'u8', 'middle')
    with pytest.raises(ValueError): raw_trace(BinaryImage(b'1234'), 0, 0)
