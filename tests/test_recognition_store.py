from pathlib import Path
import json
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.transfer import match_verified
from ecu_studio.recognition.ml import features,train,Model


def make_ms43(p, map_offset, values):
    buf=bytearray(b'\x00'*(512*1024))
    buf[0x70008:0x7000e]=b'430069'
    for i,val in enumerate(np.asarray(values).ravel()):
        buf[map_offset+2*i:map_offset+2*i+2]=int(val).to_bytes(2,'big')
    p.write_bytes(buf)
    return BinaryImage.from_file(str(p))


def test_store_index_verify_exact(tmp_path):
    img=make_ms43(tmp_path/'a.bin',0x70600,np.arange(64).reshape(8,8)*7+800)
    store=DefinitionCatalog(tmp_path/'index.sqlite3')
    m=MapDefinition(name='Zündwinkel Muster',offset=0x70600,rows=8,cols=8,
                    kind='Zündwinkel',source='xdf')
    summary=store.import_maps(img,[m],origin='Manual XDF import')
    assert summary['indexed']==1
    assert len(store.firmware_maps(img))==1
    assert store.stats()['verified_maps']==0
    rec=store.records()[0]
    with pytest.raises(ValueError,match='ausdrückliche'):
        store.verify(rec['id'],img)
    store.verify(rec['id'],img,confirm=True)
    assert store.stats()['verified_maps']==1
    refs=store.verified_references(family='Siemens MS43')
    assert refs[0].raw[0][0]==800
    assert store.firmware_maps(img)[0].verified
    changed=BinaryImage(img.original[:-1]+b'\x01')
    assert store.firmware_maps(changed)==[]


def test_cross_firmware_shift_and_refusal(tmp_path):
    base=np.rint(900+np.outer(np.arange(8)**1.25, np.arange(8)**0.8)*17).astype(int)
    a=make_ms43(tmp_path/'a.bin',0x70300,base)
    store=DefinitionCatalog(tmp_path/'db.sqlite')
    map_=MapDefinition(name='Reference torque',offset=0x70300,rows=8,cols=8,
                       kind='Drehmoment',source='xdf')
    store.import_maps(a,[map_],origin='reviewed')
    store.verify(store.records()[0]['id'],a,confirm=True)
    shifted=make_ms43(tmp_path/'b.bin',0x71A00,base+4)
    matches=match_verified(shifted,store,min_score=.91)
    assert matches
    best=matches[0]
    assert best.proposed.offset==0x71A00
    assert best.proposed.kind=='Drehmoment'
    assert not best.proposed.verified
    assert best.proposed.source=='transfer-proposed'
    assert 'NICHT' in best.evidence


def test_transfer_no_family_or_verified(tmp_path):
    store=DefinitionCatalog(tmp_path/'db.sqlite')
    no_profile=BinaryImage(bytes(range(256))*8)
    assert match_verified(no_profile,store)==[]
    img=make_ms43(tmp_path/'a.bin',0x70300,np.arange(64).reshape(8,8)*8)
    m=MapDefinition(name='Map',offset=0x70300,rows=8,cols=8,kind='Zündung',source='xdf')
    store.import_maps(img,[m],origin='XDF')
    changed=make_ms43(tmp_path/'b.bin',0x70400,np.arange(64).reshape(8,8)*8)
    assert match_verified(changed,store)==[]


def test_ml_training_abstention_and_safe_json(tmp_path):
    store=DefinitionCatalog(tmp_path/'ml.db')
    for firmware in range(4):
        blocks=[]
        for clazz in range(2):
            for sample in range(7):
                yy,xx=np.mgrid[:8,:8]
                if clazz==0:
                    arr=np.rint(200+xx**2*(10+firmware)+yy*sample*1.3).astype(int)
                else:
                    arr=np.rint(200+yy**2*(14+firmware)+xx*sample*1.1).astype(int)
                blocks.append((clazz,arr))
        buf=bytearray(8192)
        maps=[]
        for i,(clazz,arr) in enumerate(blocks):
            for n,v in enumerate(arr.flat):
                off=i*128+2*n
                buf[off:off+2]=int(v).to_bytes(2,'big')
            maps.append(MapDefinition(name=f'map_{i}',kind='ignition' if clazz==0 else 'torque',
                                      offset=i*128,rows=8,cols=8,source='xdf'))
        buf[-1]=firmware+1
        image=BinaryImage(bytes(buf))
        store.import_maps(image,maps,origin='verified training samples')
        for record in store.records(firmware_sha=image.digest):
            store.verify(record['id'],image,confirm=True)
    model=train(store)
    assert set(model.labels)=={'ignition','torque'}
    assert model.metrics['holdout_samples']>0
    assert set(model.metrics['recall_per_label'])=={'ignition','torque'}
    path=tmp_path/'semantic_model.json'
    model.save(path)
    loaded=Model.load(path)
    assert loaded.training_hash==model.training_hash
    pred=loaded.predict((np.arange(8)[:,None]*np.ones((1,8))**2).tolist())
    assert 'status' in pred
    assert loaded.predict(np.ones((8,8)))['note'].startswith('Modellscore')


