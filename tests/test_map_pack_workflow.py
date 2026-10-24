import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from ecu_studio.core.map_pack import make_pack, write_pack, read_pack, preview_pack, apply_pack, source_for_comparison
from ecu_studio.core.model import BinaryImage, load_project, read_project_snapshots
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.version_compare import compare_versions, adopt_definitions
from ecu_studio.core.versioning import make_snapshot, compare_snapshots
from ecu_studio.tools.screenshot import synthetic_versions
from tests.test_ui_filters_banner import _window


def wait(app, dialog):
    timer = QElapsedTimer(); timer.start()
    while dialog.worker and dialog.worker.isRunning() and timer.elapsed() < 10000:
        app.processEvents(); QTest.qWait(5)
    if dialog.worker: assert dialog.worker.wait(5000)
    app.processEvents()


def test_scan_pack_compare_adopt_version_save_reopen_undo(tmp_path, monkeypatch):
    app, window = _window(tmp_path, monkeypatch)
    source, definitions, target = synthetic_versions()
    pack_path = tmp_path / 'example.ecupack.json'
    write_pack(pack_path, make_pack(source, definitions[:3]))
    # Open BIN and scan using the existing detector. Never change the source.
    source_path = tmp_path / 'stand-A.bin'; source_path.write_bytes(source.original)
    window.load_state(BinaryImage.from_file(source_path), [], [], '', None)
    found = scan_calibration_candidates(window.image, use_definitions=False)
    assert found and not window.image.dirty_bytes
    from ecu_studio.ui.map_pack_dialog import MapPackDialog
    dialog = MapPackDialog(window, pack_path); wait(app, dialog)
    assert dialog.pack and dialog.adopt.isEnabled()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    dialog.apply()
    assert len(window.maps) == 3 and len(window.snapshots) == 1 and not any(m.verified for m in window.maps)
    window.undo(); assert not window.maps and not window.snapshots
    window.redo(); assert len(window.maps) == 3
    window.project_store.index_pack(pack_path); window.update_local_suggestions()
    assert window.local_suggestions[0]['relation'] == 'exact'
    # Other software stands go through the real version comparator.
    window.load_state(target, [], [], '', None)
    source_maps = source_for_comparison(read_pack(pack_path), source)
    compared = compare_versions(source, source_maps, target, window.maps)
    exact = [p for p in compared['pairs'] if p.match == 'exakt']
    added, protocol = adopt_definitions(exact, window.maps, source_label='synthetic-A')
    assert added and all(not m.verified for m in added)
    window.maps.extend(added)
    window.image.journal.extend(protocol)
    window.snapshots.append(make_snapshot(target, 'comparison', maps=window.maps))
    project = tmp_path / 'target.ecustudio'; window.project_path = str(project)
    window.save_project()
    digest = target.digest
    window.open_project_file(project)
    assert window.image.digest == digest and not window.image.dirty_bytes
    assert compare_snapshots(window.image, window.snapshots[0], window.snapshots[0], window.maps)['changed_bytes'] == 0
    assert len(read_project_snapshots(project, window.image)) == 1
    assert load_project(project)[1][0].axis_x_offset == window.maps[0].axis_x_offset
    window.saved_fingerprint = window.project_state(); window.close()


def test_gui_preview_conflict_cancel_and_stale_catalog(tmp_path, monkeypatch):
    app, window = _window(tmp_path, monkeypatch)
    source, maps, _ = synthetic_versions()
    window.load_state(source, list(maps[:1]), [], '', None)
    path = tmp_path / 'pack.json'; write_pack(path, make_pack(source, maps[:2]))
    from ecu_studio.ui.map_pack_dialog import MapPackDialog
    dialog = MapPackDialog(window, path); wait(app, dialog)
    assert dialog.preview.conflicts and not dialog.adopt.isEnabled()
    dialog.reject()
    assert len(window.maps) == 1 and not window.image.journal
    window.saved_fingerprint = window.project_state(); window.close()


def test_export_filters_and_optional_axes(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QComboBox, QCheckBox, QPushButton
    from ecu_studio.ui.map_pack_dialog import export_dialog
    app, window = _window(tmp_path, monkeypatch)
    source, maps, _ = synthetic_versions(); maps[0].verified = True
    window.load_state(source, maps[:3], [], '', None)
    window.select_map(maps[1])
    path = tmp_path / 'export.ecupack.json'
    monkeypatch.setattr(window, 'save_destination', lambda *a, **k: (str(path), ''))
    for mode, expected in ((0, 3), (1, 1), (2, 1)):
        def run_dialog(dialog):
            dialog.findChild(QComboBox).setCurrentIndex(mode)
            dialog.findChildren(QCheckBox)[0].setChecked(False)
            button = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Paket speichern …')
            button.click()
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(QDialog, 'exec', run_dialog)
        export_dialog(window)
        pack = read_pack(path)
        assert len(pack.document['maps']) == expected and not pack.document['axis_groups']
        if mode == 2: assert pack.document['maps'][0]['name'] == maps[1].name
    window.saved_fingerprint = window.project_state(); window.close()


def test_pack_comparison_passes_locked_source_and_full_provenance(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from ecu_studio.ui.map_pack_dialog import MapPackDialog
    app, window = _window(tmp_path, monkeypatch)
    source, definitions, target = synthetic_versions()
    source_path = tmp_path / 'stand-A.bin'; source_path.write_bytes(source.original)
    pack_path = tmp_path / 'example.ecupack.json'
    write_pack(pack_path, make_pack(source, definitions[:3]))
    window.load_state(target, [], [], '', None)
    dialog = MapPackDialog(window, pack_path); wait(app, dialog)
    assert not dialog.adopt.isEnabled() and dialog.compare.isEnabled()
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(source_path), ''))
    loaded = []
    monkeypatch.setattr(dialog, 'source_loaded', loaded.append)
    dialog.compare_source(); wait(app, dialog)
    image, maps, label = loaded[0]
    assert image.digest == source.digest and source.digest in label
    assert len(maps) == 3 and all(not m.verified for m in maps)
    assert not window.maps and not target.dirty_bytes
    dialog.reject()
    window.saved_fingerprint = window.project_state(); window.close()
