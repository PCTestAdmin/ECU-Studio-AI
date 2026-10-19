"""Synthetic mathematical ground truth; no real multi-firmware accuracy claim."""
from dataclasses import replace
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage,MapDefinition
from ecu_studio.core.interpolation import resample_surface
from ecu_studio.core.map_matching import match_map_catalogs,locate_reference_surfaces
from ecu_studio.core.smart_transfer import FirmwareIdentity,plan_transfer,apply_transfer


def fixture():
    y,x=np.mgrid[:3,:3];values=100+10*y+30*x+5*x*y
    yy,xx=np.mgrid[0:2:5j,0:2:5j];target_values=100+10*yy+30*xx+5*xx*yy
    m=MapDefinition('Source map',17,3,3,'u16','big',factor=.5,unit='mbar',kind='Reviewed test',verified=True,
        axes_x=[1000,2000,3000],axes_y=[10,20,30],axis_x_unit='rpm',axis_y_unit='%',
        axis_x_channel='rpm',axis_y_channel='load')
    t=replace(m,name='Target symbol',offset=333,rows=5,cols=5,endian='little',factor=.25,
        axes_x=[1000,1500,2000,2500,3000],axes_y=[10,15,20,25,30])
    a=bytearray(1024);b=bytearray(2048)
    a[m.offset:m.offset+m.length]=(values/m.factor).astype('>u2').tobytes()
    b[t.offset:t.offset+t.length]=(target_values/t.factor).astype('<u2').tobytes()
    return BinaryImage(a),BinaryImage(b),m,t,target_values


def identities(a,b):
    return dict(source_identity=FirmwareIdentity(a.digest,'SYNTHETIC','HW1','SW-A','Analytic test',True),
        target_identity=FirmwareIdentity(b.digest,'SYNTHETIC','HW1','SW-B','Analytic test',True))


def changed():
    a,b,m,t,values=fixture()
    for r in range(3):
        for c in range(3):a.write_physical(m,r,c,a.physical_value(m,r,c)+10*(r+c))
    return a,b,m,t,values


def test_bilinear_delta_different_shape_scale_endian_and_address_undo():
    a,b,m,t,base=changed()
    blocked=plan_transfer(a,b,[m],[t],links={0:0},**identities(a,b))
    assert blocked.maps[0].status=='conflict'
    p=plan_transfer(a,b,[m],[t],links={0:0},interpolate=True,**identities(a,b))
    assert p.maps[0].status=='ready' and all(c.interpolated for c in p.maps[0].cells)
    assert p.interpolation_requested and len(p.maps[0].cells)==24 and b.dirty_bytes==0
    yy,xx=np.mgrid[0:2:5j,0:2:5j]
    apply_transfer(b,p,[0],confirmed=True)
    assert b.matrix(t,physical=True)==pytest.approx(base+10*(xx+yy))
    assert b.original!=b.materialize() and b.undo() and b.materialize()==b.original
    assert b.redo() and len(b._undo)==1


def test_interpolation_descending_axes_reverse_data_and_1d():
    a,b,m,t,expected=fixture();matrix=a.matrix(m,physical=True)
    desc=replace(m,axes_x=m.axes_x[::-1],axes_y=m.axes_y[::-1])
    assert resample_surface(matrix[::-1,::-1],desc,t)==pytest.approx(expected)
    curve=replace(m,rows=1,axes_y=[],axis_y_unit='',axis_y_channel='')
    target=replace(t,rows=1,axes_y=[],axis_y_unit='',axis_y_channel='')
    assert resample_surface([[0,10,20]],curve,target).tolist()==[[0,5,10,15,20]]


@pytest.mark.parametrize('change',[
    {'axes_x':[500,1500,2000,2500,3000]}, {'axes_y':[10,15,20,25,35]},
    {'axes_x':[1000,1500,1500,2500,3000]}, {'axis_x_unit':'kPa'},
    {'axis_x_unit':''}, {'axis_x_channel':'temperature'}, {'axes_y':[]},
    {'verified':False}, {'unit':'bar'}, {'equation':'X*X'},
])
def test_unsafe_grid_transfer_conflicts_atomically(change):
    a,b,m,t,_=changed();p=plan_transfer(a,b,[m],[replace(t,**change)],links={0:0},interpolate=True,**identities(a,b))
    assert p.maps[0].status=='conflict' and not p.maps[0].cells and not b.dirty_bytes


