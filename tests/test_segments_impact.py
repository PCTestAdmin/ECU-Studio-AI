import random
import struct
from dataclasses import replace
import pytest
from ecu_studio.core.a2l import parse_a2l
from ecu_studio.core.addressing import (AddressSegment, parse_segments, locate_range)
from ecu_studio.core.impact import measure_map_impact, measure_catalogue, uncovered_patches, export_impact_csv
from ecu_studio.core.detection_32 import scan_32
from ecu_studio.core.model import MapDefinition, BinaryImage
from test_a2l_and_workflows import A2L


def test_multisegment_and_holes():
    segments=parse_segments('0xA100 0xA1FF 0x20\n0xA200 0xA2FF 0x220',0x500)
    assert locate_range(0xA120,16,segments)==0x40
    assert locate_range(0xA1F8,16,segments) is None
    assert locate_range(0xA200,16,segments)==0x220
    doc=parse_a2l(A2L)
    result=doc.link(file_size=0x500,segments=segments)
    assert {m.name for m in result.maps}=={'BOOST_REQUEST','TORQUE_MAX'}
    assert {m.offset for m in result.maps}=={0x20,0x220}
    with pytest.raises(ValueError,match='überlapp'):
        parse_segments('0x100 0x110 0x0\n0x110 0x120 0x20',0x100)
    with pytest.raises(ValueError,match='BIN-Dateisegmente'):
        parse_segments('0x100 0x11F 0x0\n0x200 0x21F 0x10',0x100)
    with pytest.raises(ValueError,match='hinaus'):
        parse_segments('0x100 0x11F 0xF0',0x100)


def test_fail_closed_std_axis_and_byte_order():
    doc=parse_a2l(A2L)
    assert any('STD_AXIS' in text for text in doc.link(file_size=0x1000,ecu_anchor=0xA000,file_anchor=0).unsupported)
    doc.byte_order='???'
    with pytest.raises(ValueError,match='Byte-Reihenfolge'):
        doc.link(file_size=0x1000,ecu_anchor=0xA000,file_anchor=0)


def test_changed_map_cockpit_and_export(tmp_path):
    original=bytearray(150)
    for i in range(4):struct.pack_into('>H',original,20+i*2,100+i*10)
    img=BinaryImage(bytes(original))
    m=MapDefinition('Drehmoment',20,2,2,'u16',factor=.5,verified=True)
    img.write(22,struct.pack('>H',150))
    img.write(100,b'\xAA')
    row=measure_map_impact(img,m)
    assert row.cells_changed==1 and row.bytes_changed>0
    assert row.max_abs_delta==20.0
    assert row.status=='manuell verifiziert'
    assert measure_catalogue(img,[m])[0].max_abs_delta==20
    assert uncovered_patches(img,[m])==(1,img.dirty_bytes)
    dst=tmp_path/'impact.csv'
    export_impact_csv(str(dst),[row])
    assert 'Drehmoment' in dst.read_text(encoding='utf-8-sig')
    img.undo(); img.undo()
    assert img.dirty_bytes==0
    assert measure_map_impact(img,m).status=='unverändert'


def test_u32_structural_scanner_only_unverified():
    random_gen=random.Random(911)
    data=bytearray(random_gen.randbytes(12000))
    for r in range(16):
        for c in range(16):struct.pack_into('>I',data,0x800+(r*16+c)*4,100000+r*2000+c*1000)
    candidates=scan_32(BinaryImage(bytes(data)),max_results=25,scan_mb=1)
    assert candidates and any(abs(m.offset-0x800)<150 for m in candidates)
    assert all(m.dtype=='u32' and m.source=='heuristic' and not m.verified for m in candidates)
