"""Two software versions: classified pairs, differences, controlled adoption, versions with definitions."""
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition, load_project, save_project
from ecu_studio.core.version_compare import adopt_definitions, compare_versions, filter_pairs
from ecu_studio.core.versioning import compare_snapshots, make_snapshot, snapshot_maps, validate_snapshot_set

SHIFT = 32


def _versions():
    """Source with four maps; target = source with 32 bytes inserted in front of them."""
    rng = np.random.default_rng(7)
    src = bytearray(rng.integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    surface = (np.add.outer(np.arange(8) * 9, np.arange(8) * 5) + 20).astype(np.uint8).tobytes()
    src[0x1000:0x1040] = surface                     # same in target
    src[0x1100:0x1140] = surface[::-1]               # values changed in target
    src[0x1200:0x1240] = bytes(range(64))            # gone in target
    dst = bytearray(src[:0x0800] + bytes(rng.integers(0, 256, SHIFT, dtype=np.uint8)) + src[0x0800:-SHIFT])
    t = 0x1100 + SHIFT
    dst[t:t + 64] = bytes(min(255, b + 3) for b in src[0x1100:0x1140])
    t = 0x1200 + SHIFT
    dst[t - 16:t + 80] = rng.integers(0, 256, 96, dtype=np.uint8).tobytes()
    maps = [MapDefinition('SAME', 0x1000, 8, 8, 'u8', source='xdf', factor=.5, unit='%'),
            MapDefinition('CHANGED', 0x1100, 8, 8, 'u8', source='xdf'),
            MapDefinition('GONE', 0x1200, 8, 8, 'u8', source='xdf')]
    return BinaryImage(bytes(src)), BinaryImage(bytes(dst)), maps


def test_pairs_are_classified_and_differences_measured():
    source, target, maps = _versions()
    result = compare_versions(source, maps, target)
    by = {p.source.name: p for p in result['pairs']}
    assert by['SAME'].match == 'exakt' and by['SAME'].target.offset == 0x1000 + SHIFT and not by['SAME'].changed
    assert by['CHANGED'].match == 'wahrscheinlich' and by['CHANGED'].changed_cells == 64
    assert by['CHANGED'].max_abs_raw == 3 and by['CHANGED'].needs_confirmation
    assert by['GONE'].match == 'nicht zuordenbar' and by['GONE'].target is None
    assert result['counts']['exakt'] == 1 and result['counts']['nicht zuordenbar'] == 1
    assert [p.source.name for p in filter_pairs(result['pairs'], 'Geändert')] == ['CHANGED']
    assert [p.source.name for p in filter_pairs(result['pairs'], 'Unverändert')] == ['SAME']
    assert [p.source.name for p in filter_pairs(result['pairs'], 'Nicht zugeordnet')] == ['GONE']


def test_equal_address_alone_is_no_match():
    source, _, maps = _versions()
    other = BinaryImage(np.random.default_rng(1).integers(0, 256, source.size, dtype=np.uint8).tobytes())
    assert all(p.match == 'nicht zuordenbar' for p in compare_versions(source, maps, other)['pairs'])


def test_two_claims_on_one_place_and_conflicting_target_definitions_are_ambiguous():
    source, target, maps = _versions()
    twice = maps[:1] + [MapDefinition('SAME_AS_CURVE', 0x1000, 1, 64, 'u8', source='xdf')]
    pairs = compare_versions(source, twice, target)['pairs']
    assert [p.match for p in pairs] == ['mehrdeutig', 'mehrdeutig'] and 'SAME_AS_CURVE' in pairs[0].evidence
    existing = [MapDefinition('OTHER', 0x1000 + SHIFT, 4, 16, 'u8', source='heuristic'),
                MapDefinition('ONLY_IN_TARGET', 0x3000, 4, 4, 'u8', source='heuristic')]
    result = compare_versions(source, maps, target, existing)
    same = result['pairs'][0]
    assert same.match == 'mehrdeutig' and 'OTHER' in same.conflict
    assert result['target_only'] == [1]
    with pytest.raises(ValueError, match='mehrdeutig'):
        adopt_definitions([same], existing, source_label='A')


def test_adoption_is_all_or_nothing_and_probable_needs_confirmation():
    source, target, maps = _versions()
    pairs = compare_versions(source, maps, target)['pairs']
    same, changed, gone = pairs
    with pytest.raises(ValueError, match='Bestätigung'):
        adopt_definitions([same, changed], [], source_label='A')
    with pytest.raises(ValueError, match='nicht zuordenbar'):
        adopt_definitions([same, gone], [], source_label='A')
    added, protocol = adopt_definitions([same, changed], [], source_label='A', confirm_probable=True)
    assert [m.offset for m in added] == [0x1000 + SHIFT, 0x1100 + SHIFT]
    assert all(m.source == 'transfer-proposed' and not m.verified for m in added)
    assert added[0].factor == .5 and added[0].unit == '%'
    assert [p['match'] for p in protocol] == ['exakt', 'wahrscheinlich'] and protocol[0]['source_offset'] == 0x1000
    again, _ = adopt_definitions([same], added, source_label='A')
    assert again == []                                         # already present: nothing doubled
    assert source.dirty_bytes == target.dirty_bytes == 0       # firmware untouched


def test_versions_store_definitions_and_any_two_can_be_compared(tmp_path):
    source, target, maps = _versions()
    first = make_snapshot(target, 'Start', maps=[])
    added, _ = adopt_definitions(compare_versions(source, maps, target)['pairs'][:1], [], source_label='A')
    target.commit([(added[0].offset, target.byte(added[0].offset), 0xEE)], label='Test')
    second = make_snapshot(target, 'Übernommen', 'Definitionen aus A', maps=added)
    diff = compare_snapshots(target, first, second, added)
    assert diff['changed_bytes'] == 1 and diff['maps_changed'] == {'SAME': 1} and diff['bytes_outside_maps'] == 0
    assert diff['definitions_added'] == ['SAME'] and diff['definitions_removed'] == []
    assert compare_snapshots(target, second, first, added)['definitions_removed'] == ['SAME']
    assert snapshot_maps(target, make_snapshot(target, 'Nur Bytes')) is None
    save_project(str(tmp_path / 'p.ecustudio'), target, added, [], '', [first, second])
    from ecu_studio.core.model import read_project_snapshots
    image, loaded, _, _ = load_project(str(tmp_path / 'p.ecustudio'))
    snaps = read_project_snapshots(str(tmp_path / 'p.ecustudio'), image)
    assert [m.name for m in snapshot_maps(image, snaps[1])] == ['SAME']
    broken = dict(second, maps=[{'name': 'x', 'offset': target.size}])
    with pytest.raises(ValueError):
        validate_snapshot_set(target, [broken])


def test_dialog_workflow_compare_view_adopt_and_save_as_version(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from tests.test_ui_filters_banner import _window
    from ecu_studio.core.model import read_project_snapshots
    from ecu_studio.ui.version_compare_dialog import VersionCompareDialog
    app, w = _window(tmp_path, monkeypatch)
    source, target, maps = _versions()
    w.load_state(target, [], [], '', None)
    project = tmp_path / 'b.ecustudio'
    w.project_path = str(project)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    dialog = VersionCompareDialog(w)
    dialog.source, dialog.source_maps, dialog.source_label = source, maps, 'Stand A'
    dialog.compared(compare_versions(source, maps, target, w.maps))
    assert dialog.table.rowCount() == 3 and 'exakt: 1' in dialog.summary.text()
    dialog.table.selectRow(1)                                    # CHANGED: values side by side
    assert dialog.view_a.rowCount() == 8 and dialog.view_b.item(0, 0).background().color().blue() < 255
    dialog.view_a.setCurrentCell(3, 4)
    assert (dialog.view_b.currentRow(), dialog.view_b.currentColumn()) == (3, 4)
    dialog.mark_unique()                                         # only SAME is unique
    assert [p.source.name for p in dialog.marked()] == ['SAME']
    dialog.compare = lambda: None                                # no background re-run in the test
    dialog.adopt()
    assert [m.name for m in w.maps] == ['SAME'] and w.maps[0].offset == 0x1000 + SHIFT
    assert w.snapshots[-1]['label'] == 'Definitionen aus Stand A' and w.image.journal[-1]['match'] == 'exakt'
    assert project.exists()
    image, loaded, _, _ = load_project(str(project))
    assert [m.name for m in loaded] == ['SAME'] and image.dirty_bytes == 0
    assert snapshot_maps(image, read_project_snapshots(str(project), image)[-1])[0].name == 'SAME'
    dialog.close(); w.close()


def _newer_project(tmp_path):
    """A project as a later version might write it: one extra map field, valid integrity hash."""
    import json
    from ecu_studio.core.storage import canonical_digest
    image = BinaryImage(bytes(4096))
    path = tmp_path / 'neu.ecustudio'
    save_project(str(path), image, [MapDefinition('KF', 0x100, 4, 4, 'u8', source='xdf')], [], '',
                 [make_snapshot(image, 'v1', maps=[MapDefinition('KF', 0x100, 4, 4, 'u8')])])
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['maps'][0]['zukunftsfeld'] = 1
    payload['snapshots'][0]['maps'][0]['zukunftsfeld'] = 1
    payload.pop('integrity_sha256')
    payload['integrity_sha256'] = canonical_digest(payload)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_projects_of_newer_versions_load_with_named_unknown_fields(tmp_path):
    from ecu_studio.core.model import read_project_snapshots
    path = _newer_project(tmp_path)
    with pytest.raises(ValueError, match='neueren Version.*zukunftsfeld'):
        load_project(str(path))                                   # strict by default: nothing dropped silently
    ignored = set()
    image, maps, _, _ = load_project(str(path), ignored_fields=ignored)
    assert ignored == {'zukunftsfeld'} and maps[0].name == 'KF'
    assert snapshot_maps(image, read_project_snapshots(str(path), image)[0])[0].name == 'KF'


def test_window_warns_when_opening_a_newer_project(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QMessageBox
    from tests.test_ui_filters_banner import _window
    app, w = _window(tmp_path, monkeypatch)
    shown = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: shown.append(a[2]))
    w.open_project_file(str(_newer_project(tmp_path)))
    assert [m.name for m in w.maps] == ['KF'] and len(w.snapshots) == 1
    assert shown and 'zukunftsfeld' in shown[0] and 'verloren' in shown[0]
    w.close()
