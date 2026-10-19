"""Regression test for the previously incorrect TunerPro XDF stride model."""
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.xdf import read_xdf
from ecu_studio.core.impact import measure_map_impact
from ecu_studio.core.analysis import analyze_map
import csv
import pytest


def test_padded_row_does_not_shift_next_line():
    data=bytes([10,11,12,255,20,21,22,254,30,31,32])
    image=BinaryImage(data)
    m=MapDefinition('Padded',0,rows=3,cols=3,dtype='u8',major_stride_bits=8,minor_stride_bits=16)
    # One pad byte between rows, last row occupies three bytes.
    assert m.length==11
    assert [[image.raw_value(m,r,c) for c in range(3)] for r in range(3)]==[
        [10,11,12],[20,21,22],[30,31,32]]
    report=analyze_map(image,m)
    assert report['max']==32
    image.write(3,b'\x01') # pad isn't a changed map cell
    assert measure_map_impact(image,m).cells_changed==0
    image.write_physical(m,1,0,25)
    assert image.byte(4)==25
    assert measure_map_impact(image,m).cells_changed==1
    assert image.original[4]==20


def test_reverse_major_and_reverse_lines():
    img=BinaryImage(bytes(range(10,18)))
    m=MapDefinition('reverse-cols',0,rows=2,cols=3,dtype='u8',major_stride_bits=-8)
    assert [[img.raw_value(m,r,c) for c in range(3)] for r in range(2)]==[
        [12,11,10],[15,14,13]]
    n=MapDefinition('reverse-rows',0,rows=2,cols=3,dtype='u8',minor_stride_bits=-8)
    assert [img.raw_value(n,r,0) for r in range(2)]==[14,10]


def test_column_major_padded_and_signed():
    # two columns, three rows, one padding byte after each column
    data=bytes([1,2,3,255,4,5,6])
    img=BinaryImage(data)
    m=MapDefinition('colmajor',0,rows=3,cols=2,dtype='u8',storage_order='column-major',
                    major_stride_bits=8,minor_stride_bits=16)
    assert m.length==7
    assert [[img.raw_value(m,r,c) for c in range(2)] for r in range(3)]==[
        [1,4],[2,5],[3,6]]


def test_unaligned_and_overlapping_strides_rejected():
    for bad in [4,7,-4]:
        with pytest.raises(ValueError):
            MapDefinition('bad',0,2,2,'u8',major_stride_bits=bad).validate(100)


def test_stride_import_realistic_xdf_and_per_definition_audit(tmp_path):
    src='''<XDFFORMAT version="1.60"><XDFHEADER><deftitle>Regression</deftitle>
    <CATEGORY index="0" name="Engine"/></XDFHEADER>
    <XDFTABLE uniqueid="0x01"><title>Engine Load Target</title>
      <CATEGORYMEM index="0" category="0"/>
      <XDFAXIS id="x"><indexcount>3</indexcount><LABEL index="0" value="1000"/>
      <LABEL index="1" value="2000"/><LABEL index="2" value="3000"/></XDFAXIS>
      <XDFAXIS id="y"><indexcount>2</indexcount></XDFAXIS>
      <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x10" mmedelementsizebits="8"
      mmedrowcount="2" mmedcolcount="3" mmedmajorstridebits="8" mmedminorstridebits="16"/>
      <MATH equation="X * 0.5"/></XDFAXIS>
    </XDFTABLE>
    <XDFCONSTANT uniqueid="0x02"><title>Unsupported nonlinear</title>
      <EMBEDDEDDATA mmedaddress="0x20" mmedelementsizebits="8"/>
      <MATH equation="X*X"/></XDFCONSTANT>
    </XDFFORMAT>'''
    xdf=tmp_path/'test.xdf';xdf.write_text(src,encoding='utf8')
    buf=bytearray(48);buf[16:23]=bytes([2,4,6,255,8,10,12])
    image=BinaryImage(bytes(buf))
    result=read_xdf(str(xdf),image)
    assert result.table_count==1 and result.constant_count==1
    assert result.coverage==1.0
    assert len(result.maps)==2
    m=result.maps[0]
    assert m.name=='Engine Load Target'
    assert m.axes_x==[1000,2000,3000]
    assert image.physical_value(m,1,2)==6
    assert m.kind.startswith('XDF-Kategorie:')
    audit=tmp_path/'audit.csv';result.write_audit_csv(audit)
    with audit.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f,delimiter=';'))
    assert rows[0]['status']=='importiert' and rows[1]['status']=='importiert'
    assert 'Schreibgeschützt' in rows[1]['reason']
    assert image.dirty_bytes==0
