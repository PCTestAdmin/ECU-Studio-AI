"""Benchmark pre-check (quality phase 6): a run refuses to measure code it was not asked to measure."""
from pathlib import Path

import pytest

from ecu_studio.tools import run_provenance


def test_record_names_the_imported_code_and_switches():
    rec = run_provenance.collect('development')
    assert Path(rec['import_path']) == run_provenance.package_root()
    assert rec['data_role'] == 'development'
    assert rec['benchmark_version'] == run_provenance.BENCHMARK_VERSION
    assert 'tricore_refs.DOUBLE_GAP_WEAK' in rec['switches']
    assert len(rec['source_digest']) == 64


def test_wrong_import_path_aborts(tmp_path):
    with pytest.raises(SystemExit, match='importiert'):
        run_provenance.require(tmp_path, allow_dirty=True)


def test_right_import_path_passes_with_src_or_package_dir():
    root = run_provenance.package_root()
    assert run_provenance.require(root.parent, allow_dirty=True)['import_path'] == str(root)
    assert run_provenance.require(root, allow_dirty=True)['import_path'] == str(root)


def test_wrong_commit_aborts(monkeypatch):
    monkeypatch.setattr(run_provenance, '_git', lambda root, *a: 'a' * 40 if a[0] == 'rev-parse' else '')
    with pytest.raises(SystemExit, match='statt'):
        run_provenance.require(expected_commit='b' * 7)
    assert run_provenance.require(expected_commit='a' * 7)['git_commit'] == 'a' * 40


def test_undeterminable_commit_aborts(monkeypatch):
    monkeypatch.setattr(run_provenance, '_git', lambda root, *a: '')
    with pytest.raises(SystemExit, match='nicht bestimmbar'):
        run_provenance.require(expected_commit='abc1234')


def test_uncommitted_changes_abort_unless_allowed(monkeypatch):
    monkeypatch.setattr(run_provenance, '_git',
                        lambda root, *a: ' M core/model.py' if a[0] == 'status' else 'c' * 40)
    with pytest.raises(SystemExit, match='nicht committete'):
        run_provenance.require()
    assert run_provenance.require(allow_dirty=True)['git_dirty'] is True


def test_source_change_during_run_is_detected(tmp_path):
    pkg = tmp_path / 'ecu_studio'
    pkg.mkdir()
    (pkg / 'a.py').write_text('x = 1\n')
    rec = {'import_path': str(pkg), 'source_digest': run_provenance.source_digest(pkg)}
    assert run_provenance.unchanged(rec)
    (pkg / 'a.py').write_text('x = 2\n')
    assert not run_provenance.unchanged(rec)


def test_comparability_reports_switches_role_and_version():
    a = {'benchmark_version': 1, 'data_role': 'development', 'switches': {'m.A': True, 'm.B': False}}
    assert run_provenance.comparable(a, dict(a)) == []
    b = {'benchmark_version': 2, 'data_role': 'holdout', 'switches': {'m.A': False, 'm.B': False},
         'source_changed': True}
    why = run_provenance.comparable(a, b)
    assert any('Benchmark-Versionen' in w for w in why)
    assert any('Datenrollen' in w for w in why)
    assert any('m.A' in w and 'm.B' not in w for w in why)
    assert any('während des Laufs' in w for w in why)


def test_benchmark_suite_aborts_before_scanning_on_wrong_path(tmp_path, monkeypatch):
    from ecu_studio.tools import benchmark_suite
    called = []
    monkeypatch.setattr(benchmark_suite, 'run', lambda *a, **k: called.append(1))
    manifest = tmp_path / 'm.json'
    manifest.write_text('[]')
    with pytest.raises(SystemExit, match='Vorprüfung'):
        benchmark_suite.main([str(manifest), '--expect-src', str(tmp_path), '--allow-dirty'])
    assert not called
