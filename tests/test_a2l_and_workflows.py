from pathlib import Path
import json
import struct
import pytest
from ecu_studio.core.a2l import parse_a2l, read_a2l, classify_name
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.workflows import (plan_map_transform, apply_batch,
    catalogue_check, export_map_pack, import_map_pack)
from ecu_studio.core.detection_extended import scan_u8

A2L = r'''
ASAP2_VERSION 1 71
/begin PROJECT Example "ECU example"
 /begin MODULE UNIT "Demo"
  /begin MOD_COMMON "common"
     BYTE_ORDER MSB_FIRST
  /end MOD_COMMON
  /begin COMPU_METHOD FACTOR "pressure scaling" LINEAR "%6.1" "mbar"
    COEFFS_LINEAR 0.1 -5
  /end COMPU_METHOD
  /begin COMPU_METHOD ID "no conversion" IDENTICAL "%3.0" "Nm"
  /end COMPU_METHOD
  /begin COMPU_METHOD FORMULA_METHOD "special" FORM "%3.2" "x"
  /end COMPU_METHOD
  /begin RECORD_LAYOUT LAYOUT1
    FNC_VALUES 1 UWORD ROW_DIR DIRECT
  /end RECORD_LAYOUT
  /begin RECORD_LAYOUT LAYOUT_DYNAMIC
    NO_AXIS_PTS_X 1 UBYTE
    AXIS_PTS_X 2 UWORD INDEX_INCR DIRECT
    FNC_VALUES 3 UWORD ROW_DIR DIRECT
  /end RECORD_LAYOUT
  /begin CHARACTERISTIC BOOST_REQUEST "Boost pressure target" MAP 0xA100 LAYOUT1 0 FACTOR 0 6000
    /begin AXIS_DESCR FIX_AXIS RPM NO_COMPU_METHOD 4 0 8000
     FIX_AXIS_PAR_DIST 0 1000 4
    /end AXIS_DESCR
    /begin AXIS_DESCR FIX_AXIS LOAD NO_COMPU_METHOD 3 0 100
     FIX_AXIS_PAR_DIST 0 5 3
    /end AXIS_DESCR
  /end CHARACTERISTIC
  /begin CHARACTERISTIC TORQUE_MAX "Torque limit" CURVE 0xA200 LAYOUT1 0 ID 0 500
    /begin AXIS_DESCR FIX_AXIS RPM NO_COMPU_METHOD 8 0 8000
    /end AXIS_DESCR
  /end CHARACTERISTIC
  /begin CHARACTERISTIC EGR_RATE "AGR control" MAP 0xA300 LAYOUT_DYNAMIC 0 ID 0 100
    /begin AXIS_DESCR STD_AXIS RPM ID 5 0 8000
    /end AXIS_DESCR
    /begin AXIS_DESCR STD_AXIS LOAD ID 4 0 8000
    /end AXIS_DESCR
  /end CHARACTERISTIC
  /begin CHARACTERISTIC CUSTOM1 "Some unexpected conversion" VALUE 0xA400 LAYOUT1 0 FORMULA_METHOD 0 1
  /end CHARACTERISTIC
 /end MODULE
/end PROJECT
'''


def test_a2l_link_linear_conversion_dimensions_and_categories():
    doc=parse_a2l(A2L)
    assert len(doc.characteristics)==4
    linked=doc.link(file_size=0x1000, ecu_anchor=0xA000,file_anchor=0)
    assert linked.total==4
    assert len(linked.maps)==2
    boost,torque=linked.maps
    assert (boost.offset,boost.rows,boost.cols)==(0x100,3,4)
    assert (boost.factor,boost.bias,boost.unit)==(0.1,-5,'mbar')
    assert boost.kind=='Ladedruck-Sollwert' and boost.ecu_address==0xA100
    assert torque.kind=='Drehmomentbegrenzung' and torque.rows==1 and torque.cols==8
    assert boost.verified is False
    assert len(linked.unsupported)==2
    assert any('LAYOUT_DYNAMIC' not in x for x in linked.unsupported)


