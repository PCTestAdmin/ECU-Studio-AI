import json
import numpy as np
import pytest
from ecu_studio.recognition.structure_model import ShapeModel,train_shape_model
from ecu_studio.recognition.families import require_family
from ecu_studio.recognition.safe_classifier import train_safe
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.core.model import BinaryImage


def make_realistic_db(tmp_path):
    # Reproducible tiny source-index fixture; cannot confer verified status.
    from ecu_studio.core.model import MapDefinition
    data=bytearray(0x80000)
    data[0x70040:0x70046]=b'430069'
    maps=[]
    for i in range(15):
        offset=0x72000+i*144
        for j in range(64):data[offset+j]=((j*(i+2)+j*j*3+i*7)%239)
        maps.append(MapDefinition('source_'+str(i),offset,8,8,'u8','big',source='xdf-preview'))
    im=BinaryImage(bytes(data));db=DefinitionCatalog(tmp_path/'db.sqlite')
    db.import_maps(im,maps,origin='MS4X sample',source_identity='gitblob:'+'a'*40)
    return db,im


def test_learned_pca_is_not_a_label(tmp_path):
    db,im=make_realistic_db(tmp_path)
    # Identify profile via stored synthetic software marker rather than pretending arbitrary bytes are firmware identity.
    import ecu_studio.recognition.structure_model as mod
    from ecu_studio.core.profiles import ECUProfile
    original=mod.identify_profile
    mod.identify_profile=lambda _:ECUProfile(family='Siemens MS43',software_version='430069')
    try:model=train_shape_model(db,im)
    finally:mod.identify_profile=original
    assert model.count>=12 and model.report['correct_map_type_claims']==0
    path=tmp_path/'shape.json';model.save(path)
    loaded=ShapeModel.load(path)
    surf=np.arange(64,dtype=float).reshape(8,8)
    assert loaded.similar(surf,family='Bosch MD1',software='430069')['status']=='abstain'
    assert loaded.similar(surf,family='Siemens MS43',software='XXXX')['status']=='abstain'
    prediction=loaded.similar(surf,family='Siemens MS43',software='430069')
    assert prediction['predicted_map_function'] is None and prediction['verified'] is False


def test_supervised_training_rejects_empty_and_wrong_families(tmp_path):
    db,_=make_realistic_db(tmp_path)
    with pytest.raises(ValueError,match='Firmwarestände'):
        train_safe(db,'Bosch MD1')
    assert require_family('Bosch MG1').name=='Bosch MG1'
    with pytest.raises(ValueError):require_family('Unknown universal decoder')


def test_corrupted_model_rejected(tmp_path):
    f=tmp_path/'model.json';f.write_text('{"format":1}')
    with pytest.raises(TypeError):ShapeModel.load(f)
