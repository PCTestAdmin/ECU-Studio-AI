"""Review checklist: order by need for a human decision, explicit decisions, persisted rejections."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition, save_project, load_project, read_project_reviews
from ecu_studio.core.review_checklist import checklist, decision, rejected_keys, is_rejected, validate_log


def cand(name, offset, layout='candidate:code-call', **kw):
    kw = {'rows': 4, 'cols': 4, 'dtype': 'u8', 'source': 'heuristic', 'record_layout': layout, **kw}
    return MapDefinition(name, offset, **kw)


def test_order_and_reasons():
    clean = cand('sauber', 0x100, axes_x=[1, 2, 3, 4], axes_y=[1, 2, 3, 4], calibrated_rate=.97)
    sign = cand('vorzeichen', 0x200, dtype='u16', dtype_alternatives=['s16'], axes_x=[1, 2, 3, 4],
                axes_y=[1, 2, 3, 4], calibrated_rate=.97)
    bare = cand('ohne achsen', 0x300, layout='candidate:row-pitch', calibrated_rate=.23)
    defined = MapDefinition('Definition', 0x400, 4, 4, 'u8', source='xdf')
    contradicted = MapDefinition('Widerspruch', 0x500, 4, 4, 'u8', source='xdf')
    done = cand('geprüft', 0x600, verified=True)
    items = checklist([clean, sign, bare, defined, contradicted, done],
                      conflicts={0x500: ['0x500: Größe – …']})
    names = [i.map.name for i in items]
    assert names == ['Widerspruch', 'ohne achsen', 'vorzeichen', 'sauber']   # definition and checked map left out
    assert items[0].priority == 'hoch' and 'Widerspruch' in items[0].reasons[0]
    assert any('ebenfalls möglich: s16' in r for r in items[2].reasons)
    assert 'Achsen fehlen' in items[1].reasons and any('23%' in r for r in items[1].reasons)
    assert items[-1].reasons == ['Automatisch erkannt, noch nicht geprüft'] and items[-1].priority == 'niedrig'


def test_shared_axes_are_linked():
    a = cand('A', 0x100, axis_x_offset=0x80, axes_x=[1, 2, 3, 4], axes_y=[1, 2, 3, 4])
    b = cand('B', 0x200, axis_x_offset=0x80, axes_x=[1, 2, 3, 4], axes_y=[1, 2, 3, 4])
    items = {i.map.name: i for i in checklist([a, b])}
    assert items['A'].links == ['X-Achse @ 0x80 gemeinsam mit 1 weiteren: B']


def test_rejections_by_table_and_latest_decision():
    m = cand('x', 0x100, rows=4, cols=8)
    log = [decision(m, 'abgelehnt', 'Text, keine Tabelle')]
    keys = rejected_keys(log)
    assert is_rejected(cand('y', 0x100, rows=8, cols=4), keys)          # transposed: same table
    assert not is_rejected(cand('z', 0x100, rows=4, cols=8, dtype='u16'), keys)
    assert not rejected_keys(log + [decision(m, 'bestätigt')])
    with pytest.raises(ValueError):
        decision(m, 'vielleicht')
    with pytest.raises(ValueError):
        validate_log([{'decision': 'abgelehnt', 'offset': -1, 'rows': 1, 'cols': 1, 'dtype': 'u8'}])


def test_reviews_round_trip_in_the_project(tmp_path):
    src = tmp_path / 'a.bin'; src.write_bytes(bytes(range(256)) * 4)
    image = BinaryImage.from_file(str(src))
    log = [decision(cand('x', 0x10), 'abgelehnt', 'Code')]
    save_project(str(tmp_path / 'p.ecustudio'), image, [], [], '', reviews=log)
    assert read_project_reviews(str(tmp_path / 'p.ecustudio')) == log
    load_project(str(tmp_path / 'p.ecustudio'))                          # still a valid format-1 project
    save_project(str(tmp_path / 'old.ecustudio'), image, [], [], '')
    assert read_project_reviews(str(tmp_path / 'old.ecustudio')) == []


def test_dialog_confirm_and_reject(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui.main_window import Window
    from ecu_studio.ui.review_dialog import ReviewDialog
    app = QApplication.instance() or QApplication([])
    w = Window()
    maps = [cand('A', 0x10), cand('B', 0x40)]
    w.load_state(BinaryImage(bytes(256)), maps, [], '', None)
    d = ReviewDialog(w)
    assert d.table.rowCount() == 2
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    d.table.selectRow(0); first = d.current(); d.confirm()
    assert first.verified and d.table.rowCount() == 1 and w.reviews[-1]['decision'] == 'bestätigt'
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('keine Tabelle', True))
    d.table.selectRow(0); second = d.current(); d.reject_map()
    assert second not in w.maps and w.reviews[-1]['reason'] == 'keine Tabelle'
    # A rescan does not offer the rejected table again.
    assert is_rejected(cand('neu', second.offset), rejected_keys(w.reviews))
    w.saved_fingerprint = w.project_state()
    d.close(); w.close()
