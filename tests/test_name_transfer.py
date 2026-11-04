"""Name transfer between sister software versions: anchored shifts, evidence classes, abstention."""
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.name_transfer import transfer_names, anchors


def _sisters():
    rng = np.random.default_rng(11)
    base = bytearray(rng.integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    y, x = np.mgrid[:8, :8]
    smooth = (40 + 5 * y + 3 * x).astype(np.uint8)
    base[0x1000:0x1040] = smooth.tobytes()                       # unchanged table
    base[0x5000:0x5040] = smooth.tobytes()[::-1]                 # table that will change values
    base[0x6000:0x6040] = bytes(64)                              # flat (zero) table
    target = bytearray(base[:0x3000] + rng.integers(0, 256, 0x200, dtype=np.uint8).tobytes() + base[0x3000:])
    t = 0x5000 + 0x200
    target[t:t + 64] = (np.frombuffer(bytes(target[t:t + 64]), np.uint8).astype(int) + 1).clip(0, 255).astype(np.uint8).tobytes()
    maps = [MapDefinition('A_unchanged', 0x1000, 8, 8, 'u8', 'big'),
            MapDefinition('B_changed', 0x5000, 8, 8, 'u8', 'big'),
            MapDefinition('C_flat', 0x6000, 8, 8, 'u8', 'big')]
    return BinaryImage(bytes(base)), BinaryImage(bytes(target)), maps


def test_anchor_chain_is_monotone():
    source, target, _ = _sisters()
    chain = anchors(source.read(0, source.size), target.read(0, target.size))
    assert chain and all(a[0] < b[0] and a[1] < b[1] for a, b in zip(chain, chain[1:]))


def test_names_follow_the_inserted_block_with_their_evidence():
    source, target, maps = _sisters()
    result = {t.source.name: t for t in transfer_names(source, target, maps)}
    assert result['A_unchanged'].target.offset == 0x1000 and result['A_unchanged'].evidence == 'identisch'
    assert result['B_changed'].target.offset == 0x5200 and result['B_changed'].evidence == 'ähnliche Werte'
    assert result['C_flat'].target.offset == 0x6200 and result['C_flat'].evidence == 'gleiche Umgebung'
    for t in result.values():
        assert t.target.source == 'transfer-proposed' and not t.target.verified
        assert t.target.name == t.source.name


def test_unrelated_image_gets_no_names():
    source, _, maps = _sisters()
    other = BinaryImage(np.random.default_rng(99).integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    assert transfer_names(source, other, maps) == []


def test_detection_in_the_target_confirms_the_place():
    from ecu_studio.core.name_transfer import confirm_by_detection
    source, target, maps = _sisters()
    result = transfer_names(source, target, maps)
    found = [MapDefinition('Strukturkandidat', 0x5200, 8, 8, 'u8', source='heuristic', label_origin='TriCore-Aufruf'),
             MapDefinition('anders', 0x6200, 4, 8, 'u8', source='heuristic')]       # other size: no confirmation
    assert confirm_by_detection(result, found) == 1
    by = {t.source.name: t for t in result}
    assert by['B_changed'].detected_in_target and 'unabhängig bestätigt' in by['B_changed'].target.notes
    assert not by['C_flat'].detected_in_target and not by['A_unchanged'].detected_in_target
    assert not by['B_changed'].target.verified


def test_unconfirmed_axes_are_not_carried_over():
    """Regression 1.19 QA: axis values of the source stayed on the proposal when the target axis moved."""
    from dataclasses import replace
    source, target, maps = _sisters()
    axis = [10, 20, 30, 40, 50, 60, 70, 80]
    src = bytearray(source.read(0, source.size)); src[0x0F00:0x0F10] = np.array(axis, '>u2').tobytes()
    dst = bytearray(target.read(0, target.size)); dst[0x0F00:0x0F10] = np.array(axis[::-1], '>u2').tobytes()
    m = replace(maps[0], axis_x_offset=0x0F00, axes_x=[float(v) for v in axis])
    (t,) = transfer_names(BinaryImage(bytes(src)), BinaryImage(bytes(dst)), [m])
    assert t.axes_dropped == ('X',) and t.target.axis_x_offset is None and t.target.axes_x == []
    assert 'nicht bestätigt' in t.target.notes


def test_detection_with_other_axes_or_byte_order_does_not_confirm():
    from dataclasses import replace
    from ecu_studio.core.name_transfer import confirm_by_detection
    source, target, maps = _sisters()
    result = [t for t in transfer_names(source, target, maps) if t.source.name == 'B_changed']
    result[0].target = replace(result[0].target, dtype='u16', rows=4, cols=8, axis_x_offset=0x100)
    other_axes = MapDefinition('k', 0x5200, 4, 8, 'u16', 'big', source='heuristic', axis_x_offset=0x300)
    assert confirm_by_detection(result, [other_axes]) == 0
    assert 'Achsen aber bei 0x300' in result[0].detection_conflict
    result[0].detection_conflict = ''
    other_order = MapDefinition('k', 0x5200, 4, 8, 'u16', 'little', source='heuristic')
    assert confirm_by_detection(result, [other_order]) == 0 and not result[0].detected_in_target
    same = MapDefinition('k', 0x5200, 8, 4, 'u16', 'big', source='heuristic', axis_y_offset=0x100)
    assert confirm_by_detection(result, [same]) == 1


def test_adopting_replaces_unnamed_detections_but_keeps_checked_maps(tmp_path, monkeypatch):
    """Regression 1.19 QA: proposals landing on a detected table (the confirmed ones) were skipped on adoption."""
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from pathlib import Path
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.core import name_transfer
    from ecu_studio.ui.main_window import Window
    app = QApplication.instance() or QApplication([])
    source, target, maps = _sisters()
    (tmp_path / 'src.bin').write_bytes(source.read(0, source.size))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(tmp_path / 'src.bin'), ''))
    monkeypatch.setattr(name_transfer, 'definition_maps', lambda path, image: maps)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    unnamed = MapDefinition('Kandidat', 0x5200, 8, 8, 'u8', 'big', source='heuristic', record_layout='candidate:code-call')
    checked = MapDefinition('Geprüft', 0x6200, 8, 8, 'u8', 'big', source='heuristic', verified=True)
    w = Window()
    w.load_state(target, [unnamed, checked], [], '', None)
    w.transfer_sister_names()
    names = {m.name for m in w.maps}
    assert names == {'A_unchanged', 'B_changed', 'Geprüft'}
    adopted = next(m for m in w.maps if m.name == 'B_changed')
    assert adopted.source == 'transfer-proposed' and 'unabhängig bestätigt' in adopted.notes
    w.saved_fingerprint = w.project_state()
    w.close()
