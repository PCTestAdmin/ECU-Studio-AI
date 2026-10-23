"""Shared-axis groups: formed by axis storage address only, with evidence class and conflicts."""
import json
import struct
import numpy as np
import pytest
from ecu_studio.core.a2l import parse_a2l
from ecu_studio.core.axis_groups import (axis_value_hints, compare_with_reference, group_index,
                                         relocated_axis, shared_axis_groups)
from ecu_studio.core.axis_records import scan_axis_records
from ecu_studio.core.model import BinaryImage, MapDefinition, load_project, save_project
from ecu_studio.core.name_transfer import transfer_names
from ecu_studio.core.xdf import read_xdf

# Two group maps (values only) share the axis objects SNM (X) and SRL (Y); a third
# map carries its own axes inline (STD_AXIS) and must not join the group.
A2L = '''/begin PROJECT P "" /begin MODULE M ""
/begin MOD_COMMON "" BYTE_ORDER MSB_LAST ALIGNMENT_BYTE 1 ALIGNMENT_WORD 1 /end MOD_COMMON
/begin RECORD_LAYOUT SstUb NO_AXIS_PTS_X 1 UBYTE AXIS_PTS_X 2 UBYTE INDEX_INCR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT GKfUb FNC_VALUES 1 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT
/begin RECORD_LAYOUT KfUb NO_AXIS_PTS_X 1 UBYTE NO_AXIS_PTS_Y 2 UBYTE AXIS_PTS_X 3 UBYTE INDEX_INCR DIRECT
  AXIS_PTS_Y 4 UBYTE INDEX_INCR DIRECT FNC_VALUES 5 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT
/begin AXIS_PTS SNM "" 0x800100 nmot SstUb 0 NO_COMPU_METHOD 8 0 255 /end AXIS_PTS
/begin AXIS_PTS SRL "" 0x800110 rl SstUb 0 NO_COMPU_METHOD 8 0 255 /end AXIS_PTS
/begin CHARACTERISTIC GKF_A "group map a" MAP 0x800200 GKfUb 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR COM_AXIS nmot NO_COMPU_METHOD 8 0 255 AXIS_PTS_REF SNM /end AXIS_DESCR
  /begin AXIS_DESCR COM_AXIS rl NO_COMPU_METHOD 8 0 255 AXIS_PTS_REF SRL /end AXIS_DESCR /end CHARACTERISTIC
/begin CHARACTERISTIC GKF_B "group map b" MAP 0x800240 GKfUb 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR COM_AXIS nmot NO_COMPU_METHOD 8 0 255 AXIS_PTS_REF SNM /end AXIS_DESCR
  /begin AXIS_DESCR COM_AXIS rl NO_COMPU_METHOD 8 0 255 AXIS_PTS_REF SRL /end AXIS_DESCR /end CHARACTERISTIC
/begin CHARACTERISTIC KF_OWN "own axes" MAP 0x800300 KfUb 0 NO_COMPU_METHOD 0 255
  /begin AXIS_DESCR STD_AXIS nmot NO_COMPU_METHOD 8 0 255 /end AXIS_DESCR
  /begin AXIS_DESCR STD_AXIS rl NO_COMPU_METHOD 8 0 255 /end AXIS_DESCR /end CHARACTERISTIC
/end MODULE /end PROJECT'''


def _a2l_bin():
    d = bytearray(0x1000)
    d[0x100:0x105] = bytes([4, 10, 20, 30, 40])          # SNM: 4 points
    d[0x110:0x114] = bytes([3, 1, 5, 9])                 # SRL: 3 points
    d[0x200:0x20C] = bytes(range(12))                    # 3 x 4 values, no header
    d[0x240:0x24C] = bytes(range(50, 62))
    d[0x300:0x302] = bytes([4, 3])
    d[0x302:0x309] = bytes([10, 20, 30, 40, 1, 5, 9])     # same values as SNM/SRL, own storage
    d[0x309:0x315] = bytes(range(100, 112))
    return bytes(d)