def test_percentage_field_is_interpolated_and_float_target_roundtrip():
    a,b,m,t,_=fixture()
    # Percentages, rather than interpolated ORI/MOD ratios, define this mode.
    raw=bytearray(a.original)
    raw[m.offset:m.offset+m.length]=np.full((3,3),200,dtype='>u2').tobytes();a=BinaryImage(raw)
    raw=bytearray(b.original);t=replace(t,dtype='f32',factor=1.)
    raw[t.offset:t.offset+t.length]=np.full((5,5),200,dtype='<f4').tobytes();b=BinaryImage(raw)
    for r in range(3):
        for c in range(3):a.write_physical(m,r,c,100+10*(r+c))
    p=plan_transfer(a,b,[m],[t],links={0:0},mode='percent',interpolate=True,**identities(a,b))
    assert p.maps[0].status=='ready'
    apply_transfer(b,p,[0],confirmed=True)
    yy,xx=np.mgrid[0:2:5j,0:2:5j]
    assert b.matrix(t,physical=True)==pytest.approx(200*(1+.1*(xx+yy)))
    assert b.undo() and b.materialize()==b.original


def test_resampling_stale_preview_overflow_bad_link_and_hardware():
    a,b,m,t,_=changed()
    with pytest.raises(ValueError):plan_transfer(a,b,[m],[t],links={-1:0},interpolate=True,**identities(a,b))
    p=plan_transfer(a,b,[m],[t],links={0:0},interpolate=True,**identities(a,b))
    b.write(0,b'\xFF')
    with pytest.raises(ValueError):apply_transfer(b,p,[0],confirmed=True)
    a,b,m,t,_=changed();p=plan_transfer(a,b,[m],[replace(t,factor=.00001)],links={0:0},interpolate=True,**identities(a,b))
    assert p.maps[0].status=='conflict' and not b.dirty_bytes


def test_mathematical_pairing_on_physical_grid_excludes_modifications():
    a,b,m,t,values=changed()
    result=match_map_catalogs(a,b,[m],[t])
    assert len(result['matches'])==1
    hit=result['matches'][0]
    assert hit['unique'] and hit['interpolated'] and not hit['name_agrees']
    assert hit['score']==pytest.approx(1) and hit['rmse']==pytest.approx(0)
    assert result['independently_verified_pairings']==0 and not b.dirty_bytes
    same_symbol=match_map_catalogs(a,b,[m],[replace(t,name=m.name)])
    assert same_symbol['matches'][0]['name_agrees']


def test_duplicate_candidates_collision_and_budget_never_unique():
    a,b,m,t,_=fixture();payload=bytearray(b.original);other=replace(t,name='other',offset=777)
    payload[777:777+t.length]=b.read(t.offset,t.length);b=BinaryImage(payload)
    report=match_map_catalogs(a,b,[m],[t,other])
    assert len(report['matches'])==2 and not any(h['unique'] for h in report['matches'])
    report=match_map_catalogs(a,b,[m,replace(m,name='another source')],[t])
    assert not any(h['unique'] for h in report['matches'])
    report=match_map_catalogs(a,b,[m],[t,other],max_comparisons=1)
    assert report['truncated'] and not any(h['unique'] for h in report['matches'])
    assert match_map_catalogs(a,b,[m],[t],cancelled=lambda:True)['cancelled']


def test_missing_physical_evidence_does_not_become_match():
    a,b,m,t,_=fixture()
    for bad in [replace(t,axes_x=[]),replace(t,unit='bar'),replace(t,axis_y_unit=''),replace(t,axes_x=[0,1,2,3,4])]:
        report=match_map_catalogs(a,b,[m],[bad])
        assert not report['matches']
        if bad.unit==m.unit:assert report['excluded']


