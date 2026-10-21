"""ASAP2 RECORD_LAYOUT decoding: counts and axes read from the file, anchor from the firmware."""
import struct
import pytest
from ecu_studio.core.a2l import parse_a2l, suggest_anchor
from ecu_studio.core.model import BinaryImage

A2L = '''/begin PROJECT P "" /begin MODULE M ""
/begin MOD_COMMON "" BYTE_ORDER MSB_LAST ALIGNMENT_BYTE 1 ALIGNMENT_WORD 2 /end MOD_COMMON
/begin COMPU_METHOD lin "" RAT_FUNC "%6.2" "kPa" COEFFS 0 1 0 0 0 2 /end COMPU_METHOD
/begin RECORD_LAYOUT KfUb NO_AXIS_PTS_X 1 UBYTE NO_AXIS_PTS_Y 2 UBYTE AXIS_PTS_X 3 UBYTE INDEX_INCR DIRECT
  AXIS_PTS_Y 4 UBYTE INDEX_INCR DIRECT FNC_VALUES 5 UWORD COLUMN_DIR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT KlUb NO_AXIS_PTS_X 1 UBYTE AXIS_PTS_X 2 UBYTE INDEX_INCR DIRECT FNC_VALUES 3 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT SstUb NO_AXIS_PTS_X 1 UBYTE AXIS_PTS_X 2 UBYTE INDEX_INCR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT GkUb FNC_VALUES 1 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT
/begin AXIS_PTS SNM "" 0x800300 nmot SstUb 0 NO_COMPU_METHOD 8 0 255 /end AXIS_PTS
/begin CHARACTERISTIC KF "map" MAP 0x800100 KfUb 0 lin 0 65535
  /begin AXIS_DESCR STD_AXIS nmot NO_COMPU_METHOD 8 0 255 /end AXIS_DESCR
  /begin AXIS_DESCR STD_AXIS rl NO_COMPU_METHOD 8 0 255 /end AXIS_DESCR /end CHARACTERISTIC
/begin CHARACTERISTIC KL "curve" CURVE 0x800200 KlUb 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR STD_AXIS tmot NO_COMPU_METHOD 8 0 255 /end AXIS_DESCR /end CHARACTERISTIC
/begin CHARACTERISTIC GK "group curve" CURVE 0x800400 GkUb 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR COM_AXIS nmot NO_COMPU_METHOD 8 0 255 AXIS_PTS_REF SNM /end AXIS_DESCR /end CHARACTERISTIC
/end MODULE /end PROJECT'''


def _bin():
    d = bytearray(0x1000)
    d[0x100:0x107] = bytes([3, 2, 10, 20, 30, 1, 5])           # nx=3 ny=2, X, Y
    d[0x107:0x108] = b'\x00'                                     # alignment pad for UWORD values
    d[0x108:0x114] = struct.pack('<6H', *range(100, 106))
    d[0x200:0x209] = bytes([4, 1, 2, 3, 4, 7, 8, 9, 10])        # curve with 4 points
    d[0x300:0x306] = bytes([5, 10, 20, 30, 40, 50])             # shared axis
    d[0x400:0x405] = bytes([1, 2, 3, 4, 5])
    return bytes(d)


def test_std_axis_records_are_decoded_from_file_counts():
    data = _bin()
    r = parse_a2l(A2L).link(file_size=len(data), ecu_anchor=0x800000, data=data)
    maps = {m.name: m for m in r.maps}
    kf = maps['KF']
    assert (kf.offset, kf.rows, kf.cols, kf.dtype, kf.storage_order) == (0x108, 2, 3, 'u16', 'column-major')
    assert kf.axes_x == [10, 20, 30] and kf.axes_y == [1, 5] and kf.factor == 2 and kf.unit == 'kPa'
    kl = maps['KL']
    assert (kl.offset, kl.rows, kl.cols) == (0x205, 1, 4) and kl.axes_x == [1, 2, 3, 4]
    gk = maps['GK']
    assert (gk.offset, gk.cols) == (0x400, 5) and gk.axes_x == [10, 20, 30, 40, 50]


