"""File switch: the definition editor never shows or edits anything of a previously opened firmware.

Bug until 1.19.1: after a firmware with maps and a selected map, loading a firmware without maps left name, offset,
dimensions, scaling and type of the old map in the editor, and its edit buttons stayed active.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path

import numpy as np
import pytest

from ecu_studio.core.model import BinaryImage, MapDefinition


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app = QApplication.instance() or QApplication([])
    for name in ('information', 'warning'):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.No)
    from ecu_studio.ui.main_window import Window
    w = Window()
    yield app, w
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.close()


def _image(seed, size=0x8000):
    return BinaryImage(np.random.default_rng(seed).integers(0, 256, size, dtype=np.uint8).tobytes())


def _firmware_a():
    return _image(1), [MapDefinition('Zuendwinkel A', 0x1230, 12, 10, 'u16', 'little', factor=0.75, bias=-3.0,
                                     unit='Grad KW', kind='Zündung', source='xdf'),
                       MapDefinition('Ladedruck A', 0x2000, 8, 8, 'u8', unit='hPa', source='xdf')]


def _firmware_c():
    return _image(3), [MapDefinition('Einspritzung C', 0x4560, 6, 5, 'u8', factor=0.04, unit='ms',
                                     kind='Einspritzung', source='xdf')]


def _editor_text(w):
    """Everything the definition editor shows the user."""
    return ' | '.join([w.name_edit.text(), w.type_edit.currentText(), w.offset_edit.text(), w.unit_edit.text(),
                       w.identification_label.text(), w.identification_detail.text(), w.map_hint.text(),
                       f'{w.rows_edit.value()}x{w.cols_edit.value()}', f'{w.factor_edit.value():g}',
                       f'{w.bias_edit.value():g}', str(w.verified_edit.isChecked())])


def _edit_widgets(w):
    return [w.name_edit, w.type_edit, w.offset_edit, w.rows_edit, w.cols_edit, w.dtype_edit, w.endian_edit,
            w.factor_edit, w.bias_edit, w.unit_edit, w.verified_edit, *w.map_action_buttons]


def _select(app, w, name):
    w.select_map(next(m for m in w.maps if m.name == name))
    app.processEvents()


def _assert_nothing_selected(w, *foreign):
    text = _editor_text(w)
    for m in foreign:
        assert m.name not in text and f'0x{m.offset:X}' not in text and (not m.unit or m.unit not in text)
    assert w.selected is None and w.map_model.rowCount() == 0
    assert not w.map_list.currentIndex().isValid()
    assert w.name_edit.text() == '' and w.offset_edit.text() == '' and w.unit_edit.text() == ''
    assert not any(widget.isEnabled() for widget in _edit_widgets(w))


def test_firmware_without_maps_clears_the_editor(window):
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    _select(app, w, 'Zuendwinkel A')
    assert w.name_edit.text() == 'Zuendwinkel A' and w.offset_edit.text() == '0x1230'
    assert all(widget.isEnabled() for widget in w.map_action_buttons)
    b = _image(2)
    w.load_state(b, [], [], '', None)
    app.processEvents()
    _assert_nothing_selected(w, *maps_a)
    w.name_edit.setText('Ueberschrieben')                 # even a programmatic apply changes nothing
    w.apply_definition()
    assert [m.name for m in maps_a] == ['Zuendwinkel A', 'Ladedruck A'] and maps_a[0].offset == 0x1230
    assert not a.dirty_bytes and not b.dirty_bytes


def test_firmware_with_other_maps_shows_only_its_own(window):
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    _select(app, w, 'Zuendwinkel A')
    c, maps_c = _firmware_c()
    w.load_state(c, maps_c, [], '', None)
    app.processEvents()
    _assert_nothing_selected(w, *maps_a)                  # no automatic carry-over of the old selection
    _select(app, w, 'Einspritzung C')
    assert w.selected is maps_c[0] and w.name_edit.text() == 'Einspritzung C' and w.offset_edit.text() == '0x4560'
    assert (w.rows_edit.value(), w.cols_edit.value(), w.unit_edit.text()) == (6, 5, 'ms')
    assert w.map_model.image is c and w.map_model.rowCount() == 6
    text = _editor_text(w)
    assert 'Zuendwinkel' not in text and '0x1230' not in text and 'Grad KW' not in text


def test_repeated_switching_between_three_files(window):
    app, w = window
    a, maps_a = _firmware_a()
    b = _image(2)
    c, maps_c = _firmware_c()
    for _ in range(3):
        w.load_state(a, maps_a, [], '', None)
        _assert_nothing_selected(w, *maps_c)
        _select(app, w, 'Ladedruck A')
        assert w.offset_edit.text() == '0x2000' and w.map_model.image is a
        w.load_state(b, [], [], '', None)
        _assert_nothing_selected(w, *maps_a, *maps_c)
        assert w.hex_model.image is b and w.raw2d.image is b
        w.load_state(c, maps_c, [], '', None)
        _assert_nothing_selected(w, *maps_a)
        _select(app, w, 'Einspritzung C')
        assert w.offset_edit.text() == '0x4560' and w.map_model.image is c
    assert not a.dirty_bytes and not b.dirty_bytes and not c.dirty_bytes


def test_save_and_reopen_project_shows_only_the_project(window, tmp_path):
    app, w = window
    c, maps_c = _firmware_c()
    source = tmp_path / 'c.bin'
    source.write_bytes(c.original)
    c = BinaryImage.from_file(str(source))
    w.load_state(c, maps_c, [], '', None)
    _select(app, w, 'Einspritzung C')
    project = tmp_path / 'c.ecustudio'
    w.project_path = str(project)
    w.save_project()
    assert project.is_file()
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    _select(app, w, 'Zuendwinkel A')
    w.open_project_file(str(project))
    app.processEvents()
    _assert_nothing_selected(w, *maps_a)
    assert [m.name for m in w.maps] == ['Einspritzung C'] and w.image.digest == c.digest
    _select(app, w, 'Einspritzung C')
    assert w.offset_edit.text() == '0x4560' and w.map_model.image is w.image


def _wait_for(app, worker):
    for _ in range(3000):
        app.processEvents()
        if worker.isFinished():
            app.processEvents()
            return
        worker.wait(20)
    raise AssertionError('Scan nicht beendet')


def test_file_switch_during_a_scan_discards_its_result(window):
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    _select(app, w, 'Zuendwinkel A')
    w.scan_maps()
    scanner = w.scanner
    reopened = BinaryImage(a.original)                   # the same bytes opened again, e.g. as another project
    w.load_state(reopened, [], [], '', None)
    _wait_for(app, scanner)
    assert w.maps == [] and w.image is reopened          # the scan was started for the previous file
    _assert_nothing_selected(w, *maps_a)


def test_late_scan_result_never_lands_in_the_next_file(window):
    """Even if a finished scan's result arrives after the switch (queued signal), it is not merged."""
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    w.scan_maps()
    _wait_for(app, w.scanner)
    late = [MapDefinition('Spaeter Scan', 0x100, 4, 4, 'u8', source='heuristic')]
    reopened = BinaryImage(a.original)
    w.load_state(reopened, [], [], '', None)
    w.scan_finished(late)                                 # identical bytes, but another opened file
    assert w.maps == [] and w.last_scan_report is None