def test_same_units_need_distinct_axis_roles_for_changed_grid():
    a,b,m,t,_=fixture()
    m=replace(m,axis_x_unit='rpm',axis_y_unit='rpm',axis_x_channel='',axis_y_channel='')
    t=replace(t,axis_x_unit='rpm',axis_y_unit='rpm',axis_x_channel='',axis_y_channel='')
    with pytest.raises(ValueError,match='Achsenrollen'):resample_surface(a.matrix(m,physical=True),m,t)


def test_unverified_named_pair_never_becomes_verified():
    a,b,m,t,_=fixture();m=replace(m,name=t.name)
    r=match_map_catalogs(a,b,[replace(m,verified=False)],[replace(t,verified=False)])
    assert r['matches'][0]['unique'] and not r['matches'][0]['source_verified']
    assert r['independently_verified_pairings']==0


def test_shifted_slightly_changed_reference_odd_word_address_and_duplicate():
    yy,xx=np.mgrid[:8,:8];values=(1000+17*yy**2+11*xx**2+3*xx*yy).astype('>u2')
    src=BinaryImage(values.tobytes());m=MapDefinition('Reference symbol',0,8,8,'u16','big',verified=True,unit='deg',factor=.5,
        axes_x=list(range(8)),axes_y=list(range(8)))
    data=bytearray(2048);modified=values.copy();modified[3,4]+=10
    data[101:101+len(values.tobytes())]=modified.tobytes();target=BinaryImage(data)
    r=locate_reference_surfaces(src,target,[m]);assert len(r['hits'])==1
    h=r['hits'][0];assert h['target_offset']==101 and h['unique']
    p=MapDefinition(**h['proposed']);assert not p.verified and not p.axes_x and not p.axes_y and p.unit=='' and p.factor==1 and p.kind=='Unbekannt'
    data[701:701+len(values.tobytes())]=modified.tobytes()
    r=locate_reference_surfaces(src,BinaryImage(data),[m]);assert not r['hits'][0]['unique']
    assert not locate_reference_surfaces(src,target,[m],cancelled=lambda:True)['hits']
    assert not target.dirty_bytes and not src.dirty_bytes


def test_two_software_markers_same_family_and_declared_identity_mismatch():
    a,b,m,t,_=changed()
    raw_a=bytearray(a.original)+bytearray(65536-a.size)
    raw_b=bytearray(b.original)+bytearray(65536-b.size)
    raw_a[8:14]=b'430069';raw_b[8:14]=b'430066'
    # These are constructed fixtures, not independent OEM firmware stands.
    a,b=BinaryImage(raw_a),BinaryImage(raw_b)
    a.write_physical(m,0,0,a.physical_value(m,0,0)+10)
    report=match_map_catalogs(a,b,[m],[t]);assert report['matches'][0]['unique']
    ids=identities(a,b)
    ids['source_identity']=replace(ids['source_identity'],family='Siemens MS43',software='430069')
    ids['target_identity']=replace(ids['target_identity'],family='Siemens MS43',software='430066')
    assert plan_transfer(a,b,[m],[t],links={0:0},interpolate=True,**ids).maps[0].status=='ready'
    ids['target_identity']=replace(ids['target_identity'],software='430069')
    with pytest.raises(ValueError,match='Software-/Kalibrierstand'):
        plan_transfer(a,b,[m],[t],links={0:0},interpolate=True,**ids)


def test_known_different_ecu_families_cannot_be_paired():
    source=bytearray(65536);source[8:14]=b'430069'
    target=bytearray(65536);target[0x176:0x17e]=b'GADC9010';target[0xffc8:0xffd8]=b'G2210_0090C0AD10'
    a,b=BinaryImage(source),BinaryImage(target)
    with pytest.raises(ValueError,match='ECU-Familien'):match_map_catalogs(a,b,[],[])
    with pytest.raises(ValueError,match='ECU-Familien'):locate_reference_surfaces(a,b,[])
