"""The ORI/MOD dialog lists unknown change regions and fills the heatmap for a selected map."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from ecu_studio.core.model import BinaryImage, MapDefinition


def test_compare_dialog_regions_and_heatmap(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QTabWidget, QTableWidget
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.ui.main_window import Window
    app = QApplication.instance() or QApplication([])
    ori = bytes(range(256)) * 16
    mod = bytearray(ori); mod[0x10:0x12] = b'\xF0\x01'; mod[0x800] ^= 0xFF
    other = tmp_path / 'mod.bin'; other.write_bytes(bytes(mod))
    w = Window()
    m = MapDefinition('K', 0x10, 4, 4, 'u8', 'big')
    w.load_state(BinaryImage(ori), [m], [], '', None)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: (str(other), '')))
    seen = {}

    def fake_exec(dialog):
        tabs = dialog.findChild(QTabWidget)
        seen['tabs'] = [tabs.tabText(i) for i in range(tabs.count())]
        maps_table = tabs.widget(0)
        maps_table.selectRow(0)
        heat = tabs.widget(3).findChild(QTableWidget)
        seen['heat'] = (heat.rowCount(), heat.columnCount(), heat.item(0, 0).text())
        return 0
    monkeypatch.setattr(QDialog, 'exec', fake_exec)
    w.compare_file()
    assert any(t.startswith('Außerhalb bekannter Kennfelder (1)') for t in seen['tabs'])
    assert seen['heat'][:2] == (4, 4) and seen['heat'][2] == f'{0xF0 - 0x10:+g}'
    w.close()
