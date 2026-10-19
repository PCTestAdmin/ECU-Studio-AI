from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from ecu_studio.core.a2l import parse_a2l
from ecu_studio.core.model import BinaryImage, MapDefinition, save_project, load_project, read_project_snapshots
from ecu_studio.core.versioning import make_snapshot, plan_restore, apply_restore, validate_snapshot


def test_versions_single_undo_and_selective_restore():
    img = BinaryImage(bytes(range(128)))
    m = MapDefinition('map', 16, rows=2, cols=2, dtype='u16')
    img.write(17, b'\xCC')
    base = make_snapshot(img, 'v1', 'Kontrollstand')
    img.write(17, b'\xDD')
    img.write(80, b'\xEE')
    preview = plan_restore(img, base, m)
    assert preview.changed_bytes == 1 and preview.selected_map == 'map'
    assert img.byte(17) == 0xDD  # no edit during preview
    assert apply_restore(img, preview)
    assert img.byte(17) == 0xCC and img.byte(80) == 0xEE
    img.undo()
    assert img.byte(17) == 0xDD and img.byte(80) == 0xEE
    img.redo()
    assert img.byte(17) == 0xCC
    whole = plan_restore(img, base)
    assert whole.changed_bytes == 1
    assert apply_restore(img, whole)
    assert img.byte(80) == 80


def test_snapshot_guard_and_staleness_and_tampering():
    img = BinaryImage(bytes(range(64)))
    snap = make_snapshot(img, 'clean')
    img.write(5, b'\xFA')
    preview = plan_restore(img, snap)
    img.write(5, b'\xFC')
    with pytest.raises(ValueError, match='veraltet'):
        apply_restore(img, preview)
    assert img.byte(5) == 0xFC
    evil = copy.deepcopy(snap)
    evil['patches'] = [[1, 200]]
    with pytest.raises(ValueError, match='Integrität'):
        validate_snapshot(img, evil)
    other = BinaryImage(bytes([0])*64)
    with pytest.raises(ValueError, match='Original-BIN'):
        plan_restore(other, snap)
    with pytest.raises(ValueError, match='Versionsname'):
        make_snapshot(img, '')


def test_snapshots_project_roundtrip(tmp_path):
    source = tmp_path/'ori.bin'; source.write_bytes(bytes(range(100)))
    img = BinaryImage.from_file(str(source)); img.write(10, b'\xFF')
    snap = make_snapshot(img, 'Revision A')
    project = tmp_path/'a.ecustudio'
    save_project(str(project), img, [], [], '', [snap])
    loaded, maps, marks, notes = load_project(str(project))
    result = read_project_snapshots(str(project), loaded)
    assert result == [snap]
    assert plan_restore(loaded, result[0]).changed_bytes == 0
    old = tmp_path/'old.ecustudio'
    save_project(str(old), img, [], [], '')
    assert read_project_snapshots(str(old), loaded) == []


A2L = '''ASAP2_VERSION 1 71
/begin PROJECT P "a"
/begin MODULE M "b"
 /begin MOD_COMMON "common" BYTE_ORDER MSB_FIRST /end MOD_COMMON
 /begin RECORD_LAYOUT RL FNC_VALUES 1 UWORD ROW_DIR DIRECT /end RECORD_LAYOUT
 /begin RECORD_LAYOUT COL FNC_VALUES 1 UWORD COLUMN_DIR DIRECT /end RECORD_LAYOUT
 /begin COMPU_METHOD SCALE "conversion" LINEAR "%5.0" "rpm" COEFFS_LINEAR 2 5 /end COMPU_METHOD
 /begin CHARACTERISTIC FOO "arbitrary calibration" MAP 0x801000 RL 0 NO_COMPU_METHOD 0 3000
  MATRIX_DIM 4 3 1
  /begin AXIS_DESCR FIX_AXIS RPM SCALE 4 0 6000 FIX_AXIS_PAR_DIST 100 50 4 /end AXIS_DESCR
  /begin AXIS_DESCR FIX_AXIS LOAD NO_COMPU_METHOD 3 0 100 FIX_AXIS_PAR 10 1 3 /end AXIS_DESCR
 /end CHARACTERISTIC
 /begin CHARACTERISTIC BAD "unsafe column order" CURVE 0x802000 COL 0 NO_COMPU_METHOD 0 3000 MATRIX_DIM 4 1 1 /end CHARACTERISTIC
/end MODULE
/end PROJECT'''


def test_a2l_fixed_axes_and_explicit_column_rejection():
    cat = parse_a2l(A2L)
    result = cat.link(file_size=16384, ecu_anchor=0x800000)
    assert len(result.maps) == 1
    item = result.maps[0]
    assert (item.rows,item.cols) == (3,4)
    assert item.axes_x == [205,305,405,505]
    assert item.axes_y == [10,12,14]
    assert any('zeilenweise' in err for err in result.unsupported)