def test_counts_above_a2l_maximum_are_not_linked():
    data = bytearray(_bin())
    data[0x200] = 40                                            # max 8 points
    r = parse_a2l(A2L).link(file_size=len(data), ecu_anchor=0x800000, data=bytes(data))
    assert 'KL' not in {m.name for m in r.maps} and any('KL' in u for u in r.unlinked)


def test_without_data_stored_axes_stay_unsupported():
    r = parse_a2l(A2L).link(file_size=0x1000, ecu_anchor=0x800000)
    assert not r.maps and any('STD_AXIS' in u for u in r.unsupported)


def test_anchor_is_only_suggested_when_many_axes_increase():
    import ecu_studio.core.a2l as a2l
    data = _bin()
    cat = parse_a2l(A2L)
    old = a2l.MIN_ANCHOR_AXES
    try:
        a2l.MIN_ANCHOR_AXES = 2
        assert suggest_anchor(cat, data, step=0x100)['anchor'] == 0x800000
        assert suggest_anchor(cat, bytes(0x1000), step=0x100) is None   # nothing decodes
    finally:
        a2l.MIN_ANCHOR_AXES = old


EPK_A2L = A2L.replace('/begin MODULE M ""', '/begin MODULE M "" /begin MOD_PAR "" EPK "SW4711" ADDR_EPK 0x800800 /end MOD_PAR')


def test_epk_identifies_software_version_and_blocks_foreign_files():
    data = bytearray(_bin())
    cat = parse_a2l(EPK_A2L)
    assert cat.epk == 'SW4711' and cat.epk_address == 0x800800
    data[0x800:0x806] = b'SW4711'
    assert cat.identity(bytes(data), 0x800000)['status'] == 'match'
    assert cat.link(file_size=len(data), ecu_anchor=0x800000, data=bytes(data)).maps
    data[0x800:0x806] = b'SW4712'
    ident = cat.identity(bytes(data), 0x800000)
    assert ident['status'] == 'mismatch' and ident['found'] == 'SW4712'
    r = cat.link(file_size=len(data), ecu_anchor=0x800000, data=bytes(data))
    assert not r.maps and 'EPK passt nicht' in r.unlinked[0]
    assert parse_a2l(A2L).identity(bytes(data), 0x800000)['status'] == 'not-declared'


def test_epk_is_checked_through_segment_tables_too():
    # Regression: with a segment table the EPK check was skipped entirely.
    from ecu_studio.core.addressing import AddressSegment
    cat = parse_a2l(EPK_A2L)
    data = bytearray(_bin())
    segments = [AddressSegment(0x800000, 0x800FFF, 0x0)]
    data[0x800:0x806] = b'SW4712'                                    # other software
    assert cat.identity(bytes(data), segments=segments)['status'] == 'mismatch'
    r = cat.link(file_size=len(data), segments=segments, data=bytes(data))
    assert not r.maps and 'EPK passt nicht' in r.unlinked[0]
    data[0x800:0x806] = b'SW4711'
    assert cat.identity(bytes(data), segments=segments)['status'] == 'match'
    assert cat.link(file_size=len(data), segments=segments, data=bytes(data)).maps
    # A segment table that does not cover ADDR_EPK cannot prove the version: warned, not hidden.
    partial = [AddressSegment(0x800000, 0x8007FF, 0x0)]
    assert cat.identity(bytes(data), segments=partial)['status'] == 'outside'
    r = cat.link(file_size=len(data), segments=partial, data=bytes(data))
    assert 'nicht in der Datei/Segmenttabelle' in r.warnings[0]


def test_link_without_data_says_epk_was_not_checked():
    r = parse_a2l(EPK_A2L).link(file_size=0x1000, ecu_anchor=0x800000)
    assert any('ohne Dateidaten nicht geprüft' in w for w in r.warnings)


def test_axes_inside_records_are_reported_as_objects():
    data = _bin()
    r = parse_a2l(A2L).link(file_size=len(data), ecu_anchor=0x800000, data=data)
    axes = {(a.offset, a.cols, a.dtype) for a in r.axis_objects}
    assert (0x102, 3, 'u8') in axes and (0x105, 2, 'u8') in axes and (0x201, 4, 'u8') in axes
    assert (0x301, 5, 'u8') in axes          # shared AXIS_PTS of the group curve
