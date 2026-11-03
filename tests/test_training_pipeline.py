"""Reproducible scorer training: role split, family-out evaluation, replacement gate, log."""
import json
import numpy as np
import pytest
from ecu_studio.core.candidate_features import FEATURES
from ecu_studio.core.candidate_model import DATA as MODEL_PATH
from ecu_studio.tools.train_candidate_model import gate, load, main


def _rows(tmp_path, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for fam, role, complete, cleared in (('A', 'training', True, True), ('B', 'training', True, True),
                                         ('C', 'training', True, True), ('P', 'training', False, True),
                                         ('D', 'development', True, False), ('T', 'test', True, False)):
        for _ in range(120):
            y = int(rng.random() < .3)
            x = rng.normal(size=len(FEATURES)) + 1.5 * y
            rows.append({'family': fam, 'role': role, 'complete': complete, 'training_allowed': cleared,
                         'cls': 'pitch', 'y': y, 'x': x.round(4).tolist()})
    path = tmp_path / 'data.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    return path


def test_test_role_and_partial_references_are_not_trained(tmp_path):
    (X, y, fam), (Xt, yt, famt) = load(_rows(tmp_path))
    assert set(fam) == {'A', 'B', 'C'} and set(famt) == {'T'}
    (X, y, fam), _ = load(_rows(tmp_path), complete_only=False)
    assert 'P' in set(fam)
    (X, y, fam), _ = load(_rows(tmp_path), roles=('training', 'development'))
    assert 'D' not in set(fam)                    # development data without clearance is never fitted


def test_gate_needs_a_clear_gain_in_every_family():
    def fam(new, old, pn=.5, po=.5):
        return {'new': {'auc': new, 'precision_at_recall_80': pn}, 'shipped': {'auc': old, 'precision_at_recall_80': po}}
    assert gate({'A': fam(.9, .8), 'B': fam(.9, .8)})[0]
    assert not gate({'A': fam(.805, .8), 'B': fam(.805, .8)})[0]                 # gain below GATE_AUC
    ok, reason = gate({'A': fam(.95, .8, pn=.3, po=.5), 'B': fam(.95, .8)})
    assert not ok and 'A' in reason                                           # one family worse
    assert not gate({'A': fam(.9, .8)})[0]                                     # one family is no comparison


def test_training_run_is_logged_and_never_replaces_the_shipped_model_by_itself(tmp_path):
    pytest.importorskip('sklearn')
    shipped = MODEL_PATH.read_bytes()
    data = _rows(tmp_path)
    main([str(data), '--out', str(tmp_path / 'm.json'), '--log', str(tmp_path / 'log.json'), '--seed', '7'])
    assert MODEL_PATH.read_bytes() == shipped
    log = json.loads((tmp_path / 'log.json').read_text(encoding='utf-8'))
    assert log['seed'] == 7 and set(log['families_out']) == {'A', 'B', 'C'} and set(log['blind_test']) == {'T'}
    assert log['promoted'] is False and len(log['data_sha256']) == 64
    model = json.loads((tmp_path / 'm.json').read_text(encoding='utf-8'))
    assert model['features'] == list(FEATURES) and model['firmware_bytes_included'] is False
    assert model['training_data_cleared'] is True
    with pytest.raises(SystemExit):
        main([str(data), '--roles', 'training,test'])


def test_training_pairs_need_an_explicit_clearance():
    """Regression 1.19 QA: a BIN cleared only for regression (MS42 provenance) was used as training data."""
    from ecu_studio.tools.build_candidate_dataset import check_manifest
    check_manifest([{'name': 'a', 'role': 'training', 'training_allowed': True},
                    {'name': 'b', 'role': 'development'}, {'name': 'c', 'role': 'test'}])
    with pytest.raises(ValueError, match='MS42'):
        check_manifest([{'name': 'MS42', 'role': 'training', 'license': 'XDF GPL-3.0'}])
    with pytest.raises(ValueError):
        check_manifest([{'name': 'x', 'role': 'training', 'training_allowed': 'yes'}])


def test_only_a_model_with_cleared_training_data_is_applied(tmp_path, monkeypatch):
    """1.19: the model shipped since 1.15.0 (MS42 "not training", undocumented sources) is kept but not applied."""
    from ecu_studio.core import candidate_model
    shipped = candidate_model.read_model()
    assert shipped is not None and shipped.get('training_data_cleared') is not True
    candidate_model.load_model.cache_clear()
    assert candidate_model.load_model() is None
    assert candidate_model.model_status() == candidate_model.NOT_CLEARED
    cleared = tmp_path / 'cleared.json'
    cleared.write_text(json.dumps(dict(shipped, training_data_cleared=True, trained_on='2026-11-03')), encoding='utf-8')
    monkeypatch.setattr(candidate_model, 'DATA', cleared)
    candidate_model.load_model.cache_clear()
    try:
        assert candidate_model.load_model() is not None and 'aktiv' in candidate_model.model_status()
    finally:
        candidate_model.load_model.cache_clear()


def test_scan_without_cleared_model_keeps_data_pattern_finds_and_reports_why():
    from ecu_studio.core.candidate_model import NOT_CLEARED
    from ecu_studio.core.model import BinaryImage
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    rng = np.random.default_rng(5)
    data = bytearray(rng.integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    table = np.array([[40 + 7 * r + 3 * c for c in range(12)] for r in range(10)], np.uint8)
    data[0x1000:0x1000 + table.size] = table.tobytes()
    report = {}
    found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False, diagnostics=report)
    assert report['candidate_model'] == NOT_CLEARED and 'model_dropped' not in report
    assert not any('Lernmodell' in m.notes for m in found)
