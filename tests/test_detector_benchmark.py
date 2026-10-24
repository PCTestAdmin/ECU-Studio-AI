import hashlib
import json
import tracemalloc
from pathlib import Path
import pytest
from ecu_studio.core.model import MapDefinition
from ecu_studio.core.reference_manifest import load_manifest
from ecu_studio.core.definitions import export_definitions
from ecu_studio.tools import benchmark_suite, detector_benchmark
from tests.test_experimental_detectors import pointer_fixture


def manifest(tmp_path):
    image, maps, _ = pointer_fixture()
    binary = tmp_path/'private-original.bin'; binary.write_bytes(image.original)
    ref = tmp_path/'private-reference.csv'; export_definitions(ref, maps)
    pair = {'name': 'synthetic-pointer', 'software': 'synthetic-v1', 'family': 'Synthetic direct pointers',
            'role': 'test', 'data_kind': 'synthetic', 'group': 'synthetic-A', 'complete': True,
            'source': 'own synthetic fixture', 'license': 'CC0 test generation',
            'bin': binary.name, 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            'reference': ref.name, 'reference_sha256': hashlib.sha256(ref.read_bytes()).hexdigest()}
    path = tmp_path/'manifest.json'; path.write_text(json.dumps({'schema': 1, 'pairs': [pair]}))
    return path


def test_three_modes_same_locked_inputs_and_no_false_independence(tmp_path):
    entries = load_manifest(manifest(tmp_path))
    result = detector_benchmark.run(entries, algorithms=['pointer-chain'], memory=True)
    exp = result['experiments'][0]
    rows = [result['baseline']['rows'][0], exp['isolated']['rows'][0], exp['combined']['rows'][0]]
    assert {r['sha256'] for r in rows} == {entries[0]['sha256']}
    assert {r['reference_sha256'] for r in rows} == {entries[0]['reference_sha256']}
    assert rows[1]['exact_2d'] == 3 and rows[1]['peak_mb'] is not None
    assert exp['comparison']['pairs'][0]['lost_exact_layouts'] == []
    assert exp['comparison']['pairs'][0]['production_verdict'] == 'not established by synthetic data'
    assert exp['isolated']['independent_pairs'] == 0 and not exp['algorithm']['production_enabled']
    assert 'private-original' not in json.dumps(result) and not tracemalloc.is_tracing()


def test_cli_reports_private_paths_neither_in_results_nor_errors(tmp_path, capsys):
    path = manifest(tmp_path)
    out, md = tmp_path/'report.json', tmp_path/'report.md'
    assert detector_benchmark.main([str(path), '--out', str(out), '--markdown', str(md), '--algorithm', 'pointer-chain']) == 0
    assert out.exists() and 'Experiment only' in md.read_text(encoding='utf-8')
    assert str(tmp_path) not in out.read_text(encoding='utf-8')
    original = path.read_bytes()
    assert detector_benchmark.main([str(path), '--out', str(path), '--markdown', str(md)]) == 1
    assert path.read_bytes() == original
    assert str(tmp_path) not in capsys.readouterr().out


def test_reference_never_passed_to_detector_mutation_or_verification_refused(tmp_path):
    entry = load_manifest(manifest(tmp_path))[0]
    def bad(image):
        assert image.path is None
        image._patches[0] = image.original[0] ^ 255
        return []
    with pytest.raises(ValueError, match='modify'): benchmark_suite.run_pair(entry, detector=bad)
    with pytest.raises(ValueError, match='verify'):
        benchmark_suite.run_pair(entry, detector=lambda image: [MapDefinition('bad', 0, 4, 4, verified=True)])


def test_nondeterministic_detector_rejected_and_tracer_stopped(tmp_path):
    entry = load_manifest(manifest(tmp_path))[0]; calls = []
    def unstable(image):
        calls.append(1)
        return [MapDefinition(str(len(calls)), 0x1000, 4, 4)]
    with pytest.raises(ValueError, match='changed'): benchmark_suite.run_pair(entry, memory=True, detector=unstable)
    assert not tracemalloc.is_tracing()


def test_invalid_registry_selection_refused_before_running():
    for names in ([], ['unknown'], ['pointer-chain', 'pointer-chain']):
        with pytest.raises(ValueError): detector_benchmark.run([], algorithms=names)
