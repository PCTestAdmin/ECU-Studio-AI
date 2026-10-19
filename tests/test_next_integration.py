from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import pytest
from ecu_studio.core.model import BinaryImage,MapDefinition,save_project,load_project
from ecu_studio.core.plugins import Plugins,ImportResult,CheckResult
from ecu_studio.core.storage import atomic_write
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.tools.next_workflows import batch_recipes


def test_old_catalog_migrates_without_losing_records_and_never_approves_public_labels(tmp_path):
    path=tmp_path/'catalog.sqlite'
    db=DefinitionCatalog(path)
    image=BinaryImage(bytes(range(64)))
    m=MapDefinition('reviewed test',0,4,4,dtype='u8',kind='Synthetic test',source='manual')
    db.import_maps(image,[m],origin='local synthetic regression')
    db.verify(db.records()[0]['id'],image,confirm=True)
    with sqlite3.connect(path) as c:
        old=m.asdict()
        for field in ('axis_x_channel','axis_y_channel','axis_x_unit','axis_y_unit','folder','favorite'):
            old.pop(field)
        c.execute('UPDATE definition SET map_json=?',(json.dumps(old),))
        c.execute('DROP TABLE firmware_provenance')
        c.execute('PRAGMA user_version=0')  # v1.10 did not set user_version
    upgraded=DefinitionCatalog(path)
    assert len(upgraded.records())==1 and upgraded.records()[0]['verified']==1
    assert upgraded.stats()['public_map_hints']>0
    assert upgraded.training_provenance()=={}
    upgraded.import_maps(image,[m],origin='local synthetic regression')
    assert upgraded.records()[0]['verified']==1
    provenance=dict(firmware_sha=image.digest,independence_group='synthetic-lineage',hardware='test',
                    source_url='local',license='self-generated synthetic',reviewer='test',reviewed_at='2026-10-17',
                    rights_confirmed=True,independence_reviewed=True)
    upgraded.review_training_provenance(provenance)
    assert upgraded.training_provenance()[image.digest]['independence_group']=='synthetic-lineage'
    image.write(0,b'\xFF')
    with pytest.raises(ValueError,match='unveränderte'):
        upgraded.verify(upgraded.records()[0]['id'],image,confirm=True)


def test_future_catalog_schema_rejected_without_mutation(tmp_path):
    p=tmp_path/'future.sqlite'
    with sqlite3.connect(p) as c:
        c.execute('PRAGMA user_version=99')
        c.execute('CREATE TABLE sentinel(value TEXT)')
    with pytest.raises(ValueError,match='neueren'):
        DefinitionCatalog(p)
    with sqlite3.connect(p) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==99
        assert c.execute('SELECT COUNT(*) FROM sqlite_master WHERE type="table"').fetchone()[0]==1


def test_plugin_cannot_confirm_maps_or_claim_flash_approval():
    registry=Plugins()
    image=BinaryImage(bytes(64))
    registry.register('import','synthetic',lambda p,n:ImportResult((MapDefinition('x',0,2,2,verified=True),),'test fixture'))
    assert not registry.import_definitions('synthetic','ignored',image).maps[0].verified
    registry.register('check','unavailable',lambda data,p:CheckResult('unsupported','synthetic','No validated algorithm'))
    assert registry.check('unavailable',image,{}).status=='unsupported'
    registry.register('check','unsafe',lambda data,p:CheckResult('pass','synthetic','test',True))
    with pytest.raises(ValueError):
        registry.check('unsafe',image,{})


def test_batch_plans_all_jobs_before_any_output_and_preserves_input(tmp_path):
    image=BinaryImage(bytes(range(32)))
    m=MapDefinition('test',0,2,2,dtype='u8',verified=True)
    project=tmp_path/'source.ecustudio'
    save_project(project,image,[m],[],'')
    recipe=tmp_path/'recipe.json'
    recipe.write_text(json.dumps({'schema':1,'source_sha256':image.digest,
                                 'operations':[{'map':'test','mode':'add','amount':2}]}))
    manifest=tmp_path/'batch.json'
    job={'project':project.name,'recipe':recipe.name,'output':'output.ecustudio'}
    manifest.write_text(json.dumps({'schema':1,'jobs':[job]}))
    assert not batch_recipes(manifest)['committed']
    assert not (tmp_path/'output.ecustudio').exists()
    manifest.write_text(json.dumps({'schema':1,'jobs':[job,{**job,'recipe':'missing.json','output':'other.ecustudio'}]}))
    with pytest.raises(FileNotFoundError):
        batch_recipes(manifest,commit=True)
    assert not (tmp_path/'output.ecustudio').exists()
    manifest.write_text(json.dumps({'schema':1,'jobs':[job]}))
    batch_recipes(manifest,commit=True)
    assert load_project(project)[0].dirty_bytes==0
    assert load_project(tmp_path/'output.ecustudio')[0].byte(0)==2
    with pytest.raises(ValueError):
        batch_recipes(manifest,commit=True)


