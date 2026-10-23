"""Project library: metadata, tags/comments, filters, migration from schema 1, large libraries."""
import sqlite3
import time
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition, save_project
from ecu_studio.core.project_store import META, ProjectStore
from ecu_studio.core.versioning import make_snapshot


def _project(tmp_path, name='EDC17 Kunde', epk=True):
    buf = bytearray(0x4000)
    if epk:
        buf[0x100:0x100 + 33] = b'33/1/EDC17_CP09/11/P_574//V8KB///'
    image = BinaryImage(bytes(buf))
    maps = [MapDefinition('KF_A', 0x1000, 4, 4, 'u8', source='a2l', verified=True),
            MapDefinition('KF_B', 0x1100, 4, 4, 'u8', source='a2l'),
            MapDefinition('Kandidat', 0x1200, 4, 4, 'u8', source='heuristic')]
    image.commit([(0x1001, 0, 7)], label='edit')
    path = tmp_path / f'{name}.ecustudio'
    save_project(str(path), image, maps, [], 'Notiz', [make_snapshot(image, 'v1')])
    return path


def test_index_reads_identity_counts_versions_and_sources(tmp_path):
    store = ProjectStore(tmp_path / 'lib.sqlite3')
    store.index(_project(tmp_path))
    (row,) = store.search()
    assert row['family'] == 'EDC17CP09' and row['maps'] == 3
    assert (row['verified'], row['unverified'], row['changed_maps'], row['versions']) == (1, 2, 1, 1)
    assert row['definition_sources'] == 'a2l' and row['app_version'] and row['created'] > 0
    assert store.search('edc17cp09') and store.families() == ['EDC17CP09']


def test_tags_and_comments_survive_reindexing_and_filter(tmp_path):
    store = ProjectStore(tmp_path / 'lib.sqlite3')
    a, b = _project(tmp_path, 'A'), _project(tmp_path, 'B', epk=False)
    store.index(a); store.index(b)
    store.annotate(a, ['Kunde X', ' stage-review ', ''], 'Prüfstand 12.10.')
    store.index(a)
    (row,) = store.search(tag='Kunde X')
    assert row['name'] == 'A' and row['tags'] == 'Kunde X,stage-review' and row['comment'] == 'Prüfstand 12.10.'
    assert [r['name'] for r in store.search('prüfstand')] == ['A']
    assert store.search(tag='Kunde') == []                          # whole tags only
    assert [r['name'] for r in store.search(family='EDC17CP09')] == ['A']
    with pytest.raises(ValueError):
        store.annotate(a, ['a,b' * 30])


OLD_SCHEMA = ('CREATE TABLE projects(path TEXT PRIMARY KEY, name TEXT NOT NULL, original_sha256 TEXT NOT NULL, '
              'bytes INTEGER NOT NULL, maps INTEGER NOT NULL, notes TEXT NOT NULL, search_text TEXT NOT NULL, '
              'modified REAL NOT NULL)')


def test_database_stays_usable_by_older_versions_and_old_rows_stay_visible(tmp_path):
    db = tmp_path / 'old.sqlite3'
    with sqlite3.connect(db) as c:
        c.execute(OLD_SCHEMA)
        c.execute("INSERT INTO projects VALUES('x.ecustudio','alt','00',16,2,'','alt',1.0)")
        c.execute('PRAGMA user_version=1')
    store = ProjectStore(db)
    (row,) = store.search('alt')
    assert row['name'] == 'alt' and row['family'] == '' and row['verified'] == 0 and row['tags'] == ''
    store.index(_project(tmp_path))
    with sqlite3.connect(db) as c:
        # What 1.16 checks and writes: schema 1 and the 8-column projects row.
        assert c.execute('PRAGMA user_version').fetchone()[0] == 1
        assert [r[1] for r in c.execute('PRAGMA table_info(projects)')] == [
            'path', 'name', 'original_sha256', 'bytes', 'maps', 'notes', 'search_text', 'modified']
        c.execute("INSERT INTO projects VALUES('y.ecustudio','von 1.16','00',16,2,'','von',2.0)")
    assert [r['name'] for r in store.search('von')] == ['von 1.16']
    with sqlite3.connect(db) as c:
        c.execute('PRAGMA user_version=2')
    with pytest.raises(ValueError, match='neueren Version'):
        ProjectStore(db)


@pytest.mark.parametrize('count', [1000, 10000])
def test_large_libraries_stay_fast(tmp_path, count):
    store = ProjectStore(tmp_path / 'big.sqlite3')
    with store.connect() as c:
        c.executemany('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?)',
                      [(f'p{i}.ecustudio', f'Projekt {i}', f'{i:064x}', 4 << 20, 900, '', f'projekt {i} kf_{i % 97}',
                        float(i)) for i in range(count)])
        c.executemany(f'INSERT INTO project_meta(path,{",".join(META)}) VALUES({",".join("?" * (len(META) + 1))})',
                      [(f'p{i}.ecustudio', ('EDC17CP09', 'MSD80', 'ME7.5')[i % 3], '', '', 'a2l', '1.17.0', float(i),
                        10, 890, i % 5, i % 4) for i in range(count)])
    begin = time.perf_counter()
    everything = store.search(limit=500)
    filtered = store.search('kf_13', family='MSD80')
    elapsed = time.perf_counter() - begin
    assert len(everything) == 500 and everything[0]['name'] == f'Projekt {count - 1}'
    assert filtered and all(r['family'] == 'MSD80' for r in filtered)
    assert elapsed < 1.0, elapsed


def test_library_dialog_lists_filters_and_annotates(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QComboBox, QDialog, QInputDialog, QPushButton, QTableView
    from tests.test_ui_filters_banner import _window
    app, w = _window(tmp_path, monkeypatch)
    w.project_store = ProjectStore(tmp_path / 'lib.sqlite3')
    w.project_store.index(_project(tmp_path, 'A'))
    w.project_store.index(_project(tmp_path, 'B', epk=False))
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('Kunde X', True))
    monkeypatch.setattr(QInputDialog, 'getMultiLineText', lambda *a, **k: ('geprüft', True))
    seen = {}

    def run(dialog):
        view = dialog.findChild(QTableView)
        family = dialog.findChild(QComboBox)
        seen['all'] = view.model().rowCount()
        family.setCurrentIndex(family.findData('EDC17CP09'))
        seen['family'] = view.model().rowCount()
        view.selectRow(0)
        next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Tags / Kommentar …').click()
        seen['tags'] = view.model().rows[0][8]
        return 0
    monkeypatch.setattr(QDialog, 'exec', run)
    w.browse_projects()
    assert seen == {'all': 2, 'family': 1, 'tags': 'Kunde X'}
    w.close()
