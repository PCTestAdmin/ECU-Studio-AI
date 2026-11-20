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


def _byte_table_then(after):
    """A 4x4 byte table at 0x40 (header at 0x38, even) followed by ``after``."""
    buf = bytearray(0x200)
    buf[0x40:0x50] = bytes([60 + i % 3 for i in range(16)])
    buf[0x50:0x50 + len(after)] = after
    return bytes(buf)


def test_record_on_the_other_parity_is_no_width_evidence():
    """Round 3 cause 1: in 16-bit data a count byte at an odd address followed by a rising
    16-bit run reads like the next record. Real records follow on the header's parity."""
    after = bytes([0, 4]) + np.asarray([100, 300, 900, 2000], '<u2').tobytes()   # 'record' at 0x51
    out = ar._width_by_boundary(_byte_table_then(after), [(1., reading(0x40, 4, 4, 'u16'))])
    assert [m.dtype for _, m in out] == ['u16']
    assert ar.WIDTH_OPEN_NOTE not in out[0][1].notes


def test_lone_curve_record_leaves_the_width_open():
    """Round 3 cause 2: a single 1-D record behind the byte reading, not followed by another
    record, header or fill, is weak evidence: the 16-bit reading stays, its width is marked open."""
    garbage = bytes([0x77, 0x99]) * 16
    after = curve_record([100, 300, 900, 2000])[:10] + garbage   # n, axis, then no values/next record
    out = ar._width_by_boundary(_byte_table_then(after), [(1., reading(0x40, 4, 4, 'u16'))])
    assert [m.dtype for _, m in out] == ['u16']
    assert ar.WIDTH_OPEN_NOTE in out[0][1].notes
    assert 'Wertebreite nicht belegt' in dtype_doubt(out[0][1])


def test_two_dimensional_record_decides_the_width():
    after = bytes([3, 3, 10, 20, 30, 1, 2, 3]) + bytes([0x77, 0x99]) * 16
    out = ar._width_by_boundary(_byte_table_then(after), [(1., reading(0x40, 4, 4, 'u16'))])
    assert sorted(m.dtype for _, m in out) == ['s8', 'u8']


def test_record_list_that_goes_on_decides_the_width():
    after = curve_record([100, 300, 900, 2000]) + curve_record([300, 500, 700, 900])
    out = ar._width_by_boundary(_byte_table_then(after + bytes([0x77, 0x99]) * 8), [(1., reading(0x40, 4, 4, 'u16'))])
    assert sorted(m.dtype for _, m in out) == ['s8', 'u8']


def test_contradicted_smoothness_candidates_are_dropped():
    """Round 3: a row-pitch run with an accepted header record strictly inside is a record
    list; a run that is only smooth signed has no sign evidence. Records themselves stay."""
    from ecu_studio.core import scoped_scan as ss
    pitch = lambda off, dtype='u16': MapDefinition('', off, 8, 8, dtype, source='heuristic',
                                                  record_layout='candidate:row-pitch')
    record = reading(0x148, 4, 4, 'u16')                    # header at 0x140
    covering, clean, signed, at_start = pitch(0x100), pitch(0x400), pitch(0x600, 's16'), pitch(0x140)
    kept = ss._contradicted_patterns([covering, clean, signed, at_start, record])
    assert covering not in kept and signed not in kept
    assert clean in kept and record in kept and at_start in kept   # a header at its own start is not inside
    old = ss.PITCH_NO_RECORDS, ss.PITCH_UNSIGNED_ONLY
    try:
        ss.PITCH_NO_RECORDS = ss.PITCH_UNSIGNED_ONLY = False
        assert len(ss._contradicted_patterns([covering, signed, record])) == 3
    finally:
        ss.PITCH_NO_RECORDS, ss.PITCH_UNSIGNED_ONLY = old


def test_open_width_is_a_review_reason():
    from ecu_studio.core.review_checklist import checklist
    m = reading(0x40, 4, 4, 'u16', axes_x=[1, 2, 3, 4], axes_y=[1, 2, 3, 4])
    m.notes += ar.WIDTH_OPEN_NOTE
    item = checklist([m])[0]
    assert any(r.startswith('Wertebreite nicht belegt') for r in item.reasons) and item.score >= 3


def test_overlapping_readings_are_named_in_the_details():
    from ecu_studio.core.confidence import overlap_note
    a=MapDefinition('Vorschlag',0x100,4,4,dtype='u16',source='heuristic')
    b=MapDefinition('KF_DEF',0x110,2,2,dtype='u8',source='a2l')
    c=MapDefinition('Weit weg',0x400,2,2,dtype='u8',source='heuristic')
    note=overlap_note(a,[a,b,c])
    assert 'KF_DEF @0x110 (Definition/geprüft)' in note and 'Weit weg' not in note
    assert 'Vorschlag @0x100 (ungeprüfter Vorschlag)' in overlap_note(b,[a,b,c])
    assert overlap_note(c,[a,b,c])==''


