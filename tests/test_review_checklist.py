"""Review checklist: order by need for a human decision, explicit decisions, persisted rejections."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition, save_project, load_project, read_project_reviews
from ecu_studio.core.review_checklist import (checklist, decision, rejected_keys, is_rejected, rejected_before,
                                             validate_log)


def cand(name, offset, layout='candidate:code-call', **kw):
    kw = {'rows': 4, 'cols': 4, 'dtype': 'u8', 'source': 'heuristic', 'record_layout': layout, **kw}
    return MapDefinition(name, offset, **kw)


def test_order_and_reasons():
    from ecu_studio.core.review_checklist import GUESSES
    code = 'candidate:code-reference'
    clean = cand('sauber', 0x100, code, axes_x=[1, 2, 3, 4], axes_y=[1, 2, 3, 4], calibrated_rate=.97)
    sign = cand('vorzeichen', 0x200, code, dtype='u16', dtype_alternatives=['s16'], axes_x=[1, 2, 3, 4],
                axes_y=[1, 2, 3, 4])
    bare = cand('ohne achsen', 0x300, layout='candidate:row-pitch', calibrated_rate=.23)
    tricore = cand('tricore', 0x380, axes_x=[1, 2, 3, 4], axes_y=[1, 2, 3, 4])
    defined = MapDefinition('Definition', 0x400, 4, 4, 'u8', source='xdf')
    contradicted = MapDefinition('Widerspruch', 0x500, 4, 4, 'u8', source='xdf')
    done = cand('geprüft', 0x600, verified=True)
    items = checklist([clean, sign, bare, tricore, defined, contradicted, done],
                      conflicts={0x500: ['0x500: Größe – …']})
    names = [i.map.name for i in items]
    # definition and checked map left out
    assert names == ['Widerspruch', 'ohne achsen', 'vorzeichen', 'tricore', 'sauber']
    assert items[0].priority == 'hoch' and 'Widerspruch' in items[0].reasons[0]
    assert any('ebenfalls möglich: s16' in r for r in items[2].reasons)
    assert 'Achsen fehlen' in items[1].reasons and any(r.startswith('Datenmuster-Vermutung') for r in items[1].reasons)
    assert any('experimentell' in r for r in items[3].reasons)
    assert items[-1].reasons == ['Automatisch erkannt, noch nicht geprüft'] and items[-1].priority == 'niedrig'
    assert not any('%' in r for i in items for r in i.reasons)          # no measured rates any more
    assert [i.group for i in items] == ['', GUESSES, '', '', '']


def test_data_pattern_guess_with_a_contradiction_stays_in_the_main_group():
    from ecu_studio.core.review_checklist import GUESSES
    guess = cand('glatt', 0x300, layout='candidate:row-pitch')
    disputed = cand('strittig', 0x500, layout='candidate:row-pitch')
    items = {i.map.name: i for i in checklist([guess, disputed], conflicts={0x500: ['0x500: Start – …']})}
    assert items['glatt'].group == GUESSES and items['strittig'].group == ''


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


def test_dialog_collapses_data_pattern_guesses_without_losing_them(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui.main_window import Window
    from ecu_studio.ui.review_dialog import ReviewDialog
    app = QApplication.instance() or QApplication([])
    w = Window()
    maps = [cand('Code', 0x10, 'candidate:code-reference'), cand('Glatt 1', 0x40, 'candidate:row-pitch'),
            cand('Glatt 2', 0x70, 'candidate:row-pitch'), cand('Geprüft', 0xA0, 'candidate:row-pitch', verified=True)]
    w.load_state(BinaryImage(bytes(256)), maps, [], '', None)
    d = ReviewDialog(w)
    assert not d.show_guesses.isChecked() and [i.map.name for i in d.items] == ['Code']
    assert '(2,' in d.show_guesses.text() and '2 Vermutungen eingeklappt' in d.count.text()
    d.show_guesses.setChecked(True)
    assert [i.map.name for i in d.items] == ['Code', 'Glatt 1', 'Glatt 2'] and d.table.rowCount() == 3
    assert 'Vermutung' in d.table.item(1, 0).text() and 'eingeklappt' not in d.count.text()
    assert len(w.maps) == 4 and maps[3].verified                       # nothing removed, confirmed map untouched
    w.saved_fingerprint = w.project_state()
    d.close(); w.close()


def test_rejection_is_bound_to_its_file_and_can_be_withdrawn():
    m = cand('x', 0x100, layout='candidate:row-pitch')
    log = [decision(m, 'abgelehnt', image_sha256='a' * 64)]
    assert is_rejected(m, rejected_keys(log, 'a' * 64))
    assert not rejected_keys(log, 'b' * 64)                               # another firmware: no effect
    withdrawn = dict(log[0], decision='zurückgenommen')
    assert not rejected_keys(validate_log(log + [withdrawn]), 'a' * 64)


def test_stronger_evidence_is_offered_again():
    weak = cand('muster', 0x100, layout='candidate:row-pitch')            # layer 3 rejected
    keys = rejected_keys([decision(weak, 'abgelehnt')])
    code = cand('code', 0x100)                                            # same table, layer 2 now
    assert not is_rejected(code, keys) and rejected_before(code, keys)
    assert is_rejected(cand('muster2', 0x100, layout='candidate:raster'), keys)
    strong = rejected_keys([decision(code, 'abgelehnt')])
    assert is_rejected(weak, strong) and not rejected_before(weak, strong)


def test_dialog_withdraws_decisions(tmp_path, monkeypatch):
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
    w.load_state(BinaryImage(bytes(256)), [cand('A', 0x10), cand('B', 0x40)], [], '', None)
    d = ReviewDialog(w)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: None)
    d.table.selectRow(0); a = d.current(); d.confirm()
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('Text', True))
    d.table.selectRow(0); b = d.current(); d.reject_map()
    assert w.reviews[-1]['image_sha256'] == w.image.digest and len(d.open_decisions()) == 2
    (conf,) = [e for e in d.open_decisions() if e['decision'] == 'bestätigt']
    d.withdraw(conf)
    assert not a.verified and 'Manuell geprüft' not in a.notes and d.table.rowCount() == 1
    (rej,) = d.open_decisions()
    d.withdraw(rej)
    assert not d.open_decisions() and not rejected_keys(w.reviews, w.image.digest)
    assert not is_rejected(cand('neu', b.offset), rejected_keys(w.reviews, w.image.digest))
    w.saved_fingerprint = w.project_state()
    d.close(); w.close()


def test_dialog_refill_does_not_measure_columns_per_cell(tmp_path, monkeypatch):
    """Columns left in ResizeToContents made every refill quadratic (MSD80, ~3800 finds: hours; 1.19 QA)."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QHeaderView
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui.main_window import Window
    from ecu_studio.ui.review_dialog import ReviewDialog
    app = QApplication.instance() or QApplication([])
    w = Window()
    w.load_state(BinaryImage(bytes(4096)), [cand(f'K{i}', 16 * i) for i in range(50)], [], '', None)
    d = ReviewDialog(w)
    d.reload()
    header = d.table.horizontalHeader()
    assert d.table.rowCount() == 50 and d.table.updatesEnabled()
    assert all(header.sectionResizeMode(c) != QHeaderView.ResizeToContents for c in range(d.table.columnCount()))
    assert header.sectionResizeMode(4) == QHeaderView.Stretch and header.sectionSize(1) > 0
    w.saved_fingerprint = w.project_state()
    d.close(); w.close()


