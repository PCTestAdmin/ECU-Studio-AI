"""Local reference search when a BIN is opened: tiers by hash, software/hardware number and family (synthetic)."""
import json
import sqlite3
from contextlib import closing

from ecu_studio.core.model import BinaryImage, MapDefinition, save_project
from ecu_studio.core.project_store import ProjectStore

HW, SW, FAMILY = '0261208123', '1037351234', 'ME7.5'


def _image(hw=HW, sw=SW, epk=True, salt=0):
    buf = bytearray(0x4000)
    if epk:
        buf[0x100:0x100 + 26] = b'40/1/ME7.5/5/5016.10//24x/'
    if hw:
        buf[0x200:0x200 + len(hw)] = hw.encode()
    if sw:
        buf[0x210:0x210 + len(sw)] = sw.encode()
    buf[0x3000] = salt                       # different bytes, same identity
    return BinaryImage(bytes(buf))


def _project(tmp_path, name, image):
    path = tmp_path / f'{name}.ecustudio'
    save_project(str(path), image, [MapDefinition('KF', 0x1000, 4, 4, 'u8', source='xdf')], [], '', [])
    return path


def _relations(store, image):
    return {r['path'].rsplit('\\', 1)[-1].rsplit('/', 1)[-1]: (r['relation'], r['level'])
            for r in store.suggestions(image)}


def test_tiers_from_identical_file_to_same_family(tmp_path):
    store = ProjectStore(tmp_path / 'lib.sqlite3')
    opened = _image()
    store.index(_project(tmp_path, 'exact', _image()))
    store.index(_project(tmp_path, 'same-ids', _image(salt=1)))
    store.index(_project(tmp_path, 'same-sw', _image(hw='0261208999', salt=2)))
    store.index(_project(tmp_path, 'same-hw', _image(sw='1037359999', salt=3)))
    store.index(_project(tmp_path, 'family', _image(hw='0261200000', sw='1037300000', salt=4)))
    store.index(_project(tmp_path, 'other', _image(hw='0261200001', sw='1037300001', epk=False, salt=5)))
    rows = store.suggestions(opened)
    assert [r['relation'] for r in rows] == ['exact', 'software+hardware', 'software', 'hardware', 'related']
    assert _relations(store, opened) == {
        'exact.ecustudio': ('exact', 'nachgewiesen'),
        'same-ids.ecustudio': ('software+hardware', 'wahrscheinlich'),
        'same-sw.ecustudio': ('software', 'wahrscheinlich'),
        'same-hw.ecustudio': ('hardware', 'mehrdeutig'),
        'family.ecustudio': ('related', 'mehrdeutig')}
    assert SW in rows[1]['evidence'] and HW in rows[1]['evidence'] and 'abweichen' in rows[1]['evidence']


def test_map_pack_with_same_software_number_is_found(tmp_path):
    store = ProjectStore(tmp_path / 'lib.sqlite3')
    with closing(sqlite3.connect(tmp_path / 'lib.sqlite3')) as c, c:
        c.execute('INSERT INTO map_packs VALUES(?,?,?,?,?,?)',
                  ('C:/packs/a.json', 'ff' * 32, '', json.dumps([]), json.dumps([SW]), 12))
    store = ProjectStore(tmp_path / 'lib.sqlite3')      # backfills identifiers of the pack row
    (row,) = store.suggestions(_image(hw='', epk=False))
    assert (row['kind'], row['relation'], row['level']) == ('pack', 'software', 'wahrscheinlich')


def test_unidentified_bin_only_matches_identical_files(tmp_path):
    store = ProjectStore(tmp_path / 'lib.sqlite3')
    blank = _image(hw='', sw='', epk=False)
    store.index(_project(tmp_path, 'blank', blank))
    store.index(_project(tmp_path, 'ident', _image()))
    assert _relations(store, blank) == {'blank.ecustudio': ('exact', 'nachgewiesen')}