def _a2l_maps():
    data = _a2l_bin()
    return {m.name: m for m in parse_a2l(A2L).link(file_size=len(data), ecu_anchor=0x800000, data=data).maps}


def test_a2l_com_axis_keeps_axis_object_and_address():
    maps = _a2l_maps()
    a, own = maps['GKF_A'], maps['KF_OWN']
    assert (a.axis_x_offset, a.axis_x_ref, a.axis_y_offset, a.axis_y_ref) == (0x101, 'SNM', 0x111, 'SRL')
    assert (own.axis_x_offset, own.axis_y_offset, own.axis_x_ref) == (0x302, 0x306, '')


def test_definition_groups_by_address_not_by_equal_values():
    maps = list(_a2l_maps().values())
    groups = shared_axis_groups(maps)
    names = sorted((g.reference, tuple(sorted(maps[i].name for i in g.indices))) for g in groups)
    assert names == [('SNM', ('GKF_A', 'GKF_B')), ('SRL', ('GKF_A', 'GKF_B'))]
    assert all(g.evidence == 'definition' and not g.uncertain for g in groups)
    assert {g.points for g in groups} == {4, 3}
    # KF_OWN has the same axis values but its own storage: only a hypothesis.
    hints = axis_value_hints(maps, groups)
    own = [i for i, m in enumerate(maps) if m.name == 'KF_OWN'][0]
    assert any(own in h for h in hints)
    assert own not in group_index(groups)


def test_xdf_linked_axis_reports_storage_of_the_linked_object(tmp_path):
    xml = '''<XDFFORMAT>
    <XDFTABLE uniqueid="0x10"><title>shared rpm</title><XDFAXIS id="z">
    <EMBEDDEDDATA mmedaddress="0x20" mmedelementsizebits="8" mmedrowcount="1" mmedcolcount="4"/></XDFAXIS></XDFTABLE>
    <XDFTABLE><title>a</title><XDFAXIS id="x"><indexcount>4</indexcount>
    <embedinfo type="3" linkobjid="0x10"/></XDFAXIS>
    <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x40" mmedelementsizebits="8" mmedrowcount="2" mmedcolcount="4"/></XDFAXIS></XDFTABLE>
    <XDFTABLE><title>b</title><XDFAXIS id="x"><indexcount>4</indexcount>
    <embedinfo type="3" linkobjid="0x10"/></XDFAXIS>
    <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x60" mmedelementsizebits="8" mmedrowcount="2" mmedcolcount="4"/></XDFAXIS></XDFTABLE>
    </XDFFORMAT>'''
    path = tmp_path / 'linked.xdf'
    path.write_text(xml)
    buf = bytearray(256)
    buf[0x20:0x24] = bytes([10, 20, 30, 40])
    maps = [m for m in read_xdf(str(path), BinaryImage(buf)).maps if m.rows > 1]
    assert [m.axis_x_offset for m in maps] == [0x20, 0x20]
    (group,) = shared_axis_groups(maps)
    assert group.evidence == 'definition' and group.points == 4 and group.indices == [0, 1]


def _cand(name, offset, rows, cols, **kw):
    return MapDefinition(name, offset, rows, cols, 'u8', source='heuristic', **kw)


def test_structural_group_is_unverified_and_conflicts_are_flagged():
    maps = [_cand('a', 0x100, 4, 6, axis_x_offset=0x40), _cand('b', 0x200, 3, 6, axis_x_offset=0x40),
            _cand('c', 0x300, 4, 5, axis_x_offset=0x40),                 # 5 points: conflict
            _cand('d', 0x400, 4, 4, axis_x_offset=0x80)]                 # alone: no group
    (group,) = shared_axis_groups(maps)
    assert group.evidence == 'structure' and group.indices == [0, 1, 2]
    assert group.points == 6 and group.uncertain and 'widersprechen' in group.issues[0]
    assert 'unsicher' in group.describe()
    mixed = [MapDefinition('x', 0x100, 4, 6, 'u8', source='a2l', axis_x_offset=0x40), maps[1]]
    assert shared_axis_groups(mixed)[0].evidence == 'structure'   # weakest member decides


