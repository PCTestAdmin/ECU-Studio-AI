import csv
import hashlib
import json
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition, save_project, load_project
from ecu_studio.core.definitions import import_definitions, export_definitions
from ecu_studio.core.search import hex_pattern_search, compare_reference, export_patch_csv
from ecu_studio.core.analysis import analyze_map, find_similar_maps


def test_overlay_undo_redo_and_non_destructive(tmp_path):
    initial=bytes(range(200))
    image=BinaryImage(initial)
    image.write(5,b"\x00\x00")
    assert initial[5:7]==bytes([5,6])
    assert image.read(5,2)==b"\x00\x00"
    assert image.dirty_bytes==2
    assert image.undo()
    assert image.materialize()==initial
    assert image.redo()
    assert image.materialize()[5:7]==b"\x00\x00"
    image.write(5,b"\x05\x06")
    assert image.dirty_bytes==0


def test_physical_values_endianness_and_overflow():
    image=BinaryImage(bytes(32))
    m=MapDefinition("x",offset=2,rows=2,cols=2,dtype="u16",endian="big",factor=.1,bias=-30)
    image.write_physical(m,0,0,100)
    assert image.read(2,2)==bytes.fromhex("0514")
    assert image.physical_value(m,0,0)==pytest.approx(100)
    with pytest.raises(ValueError):image.write_physical(m,0,1,999999)
    assert image.raw_value(m,0,1)==0
    m.endian="little"
    assert image.raw_value(m,0,0)==0x1405


def test_project_hash_and_restore(tmp_path):
    f=tmp_path/"original.bin"
    f.write_bytes(b"\0"*100)
    img=BinaryImage.from_file(str(f))
    m=MapDefinition("Custom",0,4,4,dtype="u8")
    img.write(4,b"\x08\x09")
    p=tmp_path/"project.ecustudio"
    save_project(str(p),img,[m],[{"offset":4,"label":"Marker"}],"notes")
    image,maps,bookmarks,notes=load_project(str(p))
    assert image.read(4,2)==b"\x08\x09"
    assert maps[0].name=="Custom" and notes=="notes" and bookmarks[0]["offset"]==4
    f.write_bytes(b"X"*100)
    with pytest.raises(ValueError,match="SHA-256"):load_project(str(p))


def test_csv_and_scan_and_search(tmp_path):
    initial=bytes.fromhex("AA BB CC DD AA 01 CC DD")
    img=BinaryImage(initial)
    assert hex_pattern_search(img,"AA ?? CC DD")==[0,4]
    assert hex_pattern_search(img,"AA FF")==[]
    with pytest.raises(ValueError):hex_pattern_search(img,"NOT HEX")
    m=MapDefinition("BOOST",offset=0,rows=1,cols=2,dtype="u16",kind="Boost-Verdacht")
    p=tmp_path/"maps.csv"
    export_definitions(str(p),[m])
    imported=import_definitions(str(p),len(initial))
    assert imported[0].name=="BOOST" and imported[0].offset==0
    img.write(0,b"\x0F")
    audit=tmp_path/"audit.csv"
    export_patch_csv(str(audit),img)
    assert "0x00000000" in audit.read_text(encoding="utf-8-sig")
    ref=tmp_path/"ref.bin"; ref.write_bytes(initial)
    total,ranges=compare_reference(img,str(ref))
    assert total==1 and ranges==[(0,1)]


def test_structural_review():
    b=BinaryImage(bytes([1,2,3,4]))
    m=MapDefinition("test",0,rows=2,cols=2,dtype="u8")
    review=analyze_map(b,m)
    assert review["min"]==1 and review["max"]==4


def test_restore_patch_validation():
    img=BinaryImage(b"abc")
    with pytest.raises(ValueError):img.restore_patches([[3,1]])
    with pytest.raises(ValueError):img.restore_patches([[0, 256]])
    with pytest.raises(ValueError):img.restore_patches([[0,1],[0,2]])


def test_html_report_escapes_user_metadata():
    from ecu_studio.core.report import make_report_html
    img=BinaryImage(bytes(range(16)))
    m=MapDefinition("<script>bad</script>",0,2,2,dtype="u8",notes="test")
    result=make_report_html(img,[m],"<b>notes</b>")
    assert "&lt;script&gt;bad&lt;/script&gt;" in result
    assert "&lt;b&gt;notes&lt;/b&gt;" in result