def test_rows_from_before_the_identifier_table_are_backfilled_without_opening_bins(tmp_path):
    db = tmp_path / 'lib.sqlite3'
    store = ProjectStore(db)
    store.index(_project(tmp_path, 'old', _image(salt=9)))
    with closing(sqlite3.connect(db)) as c, c:
        c.execute('DROP TABLE identifiers')               # as written by a version without the table
    (tmp_path / 'old.ecustudio').unlink()               # backfill must not need the project file
    store = ProjectStore(db)
    assert _relations(store, _image()) == {'old.ecustudio': ('software+hardware', 'wahrscheinlich')}


def test_relation_follows_current_metadata_when_an_older_version_reindexed(tmp_path):
    db = tmp_path / 'lib.sqlite3'
    store = ProjectStore(db)
    store.index(_project(tmp_path, 'p', _image(salt=7)))
    with closing(sqlite3.connect(db)) as c, c:            # older version rewrote metadata, not identifiers
        c.execute("UPDATE project_meta SET software='1037300042', hardware='0261200042'")
    assert _relations(store, _image()) == {'p.ecustudio': ('related', 'mehrdeutig')}


def test_index_many_batches_collects_errors_reports_progress_and_can_be_cancelled(tmp_path):
    store = ProjectStore(tmp_path / 'lib.sqlite3')
    paths = [_project(tmp_path, f'p{i}', _image(salt=i)) for i in range(5)]
    broken = tmp_path / 'broken.ecustudio'
    broken.write_text('{kein json')
    progress = []
    result = store.index_many([*paths[:2], broken, *paths[2:]], progress=lambda done, total: progress.append(done))
    assert (result.indexed, result.cancelled) == (5, False)
    assert [p for p, _ in result.errors] == [str(broken)]
    assert progress == [1, 2, 3, 4, 5, 6] and len(store.search()) == 5
    other = ProjectStore(tmp_path / 'other.sqlite3')
    calls = []
    result = other.index_many(paths, cancelled=lambda: len(calls) >= 2, progress=lambda d, t: calls.append(d))
    assert result.cancelled and result.indexed == 2 and len(other.search()) == 2


def test_window_lists_levels_with_evidence_and_indexes_folders_in_one_batch(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QLabel, QMessageBox, QPushButton
    from tests.test_ui_filters_banner import _window
    app, w = _window(tmp_path, monkeypatch)
    w.project_store = ProjectStore(tmp_path / 'lib.sqlite3')
    good = [_project(tmp_path, f'p{i}', _image(salt=i + 1)) for i in range(3)]
    broken = tmp_path / 'broken.ecustudio'
    broken.write_text('{kein json')
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: warnings.append(a[2]))
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *a, **k: ([*map(str, good), str(broken)], ''))

    def library(dialog):
        next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Bestehende Projekte indexieren …').click()
        return 0
    monkeypatch.setattr(QDialog, 'exec', library)
    w.browse_projects()
    assert len(w.project_store.search()) == 3
    assert len(warnings) == 1 and 'broken.ecustudio' in warnings[0] and '1 Datei(en)' in warnings[0]

    w.load_state(_image(), [], [], '', None)
    w.update_local_suggestions()
    seen = {}

    def suggestions(dialog):
        choices = dialog.findChild(QComboBox)
        seen['items'] = [choices.itemText(i) for i in range(choices.count())]
        seen['labels'] = [label.text() for label in dialog.findChildren(QLabel)]
        return 0
    monkeypatch.setattr(QDialog, 'exec', suggestions)
    w.show_local_suggestions()
    assert seen['items'] == ['wahrscheinlich · Projekt · p0.ecustudio', 'wahrscheinlich · Projekt · p1.ecustudio',
                             'wahrscheinlich · Projekt · p2.ecustudio']
    assert any('Gleiche Hardware- und Softwarenummer' in text for text in seen['labels'])
    assert any('Nur eine identische Datei' in text for text in seen['labels'])
    w.saved_fingerprint = w.project_state()
    w.close()


def test_library_benchmark_runs_on_a_small_synthetic_index():
    from ecu_studio.tools.library_benchmark import run
    result = run(300, 30, 2)
    assert result['suggestions_known_ids']['results'] > 0 and result['suggestions_unknown_ids']['results'] == 0
    assert result['index']['per_project_batched_ms'] < result['index']['per_project_one_transaction_ms']