def test_atomic_create_never_overwrites_existing_or_content_addressed_original(tmp_path):
    p=tmp_path/'new.ecustudio'
    p.write_bytes(b'existing')
    with pytest.raises(FileExistsError):
        atomic_write(p,b'replacement',overwrite=False)
    assert p.read_bytes()==b'existing'
    protected=tmp_path/'.ecustudio-originals'/('a'*64+'.bin')
    with pytest.raises(ValueError,match='Originalbackup'):
        atomic_write(protected,b'wrong')


def test_gui_worker_transfer_preview_and_virtual_catalogue(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
    from PySide6.QtCore import QSettings,Qt,QElapsedTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from ecu_studio.ui.main_window import Window,ScanWorker
    from ecu_studio.ui.next_dialogs import SmartTransferDialog,SurfaceEditDialog,LogAnalyzerDialog
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window()
    image=BinaryImage(bytes(range(128)))
    m=MapDefinition('test',0,2,2,dtype='u8',verified=True,axes_x=[1,2],axes_y=[3,4])
    source=BinaryImage(image.original)
    source.write_physical(m,0,1,5)
    w.load_state(image,[m],[],'',None)
    initial_fingerprint=w.saved_fingerprint
    w.select_map(m)
    w.open_map_tab()
    assert len(w.map_editors)==1
    assert w.map_editors[0].model.values()==[[0.,1.],[2.,3.]]
    edit=SurfaceEditDialog(image,m,[(0,0)],w.on_edited,w)
    edit.amount.setValue(5)
    edit.calculate()
    assert edit.preview.changed_cells==1
    edit.apply()
    w.undo()
    assert image.dirty_bytes==0
    assert w.project_state()!=initial_fingerprint  # persist the audit even after net-zero undo
    transfer=SmartTransferDialog(w)
    transfer.source=source
    transfer.source_maps=[m]
    for field,value in ((transfer.family,'synthetic'),(transfer.hardware_source,'hardware'),
                        (transfer.hardware_target,'hardware'),(transfer.software_source,'source'),
                        (transfer.software_target,'target'),(transfer.evidence,'synthetic test')):
        field.setText(value)
    transfer.reviewed.setChecked(True)
    transfer.preview()
    elapsed=QElapsedTimer()
    elapsed.start()
    while transfer.worker.isRunning() and elapsed.elapsed()<5000:
        app.processEvents()
        QTest.qWait(5)
    transfer.worker.wait(5000)
    app.processEvents()
    assert transfer.plan and transfer.plan.maps[0].status=='ready'
    assert image.dirty_bytes==0
    transfer.hardware_target.setText('different')
    assert transfer.plan is None and not transfer.apply_button.isEnabled()
    transfer.reject()
    # Cancellation returns no partial candidates; never add a partial scan.
    worker=ScanWorker(BinaryImage(bytes(16384)))
    worker.requestInterruption()
    # QThread only reports interruption after start, so exercise scan callback directly.
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    assert scan_calibration_candidates(image,cancelled=lambda:True)==[]
    w.set_byte_radix(10)
    assert w.hex_model.setData(w.hex_model.index(0,0),'255')
    assert w.hex_model.data(w.hex_model.index(0,0))=='255'
    assert not w.hex_model.setData(w.hex_model.index(0,0),'256')
    w.autosave()
    recovered=tmp_path/'.ecu_studio_ai'/'recovery'/f'{image.digest}.ecustudio'
    assert load_project(recovered)[0].byte(0)==255
    w.saved_fingerprint=w.project_state()
    w.close()