def test_rescan_honours_fusion_rejections_and_reload(tmp_path, monkeypatch):
    """Scan merge after a reload: no partial duplicate of a definition, rejections only for this file,
    stronger evidence offered again (regressions 1.19 QA)."""
    import hashlib
    from types import SimpleNamespace
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: None)
    from ecu_studio.ui.main_window import Window
    app = QApplication.instance() or QApplication([])
    src = tmp_path / 'fw.bin'; src.write_bytes(bytes(range(256)) * 16)
    image = BinaryImage.from_file(str(src))
    definition = MapDefinition('Def', 0x100, 8, 8, 'u8', source='xdf')
    w = Window()
    w.load_state(image, [definition], [], '', None)
    w.reviews = [decision(cand('weak', 0x400, layout='candidate:row-pitch'), 'abgelehnt', image_sha256=image.digest),
                 decision(cand('elsewhere', 0x600), 'abgelehnt', image_sha256='0' * 64)]
    project = tmp_path / 'p.ecustudio'
    save_project(str(project), image, w.maps, [], '', reviews=w.reviews)
    w.saved_fingerprint = w.project_state()
    w.close()
    w = Window()
    w.open_project_file(str(project))
    assert len(w.reviews) == 2
    partial = cand('teilweise', 0x130, rows=8, cols=8)          # 16 of 64 bytes inside the definition
    stronger = cand('stärker', 0x400)                           # code evidence for the rejected pattern table
    other_file = cand('andere Datei', 0x600)                    # rejected on another firmware only
    w.scanner = SimpleNamespace(source_digest=hashlib.sha256(w.image.materialize()).digest(), isRunning=lambda: False,
                                wait=lambda: True)
    w.scan_finished([partial, stronger, other_file])
    names = [m.name for m in w.maps]
    assert 'teilweise' not in names and 'stärker' in names and 'andere Datei' in names
    assert 'stärkerem Beleg' in next(m for m in w.maps if m.name == 'stärker').notes
    assert w.last_scan_report['fusion']['counts']['conflicts'] == 1
    w.saved_fingerprint = w.project_state()
    w.close()


def test_finished_workers_are_waited_for_before_release(tmp_path, monkeypatch):
    """Qt 6 reports isRunning() False while a thread still runs its finish; release waits for the real end."""
    import time
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QThread, Qt, QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui.main_window import Window
    app = QApplication.instance() or QApplication([])
    seen = {}

    class Worker(QThread):
        def run(self):
            pass

    worker = Worker()
    worker.finished.connect(lambda: (seen.setdefault('in', 1), time.sleep(.3), seen.setdefault('out', 1)),
                            Qt.ConnectionType.DirectConnection)
    worker.start()
    while 'in' not in seen:
        time.sleep(.001)
    assert not worker.isRunning() and 'out' not in seen          # "not running", yet still finishing
    Window._release_worker(worker)
    assert 'out' in seen                                          # released only after the thread ended
    Window._release_worker(None)