def test_axis_inside_a_member_value_block_is_uncertain():
    maps = [_cand('a', 0x100, 4, 6, axis_x_offset=0x104), _cand('b', 0x200, 4, 6, axis_x_offset=0x104)]
    assert 'Wertebereich' in shared_axis_groups(maps)[0].issues[0]


def test_short_or_constant_axes_give_no_hints():
    maps = [_cand('a', 0x100, 4, 3, axes_x=[1, 2, 3]), _cand('b', 0x200, 4, 3, axes_x=[1, 2, 3]),
            _cand('c', 0x300, 4, 4, axes_x=[5, 5, 5, 5]), _cand('d', 0x400, 4, 4, axes_x=[5, 5, 5, 5])]
    assert axis_value_hints(maps) == []


def test_header_record_candidates_carry_their_axis_offsets():
    buf = bytearray(4096)
    rec = bytes([8, 6]) + bytes([10, 20, 30, 40, 50, 60, 70, 80]) + bytes([1, 3, 6, 10, 15, 21])
    z = (np.add.outer(np.arange(6) * 9, np.arange(8) * 7) + 11).astype(np.uint8).tobytes()
    buf[0x400:0x400 + len(rec) + len(z)] = rec + z
    found = [m for m in scan_axis_records(BinaryImage(bytes(buf))) if m.offset == 0x410 and m.dtype == 'u8']
    assert found and (found[0].axis_x_offset, found[0].axis_y_offset) == (0x402, 0x40A)


def test_reference_comparison_counts_axis_addresses_and_group_pairs():
    ref = [MapDefinition('A', 0x100, 4, 6, 'u8', source='a2l', axis_x_offset=0x40, axis_y_offset=0x50),
           MapDefinition('B', 0x200, 4, 6, 'u8', source='a2l', axis_x_offset=0x40, axis_y_offset=0x60),
           MapDefinition('C', 0x300, 4, 6, 'u8', source='a2l', axis_x_offset=0x40, axis_y_offset=0x70)]
    found = [_cand('a', 0x100, 4, 6, axis_x_offset=0x40), _cand('b', 0x200, 6, 4, axis_x_offset=0x40),
             _cand('c', 0x300, 4, 6, axis_x_offset=0x90), _cand('z', 0x900, 4, 6, axis_x_offset=0x90)]
    r = compare_with_reference(found, ref)
    assert r['matched_maps'] == 3 and (r['axis_with_address'], r['axis_address_correct']) == (3, 2)
    # Reference pairs among matched maps: A-B, A-C, B-C; found: a-b (c pairs only with unmatched z).
    assert (r['pairs_reference'], r['pairs_found'], r['pairs_agree']) == (3, 1, 1)
    assert r['pair_precision'] == 1.0 and r['pair_recall'] == pytest.approx(1 / 3, abs=1e-4)


def test_projects_keep_axis_references_and_old_projects_still_load(tmp_path):
    data = _a2l_bin()
    image = BinaryImage(data)
    maps = list(_a2l_maps().values())
    save_project(str(tmp_path / 'p.ecuproj'), image, maps, [], '')
    _, loaded, _, _ = load_project(str(tmp_path / 'p.ecuproj'))
    assert [(m.axis_x_offset, m.axis_x_ref) for m in loaded] == [(m.axis_x_offset, m.axis_x_ref) for m in maps]
    payload = json.loads((tmp_path / 'p.ecuproj').read_text(encoding='utf-8'))
    for m in payload['maps']:
        for key in ('axis_x_offset', 'axis_y_offset', 'axis_x_ref', 'axis_y_ref'):
            m.pop(key)
    payload.pop('integrity_sha256')
    (tmp_path / 'old.ecuproj').write_text(json.dumps(payload), encoding='utf-8')
    _, old, _, _ = load_project(str(tmp_path / 'old.ecuproj'))
    assert all(m.axis_x_offset is None for m in old) and shared_axis_groups(old) == []


