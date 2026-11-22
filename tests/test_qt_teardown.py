"""Deferred calls and worker signals of a deleted main window touch nothing (Qt teardown, after 1.21.0-rc1).

Before: ``QTimer.singleShot(0, self.method)`` without a context object and the closures of the checksum
worker still ran after the window was deleted, on deleted child widgets ("Internal C++ object (QLabel)
already deleted" at the end of the test run, from update_identity_banner and _show_integrity_state).
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
from ecu_studio.core.model import BinaryImage, MapDefinition


def _window(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui.main_window import Window
    app = QApplication.instance() or QApplication([])
    return app, Window()


def _delete(app, widget):
    from PySide6.QtCore import QCoreApplication, QEvent
    widget.hide()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_deferred_calls_and_worker_results_after_deletion_touch_nothing(tmp_path, monkeypatch):
    import shiboken6
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda kind, value, tb: errors.append(value))
    app, w = _window(tmp_path, monkeypatch)
    # load_state defers the identity hint bar and the automatic checksum check (QTimer.singleShot(0, ...))
    w.load_state(BinaryImage(bytes(4096)), [MapDefinition('KF', 0, 4, 4, 'u8', source='xdf')], [], '', None)
    _delete(app, w)
    assert not shiboken6.isValid(w)
    app, w = _window(tmp_path, monkeypatch)
    w.load_state(BinaryImage(bytes(4096)), [], [], '', None)
    app.processEvents()                          # the checksum check starts in its worker
    worker = w.integrity_worker
    _delete(app, w)                              # window gone while the worker may still report
    if worker is not None and shiboken6.isValid(worker):
        worker.wait(10000)
    app.processEvents()
    assert errors == []