def test_a2l_relative_anchors_and_out_of_range():
    doc=parse_a2l(A2L)
    r=doc.link(file_size=0x200,ecu_anchor=0xA100,file_anchor=0x140)
    assert any(m.offset==0x140 for m in r.maps)
    assert len(r.out_of_range)>=1
    with pytest.raises(ValueError):doc.link(file_size=100,ecu_anchor=0,file_anchor=999)


def test_a2l_preserve_bytes_and_reject_invalid(tmp_path):
    f=tmp_path/'car.a2l'; f.write_text(A2L,encoding='utf-8')
    assert len(read_a2l(str(f)).characteristics)==4
    with pytest.raises(ValueError,match='stimmt nicht'):
        parse_a2l('/begin PROJECT A "x" /end MODULE')
    with pytest.raises(ValueError,match='nicht geschlossene'):
        parse_a2l('/begin PROJECT A "x"')
    assert classify_name('Ignition timing')=='Zündwinkel'
    assert classify_name('unknown dimension')=='Unbekannt'


def test_batch_preview_edit_one_undo_and_range_validation():
    original=bytearray(128)
    for i in range(16):struct.pack_into('>H',original,32+2*i,100+i)
    image=BinaryImage(bytes(original))
    m=MapDefinition('Map',32,rows=4,cols=4,dtype='u16',factor=.1)
    p=plan_map_transform(image,m,mode='percent',amount=10)
    assert p.changed_cells==16
    assert image.dirty_bytes==0  # preview does not edit
    apply_batch(image,p)
    assert image.dirty_bytes>0
    assert image._undo and len(image._undo)==1
    assert image.physical_value(m,0,0)==pytest.approx(11)
    image.undo()
    assert image.materialize()==bytes(original)
    with pytest.raises(ValueError,match='außerhalb'):
        plan_map_transform(image,m,mode='set',amount=1e12)
    assert image.materialize()==bytes(original)
    with pytest.raises(ValueError,match='Ausschnitt'):
        plan_map_transform(image,m,mode='add',amount=1,row_range=(2,1))


def test_map_pack_sha_guard_and_catalogue_check(tmp_path):
    m=MapDefinition('one',0,rows=2,cols=2,dtype='u8',verified=True)
    n=MapDefinition('duplicate',0,rows=2,cols=2,dtype='u8')
    other=MapDefinition('overlap',3,rows=2,cols=2,dtype='u8')
    qa=catalogue_check([m,n,other],10)
    assert qa['duplicates'] and qa['overlaps']
    assert not qa['invalid']
    file=tmp_path/'sample.ecupack.json'
    original=BinaryImage(bytes(40))
    export_map_pack(str(file),[m],original)
    maps,explain=import_map_pack(str(file),image=original)
    assert len(maps)==1 and maps[0].verified and 'Exakt' in explain
    different=BinaryImage(bytes(39))
    with pytest.raises(ValueError,match='SHA-256'):
        import_map_pack(str(file),image=different)
    maps,explain=import_map_pack(str(file),image=different,allow_mismatch=True)
    assert maps[0].verified is False


def test_unsigned_8bit_structural_scan():
    import random
    data=bytearray(random.Random(10).randbytes(5000))
    for r in range(16):
        for c in range(16):
            data[0x600+r*16+c]=80+r*4+c//2
    found=scan_u8(BinaryImage(bytes(data)),max_results=20,scan_mb=1)
    assert found and any(abs(m.offset-0x600)<100 for m in found)
    assert all(m.dtype=='u8' and m.kind=='Unbekannt' and not m.verified for m in found)


def test_a2l_with_byte_undefined_in_cp1252_is_readable(tmp_path):
    # Regression: a real BMW A2L contains 0x81 in a comment; cp1252 rejected it.
    from ecu_studio.core.a2l import read_a2l
    text = (b'/begin PROJECT P "" /begin MODULE M "\x81 Kommentar \xe4" '
            b'/begin CHARACTERISTIC K "x" VALUE 0x100 RL 0 CM 0 255 /end CHARACTERISTIC '
            b'/end MODULE /end PROJECT')
    path = tmp_path / 'x.a2l'
    path.write_bytes(text)
    assert [c.name for c in read_a2l(str(path)).characteristics] == ['K']
