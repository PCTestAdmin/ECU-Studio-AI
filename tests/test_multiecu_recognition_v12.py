"""Checks for real-world XDF math/layout and ECU-independent exact pairings."""
import json
from pathlib import Path
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.equations import evaluate_equation,parse_equation
from ecu_studio.core.xdf import read_xdf
from ecu_studio.core.definition_registry import remember_pair, lookup_pair, search_local_xdfs


def fixture_xdf(title='Unknown ECU',formula='X*X',address='0x10'):
    return f'''<?xml version="1.0"?><XDFFORMAT version="1.60">
<XDFHEADER><deftitle>{title}</deftitle><CATEGORY index="0" name="Fuel"/></XDFHEADER>
<XDFTABLE uniqueid="0x1"><title>Lambda correction</title>
<XDFAXIS id="x"><indexcount>2</indexcount><LABEL index="0" value="800"/><LABEL index="1" value="2000"/></XDFAXIS>
<XDFAXIS id="y"><indexcount>2</indexcount><LABEL index="0" value="1"/><LABEL index="1" value="2"/></XDFAXIS>
<XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="{address}" mmedtypeflags="0x2" mmedelementsizebits="16" mmedrowcount="2" mmedcolcount="2"/>
<MATH equation="{formula}"/></XDFAXIS></XDFTABLE></XDFFORMAT>'''


def test_nonlinear_named_xdf_maps_decode_correctly_and_are_readonly(tmp_path):
    x=tmp_path/'universal.xdf';x.write_text(fixture_xdf(),encoding='utf8')
    buf=bytearray(256);buf[16:24]=b'\x02\x00\x03\x00\x04\x00\x05\x00'
    image=BinaryImage(bytes(buf));result=read_xdf(str(x),image)
    assert result.coverage==1
    m=result.maps[0]
    assert m.name=='Lambda correction'
    assert m.equation=='X*X'
    assert m.axes_x==[800,2000]
    assert image.physical_value(m,1,1)==25
    assert result.entries[0]['status']=='importiert'
    assert 'Schreibgeschützt' in result.entries[0]['reason']
    with pytest.raises(ValueError,match='schreibgeschützt'):
        image.write_physical(m,0,0,100)
    assert image.dirty_bytes==0


def test_nonlinear_axis_can_decode_non_affine_expression(tmp_path):
    data=bytearray(128)
    data[8:10]=bytes([2,3]);data[16:20]=bytes([2,4,6,8])
    x=tmp_path/'axis.xdf';x.write_text('''<XDFFORMAT><XDFTABLE><title>Axis demo</title>
    <XDFAXIS id="x"><EMBEDDEDDATA mmedaddress="0x8" mmedelementsizebits="8"/><indexcount>2</indexcount><MATH equation="X*X"/></XDFAXIS>
    <XDFAXIS id="y"><indexcount>2</indexcount></XDFAXIS>
    <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x10" mmedelementsizebits="8" mmedrowcount="2" mmedcolcount="2"/><MATH equation="X/2"/></XDFAXIS>
    </XDFTABLE></XDFFORMAT>''')
    m=read_xdf(str(x),BinaryImage(bytes(data))).maps[0]
    assert m.axes_x==[4,9]
    assert m.factor==.5


def test_unsafe_equations_rejected_and_never_evaluated(tmp_path):
    for formula in ['__import__("os")','X.__class__','(lambda:1)()','X[0]','X**100','pow(X,100)']:
        with pytest.raises(ValueError):
            if formula=='X**100':evaluate_equation(formula,8)
            else:parse_equation(formula)
    x=tmp_path/'malicious.xdf'
    x.write_text(fixture_xdf(formula='X.__class__'),encoding='utf8')
    r=read_xdf(str(x), BinaryImage(bytes(128)))
    assert r.maps==[]
    assert r.excluded['Ungültige/komplexe Definition']==1


def test_exact_approved_pair_is_manufacturer_independent_and_rejects_changes(tmp_path):
    image=BinaryImage(bytes(range(128))) # unknown ECU deliberately
    x=tmp_path/'reference.xdf'; x.write_text(fixture_xdf(),encoding='utf8')
    db=tmp_path/'pairs.json'
    assert lookup_pair(image,db) is None
    remember_pair(image,x,db)
    pair=lookup_pair(image,db)
    assert pair and pair.path==x and pair.bin_sha256==image.digest
    other=BinaryImage(bytes([1])*128)
    assert lookup_pair(other,db) is None
    x.write_text(fixture_xdf(title='CHANGED'),encoding='utf8')
    assert lookup_pair(image,db) is None # definition tampered with
    pairs=json.loads(db.read_text())
    assert 'original' not in pairs['pairs'][0] and 'bytes' not in pairs['pairs'][0]
    assert len(pairs['pairs'])==1


def test_search_local_definitions_handles_any_ecu_without_fabricating_match(tmp_path):
    image=BinaryImage(bytes(1234))
    (tmp_path/'folder').mkdir()
    src=tmp_path/'folder'/'Toyota_ECU.xdf'
    src.write_text(fixture_xdf(),encoding='utf8')
    results=search_local_xdfs(image,[tmp_path])
    assert len(results)==1
    assert results[0][0]==src
    assert results[0][1]=='unverified'


def test_source_is_original_and_no_patch_written(tmp_path):
    original=bytearray(512*1024)
    original[0x70008:0x7000e]=b'430069'
    image=BinaryImage(bytes(original))
    x=tmp_path/'430069_512K.xdf'
    x.write_text(fixture_xdf(address='0x70010', formula='(X-1)/2'),encoding='utf8')
    result=read_xdf(str(x),image)
    assert len(result.maps)==1
    assert image.digest==BinaryImage(bytes(original)).digest
    assert image.dirty_bytes==0
