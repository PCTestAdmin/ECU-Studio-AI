"""Catalogue filter by measured confidence, identity hint bar, no duplicate shortcuts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import collections
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


def test_confidence_filter(tmp_path, monkeypatch):
    from ecu_studio.ui.main_window import TIER_FILTERS
    app, w = _window(tmp_path, monkeypatch)
    assert TIER_FILTERS[1:4] == ('Code-Beleg', 'Strukturbeleg', 'Datenmuster-Vermutung')
    maps = [MapDefinition('code', 0, 2, 2, 'u8', source='heuristic', record_layout='candidate:code-reference'),
            MapDefinition('kopf', 8, 2, 2, 'u8', source='heuristic', record_layout='candidate:nx,ny,x,y,z'),
            MapDefinition('vermutet', 24, 2, 2, 'u8', source='heuristic', record_layout='candidate:row-pitch'),
            MapDefinition('definiert', 16, 2, 2, 'u8', source='xdf')]
    w.load_state(BinaryImage(bytes(64)), maps, [], '', None)
    shown = {}
    for i, choice in enumerate(TIER_FILTERS):
        w.tier_filter.setCurrentIndex(i)
        shown[choice] = w.catalog_model.rowCount()
    assert shown[TIER_FILTERS[0]] == 4
    assert [shown[c] for c in TIER_FILTERS[1:5]] == [1, 1, 1, 1]
    assert shown[TIER_FILTERS[5]] == 4                       # nothing confirmed by the user yet
    w.maps[2].verified = True
    w.tier_filter.setCurrentIndex(0); w.tier_filter.setCurrentIndex(5)
    assert w.catalog_model.rowCount() == 3
    w.tier_filter.setCurrentIndex(3)                         # a confirmed guess is no longer a guess
    assert w.catalog_model.rowCount() == 0
    w.saved_fingerprint = w.project_state()            # test edit: no "unsaved changes" question
    w.close()


def test_identity_banner_names_family_and_status(tmp_path, monkeypatch):
    app, w = _window(tmp_path, monkeypatch)
    buf = bytearray(0x4000); buf[0x100:0x100 + 33] = b'33/1/EDC17_CP09/11/P_574//V8KB///'
    w.load_state(BinaryImage(bytes(buf)), [], [], '', None)
    w.update_identity_banner()
    text = w.identity_banner_text.text()
    assert 'EDC17CP09' in text and 'validiert' in text and not w.identity_banner.isHidden()
    w.load_state(BinaryImage(bytes(0x4000)), [], [], '', None)
    w.update_identity_banner()
    assert 'nicht aus der Datei bestimmbar' in w.identity_banner_text.text()
    w.close()


def test_no_shortcut_is_bound_twice(tmp_path, monkeypatch):
    from PySide6.QtGui import QAction
    app, w = _window(tmp_path, monkeypatch)
    keys = collections.Counter(a.shortcut().toString() for a in w.findChildren(QAction) if not a.shortcut().isEmpty())
    assert [k for k, n in keys.items() if n > 1] == []
    w.close()
