import copy
import hashlib
import json
from pathlib import Path
import pytest

from ecu_studio.core.reference_manifest import load_manifest
from ecu_studio.tools import validation_report, benchmark_suite
from tests.test_benchmark_suite import _pair


def locked(tmp_path):
    pair = _pair(tmp_path, 'public-pair', 7)
    pair.update(software='synthetic-A', source='synthetic', license='CC0', data_kind='synthetic', group='group-A')
    for key, hash_key in (('bin', 'sha256'), ('reference', 'reference_sha256')):
        path = Path(pair[key]); pair[hash_key] = hashlib.sha256(path.read_bytes()).hexdigest()
        pair[key] = path.name
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'schema': 1, 'pairs': [pair]}))
    return path, pair


def test_locked_manifest_relative_paths_hashes_and_privacy(tmp_path):
    path, pair = locked(tmp_path)
    entries = load_manifest(path)
    assert Path(entries[0]['bin']).is_absolute()
    out, md = tmp_path / 'report.json', tmp_path / 'report.md'
    assert validation_report.main([str(path), '--out', str(out), '--markdown', str(md)]) == 0
    raw = out.read_text(encoding='utf-8')
    assert str(tmp_path) not in raw and '.bin' not in raw and pair['sha256'] in raw
    result = json.loads(raw)
    assert result['independent_pairs'] == 0 and result['synthetic_pairs'] == 1
    assert result['miss_analysis'][0]['reference_2d'] == 1
    assert validation_report.main([str(path), '--out', str(out), '--markdown', str(md), '--baseline', str(out)]) == 1


@pytest.mark.parametrize('change', [
    {'sha256': '0'*64}, {'reference_sha256': '0'*64}, {'software': ''}, {'name': 'C:/private/file'},
    {'complete': 'yes'}, {'role': 'other'}, {'source': '/home/private'}, {'data_kind': ''},
])
def test_manifest_refuses_unlocked_inputs(tmp_path, change):
    path, pair = locked(tmp_path); pair.update(change)
    path.write_text(json.dumps({'schema': 1, 'pairs': [pair]}))
    with pytest.raises(ValueError): load_manifest(path)


def test_leakage_and_real_data_in_ci_rejected(tmp_path, monkeypatch):
    path, pair = locked(tmp_path)
    path.write_text(json.dumps({'schema': 1, 'pairs': [pair, dict(pair, name='other', role='training')]}))
    with pytest.raises(ValueError, match='leakage'): load_manifest(path)
    path.write_text(json.dumps({'schema': 1, 'pairs': [dict(pair, data_kind='real')]}))
    monkeypatch.setenv('CI', 'true')
    with pytest.raises(ValueError, match='local'): load_manifest(path)


def test_output_cannot_overwrite_original_or_definition(tmp_path):
    path, pair = locked(tmp_path)
    original = (tmp_path / pair['bin']).read_bytes()
    assert validation_report.main([str(path), '--out', str(tmp_path / pair['bin']),
                                   '--markdown', str(tmp_path / 'report.md')]) == 1
    assert (tmp_path / pair['bin']).read_bytes() == original


def test_changed_reference_or_role_not_comparable():
    from tests.test_benchmark_suite import _row
    before = {'rows': [_row('pair', 1, 2, .5)]}
    for change in ({'reference_sha256': 'new'}, {'role': 'development'}, {'complete_reference': False}, {'family': 'other'}):
        after = copy.deepcopy(before); after['rows'][0].update(change)
        assert benchmark_suite.compare_runs(before, after)['pairs'][0]['verdict'] == 'nicht vergleichbar'


def test_near_identical_cross_role_groups_rejected_before_scan(tmp_path, monkeypatch):
    path, pair = locked(tmp_path)
    other = _pair(tmp_path, 'different-alias', 8)
    other.update({k: pair[k] for k in ('software', 'source', 'license', 'data_kind', 'complete')})
    other.update(role='development', group='separate-label')
    for key, digest in (('bin', 'sha256'), ('reference', 'reference_sha256')):
        other[digest] = hashlib.sha256(Path(other[key]).read_bytes()).hexdigest()
    path.write_text(json.dumps({'schema': 1, 'pairs': [pair, other]}))
    entries = load_manifest(path)
    monkeypatch.setattr(benchmark_suite, 'run', lambda *a, **k: pytest.fail('must refuse before scanning'))
    with pytest.raises(ValueError, match='Near-identical'): validation_report.run(entries)
