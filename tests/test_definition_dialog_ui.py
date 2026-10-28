"""Guided definition dialog and XDF export in the main window (offscreen)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import struct
from pathlib import Path
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from ecu_studio.core.model import BinaryImage, MapDefinition


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app = QApplication.instance() or QApplication([])
    from ecu_studio.ui.main_window import Window
    raw = bytearray(4096)
    for i in range(16):
        struct.pack_into('>H', raw, 0x100 + 2 * i, 1000 + 10 * i)
    struct.pack_into('>4H', raw, 0x200, 800, 1600, 2400, 3200)
    image = BinaryImage(bytes(raw))
    w = Window()
    w.load_state(image, [MapDefinition('Kennfeld A', 0x100, 4, 4, 'u16', 'big', source='heuristic'),
                         MapDefinition('Float', 0x300, 2, 2, 'f32')], [], '', None)
    w.select_map(w.maps[0])
    yield w
    w.saved_fingerprint = w.project_state()
    w.close()


def test_dialog_checks_previews_and_blocks_invalid_input(window):
    from ecu_studio.ui.definition_dialog import DefinitionDialog
    d = DefinitionDialog(window.image, window.selected, window)
    assert d.proposal is not None and not d.apply_button.isEnabled()        # unchanged: nothing to apply
    assert d.table.rowCount() == 4 and d.table.item(0, 0).text() == '1000'
    d.factor.setValue(0.1)
    assert not d.apply_button.isEnabled()                                    # edits need a new check
    assert d.check() and d.apply_button.isEnabled() and d.table.item(0, 1).text() == '101'
    d.offset.setText('0xFF0')                                                # 32 bytes past the end
    assert not d.check() and not d.apply_button.isEnabled() and 'außerhalb' in d.result.text()
    d.offset.setText('0x100'); d.axis_x['offset'].setText('0x200')
    assert d.check() and d.proposal.proposed.axes_x == [800, 1600, 2400, 3200]
    assert d.table.horizontalHeaderItem(0).text() == '800'


def test_accepted_edit_changes_definition_only_and_is_undoable(window, monkeypatch):
    from ecu_studio.ui import definition_dialog
    before = window.image.materialize()

    def run(self):
        self.name.setText('Ladedruck Soll'); self.factor.setValue(0.01)
        assert self.check()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(definition_dialog.DefinitionDialog, 'exec', run)
    window.edit_definition_dialog()
    assert window.maps[0].name == 'Ladedruck Soll' and window.selected is window.maps[0]
    assert not window.maps[0].verified and window.image.materialize() == before
    window.undo()
    assert window.maps[0].name == 'Kennfeld A' and window.maps[0].factor == 1.0


def test_cancel_changes_nothing(window, monkeypatch):
    from ecu_studio.ui import definition_dialog
    snapshot = [m.asdict() for m in window.maps]

    def run(self):
        self.name.setText('Verworfen'); self.check()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(definition_dialog.DefinitionDialog, 'exec', run)
    window.edit_definition_dialog()
    assert [m.asdict() for m in window.maps] == snapshot


def test_xdf_export_from_window_reports_roundtrip_and_skips_float(window, tmp_path, monkeypatch):
    target = tmp_path / 'out.xdf'
    monkeypatch.setattr(window, 'save_destination', lambda *a, **k: (str(target), ''))
    shown = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: shown.append(('info', a[2])))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: shown.append(('warn', a[2])))
    window.export_xdf_file()
    kind, text = shown[0]
    assert kind == 'info' and target.exists()
    assert '1 Definitionen exportiert' in text and 'Float' in text and 'Rückimport geprüft' in text
