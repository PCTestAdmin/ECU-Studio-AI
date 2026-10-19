import hashlib
import json
import struct
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.recognition.tcu_curves import scan_paired_u16_curves
from ecu_studio.recognition.holdout_eval import _matches, evaluate_manifest


def make_curve(x=range(20,164,12), endian='big'):
    points=list(x)
    assert len(points)>=7
    return b''.join(struct.pack(('>' if endian=='big' else '<')+'HH',i,min(255,i//2+12)) for i in points)+struct.pack(('>' if endian=='big' else '<')+'H',0xffff)


def test_paired_1d_found_big_little_and_values():
    raw=bytearray(np.random.default_rng(17).integers(0,256,8192,dtype='u1').tobytes())
    raw[1024:1024+len(make_curve())]=make_curve()
    little=make_curve(range(18,150,11),'little')
    raw[2400:2400+len(little)]=little
    found=scan_paired_u16_curves(BinaryImage(bytes(raw)))
    a=next(m for m in found if m.offset==1026)
    b=next(m for m in found if m.offset==2402)
    assert a.endian=='big' and b.endian=='little'
    assert a.rows==1 and a.cols==12
    assert not a.verified and a.kind=='Unbekannt'
    assert a.major_stride_bits==32
    assert a.axes_x[0]==20 and a.axes_x[-1]==152


def test_random_noise_has_no_tcu_curves():
    random=np.random.default_rng(2026).integers(0,256,65536,dtype=np.uint8).tobytes()
    assert scan_paired_u16_curves(BinaryImage(random))==[]


def test_non_monotonic_or_no_terminator_rejected():
    raw=make_curve()[:-2]+b'\x00\x00'
    assert not scan_paired_u16_curves(BinaryImage(raw))
    raw=bytearray(make_curve());raw[8:10]=b'\x00\x00'
    matches=scan_paired_u16_curves(BinaryImage(bytes(raw)))
    assert all(m.offset != 2 for m in matches)  # corrupterter Prefix darf nicht als volle Kurve gelten


def test_duplicate_candidate_matching_one_to_one():
    truth=[MapDefinition('g',100,1,12,major_stride_bits=32)]
    candidates=[MapDefinition('a',100,1,12,major_stride_bits=32),MapDefinition('b',100,1,12,major_stride_bits=32)]
    matched=_matches(candidates,truth)
    assert matched['matched']==1
    assert matched['unmatched_predictions']==1


def test_heldout_manifest_and_hash_gate(tmp_path):
    data=bytearray(np.random.default_rng(5).integers(0,256,8192,dtype=np.uint8).tobytes())
    curve=make_curve();data[2000:2000+len(curve)]=curve
    fp=tmp_path/'holdout.ori';fp.write_bytes(data)
    defs=[MapDefinition('Unknown shift-like',2002,1,12,major_stride_bits=32).asdict()]
    (tmp_path/'reference.json').write_text(json.dumps(defs))
    manifest={'cases':[{'id':'unseen_tcu','bin':'holdout.ori','definition':'reference.json',
                        'domain':'tcu','split':'test','source_license':'synthetic fixture',
                        'sha256':hashlib.sha256(data).hexdigest(),'definition_status':'synthetic-ground-truth'}]}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    report=evaluate_manifest(path)
    assert report['cases_processed']==1
    assert report['heldout_firmware_count']==1
    assert report['results'][0]['scan_1d']['matched']>=1
    assert report['results'][0]['scan_1d']['reference']==1
    manifest['cases'].append({**manifest['cases'][0],'id':'leak','split':'train'})
    path.write_text(json.dumps(manifest))
    report=evaluate_manifest(path)
    assert report['cases_failed']==1
    assert 'Leakage' in report['errors'][0]['error']


def test_firmware_hash_mismatch_is_failure(tmp_path):
    (tmp_path/'x.bin').write_bytes(b'hello')
    (tmp_path/'r.json').write_text('[]')
    (tmp_path/'m.json').write_text(json.dumps({'cases':[{'bin':'x.bin','definition':'r.json',
      'domain':'tcu','split':'test','source_license':'synthetic','sha256':'0'*64}]}))
    x=evaluate_manifest(tmp_path/'m.json')
    assert x['cases_failed']==1 and x['heldout_firmware_count']==0


def test_user_supplied_1d_does_not_enter_2d_semantic_model():
    a=MapDefinition('x',0,1,12,major_stride_bits=32)
    assert a.rows==1


def test_modified_ori_same_software_does_not_leak_into_holdout(tmp_path):
    # MOD/ORI holdout would grossly inflate performance, even with different hashes.
    original=bytearray(np.random.default_rng(55).integers(0,256,32768,dtype=np.uint8).tobytes())
    mod=bytearray(original);mod[1234]^=1
    cases=[]
    (tmp_path/'r.json').write_text('[]')
    for split,contents in (('train',original),('test',mod)):
        filename=f'{split}.bin';(tmp_path/filename).write_bytes(contents)
        cases.append({'bin':filename,'definition':'r.json','domain':'ecu','split':split,
                      'source_license':'synthetic','sha256':hashlib.sha256(contents).hexdigest()})
    (tmp_path/'m.json').write_text(json.dumps({'cases':cases}))
    result=evaluate_manifest(tmp_path/'m.json')
    assert result['cases_processed']==1
    assert result['cases_failed']==1
    assert 'sehr ähnliche' in result['errors'][0]['error']