def test_file_switch_after_a_scan(window):
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    w.scan_maps()
    _wait_for(app, w.scanner)
    _select(app, w, 'Ladedruck A')
    c, maps_c = _firmware_c()
    w.load_state(c, maps_c, [], '', None)
    _assert_nothing_selected(w, *maps_a)
    assert w.maps == maps_c and w.last_scan_report is None


def test_file_switch_after_editing_a_map(window):
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    _select(app, w, 'Ladedruck A')
    index = w.map_model.index(0, 0)
    before = a.byte(0x2000)
    assert w.map_model.setData(index, str((before + 7) % 256))
    w.on_edited()
    assert a.dirty_bytes == 1
    b = _image(2)
    w.load_state(b, [], [], '', None)
    _assert_nothing_selected(w, *maps_a)
    assert not b.dirty_bytes and w.map_model.image is None
    w.map_model.setData(w.map_model.index(0, 0), '0')    # no target any more: nothing written anywhere
    assert a.dirty_bytes == 1 and not b.dirty_bytes


def test_removing_the_selected_map_clears_the_editor(window):
    app, w = window
    a, maps_a = _firmware_a()
    w.load_state(a, maps_a, [], '', None)
    _select(app, w, 'Zuendwinkel A')
    w.drop_map(maps_a[0])
    assert w.selected is None and 'Zuendwinkel A' not in _editor_text(w)
    assert not any(widget.isEnabled() for widget in _edit_widgets(w))


def test_editor_starts_disabled(window):
    app, w = window
    assert w.selected is None and not any(widget.isEnabled() for widget in _edit_widgets(w))