def _mixed_record(nx, ny):
    """u8 counts, u8 X axis, 16-bit big-endian Y axis and 16-bit smooth values, at 0x100 in an empty image."""
    x = bytes(10 + 10 * i for i in range(nx))
    y = np.asarray([500 + 400 * j for j in range(ny)], '>u2').tobytes()
    z = np.asarray([[1000 + 37 * i + 53 * j + 3 * i * j for i in range(nx)] for j in range(ny)], '>u2').tobytes()
    buf = bytearray(0x400)
    rec = bytes([nx, ny]) + x + y + z
    buf[0x100:0x100 + len(rec)] = rec
    return BinaryImage(bytes(buf))


def _has_record(image, header, nx, ny):
    return any(m.candidate_region_start == header and (m.rows, m.cols) == (ny, nx) and m.width == 2
               for m in ar.scan_axis_records(image, max_results=200))


def test_sixteen_bit_fields_lie_on_their_records_alignment(monkeypatch):
    assert _has_record(_mixed_record(8, 6), 0x100, 8, 6)          # even X axis: Y axis and values aligned
    odd = _mixed_record(7, 6)                                      # Y axis an odd distance behind the header
    assert not _has_record(odd, 0x100, 7, 6)
    monkeypatch.setattr(ar, 'RECORD_ALIGNED_16', False)
    assert _has_record(odd, 0x100, 7, 6)                           # the switch alone decides


def test_header_contradicted_by_code_does_not_displace_a_pattern_reading():
    """Phase 4 (MS43 regression of round 3, synthetic layout): three 8x8 byte tables in a row, the outer two
    addressed by program code. Bytes inside the middle table and the next one also read as a header record;
    that record overlaps a code-referenced table with another start, so it is no evidence against the middle
    reading. A header that no code contradicts still removes the pattern reading."""
    from ecu_studio.core import scoped_scan as ss
    code = lambda off: MapDefinition('', off, 8, 8, 'u8', source='heuristic', record_layout='candidate:code-reference')
    pitch = MapDefinition('', 0x140, 8, 8, 'u8', source='heuristic', record_layout='candidate:row-pitch')
    left, right = code(0x100), code(0x180)
    weak = reading(0x186, 6, 8, 'u8')                       # header at 0x176 inside the pitch, data in the right table
    weak.candidate_region_start = 0x176
    kept = ss._contradicted_patterns([left, pitch, right, weak])
    assert pitch in kept and weak in kept                     # nothing removed here; the ranking decides overlaps
    confirmed = reading(0x186, 6, 8, 'u8')
    confirmed.candidate_region_start = 0x176
    assert pitch not in ss._contradicted_patterns([left, pitch, confirmed])   # no code against the header
    same = code(0x186)                                        # code addresses the record itself: confirms it
    assert pitch not in ss._contradicted_patterns([left, pitch, same, weak])
    old = ss.HEADS_CODE_CHECKED
    try:
        ss.HEADS_CODE_CHECKED = False
        assert pitch not in ss._contradicted_patterns([left, pitch, right, weak])
    finally:
        ss.HEADS_CODE_CHECKED = old


def test_sign_chosen_without_evidence_keeps_the_other_reading_open():
    """Phase 4: a 0/255 flag table reads smooth as -1/0; the wrap rule may pick signed, but the
    unsigned reading stays as an alternative and the type is shown as not established."""
    flags = bytes([0x00, 0xFF] * 8 + [0xFF, 0x00] * 8)          # 4 x 8 cells
    image = BinaryImage(bytes(64) + flags + bytes(64))
    readings = [(1., reading(64, 4, 8, 'u8')), (1., reading(64, 4, 8, 's8'))]
    out = ar._sign_by_wraps(image, readings)
    assert len(out) == 1
    m = out[0][1]
    other = 'u8' if m.dtype == 's8' else 's8'
    assert m.dtype_alternatives == [other]
    assert dtype_doubt(m).startswith('Vorzeichen nicht belegt')
    old = ar.SIGN_KEEPS_ALTERNATIVE
    try:
        ar.SIGN_KEEPS_ALTERNATIVE = False
        assert ar._sign_by_wraps(image, [(1., reading(64, 4, 8, 'u8')), (1., reading(64, 4, 8, 's8'))])[0][1].dtype_alternatives == []
    finally:
        ar.SIGN_KEEPS_ALTERNATIVE = old
    plain = BinaryImage(bytes(64) + bytes(range(32)) + bytes(64))  # no top bit: nothing to decide, nothing flagged
    assert all(not m.dtype_alternatives for _, m in ar._sign_by_wraps(plain, [(1., reading(64, 4, 8, 'u8'))]))


def test_flat_record_table_with_top_bit_keeps_both_signs_open():
    """Phase 4: a flat record table (every cell 0x8000) reads equally smooth in both signs; no code fixes
    the sign of a record, so the other sign stays open."""
    import numpy as np
    x, y = [100, 200, 400, 800], [10, 20, 30, 40]
    rec = np.array([4, 4] + x + y + [0x8000] * 16, '<u2').tobytes()
    image = BinaryImage(bytes(64) + rec + bytes(64))
    found = [m for m in ar.scan_axis_records(image, max_results=50) if m.offset == 64 + 20 and m.width == 2]
    assert found
    assert all(m.dtype_alternatives and dtype_doubt(m).startswith('Vorzeichen nicht belegt') for m in found)
