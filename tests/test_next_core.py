"""Synthetic regression cases; no real ECU accuracy or flashability claims."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage,MapDefinition,save_project,load_project
from ecu_studio.core.smart_transfer import FirmwareIdentity,plan_transfer,apply_transfer,suggest_links
from ecu_studio.core.log_analyzer import read_log,analyze_log,map_occupancy,write_log_report
from ecu_studio.core.workflows import plan_map_transform,apply_batch
from ecu_studio.core.editing import plan_surface_edit,plan_recipe
from ecu_studio.core.versioning import make_snapshot,plan_restore,apply_restore
from ecu_studio.core.storage import atomic_write
from ecu_studio.core.project_store import ProjectStore
from ecu_studio.formats.archive import archive_members,read_archive_image
from ecu_studio.recognition.evaluation import detection_metrics,validate_manifest,promotion_gate


def images():
    a=bytearray(160)
    a[16:24]=np.array([100,200,300,400],dtype='>u2').tobytes()
    b=bytearray(192)
    b[100:108]=np.array([1100,1200,1300,1400],dtype='<u2').tobytes()
    source,target=BinaryImage(a),BinaryImage(b)
    m=MapDefinition('Target',16,2,2,kind='Reviewed synthetic',verified=True,axes_x=[1000,2000],axes_y=[10,20],unit='mbar')
    t=replace(m,offset=100,endian='little',factor=.5,bias=10)
    source.write_physical(m,0,1,220)
    return source,target,m,t


def identity(image,**kw):
    return replace(FirmwareIdentity(image.digest,'SYNTHETIC','HW-test','SW-test','Independent test fixture',True),**kw)


def plan(source,target,m,t,**kw):
    return plan_transfer(source,target,[m],[t],source_identity=identity(source),target_identity=identity(target),**kw)


def test_physical_transfer_moved_scaled_different_endian_single_undo():
    source,target,m,t=images()
    original=target.original
    p=plan(source,target,m,t)
    assert p.maps[0].status=='ready'
    assert p.maps[0].cells[0].target_before==610
    assert p.maps[0].cells[0].target_after==630
    assert target.dirty_bytes==0
    with pytest.raises(ValueError,match='Bestätigung'):
        apply_transfer(target,p,[0])
    apply_transfer(target,p,[0],confirmed=True)
    assert target.physical_value(t,0,1)==630
    assert target.read(16,8)==bytes(8)  # Never copy to the source address.
    assert len(target._undo)==1 and target.original==original
    assert target.undo() and target.materialize()==original
    assert target.redo() and target.physical_value(t,0,1)==630
    assert json.dumps(p.report())


@pytest.mark.parametrize('change',[
    {'verified':False},{'axes_x':[]},{'axes_y':[10,30]},{'cols':1},{'unit':'unknown'},
    {'equation':'X*X'},{'axis_x_unit':'kPa'},
])
def test_transfer_conflicts_never_write(change):
    source,target,m,t=images()
    result=plan(source,target,m,replace(t,**change))
    assert result.maps[0].status=='conflict' and not result.maps[0].cells
    with pytest.raises(ValueError):
        apply_transfer(target,result,[0],confirmed=True)
    assert target.dirty_bytes==0


def test_transfer_rejects_hardware_unknown_identity_stale_or_ambiguous():
    source,target,m,t=images()
    for bad in (identity(target,hardware='HW-other'),identity(target,reviewed=False),identity(target,sha256='0'*64)):
        with pytest.raises(ValueError):
            plan_transfer(source,target,[m],[t],source_identity=identity(source),target_identity=bad)
    duplicate=plan_transfer(source,target,[m],[t,replace(t,offset=120)],source_identity=identity(source),target_identity=identity(target))
    assert duplicate.maps[0].status=='conflict'
    preview=plan(source,target,m,t)
    target.write(0,b'\xFF')
    before=target.materialize()
    with pytest.raises(ValueError,match='geändert'):
        apply_transfer(target,preview,[0],confirmed=True)
    assert target.materialize()==before


def test_transfer_percent_zero_overflow_and_overlapping_maps():
    source,target,m,t=images()
    m=replace(m,factor=1000)
    source.write_physical(m,0,1,60000000)
    assert plan(source,target,m,t).maps[0].status=='conflict'
    source,target,m,t=images()
    source=BinaryImage(bytes(160))
    source.write_physical(m,0,1,1)
    assert plan(source,target,m,t,mode='percent').maps[0].status=='conflict'
    source,target,m,t=images()
    m2,t2=replace(m,name='second'),replace(t,name='second')
    p=plan_transfer(source,target,[m,m2],[t,t2],source_identity=identity(source),target_identity=identity(target))
    assert all(x.status=='conflict' for x in p.maps)


def test_moved_link_unique_unverified():
    raw=bytes(range(64))
    a=BinaryImage(raw)
    b=BinaryImage(b'\xFF'*20+raw+b'\xFF'*20)
    m=MapDefinition('test',0,4,8,dtype='u16',verified=True)
    hit=suggest_links(a,b,[m])
    assert len(hit)==1 and hit[0].offset==20 and not hit[0].verified
    assert not suggest_links(a,BinaryImage(raw+raw),[m])


def test_log_german_decimal_units_missing_values_and_report_escape(tmp_path):
    p=tmp_path/'test.csv'
    p.write_text('Logger preamble\nDrehzahl [rpm];Last [%];Boost actual [kPa];Boost target [bar];Lambda actual;Lambda target\n'
                 '1000;10;110;1,0;1,10;1,0\n1500;15;140;1,0;1,0;1,0\n2000;20;bad;1,0;NaN;1,0\n',encoding='utf-8')
    log=read_log(str(p))
    report=analyze_log(log)
    assert log.sample_count==3 and log.invalid_values==2
    assert report['findings'][0]['deviation_samples']==1
    assert report['findings'][1]['deviation_samples']==1
    m=MapDefinition('<script>',0,2,2,dtype='u8',verified=True,axes_x=[1000,2000],axes_y=[10,20],
                    axis_x_channel='rpm',axis_y_channel='load',axis_x_unit='rpm',axis_y_unit='%')
    heat=map_occupancy(log,m,report['abnormal_mask'])
    assert heat['mapped_samples']==3
    assert np.sum(heat['counts'])==pytest.approx(3)
    assert np.array(heat['counts'])==pytest.approx(np.array([[1.25,.25],[.25,1.25]]))
    assert np.sum(heat['anomalies'])==pytest.approx(2)
    output=tmp_path/'report.html'
    write_log_report(output,log,report,heat)
    text=output.read_text(encoding='utf-8')
    assert '<script>' not in text and '&lt;script&gt;' in text


def test_heat_descending_axes_range_no_clamping_and_unknown_units(tmp_path):
    p=tmp_path/'data.csv'
    p.write_text('rpm,load [%]\n1000,10\n2000,20\n999,10\n3000,20\n')
    log=read_log(p)
    m=MapDefinition('x',0,2,2,verified=True,axes_x=[2000,1000],axes_y=[20,10],
                    axis_x_channel='rpm',axis_y_channel='load',axis_x_unit='rpm',axis_y_unit='%')
    h=map_occupancy(log,m)
    assert h['mapped_samples']==2 and h['excluded_samples']==2
    assert h['counts']==[[1.,0.],[0.,1.]]
    with pytest.raises(ValueError):
        map_occupancy(log,replace(m,axis_x_unit='unknown'))
    with pytest.raises(ValueError):
        map_occupancy(log,replace(m,axes_x=[1000,1000]))
    with pytest.raises(ValueError):
        map_occupancy(log,replace(m,verified=False))


def test_pressure_reference_mismatch_not_compared_and_duplicate_channel_rejected(tmp_path):
    p=tmp_path/'log.csv'
    p.write_text('Boost actual absolute [bar],Boost target gauge [bar]\n2,1\n')
    result=analyze_log(read_log(p))
    assert result['findings'][0]['status']=='unavailable'
    p.write_text('rpm,Engine speed [rpm]\n1000,1000\n')
    with pytest.raises(ValueError,match='doppelt'):
        read_log(p)
    p.write_text('rpm,load\n1000,10\n')
    with pytest.raises(ValueError,match='Einheit'):
        read_log(p)
    assert 'load' in read_log(p,{'load':('load','%')}).channels


@pytest.mark.parametrize('order',['row-major','column-major'])
@pytest.mark.parametrize('major',[8,-8,16,-16])
@pytest.mark.parametrize('minor',[0,16,-16])
def test_vector_matrix_matches_scalar_for_strides(order,major,minor):
    image=BinaryImage(bytes(range(128)))
    image.write(5,b'\xFE')
    m=MapDefinition('padded',2,3,4,dtype='u8',storage_order=order,major_stride_bits=major,minor_stride_bits=minor,factor=.5,bias=10)
    expected=[[image.raw_value(m,r,c) for c in range(m.cols)] for r in range(m.rows)]
    assert image.matrix(m).tolist()==expected
    assert image.matrix(m,physical=True)==pytest.approx(np.array(expected)*.5+10)


def test_stale_batch_cannot_overwrite_later_edit():
    image=BinaryImage(bytes(range(32)))
    m=MapDefinition('x',0,2,4,dtype='u8')
    preview=plan_map_transform(image,m,mode='add',amount=2)
    image.write(0,b'\xFF')
    prior=image.materialize()
    with pytest.raises(ValueError,match='veraltet'):
        apply_batch(image,preview)
    assert image.materialize()==prior


def test_strided_snapshot_restore_preserves_gap_edits():
    image=BinaryImage(bytes(range(64)))
    m=MapDefinition('padded',0,2,3,dtype='u8',minor_stride_bits=16)
    snap=make_snapshot(image,'base')
    image.write(0,b'\xFF')
    image.write(3,b'\xEE')
    apply_restore(image,plan_restore(image,snap,m))
    assert image.byte(0)==0 and image.byte(3)==0xEE


def test_edit_selection_interpolation_preserves_outside_and_atomic_overflow():
    image=BinaryImage(bytes([10,99,30,40,50,60]))
    m=MapDefinition('x',0,2,3,dtype='u8',verified=True)
    preview=plan_surface_edit(image,m,'interpolate_x',cells=[(0,0),(0,1),(0,2)])
    assert image.byte(1)==99
    apply_batch(image,preview)
    assert image.materialize()==bytes([10,20,30,40,50,60])
    assert image.undo() and image.byte(1)==99
    with pytest.raises(ValueError,match='überlauf'):
        plan_surface_edit(image,m,'add',amount=300)
    assert image.byte(0)==10 and image.byte(1)==99
    recipe={'schema':1,'source_sha256':image.digest,'operations':[{'map':'x','mode':'add','amount':2},{'map':'x','mode':'set','amount':999}]}
    with pytest.raises(ValueError):
        plan_recipe(image,[m],recipe)
    assert image.dirty_bytes==0


def test_project_integrity_original_backup_recovery_and_previous_version(tmp_path):
    source=tmp_path/'ori.bin'
    source.write_bytes(bytes(range(64)))
    image=BinaryImage.from_file(str(source))
    image.write(5,b'\xFF')
    project=tmp_path/'test.ecustudio'
    save_project(project,image,[],[],'one')
    save_project(project,image,[],[],'two')
    assert load_project(str(project)+'.bak')[3]=='one'
    source.unlink()
    loaded=load_project(project)[0]
    assert loaded.materialize()==image.materialize() and loaded.original==image.original
    payload=json.loads(project.read_text(encoding='utf-8'))
    payload['notes']='tampered'
    project.write_text(json.dumps(payload),encoding='utf-8')
    with pytest.raises(ValueError,match='integrität'):
        load_project(project)
    from ecu_studio.core.storage import canonical_digest
    payload['journal']=['invalid audit entry']
    payload['integrity_sha256']=canonical_digest(payload)
    project.write_text(json.dumps(payload),encoding='utf-8')
    with pytest.raises(ValueError,match='Änderungsprotokoll'):
        load_project(project)


def test_protected_hardlink_and_failed_write_preserve_original(tmp_path,monkeypatch):
    source=tmp_path/'ori.bin'
    source.write_bytes(b'original')
    alias=tmp_path/'alias.bin'
    os.link(source,alias)
    with pytest.raises(ValueError,match='Original'):
        atomic_write(alias,b'new',protected=(source,))
    assert source.read_bytes()==b'original'
    target=tmp_path/'project'
    target.write_bytes(b'old')
    def fail(*_):
        raise OSError('simulated disk replace failure')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):
        atomic_write(target,b'new')
    assert target.read_bytes()==b'old'
    assert not list(tmp_path.glob('*.tmp'))


def test_project_store_schema_and_literal_search(tmp_path):
    project=tmp_path/'Project.ecustudio'
    save_project(project,BinaryImage(bytes(16)),[],[],'100% reviewed')
    store=ProjectStore(tmp_path/'index.sqlite3')
    store.index(project)
    store.index(project)
    assert len(store.search())==1 and len(store.search('% reviewed'))==1
    assert not store.search('_reviewed')


@pytest.mark.parametrize('name',['../evil.bin','/absolute.bin','C:/escape.bin','nested/../../evil.bin'])
def test_zip_rejects_unsafe_paths(tmp_path,name):
    archive=tmp_path/'data.zip'
    with ZipFile(archive,'w') as z:
        z.writestr(name,b'abc')
    with pytest.raises(ValueError):
        archive_members(archive)


def test_zip_memory_import_and_exact_metric_not_overlap_proxy(tmp_path):
    archive=tmp_path/'data.zip'
    with ZipFile(archive,'w') as z:
        z.writestr('safe/ori.bin',bytes(range(32)))
    assert read_archive_image(archive,'safe/ori.bin').original==bytes(range(32))
    truth=MapDefinition('x',10,2,2)
    wrong=replace(truth,offset=12)
    metric=detection_metrics([truth,wrong],[truth],1024**2,exhaustive=True)
    assert metric['precision']==.5 and metric['recall']==1 and metric['f1']==pytest.approx(2/3)
    assert metric['false_alarms_per_mb']==1
    assert detection_metrics([wrong],[truth],1024**2)['precision'] is None


def test_manifest_rejects_near_identical_ori_mod_even_different_groups(tmp_path):
    rng=np.random.default_rng(40)
    a=rng.bytes(8192)
    b=bytearray(a)
    b[0]=b[0]^1
    defs=tmp_path/'defs.json'
    defs.write_text(json.dumps([MapDefinition('truth',0,2,2,verified=True).asdict()]))
    cases=[]
    for i,payload in enumerate((a,b)):
        path=tmp_path/f'{i}.bin'
        path.write_bytes(payload)
        cases.append(dict(id=str(i),binary=path.name,sha256=hashlib.sha256(payload).hexdigest(),
            definitions=defs.name,definitions_sha256=hashlib.sha256(defs.read_bytes()).hexdigest(),
            family='SYNTHETIC',software=str(i),independence_group=str(i),source_url='local-generator',
            source_license='self-generated',license_reviewer='test',definition_reviewer='test',
            data_kind='synthetic',split='train' if i==0 else 'test',license_reviewed=True,definitions_verified=True))
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'schema':1,'cases':cases}))
    with pytest.raises(ValueError,match='Leakage'):
        validate_manifest(manifest)
    gate=promotion_gate({'results':{'old':[],'new':[]}},'old','new')
    assert not gate['eligible']


def test_bit_search_masks_cross_chunk_and_raw_signed_endian():
    from ecu_studio.core.search import bit_pattern_search,raw_value_search
    data=bytearray(1024**2+4)
    data[1024**2-1:1024**2+1]=b'\xAB\xF1'
    image=BinaryImage(data)
    assert bit_pattern_search(image,'1010???? 11110001')==[1024**2-1]
    assert raw_value_search(BinaryImage(b'\xAA\xFF\xEC\xBB'),-20,'s16','big')==[1]
    with pytest.raises(ValueError):
        bit_pattern_search(image,'101')


def test_interpolation_uses_nonuniform_physical_axes():
    image=BinaryImage(bytes([0,99,100]))
    m=MapDefinition('uneven axis',0,1,3,dtype='u8',axes_x=[1000,1500,3000])
    preview=plan_surface_edit(image,m,'interpolate_x')
    apply_batch(image,preview)
    assert image.byte(1)==25  # physical quarter interval, not half the indices