def test_axis_offset_outside_the_file_is_rejected():
    with pytest.raises(ValueError, match='Achsenadresse'):
        MapDefinition('a', 0, 2, 2, 'u8', axis_x_offset=4096).validate(4096)


def test_transferred_maps_keep_axis_offsets_only_where_target_confirms():
    rng = np.random.default_rng(3)
    src = bytearray(rng.integers(0, 256, 8192, dtype=np.uint8).tobytes())
    src[0x1000:0x1008] = bytes([10, 20, 30, 40, 50, 60, 70, 80])
    dst = bytes(16) + bytes(src)                                      # everything moved by +16
    source, target = BinaryImage(bytes(src)), BinaryImage(dst)
    assert relocated_axis(source, target, 0x1000, 4, 16) == 0x1010
    assert relocated_axis(source, target, 0x1000, 4, 17) is None
    m = MapDefinition('M', 0x1100, 4, 4, 'u8', source='xdf', axis_x_offset=0x1000, axis_y_offset=0x1F00)
    changed = bytearray(dst)
    changed[0x1F10] ^= 0xFF                                           # Y axis differs in the target
    (t,) = transfer_names(source, BinaryImage(bytes(changed)), [m])
    assert t.target.offset == 0x1110
    assert (t.target.axis_x_offset, t.target.axis_y_offset) == (0x1010, None)


def test_map_groups_and_function_graph_use_axis_addresses():
    from ecu_studio.core.function_graph import build_function_graph, related_maps
    from ecu_studio.core.map_groups import group_maps
    maps = list(_a2l_maps().values())
    axis = [g for g in group_maps(maps) if g.key.startswith('axis:')]
    assert len(axis) == 2 and all('Definition' in g.basis for g in axis)
    graph = build_function_graph(BinaryImage(_a2l_bin()), maps)
    own = [i for i, m in enumerate(maps) if m.name == 'KF_OWN'][0]
    a = [i for i, m in enumerate(maps) if m.name == 'GKF_A'][0]
    b = [i for i, m in enumerate(maps) if m.name == 'GKF_B'][0]
    rel = related_maps(graph, a)
    assert rel['axes'] == [b] and own in rel['axis_hints']   # equal values: hypothesis only
    assert related_maps(graph, own)['axes'] == []


def test_catalogue_detail_and_graph_dialog_show_shared_axes(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from tests.test_ui_filters_banner import _window
    from PySide6.QtCore import Qt
    from ecu_studio.core.function_graph import build_function_graph
    from ecu_studio.ui.function_graph_dialog import FunctionGraphDialog
    app, w = _window(tmp_path, monkeypatch)
    image, maps = BinaryImage(_a2l_bin()), list(_a2l_maps().values())
    w.load_state(image, maps, [], '', None)
    rows = {w.catalog_model.data(w.catalog_model.index(r, 0), Qt.ItemDataRole.UserRole):
            w.catalog_model.data(w.catalog_model.index(r, 0)) for r in range(w.catalog_model.rowCount())}
    names = {m.name: i for i, m in enumerate(maps)}
    assert 'Achse geteilt' in rows[names['GKF_A']] and 'Achse geteilt' not in rows[names['KF_OWN']]
    tip = w.catalog_model.data(w.catalog_model.index(list(rows).index(names['GKF_B']), 0), Qt.ItemDataRole.ToolTipRole)
    assert 'SNM' in tip and 'aus Definition' in tip
    w.select_map(maps[names['GKF_A']])
    assert 'Teilt die Achse mit: GKF_B' in w.map_hint.text()
    dialog = FunctionGraphDialog(w, maps, build_function_graph(image, maps), lambda m: None)
    top = [dialog.tree.topLevelItem(k).text(0) for k in range(dialog.tree.topLevelItemCount())]
    assert top[1].startswith('Gemeinsame gespeicherte Achse (2') and 'Hypothese (1)' in top[2]
    dialog.close(); w.close()
