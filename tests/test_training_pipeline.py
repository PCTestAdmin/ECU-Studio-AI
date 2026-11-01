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
    for fam, role, complete in (('A', 'training', True), ('B', 'training', True), ('C', 'training', True),
                                ('P', 'training', False), ('T', 'test', True)):
        for _ in range(120):
            y = int(rng.random() < .3)
            x = rng.normal(size=len(FEATURES)) + 1.5 * y
            rows.append({'family': fam, 'role': role, 'complete': complete, 'cls': 'pitch', 'y': y,
                         'x': x.round(4).tolist()})
    path = tmp_path / 'data.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    return path


def test_test_role_and_partial_references_are_not_trained(tmp_path):
    (X, y, fam), (Xt, yt, famt) = load(_rows(tmp_path))
    assert set(fam) == {'A', 'B', 'C'} and set(famt) == {'T'}
    (X, y, fam), _ = load(_rows(tmp_path), complete_only=False)
    assert 'P' in set(fam)


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
    with pytest.raises(SystemExit):
        main([str(data), '--roles', 'training,test'])
