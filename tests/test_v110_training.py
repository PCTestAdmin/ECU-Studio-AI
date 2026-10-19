"""Regression and safety checks for v1.10 trained synthetic-domain model."""
import json
from pathlib import Path
import numpy as np
import pytest
from ecu_studio.recognition.structure_rejector import (
    StructureRejector, installed_rejector, structural_features, FEATURES)
from ecu_studio.recognition.train_structure_rejector import make_set, train, SEED
from ecu_studio.recognition.ml import Model, features as semantic_features
from ecu_studio.core.precision import rank_candidates
from ecu_studio.core.model import BinaryImage,MapDefinition


def test_model_is_trained_portable_and_does_not_claim_verified_semantics():
    obj=installed_rejector()
    assert obj is not None and len(obj.trees)==24
    assert obj.metrics['train_samples']==4000
    assert obj.metrics['real_heldout_firmwares']==0
    assert not obj.metrics['semantic_model_retrained']
    assert obj.metrics['verified_map_type_labels']==0
    assert len(structural_features(np.arange(36).reshape(6,6)))==FEATURES
    result=obj.assess((100+np.outer(np.arange(8)**2,np.arange(8)**.6)*9).astype(int))
    assert result['status']=='synthetic-structure-only'
    assert 'KEIN Nachweis' in result['note']
    assert not any(k in result for k in ('label','kind','verified','map_name'))


def test_forest_json_and_tree_scorer_roundtrip(tmp_path):
    obj=installed_rejector()
    path=tmp_path/'model.json'
    obj.save(path)
    loaded=StructureRejector.load(path)
    y,x=np.mgrid[:12,:12]
    matrix=300+3*x*x+9*y*y+7*np.sin(x/3)
    assert loaded.assess(matrix)==obj.assess(matrix)
    damaged=json.loads(path.read_text())
    damaged['trees'][0]['left'][0]=0
    path.write_text(json.dumps(damaged))
    with pytest.raises(ValueError,match='Baum'):
        StructureRejector.load(path)


def test_new_model_synthetic_holdout_and_negative_screen():
    """Synthetic regression; deliberately NOT a real ECU accuracy claim."""
    from ecu_studio.recognition.train_structure_rejector import surface
    rng=np.random.default_rng(541821)
    obj=installed_rejector()
    p=[obj.assess(surface(rng,True,6))['plausible_synthetic_geometry'] for _ in range(50)]
    n=[obj.assess(surface(rng,False,14))['plausible_synthetic_geometry'] for _ in range(50)]
    assert sum(p)>=45
    assert sum(n)<=4


def test_existing_semantic_predict_uses_only_once_standardized_ood():
    yy,xx=np.mgrid[:10,:10]
    raw=(230+xx**2*5+yy**2*17).astype(float)
    f=semantic_features(raw)
    model=Model(labels=['A','B'],mean=f.tolist(),scale=[.01]*80,
                weights=[[0.,0.]]*80,bias=[12.,-8.],
                metrics={'release_gate':'test','heldout_macro_recall':1.,
                    'precision_per_label':{'A':1.,'B':1.},
                    'recall_per_label':{'A':1.,'B':1.}},
                training_hash='test',family='Siemens MS43')
    prediction=model.predict(raw,family='Siemens MS43')
    assert prediction['status']=='ml-proposed'
    raw_changed=raw+np.arange(10)[None,:]**4*100
    assert model.predict(raw_changed,family='Siemens MS43')['status']=='abstain'
    assert model.predict(raw,family='Bosch MG1')['status']=='abstain'


def test_ranker_keeps_sample_maps_and_does_not_invent_type():
    here=Path(__file__).parents[1]
    raw=(here/'examples/demo_synthetic.bin').read_bytes()
    # sample map coordinates known from preexisting regression test
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    out=scan_calibration_candidates(BinaryImage(raw))
    assert {0x1000,0x2000}.issubset({m.offset for m in out})
    assert all(m.kind=='Unbekannt' and not m.verified for m in out)
    assert any('Synthetisch trainierter KI-Strukturwert' in m.notes for m in out)


def test_trainer_is_reproducible_independent_split():
    a=train(seed=442, samples_per_class=90, algorithm='linear',epochs=50)
    b=train(seed=442, samples_per_class=90, algorithm='linear',epochs=50)
    assert a.training_hash==b.training_hash
    assert np.allclose(a.weights,b.weights)
    assert a.metrics['real_heldout_firmwares']==0
    assert a.metrics['holdout_samples']==1000
