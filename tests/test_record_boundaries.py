"""Record rules of 1.21.0 (synthetic data only): value width from the record boundary,
16-bit fields on even addresses, byte-order votes only from records that decide the order,
and the data-type doubt shown to the user."""
import numpy as np
from ecu_studio.core import axis_records as ar
from ecu_studio.core.confidence import dtype_doubt
from ecu_studio.core.model import BinaryImage, MapDefinition

LAYOUT = 'candidate:nx,ny,x,y,z'


def curve_record(points, pad=0):
    """n (16 bit), rising 16-bit little-endian axis, then values (all little endian, aligned)."""
    return (bytes(pad) + np.asarray([len(points)], '<u2').tobytes() + np.asarray(points, '<u2').tobytes()
            + bytes(range(len(points))))


def reading(offset, rows, cols, dtype, endian='little', **kw):
    return MapDefinition('', offset, rows, cols, dtype, endian, source='heuristic', record_layout=LAYOUT,
                         candidate_region_start=offset - 8, **kw)


def test_record_start_needs_a_count_and_a_strictly_rising_axis():
    buf = bytes(4) + curve_record([100, 300, 900, 2000])
    assert ar._record_start(buf, 4, 'little')
    assert ar._record_start(buf, 2, 'little')                       # up to three alignment bytes before it
    assert not ar._record_start(bytes(4) + curve_record([100, 300, 200, 2000]), 4, 'little')
    assert not ar._record_start(np.asarray([2, 1, 2], '<u2').tobytes() + bytes(8), 0, 'little')   # count < 3
    assert not ar._record_start(bytes(64), 0, 'little')


def test_word_reading_of_a_byte_table_becomes_bytes():
    rows, cols = 4, 4
    table = bytes([60 + i % 3 for i in range(rows * cols)])             # byte table at 0x40
    buf = bytearray(0x200)
    buf[0x40:0x40 + 16] = table
    nxt = curve_record([100, 300, 900, 2000])
    buf[0x40 + 16:0x40 + 16 + len(nxt)] = nxt                          # next record right behind the bytes
    out = ar._width_by_boundary(bytes(buf), [(1., reading(0x40, rows, cols, 'u16'))])
    assert sorted(m.dtype for _, m in out) == ['s8', 'u8']
    assert all('Wertebreite 1 Byte' in m.notes for _, m in out)


def test_word_reading_stays_when_a_record_follows_the_words():
    rows, cols = 4, 4
    buf = bytearray(0x200)
    buf[0x40:0x40 + 32] = (0x1000 + 0x100 * (np.arange(16) % 5)).astype('<u2').tobytes()   # no count-like bytes
    nxt = curve_record([100, 300, 900, 2000])
    buf[0x60:0x60 + len(nxt)] = nxt                                    # behind the 16-bit reading
    out = ar._width_by_boundary(bytes(buf), [(1., reading(0x40, rows, cols, 'u16'))])
    assert [m.dtype for _, m in out] == ['u16']
    lone = ar._width_by_boundary(bytes(0x200), [(1., reading(0x40, rows, cols, 'u16'))])   # no record anywhere
    assert [m.dtype for _, m in lone] == ['u16']


def test_image_parity_needs_enough_votes_and_a_clear_majority():
    def votes(even, odd):
        found = [(1., MapDefinition('', 0, 4, 4, 'u16', candidate_region_start=2 * i)) for i in range(even)]
        found += [(1., MapDefinition('', 0, 4, 4, 'u16', candidate_region_start=2 * i + 1)) for i in range(odd)]
        return ar._image_parity(found, {id(m): ('little', m) for _, m in found})
    assert votes(30, 2) == 0
    assert votes(20, 5) == 0
    assert votes(20, 6) is None          # less than four to one
    assert votes(10, 0) is None          # too few votes
    assert votes(1, 40) == 1


def test_small_axis_values_do_not_vote_for_a_byte_order():
    small = np.asarray([10, 20, 40, 80], '<u2').tobytes() + np.asarray([1, 2, 3, 4], '<u2').tobytes()
    assert ar._both_orders(small, 0, 4, 4, 2, 2, 'little')           # v and v*256 both rise
    wide = np.asarray([300, 520, 1000, 1700], '<u2').tobytes() + np.asarray([260, 600, 900, 1400], '<u2').tobytes()
    assert not ar._both_orders(wide, 0, 4, 4, 2, 2, 'little')


def test_aligned_image_drops_odd_word_readings():
    """Many records with 16-bit axes on even addresses: a 16-bit reading at an odd address is dropped."""
    from test_record_widths import record, surface, image
    recs = [record([500, 1000, 1500, 2000, 3000, 4000], [100, 200, 300, 400, 500], 2, 2,
                   surface(5, 6, base=20 + 3 * i, dtype='<u2') * 7, align=4) for i in range(24)]
    img, starts = image(*recs, size=0x4000)
    found = ar.scan_axis_records(img, max_results=500)
    assert {m.offset % 2 for m in found if m.width == 2} <= {0}
    assert len([m for m in found if m.offset - 24 in starts]) >= 20


def test_dtype_doubt_texts():
    pattern = MapDefinition('', 0, 8, 8, 'u8', source='heuristic', record_layout='candidate:row-pitch')
    assert 'Glätte' in dtype_doubt(pattern)
    signed = reading(0x40, 4, 4, 'u8', dtype_alternatives=['s8'])
    assert 's8' in dtype_doubt(signed)
    record = reading(0x40, 4, 4, 'u16')
    assert dtype_doubt(record) == ''
    record.verified = True
    record.dtype_alternatives = ['s16']
    assert dtype_doubt(record) == ''                                  # checked by the user
    defined = MapDefinition('', 0, 8, 8, 'u8', source='xdf', record_layout='candidate:row-pitch')
    assert dtype_doubt(defined) == ''


def test_catalogue_marks_unproven_types_and_transferred_names():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from ecu_studio.ui.catalogue import CatalogueModel
    app = QApplication.instance() or QApplication([])
    guessed = reading(0x40, 4, 4, 'u8', dtype_alternatives=['s8'])
    proven = reading(0x80, 4, 4, 'u16')
    moved = MapDefinition('KF_A', 0xC0, 4, 4, 'u16', source='transfer-proposed',
                          label_origin='Namensübertragung · Anker')
    model = CatalogueModel()
    model.set_context([guessed, proven, moved], [0, 1, 2], [])
    text = [model.data(model.index(r, 0)) for r in range(3)]
    assert '4×4  u8?' in text[0] and '4×4  u16 ' in text[1]
    assert 'Name übertragen (ungeprüft)' in text[2]
    tip = model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole)
    assert 'Datentyp u8 nicht belegt' in tip and 's8' in tip
    assert 'nicht belegt' not in model.data(model.index(1, 0), Qt.ItemDataRole.ToolTipRole)
    assert app is not None
