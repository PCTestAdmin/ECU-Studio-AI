"""Independent safety/regression checks for v1.6 precision and source discovery."""
import json
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.precision import surface_evidence, rank_candidates
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.source_registry import discovery_sources, BRANDS
from ecu_studio.recognition.ml import Model


def test_structured_surface_beats_random_bytes():
    y,x=np.mgrid[:16,:16]
    surface=500+17*y+3*x+np.rint(4*np.sin(x/4)).astype(int)
    random=np.random.default_rng(9872).integers(0,65536,(16,16))
    assert surface_evidence(surface)['valid']
    assert not surface_evidence(random)['valid']
    assert surface_evidence(surface)['score']>surface_evidence(random)['score']
    assert not surface_evidence(np.ones((16,16)))['valid']


def test_precision_ranking_no_semantic_claim_and_overlap():
    y,x=np.mgrid[:16,:16]
    raw=bytearray(4096)
    values=(400+12*y+7*x).astype(int)
    for n,v in enumerate(values.flat):raw[512+2*n:514+2*n]=int(v).to_bytes(2,'big')
    img=BinaryImage(bytes(raw))
    a=MapDefinition('Candidate A',512,16,16,'u16','big',kind='Boost',source='heuristic',confidence=.40)
    b=MapDefinition('Candidate B',512,16,16,'u16','big',kind='AGR',source='heuristic',confidence=.30)
    got=rank_candidates(img,[a,b])
    assert len(got)==1
    assert got[0].offset==512 and got[0].kind=='Unbekannt'
    assert not got[0].verified and got[0].type_score==0.
    assert 'KEIN bestätigter Kennfeldtyp' in got[0].notes


def test_source_registry_has_explicit_nontraining_records(tmp_path):
    db=DefinitionCatalog(tmp_path/'test.db')
    sources=discovery_sources(db)
    assert len(sources)>=7
    assert set(BRANDS)=={r['brand'] for r in sources}
    assert all(s['training_approved']==0 for s in sources)
    assert all(s['status']!='verified' for s in sources)
    assert db.stats()['verified_maps']==0
    assert any(s['git_blob_sha1'] for s in discovery_sources(db,'Audi'))
    assert any(s['status']=='awaiting_verified_source' for s in discovery_sources(db,'Mercedes-Benz'))
    assert all(s['format'].lower().find('bin')<0 for s in sources if s['status']=='reference_only')


def test_model_legacy_family_scope_rejected_without_surface_access():
    model=Model(labels=['A','B'], mean=[0.]*80,scale=[1.]*80,
                weights=[[0.,0.]]*80,bias=[0.,0.],metrics={'heldout_macro_recall':1.},training_hash='x')
    assert model.predict(np.zeros((8,8)),family='Bosch MG1')['status']=='abstain'
    model.family='Siemens MS43'
    assert model.predict(np.zeros((8,8)),family='Bosch MG1')['status']=='abstain'
    assert model.predict(np.ones((8,8)),family='Siemens MS43')['status']=='abstain'


def test_existing_ms43_shape_model_abstains_on_synthetic_planes():
    from pathlib import Path
    from ecu_studio.recognition.structure_model import ShapeModel
    model=ShapeModel.load(Path(__file__).parents[1]/'src/ecu_studio/recognition/data/ms43_430069_structure_model.json')
    yy,xx=np.mgrid[:16,:16]
    for fake in (xx*100+yy*20, np.ones((16,16))*1000):
        result=model.similar(fake,family='Siemens MS43',software='430069')
        assert result['status']=='abstain'
        assert result['predicted_map_function'] is None


def test_bundled_two_known_synthetic_maps_are_kept_and_noise_is_not_promoted():
    from pathlib import Path
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    path=Path(__file__).parents[1]/'examples/demo/demo_synthetic.bin'
    image=BinaryImage(path.read_bytes())
    candidates=scan_calibration_candidates(image)
    assert {0x1000,0x2000}.issubset({m.offset for m in candidates})
    assert all(m.kind=='Unbekannt' and not m.verified for m in candidates)
    noise=np.random.default_rng(121).integers(0,256,32*1024,dtype=np.uint8).tobytes()
    assert scan_calibration_candidates(BinaryImage(noise))==[]
