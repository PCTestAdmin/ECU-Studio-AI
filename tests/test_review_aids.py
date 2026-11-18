"""Review aids for unproven data types (1.21.0, synthetic): open questions, missing evidence, readings side by
side, overlaps, filters, and the byte order an image does not decide."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import numpy as np
from ecu_studio.core import axis_records
from ecu_studio.core.axis_records import ENDIAN_OPEN, scan_axis_records
from ecu_studio.core.confidence import (BYTE_ORDER, PATTERN, SIGN, WIDTH, dtype_doubt, missing_evidence, overlapping,
                                        type_doubts)
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.review_checklist import DTYPE, OVERLAP, checklist
from ecu_studio.core.type_readings import readings


def cand(name, offset, layout='candidate:nx,ny,x,y,z', **kw):
    kw = {'rows': 2, 'cols': 2, 'dtype': 'u16', 'endian': 'little', 'source': 'heuristic', 'record_layout': layout,
          'axes_x': [1, 2], 'axes_y': [1, 2], **kw}
    return MapDefinition(name, offset, **kw)


def test_several_open_questions_are_all_named_with_the_missing_evidence():
    m = cand('A', 0, dtype='s16', dtype_alternatives=['u16'], notes=f'{ENDIAN_OPEN}: uneinig.')
    keys = [k for k, _ in type_doubts(m)]
    assert keys == [SIGN, BYTE_ORDER]
    assert 'Vorzeichen' in dtype_doubt(m) and 'Byte-Reihenfolge' in dtype_doubt(m)
    missing = missing_evidence(m)
    assert len(missing) == 2 and missing[0].startswith('Vorzeichen:') and missing[1].startswith('Byte-Reihenfolge:')
    # checked maps and definitions carry no open question
    assert not type_doubts(cand('B', 0, dtype_alternatives=['s16'], verified=True))
    assert not type_doubts(MapDefinition('C', 0, 2, 2, 'u16', source='a2l', notes=ENDIAN_OPEN))
    # an 8-bit table has no byte order to doubt
    assert BYTE_ORDER not in dict(type_doubts(cand('D', 0, dtype='u8', notes=ENDIAN_OPEN)))
    # a data pattern guess says that location and type rest on the values only
    assert PATTERN in dict(type_doubts(cand('E', 0, layout='candidate:row-pitch')))


def test_readings_show_the_same_bytes_in_each_open_type_raw_values_only():
    raw = np.array([0x0010, 0x8000, 0x7FFF, 0xFFFF], '<u2').tobytes()
    img = BinaryImage(raw + bytes(16))
    m = cand('A', 0, dtype='u16', dtype_alternatives=['s16'])
    out = readings(img, m)
    assert [(r.dtype, r.endian, r.chosen) for r in out] == [('u16', 'little', True), ('s16', 'little', False)]
    assert (out[0].low, out[0].high) == (0x10, 0xFFFF) and (out[1].low, out[1].high) == (-32768, 0x7FFF)
    assert 'gewählt' in out[0].describe() and 'gewählt' not in out[1].describe()
    # byte order open too: every sign in both orders
    m.notes = ENDIAN_OPEN
    assert {(r.dtype, r.endian) for r in readings(img, m)} == {('u16', 'little'), ('s16', 'little'),
                                                               ('u16', 'big'), ('s16', 'big')}
    # width open: the 8-bit table of the same shape
    w = cand('W', 0, notes='Wertebreite offen: auch eine 8-Bit-Tabelle gleicher Form.')
    assert ('u8', 4) in {(r.dtype, r.cells) for r in readings(img, w)}
    # nothing open: nothing to compare
    assert readings(img, cand('B', 0)) == []


def test_overlaps_are_counted_in_one_sweep():
    maps = [cand('A', 0), cand('B', 4), cand('C', 6), cand('D', 0x100)]   # 2x2 u16 = 8 bytes each
    assert overlapping(maps) == {0: 2, 1: 2, 2: 2}
    assert overlapping([]) == {}


def test_checklist_names_topics_byte_order_overlaps_and_missing_evidence():
    order = cand('Reihenfolge', 0x100, notes=f'{ENDIAN_OPEN}: uneinig.')
    a, b = cand('A', 0x200), cand('B', 0x204)
    clean = cand('Sauber', 0x300)
    items = {i.map.name: i for i in checklist([order, a, b, clean])}
    assert DTYPE in items['Reihenfolge'].topics and items['Reihenfolge'].missing
    assert any('Byte-Reihenfolge nicht belegt' in r for r in items['Reihenfolge'].reasons)
    assert OVERLAP in items['A'].topics and OVERLAP in items['B'].topics and OVERLAP not in items['Sauber'].topics
    assert items['Reihenfolge'].score > items['Sauber'].score and items['A'].score > items['Sauber'].score
    assert not items['Sauber'].missing and not items['Sauber'].topics


def big_wide_record(i, order):
    """16-bit counts and axes in ``order``: fixes the byte order by itself (own count)."""
    x, y = [0, 500, 1000, 2000, 3000, 4500], [100, 200, 400, 800, 1600]
    yy, xx = np.mgrid[:len(y), :len(x)]
    z = 300 + 50 * yy + 20 * xx + 7 * i + 3 * xx * yy
    t = ('>' if order == 'big' else '<') + 'u2'
    return np.array([len(x), len(y)] + x + [v + i for v in y], t).tobytes() + z.astype(t).tobytes()


def index_record():
    yy, xx = np.mgrid[:6, :8]
    z = (20 + 9 * yy + 5 * xx).astype('<u2')
    return bytes([8, 6]) + np.arange(8, dtype='<u2').tobytes() + np.arange(6, dtype='<u2').tobytes() + z.tobytes()


def split_image(n_little, n_big):
    buf = bytearray(0x200)
    for i in range(n_little):
        buf += big_wide_record(i, 'little') + bytes(8)
    for i in range(n_big):
        buf += big_wide_record(i, 'big') + bytes(8)
    at = len(buf)
    buf += index_record() + bytes(8) + bytes(0x200)
    return BinaryImage(bytes(buf)), at


def test_undecided_image_byte_order_is_shown_open(monkeypatch):
    img, at = split_image(12, 12)            # records disagree, no majority
    found = scan_axis_records(img, max_results=200)
    index = [m for m in found if m.candidate_region_start == at and m.width == 2]
    assert index and all(ENDIAN_OPEN in m.notes for m in index)
    assert all('Byte-Reihenfolge' in dtype_doubt(m) for m in index)
    # records whose own 16-bit counts fix their order stay unmarked
    own = [m for m in found if m.candidate_region_start is not None and m.candidate_region_start < at]
    assert own and not any(ENDIAN_OPEN in m.notes for m in own)
    # switch off: the old silent behaviour
    monkeypatch.setattr(axis_records, 'ENDIAN_KEEPS_OPEN', False)
    assert not any(ENDIAN_OPEN in m.notes for m in scan_axis_records(img, max_results=200))


def test_a_decided_image_byte_order_marks_nothing():
    img, _ = split_image(24, 0)
    assert not any(ENDIAN_OPEN in m.notes for m in scan_axis_records(img, max_results=200))


def _window(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtWidgets import QApplication
    from ecu_studio.ui.main_window import Window
    QApplication.instance() or QApplication([])
    return Window()


def test_dialog_filters_by_review_reason_and_shows_missing_evidence(tmp_path, monkeypatch):
    from ecu_studio.ui.review_dialog import ReviewDialog
    w = _window(tmp_path, monkeypatch)
    maps = [cand('Typ offen', 0x10, dtype_alternatives=['s16']), cand('Sauber', 0x40),
            cand('Ü1', 0x80), cand('Ü2', 0x84)]
    w.load_state(BinaryImage(bytes(256)), maps, [], '', None)
    d = ReviewDialog(w)
    assert d.table.rowCount() == 4
    d.topic.setCurrentText(DTYPE)
    assert [i.map.name for i in d.items] == ['Typ offen']
    assert 'Vorzeichen:' in d.table.item(0, 5).text() and '?' in d.table.item(0, 3).text()
    assert 'Prüfgrund' in d.count.text()
    d.topic.setCurrentText(OVERLAP)
    assert sorted(i.map.name for i in d.items) == ['Ü1', 'Ü2']
    d.topic.setCurrentIndex(0)
    assert d.table.rowCount() == 4
    w.saved_fingerprint = w.project_state()
    d.close(); w.close()


def test_catalogue_filters_unproven_types_and_overlaps_and_details_show_readings(tmp_path, monkeypatch):
    from ecu_studio.ui.main_window import TIER_FILTERS
    w = _window(tmp_path, monkeypatch)
    raw = np.array([0x0010, 0x8000, 0x7FFF, 0xFFFF], '<u2').tobytes()
    maps = [cand('Typ offen', 0, dtype_alternatives=['s16']), cand('Sauber', 0x40),
            cand('Ü1', 0x80), cand('Ü2', 0x84), cand('Geprüft', 0xC0, verified=True)]
    w.load_state(BinaryImage(raw + bytes(252)), maps, [], '', None)
    w.tier_filter.setCurrentText(TIER_FILTERS[6])
    assert [w.maps[w.catalog_model.indices[r]].name for r in range(w.catalog_model.rowCount())] == ['Typ offen']
    w.tier_filter.setCurrentText(TIER_FILTERS[7])
    assert sorted(w.maps[i].name for i in w.catalog_model.indices) == ['Ü1', 'Ü2']
    w.tier_filter.setCurrentIndex(0)
    w.select_map(maps[0])
    detail = w.identification_detail.text()
    assert 'Fehlender Beleg' in detail and 'Lesarten derselben Bytes' in detail and 's16 little: -32768' in detail
    # checked entries are set apart in the list
    from PySide6.QtCore import Qt
    row = next(r for r in range(w.catalog_model.rowCount()) if w.maps[w.catalog_model.indices[r]].name == 'Geprüft')
    assert w.catalog_model.data(w.catalog_model.index(row, 0), Qt.ItemDataRole.FontRole).bold()
    w.saved_fingerprint = w.project_state()
    w.close()
