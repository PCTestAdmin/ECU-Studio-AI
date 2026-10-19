from pathlib import Path
import csv
import struct
import pytest

from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.quality import audit_map, audit_catalog, write_quality_csv
from ecu_studio.core.raw_trace import raw_trace


def test_map_raw_physical_are_consistent_with_independent_struct():
    b=bytearray(100)
    for i,n in enumerate((-200,-100,0,150)):
        struct.pack_into('<h',b,4+2*i,n)
    im=BinaryImage(bytes(b))
    m=MapDefinition('Test',4,rows=2,cols=2,dtype='s16',endian='little',factor=.25,bias=-5,
                    axes_x=[1000.,2000.],axes_y=[10.,20.],kind='Drehmoment',source='xdf')
    assert im.physical_value(m,0,0)==-55.0
    q=audit_map(im,m)
    assert q.samples_checked==4 and q.decode_mismatches==0
    assert q.min_value==-55.0 and q.max_value==32.5
    assert q.axes_x=='vollständig' and q.axes_y=='vollständig'
    im.write_physical(m,0,1,-4)
    assert im.raw_value(m,0,1)==4
    assert audit_map(im,m).decode_mismatches==0


def test_invalid_axis_is_reported_not_assumed():
    m=MapDefinition('unknown',0,rows=2,cols=2,dtype='u16',axes_x=[1],axes_y=[],source='heuristic')
    q=audit_map(BinaryImage(bytes(8)),m)
    assert q.status=='REVIEW' and q.axes_x=='ungültig/unvollständig'
    assert 'Kennfeldfunktion' in ' '.join(q.warnings)


def test_xdf_out_of_calibration_window_warns():
    buf=bytearray(0x80000);buf[0x70008:0x7000e]=b'430069'
    im=BinaryImage(bytes(buf))
    m=MapDefinition('Test',0x3000,rows=1,cols=1,source='xdf')
    q=audit_map(im,m)
    assert 'außerhalb bekannten Kalibrierfensters' in ' '.join(q.warnings)


def test_quality_report_csv_and_rejected_layout(tmp_path):
    im=BinaryImage(bytes(32))
    m1=MapDefinition('okay',0,rows=1,cols=1,source='manual')
    m2=MapDefinition('out',100,rows=1,cols=1)
    reports=audit_catalog(im,[m1,m2])
    assert reports[0].decode_mismatches==0 and reports[1].status=='REJECT'
    dest=tmp_path/'audit.csv';write_quality_csv(dest,reports)
    with dest.open(encoding='utf-8-sig',newline='') as file:
        rows=list(csv.DictReader(file,delimiter=';'))
    assert len(rows)==2 and rows[1]['status']=='REJECT'


@pytest.mark.parametrize('endian',('big','little'))
@pytest.mark.parametrize('dtype,values',[
 ('u8',[0,255,10,20]),('s8',[-128,127,-1,0]),
 ('u16',[0,65535,100,200]),('s16',[-32768,32767,-100,500]),
 ('u32',[0,4294967295,100,200]),('s32',[-2147483648,2147483647,-100,500])])
def test_raw_trace_decodes_independently(dtype,values,endian):
    width=int(dtype[1:])//8
    data=b''.join(v.to_bytes(width,endian,signed=dtype.startswith('s')) for v in values)
    points=raw_trace(BinaryImage(data),0,len(values),dtype,endian).points
    assert [v for _,v in points]==values


def test_full_window_lod_retains_isolated_high_low_spikes():
    raw=bytearray(65536*2)
    raw[12345*2:12345*2+2]=(65535).to_bytes(2,'big')
    raw[44000*2:44000*2+2]=(1).to_bytes(2,'big')
    im=BinaryImage(bytes(raw))
    trace=raw_trace(im,0,65536,'u16','big',max_points=1200)
    assert (12345*2,65535) in trace.points
    assert (44000*2,1) in trace.points
    assert len(trace.points)<=1202
