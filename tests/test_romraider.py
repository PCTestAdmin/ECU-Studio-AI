import struct
import pytest
from ecu_studio.core.model import BinaryImage,MapDefinition
from ecu_studio.core.romraider import read_romraider
from ecu_studio.core.workflows import plan_map_transform,apply_batch

XML='''<roms><rom><romid><xmlid>BASE</xmlid></romid>
<table type="3D" name="Ignition" category="Ignition" storagetype="float" endian="big" sizex="3" sizey="2">
<scaling units="deg" expression="x*0.5-1"/>
<table type="X Axis" name="RPM" storagetype="uint16" endian="big"><scaling units="rpm" expression="x"/></table>
<table type="Y Axis" name="Load" storagetype="uint8"><scaling units="%" expression="x"/></table>
</table></rom><rom base="BASE"><romid><xmlid>TEST1234</xmlid>
<internalidaddress>20</internalidaddress><internalidstring>TEST1234</internalidstring><filesize>1kb</filesize></romid>
<table name="Ignition" storageaddress="100"><table type="X Axis" storageaddress="80"/><table type="Y Axis" storageaddress="90"/></table>
</rom></roms>'''

def fixture(tmp_path,xml=XML):
    raw=bytearray(1024);raw[0x20:0x28]=b'TEST1234'
    raw[0x80:0x86]=struct.pack('>3H',1000,2000,3000);raw[0x90:0x92]=bytes([10,50])
    raw[0x100:0x118]=struct.pack('>6f',2,3,4,5,6,7)
    path=tmp_path/'ecu_defs.xml';path.write_text(xml,encoding='utf-8')
    return path,BinaryImage(raw)

def test_inheritance_float_axes_and_hex_identity(tmp_path):
    path,image=fixture(tmp_path);r=read_romraider(path,image)
    assert len(r.maps)==1 and not r.excluded
    m=r.maps[0]
    assert (m.offset,m.rows,m.cols,m.dtype,m.verified)==(256,2,3,'f32',False)
    assert m.axes_x==[1000,2000,3000] and m.axes_y==[10,50]
    assert m.axis_x_unit=='rpm' and m.axis_y_unit=='%'
    assert image.physical_value(m,0,1)==.5 and image.matrix(m)[1,2]==7
    from ecu_studio.core.quality import audit_map
    assert audit_map(image,m).decode_mismatches==0
    image.write_physical(m,0,0,.125)
    assert image.raw_value(m,0,0)==2.25 and image.undo()
    assert not image.dirty_bytes

def test_float_batch_roundtrip_atomic_overflow(tmp_path):
    path,image=fixture(tmp_path);m=read_romraider(path,image).maps[0]
    preview=plan_map_transform(image,m,mode='add',amount=.125)
    apply_batch(image,preview)
    assert image.physical_value(m,0,1)==.625 and image.undo()
    with pytest.raises(ValueError):image.write_physical(m,0,0,float('nan'))
    with pytest.raises(ValueError):image.write_physical(m,0,0,1e40)
    assert not image.dirty_bytes

@pytest.mark.parametrize('change',[
    lambda x:x.replace('TEST1234</internalidstring>','OTHER123</internalidstring>'),
    lambda x:x.replace('1kb','2kb'),
    lambda x:x.replace('base="BASE"','base="TEST1234"'),
    lambda x:x.replace('base="BASE"','base="MISSING"'),
])
def test_wrong_rom_size_and_inheritance_fail_closed(tmp_path,change):
    path,image=fixture(tmp_path,change(XML))
    with pytest.raises(ValueError):read_romraider(path,image)

@pytest.mark.parametrize('change',[
    lambda x:x.replace('storageaddress="100"','storageaddress="3ff"'),
    lambda x:x.replace('storageaddress="80"','storageaddress="3ff"'),
    lambda x:x.replace('storagetype="float"','storagetype="nonsense"'),
    lambda x:x.replace('expression="x*0.5-1"','expression="__import__(x)"'),
])
def test_unsupported_entry_excluded_with_reason(tmp_path,change):
    path,image=fixture(tmp_path,change(XML));result=read_romraider(path,image)
    assert not result.maps and sum(result.excluded.values())==1
    assert not image.dirty_bytes

def test_nonfinite_float_and_nonaffine_readonly(tmp_path):
    path,image=fixture(tmp_path);image.write(256,struct.pack('>f',float('inf')))
    assert not read_romraider(path,image).maps
    path,image=fixture(tmp_path,XML.replace('x*0.5-1','x*x'))
    m=read_romraider(path,image).maps[0]
    assert image.physical_value(m,0,0)==4
    with pytest.raises(ValueError):image.write_physical(m,0,0,9)

def test_ambiguous_rom_and_xml_entities_rejected(tmp_path):
    duplicate=XML[XML.index('<rom base='):XML.rindex('</roms>')].replace('<xmlid>TEST1234','<xmlid>ANOTHER')
    path,image=fixture(tmp_path,XML.replace('</roms>',duplicate+'</roms>'))
    with pytest.raises(ValueError):read_romraider(path,image)
    path.write_text('<!DOCTYPE roms [<!ENTITY x "test">]>'+XML)
    with pytest.raises(Exception):read_romraider(path,image)
