"""English interface: catalog lookup, composed texts, combo boxes keep original values, whole UI translated."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import re
from pathlib import Path
import pytest
from ecu_studio.core import i18n
from ecu_studio.tools.i18n_extract import main as extract_main

GERMAN = re.compile(r'[äöüÄÖÜß]|\b(und|nicht|mit|für|Datei|Kennfeld\w*|keine|oder|eine|zum|zur|alle|Achse\w*|Werte|'
                    r'Zeilen|Spalten|Vorschau|öffnen|speichern|Ansicht|Werkzeuge|Hilfe|Einstellungen|Versionen|'
                    r'Lesezeichen|Typ|Einheit|ungeprüft|Unbekannt|Vermutung|gesichert)\b')


@pytest.fixture
def english():
    i18n.set_language('en')
    yield
    i18n.set_language('de')


def test_catalog_is_complete():
    assert extract_main(['--check']) == 0


def test_exact_template_multiline_and_passthrough(english):
    assert i18n.t('Datei') == 'File'
    assert i18n.t('12 Kennfelder exportiert') == '12 maps exported'
    assert i18n.t('Strukturkandidat @ 0x00001234') == 'Structure candidate @ 0x00001234'
    # Lines of a longer label are translated one by one.
    assert i18n.t('Größe: 4,096 Bytes\nfrei formulierter Rest') == 'Size: 4,096 bytes\nfrei formulierter Rest'
    assert i18n.t('0x1F00') == '0x1F00' and i18n.t('MS43 430069') == 'MS43 430069'
    i18n.set_language('de')
    assert i18n.t('Datei') == 'Datei'


def test_combo_shows_english_but_returns_original(tmp_path, english):
    from PySide6.QtWidgets import QApplication, QComboBox
    from ecu_studio.ui import i18n_qt
    app = QApplication.instance() or QApplication([])
    i18n_qt.install(app, 'en')
    box = QComboBox()
    box.addItems(['Alle Typen', 'Zündung', 'Unbekannt'])
    assert box.model().index(1, 0).data() == 'Ignition'
    box.setCurrentText('Zündung')
    assert box.currentIndex() == 1 and box.currentText() == 'Zündung' and box.itemText(2) == 'Unbekannt'
    assert box.findText('Unbekannt') == 2


def test_main_window_and_dialog_smoke_in_english(tmp_path, monkeypatch, english):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QMenu
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui import i18n_qt
    app = QApplication.instance() or QApplication([])
    i18n_qt.install(app, 'en')
    from ecu_studio.ui.main_window import Window
    w = Window(); w.show(); app.processEvents()
    texts = {a.text() for a in w.findChildren(QAction)} | {m.title() for m in w.findChildren(QMenu)}
    texts |= {x.text() for x in w.findChildren(QLabel)} | {b.text() for b in w.findChildren(QAbstractButton)}
    left = sorted(t for t in texts if t and GERMAN.search(t))
    assert left == [], left[:10]
    w.close()
    from ecu_studio.tools.gui_smoke import run
    assert run(str(tmp_path / 'smoke')) == 0