def test_ml_refuses_insufficient_training(tmp_path):
    store=DefinitionCatalog(tmp_path/'empty.db')
    with pytest.raises(ValueError,match='Mindestens zwei'):
        train(store)
    assert len(features(np.arange(16).reshape(4,4)))==80


def test_batch_index_real_xdf_fixture(tmp_path):
    from ecu_studio.tools.recognition_v13 import execute
    from types import SimpleNamespace
    import shutil
    source=Path(__file__).parents[1]/'examples'/'demo'/'xdf_stride_demo.xdf'
    binary=Path(__file__).parents[1]/'examples'/'demo'/'xdf_stride_demo.bin'
    shutil.copy2(source,tmp_path/'a.xdf')
    shutil.copy2(binary,tmp_path/'a.bin')
    (tmp_path/'manifest.json').write_text(json.dumps({'pairs':[
        {'bin':'a.bin','xdf':'a.xdf'},
        {'bin':'a.bin','xdf':'missing.xdf'}]}),encoding='utf8')
    args=SimpleNamespace(db=str(tmp_path/'db.sqlite'),manifest=str(tmp_path/'manifest.json'),
                         catalog='batch',bin=None,xdf=None,model=None,max_references=3,max_candidates=20)
    output=execute(args)
    assert output['successful']==1
    assert output['indexed']>=1
    assert output['pairs']==2
    store=DefinitionCatalog(tmp_path/'db.sqlite')
    assert store.stats()['verified_maps']==0
    assert len(store.records())>=1


def test_verified_invalidated_on_definition_change(tmp_path):
    image=make_ms43(tmp_path/'a.bin',0x70300,np.arange(64).reshape(8,8)*8+300)
    store=DefinitionCatalog(tmp_path/'db.sqlite')
    m=MapDefinition(name='Test map',kind='Zündung',offset=0x70300,rows=8,cols=8,source='xdf')
    store.import_maps(image,[m],origin='Manual')
    store.verify(store.records()[0]['id'],image,confirm=True)
    assert store.stats()['verified_maps']==1
    m.factor=2.0
    store.import_maps(image,[m],origin='Updated map metadata')
    assert store.stats()['verified_maps']==0
    assert not store.verified_references()


def test_ambiguous_transfer_never_unique(tmp_path):
    base=np.rint(350+np.outer(np.arange(8)**1.4,np.arange(8)**0.7)*17).astype(int)
    image=make_ms43(tmp_path/'ref.bin',0x70300,base)
    store=DefinitionCatalog(tmp_path/'db.sqlite')
    m=MapDefinition(name='Verified test',kind='torque',offset=0x70300,rows=8,cols=8,source='xdf')
    store.import_maps(image,[m],origin='Manual')
    store.verify(store.records()[0]['id'],image,confirm=True)
    buf=bytearray(make_ms43(tmp_path/'target.bin',0x71500,base).original)
    for i,v in enumerate(base.flat):
        pos=0x72800+i*2
        buf[pos:pos+2]=int(v).to_bytes(2,'big')
    matches=match_verified(BinaryImage(buf),store)
    assert matches
    assert matches[0].runner_up>=.99
    assert not matches[0].uniquely_located


def test_uploaded_ecu_examples_are_not_falsely_labeled(tmp_path):
    store=DefinitionCatalog(tmp_path/'db.sqlite')
    for location in list(Path('/mnt/data').glob('MS43_*430069_512KB.bin')) + list(Path('/mnt/data').glob('GS20_*64KB.bin')):
        if not location.exists():
            continue
        image=BinaryImage.from_file(str(location))
        assert store.firmware_maps(image)==[]
        assert match_verified(image,store)==[]
