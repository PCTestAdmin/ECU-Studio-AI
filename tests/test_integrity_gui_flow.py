"""GUI flows of the checksum system: cancel and restart, save and reopen, export with incomplete coverage."""
import threading
from pathlib import Path

import pytest

from ecu_studio.core import integrity as ig
from ecu_studio.core.model import BinaryImage
from test_integrity import _edit, _multipoint


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app = QApplication.instance() or QApplication([])
    from ecu_studio.ui.main_window import Window
    w = Window()
    w.integrity_timer.stop()
    yield app, w
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.close()


def _wait(app, w, fresh=True):
    for _ in range(500):
        app.processEvents()
        worker = w.integrity_worker
        if worker is not None and worker.isFinished() and (not fresh or w._integrity_fresh()):
            app.processEvents()
            return
        worker and worker.wait(20)
    raise AssertionError('Prüfung nicht beendet')


def test_cancel_and_restart_in_the_window(window, monkeypatch):
    app, w = window
    from ecu_studio.ui import main_window
    real = main_window.check_integrity
    gate = threading.Event()

    def held(snapshot, **kwargs):
        gate.wait(5)                                       # the user cancels while this runs
        return real(snapshot, **kwargs)
    monkeypatch.setattr(main_window, 'check_integrity', held)
    image = _multipoint()
    gate.set()
    w.load_state(image, [], [], '', None)                 # schedules the automatic first check
    w.integrity_timer.stop()
    _wait(app, w)
    assert w.integrity_report.status == ig.INCOMPLETE
    gate.clear()
    _edit(image, 0x3400)
    w.on_edited()
    w.integrity_timer.stop()
    w.check_integrity_async()
    w.integrity_worker.requestInterruption()              # user presses "Abbrechen"
    gate.set()
    _wait(app, w, fresh=False)
    assert not w._integrity_fresh() and w.integrity_report.status == ig.INCOMPLETE   # old report kept
    assert w.checksum_chip.text() == 'CHECKSUMME: VERALTET'
    assert not w.integrity_preview_button.isEnabled()     # nothing correctable from a stale report
    w.check_integrity_async()                              # restart after the cancel
    _wait(app, w)
    assert w.integrity_report.status == ig.INVALID and w.integrity_preview_button.isEnabled()
    assert 'Flashfreigabe: keine' in w.integrity_info.text()


def test_corrected_copy_saved_and_reopened(window, tmp_path):
    app, w = window
    source = tmp_path / 'ecu.bin'
    source.write_bytes(_multipoint().original)
    image = BinaryImage.from_file(str(source))
    _edit(image, 0x3400)
    log = ig.write_corrected_copy(image, ig.plan_correction(image), tmp_path / 'kopie.bin')
    reopened = BinaryImage.from_file(str(tmp_path / 'kopie.bin'))
    assert reopened.digest == log['sha256_output'] and source.read_bytes() == image.original
    w.load_state(reopened, [], [], '', None)
    w.integrity_timer.stop()
    w.check_integrity_async()
    _wait(app, w)
    report = w.integrity_report
    assert report.status == ig.INCOMPLETE and not report.errors          # checksums hold, never "valid"
    assert report.sha256_original == log['sha256_output']


def test_export_dialog_names_incomplete_coverage(window, monkeypatch):
    app, w = window
    from PySide6.QtWidgets import QMessageBox
    image = _multipoint()
    w.load_state(image, [], [], '', None)
    w.integrity_timer.stop()
    _edit(image, 0x18000)                                  # outside every checksum range
    w.on_edited()
    w.integrity_timer.stop()
    shown = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda box: shown.append(box.text()) or 0)
    w.export_bin()                                         # dialog answered with "no": nothing is written
    [text] = shown
    assert 'bekannte Prüfsummen stimmen, Prüfung UNVOLLSTÄNDIG – nicht flashbereit' in text
    assert '3. Checksummenabdeckung: NICHT vollständig (Unvollständige Prüfung)' in text
    assert '4. Signaturen: nicht geprüft' in text and '6. Flashfreigabe: keine' in text
    assert 'FLASH-PREFLIGHT: GRÜN' not in text
    messages = []
    monkeypatch.setattr(w.statusBar(), 'showMessage', lambda m, *a: messages.append(m))
    w.flash_preflight()
    assert any('UNVOLLSTÄNDIG' in m for m in messages)
    assert 'Checksummenabdeckung: NICHT vollständig' in w.diff_view.toPlainText()


def test_repeated_checks_in_the_window_reuse_nothing(window):
    app, w = window
    image = _multipoint()
    w.load_state(image, [], [], '', None)
    w.integrity_timer.stop()
    reports = []
    for i in range(4):
        _edit(image, 0x18000 + i)
        w.on_edited()
        w.integrity_timer.stop()
        w.check_integrity_async()
        _wait(app, w)
        reports.append(w.integrity_report)
    assert len({id(r) for r in reports}) == 4 and len({r.sha256_current for r in reports}) == 4
    assert all(r.status == ig.INCOMPLETE for r in reports)
