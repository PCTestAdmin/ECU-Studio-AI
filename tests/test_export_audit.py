"""v1.8 regression tests: truthfulness, provenance, decoder integrity and diff."""
import hashlib
import json
import zlib
from pathlib import Path
import pytest

from ecu_studio.core.checksum_audit import (load_checksum_profile,verify_checksums,
                                             audit_export, write_audit_json)
from ecu_studio.core.map_groups import group_maps, export_groups_csv
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.tools.calibration_v18 import main


def make_fixture(tmp_path):
    data=bytearray(range(128))*4
    data[-4:]=(zlib.crc32(data[:256])&0xFFFFFFFF).to_bytes(4,'big')
    img=BinaryImage(bytes(data))
    file=tmp_path/'file.bin';file.write_bytes(data)
    profile={'format':1,'firmware_sha256':img.digest,'source':'synthetic fixture',
             'reviewer':'automated test reviewer', 'reviewed':True,
             'slots':[{'name':'Calibration block', 'algorithm':'crc32-ieee',
                       'start':0,'end':256,'storage_offset':508,'endian':'big'}]}
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile),encoding='utf8')
    return img,profile,path,file


def test_checksum_match_patch_and_restore(tmp_path):
    img,profile,path,_=make_fixture(tmp_path)
    reviewed=load_checksum_profile(path,img)
    result=verify_checksums(img,reviewed)
    assert result['status']=='match'
    assert result['verified'] is True
    img.write(2,b'\xaa')
    assert verify_checksums(img,reviewed)['status']=='mismatch'
    assert verify_checksums(img,None)['status']=='unknown'
    assert verify_checksums(img,None)['verified'] is False
    assert img.undo()
    assert verify_checksums(img,reviewed)['verified'] is True


def test_profiles_cannot_falsely_certify_other_firmware(tmp_path):
    img,profile,path,_=make_fixture(tmp_path)
    profile['firmware_sha256']='a'*64
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='SHA-256'):load_checksum_profile(path,img)
    profile['firmware_sha256']=img.digest
    profile['reviewed']='yes'
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='manuell'):load_checksum_profile(path,img)
    profile['reviewed']=True
    profile['slots'][0]['storage_offset']=254
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='Selbstreferenz'):load_checksum_profile(path,img)
    profile['slots'][0]['storage_offset']=512
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='außerhalb'):load_checksum_profile(path,img)
    profile['slots'][0]['storage_offset']=508
    profile['slots'][0]['algorithm']='unknown'
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='nicht unterstützt'):load_checksum_profile(path,img)


def test_integrity_audit_changes_outside_maps_and_csv(tmp_path):
    img,profile,path,_=make_fixture(tmp_path)
    m=MapDefinition('Ladedruck',0,rows=2,cols=4,kind='Ladedruck / Boost',
                    axes_x=[1,2,3,4],axes_y=[10,20],source='xdf',verified=False)
    img.write(2,b'\x05')
    img.write(300,b'\x0A')
    report=audit_export(img,[m],load_checksum_profile(path,img))
    assert report['dirty_bytes']==2
    assert report['changed_outside_maps']==1
    assert report['changed_map_count']==1
    assert report['changed_maps'][0]['cells_changed']==1
    assert report['checksums']['status']=='mismatch'
    assert report['flash_approved'] is False
    dst=tmp_path/'report.json'
    write_audit_json(dst,report)
    assert json.loads(dst.read_text())['changed_outside_maps']==1
    assert any(x['code']=='unverified-modification' for x in report['issues'])


def test_map_grouping_uses_labels_without_promoting_guesses(tmp_path):
    maps=[
      MapDefinition('Drehmoment A',0,2,2,kind='Drehmoment',verified=True,source='manual'),
      MapDefinition('Torque B',64,2,2,kind='Drehmoment',source='xdf'),
      MapDefinition('Möglicher Boost',128,2,2,kind='Unbekannt',source='heuristic'),
      MapDefinition('Vielleicht Ladedruck',144,2,2,kind='Boost-Verdacht',source='heuristic'),
      MapDefinition('Lambda C',512,2,2,kind='Luftmasse / Lambda',source='xdf'),
    ]
    groups=group_maps(maps)
    d=next(g for g in groups if g.title=='Drehmoment')
    assert d.indices==(0,1) and d.verified_members==1
    assert any(set(g.indices)=={2,3} and 'unbestätigt' in g.title for g in groups)
    assert not any('Ladedruck' in g.title for g in groups)
    p=tmp_path/'groups.csv'
    export_groups_csv(p,groups,maps)
    assert 'Möglicher Boost' in p.read_text(encoding='utf-8-sig')
    assert 'ungeprüft' in p.read_text(encoding='utf-8-sig')


def test_cli_checksum_groups_and_modified_image(tmp_path,capsys):
    img,profile,path,file=make_fixture(tmp_path)
    mod=tmp_path/'mod.bin';d=bytearray(file.read_bytes());d[3]=0xAA;mod.write_bytes(d)
    out=tmp_path/'audit.json'
    assert main(['audit',str(file),'--profile',str(path),'--mod',str(mod),'--out',str(out)])==0
    assert json.loads(out.read_text())['checksums']['status']=='mismatch'
    assert file.read_bytes()==img.original
    csv=tmp_path/'maps.csv'
    csv.write_text('name,offset,rows,cols,dtype,kind\nLadedruck,0x0,2,2,u16,Ladedruck / Boost\n')
    groupfile=tmp_path/'groups.csv'
    assert main(['groups',str(file),str(csv),'--csv',str(groupfile)])==0
    assert groupfile.exists()


def test_sum16_algorithm(tmp_path):
    img,profile,path,_=make_fixture(tmp_path)
    d=bytearray(img.original)
    d[508:510]=(sum(d[0:64])&0xFFFF).to_bytes(2,'little')
    i=BinaryImage(bytes(d))
    profile['firmware_sha256']=i.digest
    profile['slots']=[{'name':'sum16', 'algorithm':'sum16-bytes',
                       'start':0,'end':64,'storage_offset':508,'endian':'little'}]
    path.write_text(json.dumps(profile))
    assert verify_checksums(i,load_checksum_profile(path,i))['verified'] is True
