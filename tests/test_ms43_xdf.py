import hashlib
from pathlib import Path
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.xdf import _affine, read_xdf, recognize_ms43
from ecu_studio.core.scoped_scan import scan_calibration_candidates

SAMPLE='''<?xml version="1.0"?><XDFFORMAT version="1.60">
<XDFHEADER><deftitle>MS43 Fixture 430069</deftitle><BASEOFFSET offset="0x70000" subtract="0"/>
<CATEGORY index="0" name="Drehmoment"/></XDFHEADER>
<XDFTABLE uniqueid="0x17"><title>Ignition Advance Main</title>
<description>ignition advance main table</description><CATEGORYMEM index="0" category="0"/>
<XDFAXIS id="x"><EMBEDDEDDATA mmedaddress="0x10" mmedelementsizebits="8"/>
<indexcount>2</indexcount><units>rpm</units><MATH equation="X*100"/></XDFAXIS>
<XDFAXIS id="y"><LABEL index="0" value="3"/><LABEL index="1" value="7"/><indexcount>2</indexcount></XDFAXIS>
<XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x20" mmedtypeflags="0x04" mmedelementsizebits="16"
 mmedrowcount="2" mmedcolcount="2"/><units>deg</units><MATH equation="X/2-10"/></XDFAXIS>
</XDFTABLE>
<XDFCONSTANT uniqueid="0x18"><title>Engine RPM Limiter</title><EMBEDDEDDATA mmedaddress="0x70" mmedelementsizebits="16"/>
<units>rpm</units><MATH equation="X*10"/></XDFCONSTANT>
<XDFTABLE uniqueid="0x19"><title>Nonlinear map</title><XDFAXIS id="z">
<EMBEDDEDDATA mmedaddress="0x30" mmedelementsizebits="8" mmedrowcount="2" mmedcolcount="2"/>
<MATH equation="X*X"/></XDFAXIS></XDFTABLE>
<XDFTABLE uniqueid="0x20"><title>Unsupported stride</title><XDFAXIS id="z">
<EMBEDDEDDATA mmedaddress="0x40" mmedelementsizebits="8" mmedrowcount="2" mmedcolcount="2"
 mmedmajorstridebits="-32"/></XDFAXIS></XDFTABLE>
</XDFFORMAT>'''


def test_xdf_import_address_axis_math_column_major_and_skips(tmp_path):
    data=bytearray(0x80000)
    data[0x70008:0x7000e]=b'430069'
    data[0x70010:0x70012]=bytes([12,24])
    data[0x70020:0x70028]=(10).to_bytes(2,'big')+(20).to_bytes(2,'big')+(30).to_bytes(2,'big')+(40).to_bytes(2,'big')
    data[0x70070:0x70072]=(500).to_bytes(2,'big')
    xdf=tmp_path/'430069_512K.xdf'
    xdf.write_text(SAMPLE,encoding='utf-8')
    image=BinaryImage(bytes(data))
    digest=image.digest
    result=read_xdf(str(xdf),image)
    assert result.table_count==3 and result.constant_count==1
    assert len(result.maps)==4
    assert result.excluded['Ungültige/komplexe Definition']==0
    assert result.excluded['Nicht zusammenhängendes Speicherlayout']==0
    m=next(x for x in result.maps if x.name=='Ignition Advance Main')
    assert (m.offset,m.cols,m.rows)==(0x70020,2,2)
    assert m.kind=='Zündwinkel'
    assert m.storage_order=='column-major'
    assert m.axes_x==[1200.,2400.] and m.axes_y==[3.,7.]
    assert image.physical_value(m,1,0)==0 # storage order: second word 20
    assert not m.verified and m.source=='xdf'
    assert next(x for x in result.maps if x.name=='Engine RPM Limiter').factor==10
    assert image.digest==digest and not image.dirty_bytes
    image.write_physical(m,1,0,20)
    assert image.raw_value(m,1,0)==60
    assert image.original[0x70022:0x70024]==(20).to_bytes(2,'big')


def test_affine_formula_requires_provable_linear_scaling():
    assert _affine('2*X - 0.5')==(2,-0.5)
    assert _affine('X/2')==(0.5,0)
    for expr in ('X*X','X / (X + 2)', '1/X', 'sin(X)', 'X.__class__', 'X**2','(2+X)*X'):
        with pytest.raises((ValueError,SyntaxError)):_affine(expr)


def test_detection_does_not_fake_ms43_identity():
    buf=bytearray(0x80000)
    assert recognize_ms43(BinaryImage(bytes(buf)))['version'] is None
    buf[0x70008:0x7000e]=b'430069'
    profile=recognize_ms43(BinaryImage(bytes(buf)))
    assert profile['cal_start']==0x70000 and profile['version']=='430069'


def test_ms43_scoped_scan_ignores_program_code():
    # Put a nice fake 16x16 map in executable-code range, not calibration.
    data=bytearray(0x80000)
    data[0x70008:0x7000e]=b'430069'
    for r in range(16):
        for c in range(16):
            offset=0x1000+(r*16+c)*2
            data[offset:offset+2]=(600+5*r+2*c).to_bytes(2,'big')
    image=BinaryImage(bytes(data))
    maps=scan_calibration_candidates(image,limits=(10,5,5,5))
    assert not maps or all(m.offset>=0x70000 for m in maps)
    assert all(m.kind=='Unbekannt' for m in maps)
