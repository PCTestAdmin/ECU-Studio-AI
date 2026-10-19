"""Isolated Qt integration smoke, also callable from the packaged Windows EXE."""
from __future__ import annotations
import json
import tempfile
import os
import time
from pathlib import Path
from unittest.mock import patch


def run(output):
    from PySide6.QtCore import QSettings,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QFont
    from PySide6.QtTest import QTest
    import numpy as np
    from ..ui.main_window import Window
    from ..ui.next_dialogs import SmartTransferDialog,LogAnalyzerDialog,SurfaceEditDialog
    from ..core.model import BinaryImage,MapDefinition,save_project
    from ..core.log_analyzer import read_log,analyze_log
    from ..core.smart_transfer import FirmwareIdentity,plan_transfer,apply_transfer
    from ..core.editing import plan_surface_edit
    from ..core.workflows import apply_batch
    from dataclasses import replace
    out=Path(output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    result={'checks':[],'data':'synthetic GUI integration; not real ECU validation'}
    app=QApplication.instance() or QApplication([])
    # Qt's Windows offscreen platform has no automatic system font inventory.
    # Register installed fonts explicitly for inspectable screenshots.
    for name in ('segoeui.ttf','consola.ttf'):
        font=Path('C:/Windows/Fonts')/name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Segoe UI',10))
    with tempfile.TemporaryDirectory() as directory, patch.object(Path,'home',return_value=Path(directory)), patch.dict(os.environ,{'LOCALAPPDATA':directory}):
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,directory)
        window=Window()
        window.resize(1510,930)
        y,x=np.mgrid[:12,:16]
        raw=bytearray(65536)
        raw[4096:4480]=(1000+20*x+30*y+x*y).astype('>u2').tobytes()
        m=MapDefinition('Synthetische Prüftabelle',4096,12,16,dtype='u16',kind='Unbekannt',
                        axes_x=np.linspace(1000,7000,16).tolist(),axes_y=np.linspace(0,100,12).tolist(),
                        verified=True,unit='mbar',axis_x_channel='rpm',axis_y_channel='load',
                        axis_x_unit='rpm',axis_y_unit='%')
        image=BinaryImage(raw)
        window.load_state(image,[m,replace(m,name='Zweite Prüftabelle',offset=8192)],[],'Synthetischer GUI-Prüflauf',None)
        window.select_map(m)
        assert window.map_model.values()[0][0]==1000
        window.open_map_tab()
        pane=window.map_editors[0]
        pane.table.selectAll()
        preview=plan_surface_edit(image,m,'add',cells=[(1,1)],amount=10)
        apply_batch(image,preview)
        window.on_edited()
        assert pane.model.data(pane.model.index(1,1))=='1061'
        window.undo()
        assert image.physical_value(m,1,1)==1051
        window.redo()
        result['checks'].append('main window / map tab / numeric surface / undo / redo')
        window.show()
        app.processEvents()
        QTest.qWait(100)
        assert window.grab().save(str(out/'workspace.png'))
        window.filter.setText('Zweite')
        assert window.catalog_model.rowCount()==1
        window.filter.clear()
        window.selected=m
        window.toggle_favorite()
        window.kind_filter.setCurrentText('Favoriten')
        assert window.catalog_model.rowCount()==1
        window.kind_filter.setCurrentIndex(0)
        result['checks'].append('virtual catalogue filter and favorites')
        window.tabs.setCurrentWidget(window.view3d)
        app.processEvents()
        assert window.grab().save(str(out/'surface-3d.png'))
        log_path=Path(directory)/'drive.csv'
        log_path.write_text('rpm,load [%],Boost actual [bar],Boost target [bar]\n1000,10,1.1,1\n3000,50,1.4,1\n5000,80,1.2,1\n',encoding='utf-8')
        dialog=LogAnalyzerDialog(window)
        dialog.path=str(log_path)
        dialog.show_headers(['rpm','load [%]','Boost actual [bar]','Boost target [bar]'])
        log=read_log(log_path)
        dialog.show_analysis((log,analyze_log(log)))
        dialog.heatmap()
        assert dialog.occupancy['mapped_samples']==3
        dialog.show()
        app.processEvents()
        assert dialog.grab().save(str(out/'log-to-map.png'))
        dialog.reject()
        result['checks'].append('CSV channel mapping / analysis / heatmap dialog')
        src=BinaryImage(raw)
        src.write_physical(m,1,1,1061)
        transfer=SmartTransferDialog(window)
        transfer.source=src
        transfer.source_maps=[m]
        original_target=BinaryImage(raw)
        id_source=FirmwareIdentity(src.digest,'synthetic','test','source','synthetic smoke',True)
        id_target=replace(id_source,sha256=original_target.digest,software='target')
        plan=plan_transfer(src,original_target,[m],[m],source_identity=id_source,target_identity=id_target)
        transfer.show_plan(plan)
        transfer.maps_view.selectRow(0)
        transfer.show()
        app.processEvents()
        assert transfer.grab().save(str(out/'smart-transfer.png'))
        transfer.reject()
        apply_transfer(original_target,plan,[0],confirmed=True)
        assert original_target.physical_value(m,1,1)==1061
        result['checks'].append('transfer dialog / cell preview / confirmed transaction')
        project=Path(directory)/'smoke.ecustudio'
        save_project(project,image,window.maps,[],'GUI smoke')
        window.project_store.index(project)
        assert len(window.project_store.search('smoke'))==1
        result['checks'].append('project persistence / original backup / searchable index')
        # Exercise the independent cross-manufacturer format path in the actual
        # window, including float rendering and ORI/MOD curves.
        import struct
        float_raw=bytearray(1024)
        float_raw[32:40]=b'FLOAT123'
        float_raw[256:280]=struct.pack('>6f',1.25,2.5,3.75,5.,6.25,7.5)
        xml=Path(directory)/'ecu_defs.xml'
        xml.write_text('''<roms><rom><romid><xmlid>FLOAT123</xmlid>
        <internalidaddress>20</internalidaddress><internalidstring>FLOAT123</internalidstring>
        <filesize>1kb</filesize></romid><table type="3D" name="Float-Prueftabelle"
        storageaddress="100" storagetype="float" endian="big" sizex="3" sizey="2">
        <scaling units="test" expression="x"/><table type="Static X Axis" name="X">
        <data>1</data><data>2</data><data>3</data></table><table type="Static Y Axis" name="Y">
        <data>10</data><data>20</data></table></table></rom></roms>''',encoding='utf-8')
        float_image=BinaryImage(float_raw)
        window.load_state(float_image,[],[],'RomRaider · synthetischer Format-Test',None)
        window._import_romraider_path(xml,approved_reuse=True)
        assert len(window.maps)==1
        fm=window.maps[0];window.select_map(fm)
        assert window.map_model.data(window.map_model.index(0,0))=='1.25'
        data,axis=window.curve_view.curve_data()
        assert axis and data[0][1]==1.25
        from ..core.compare_maps import compare_images
        float_image.write_physical(fm,0,0,1.375)
        assert compare_images(float_image.original,float_image,[fm])['maps_changed']==1
        assert float_image.undo() and not float_image.dirty_bytes
        app.processEvents()
        assert window.grab().save(str(out/'romraider-float-regression.png'))
        result['checks'].append('RomRaider exact identity / float table / inherited-format path / curves / ORI-MOD / undo')
        # End-to-end reviewed pairing + opt-in interpolation between two
        # synthetic software versions, different grid sizes and byte orders.
        from ..ui.map_matching_dialog import MapMatchingDialog
        from ..core.map_matching import match_map_catalogs
        from PySide6.QtWidgets import QMessageBox
        raw_a=bytearray(1024);raw_b=bytearray(2048)
        raw_a[17:25]=np.array([[100,140],[180,220]],dtype='>u2').tobytes()
        raw_b[333:351]=np.array([[100,120,140],[140,160,180],[180,200,220]],dtype='<u2').tobytes()
        map_a=MapDefinition('Synthetic matched map',17,2,2,'u16','big',unit='mbar',kind='Reviewed synthetic',verified=True,
            axes_x=[1000,3000],axes_y=[10,30],axis_x_unit='rpm',axis_y_unit='%',axis_x_channel='rpm',axis_y_channel='load')
        map_b=replace(map_a,offset=333,rows=3,cols=3,endian='little',axes_x=[1000,2000,3000],axes_y=[10,20,30])
        version_a=BinaryImage(raw_a);version_b=BinaryImage(raw_b)
        version_a.write_physical(map_a,1,1,260)
        window.load_state(version_b,[map_b],[],'Synthetic target software B',None)
        match_dialog=MapMatchingDialog(window,version_a,[map_a])
        matches=match_map_catalogs(version_a,version_b,[map_a],[map_b])
        assert matches['matches'][0]['unique'] and matches['matches'][0]['rmse']==0
        match_dialog.show_report(matches);match_dialog.matches_view.selectRow(0)
        match_dialog.show();app.processEvents()
        assert len(match_dialog.cells_model.rows)==9
        assert match_dialog.grab().save(str(out/'cross-version-matching.png'))
        match_dialog.accept_links();assert match_dialog.selected_links=={0:0}
        transfer=SmartTransferDialog(window);transfer.source=version_a;transfer.source_maps=[map_a]
        transfer.source_name.setText('Synthetic software A → software B')
        transfer.links=match_dialog.selected_links;transfer.link_target_key=match_dialog.target_key
        for field,text in [(transfer.family,'SYNTHETIC'),(transfer.hardware_source,'HW1'),
              (transfer.hardware_target,'HW1'),(transfer.software_source,'SW-A'),(transfer.software_target,'SW-B'),
              (transfer.evidence,'Analytic synthetic interpolation fixture')]:field.setText(text)
        transfer.reviewed.setChecked(True);transfer.interpolate.setChecked(True);transfer.preview()
        deadline=time.monotonic()+30
        while transfer.worker and transfer.worker.isRunning() and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        app.processEvents()
        assert transfer.plan and transfer.plan.maps[0].status=='ready'
        assert len(transfer.plan.maps[0].cells)==4
        transfer.maps_view.selectRow(0);transfer.show();app.processEvents()
        assert transfer.grab().save(str(out/'cross-version-interpolation.png'))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
            transfer.apply()
        assert version_b.physical_value(map_b,1,1)==170
        assert version_b.undo() and version_b.materialize()==version_b.original
        assert version_b.redo() and version_b.physical_value(map_b,1,1)==170
        assert version_b.undo();transfer.reject()
        result['cross_version']={'source_grid':[2,2],'target_grid':[3,3],'matched_on_originals':True,
            'center_delta':10,'interpolation_apply_undo_redo':True,'real_oem_ground_truth':False}
        result['checks'].append('cross-version physical matching / bilinear transfer / cell preview / apply / undo / redo')
        from ..core.map_matching import locate_reference_surfaces
        yy,xx=np.mgrid[:8,:8]
        reference=(1000+17*yy**2+11*xx**2+3*xx*yy).astype('>u2')
        source_ref=BinaryImage(reference.tobytes())
        map_ref=MapDefinition('Synthetic shifted reference',0,8,8,'u16','big',verified=True)
        target_raw=bytearray(2048);reference[3,4]+=10
        target_raw[501:629]=reference.tobytes();target_ref=BinaryImage(target_raw)
        locations=locate_reference_surfaces(source_ref,target_ref,[map_ref])
        assert locations['hits'][0]['unique'] and locations['hits'][0]['target_offset']==501
        window.load_state(target_ref,[],[],'Synthetic shifted target',None)
        transfer=SmartTransferDialog(window);transfer.source=source_ref;transfer.source_maps=[map_ref]
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):
            transfer.show_locations(locations)
        assert transfer.proposals[0].offset==501 and not transfer.proposals[0].verified
        assert not transfer.proposals[0].axes_x and transfer.proposals[0].unit==''
        transfer.show();app.processEvents()
        assert transfer.grab().save(str(out/'shifted-map-recognition.png'))
        assert not window.maps and not target_ref.dirty_bytes
        transfer.reject()
        result['checks'].append('tolerant shifted map recognition / odd word address / competing-match guard / unverified raw proposal')
        ms42_path=os.environ.get('ECU_STUDIO_MS42_REGRESSION_BIN')
        if ms42_path:
            from ..recognition.bundled_definitions import definition_candidates
            ms42=BinaryImage(Path(ms42_path).read_bytes())
            maps42=definition_candidates(ms42)
            assert len(maps42)==592 and all(m.folder!='Axis' for m in maps42)
            window.load_state(ms42,maps42,[],'MS42 0110C6 · öffentlicher Kompatibilitätstest',None)
            window.select_map(next(m for m in maps42 if min(m.rows,m.cols)>1))
            window.kind_filter.setCurrentIndex(0);window.filter.clear()
            app.processEvents()
            assert window.grab().save(str(out/'ms42-definition-regression.png'))
            assert not ms42.dirty_bytes
            result['public_ms42']={'sha256':ms42.digest,'maps':len(maps42),'unchanged':True,'variant_verified':False}
            result['checks'].append('public MS42 definition layout / standalone axes excluded / table rendering')
        private_bin=os.environ.get('ECU_STUDIO_MS43_REGRESSION_BIN')
        if private_bin:
            result['data']='Synthetic GUI checks plus local real MS43 regression; no independent map verification'
            # Opt-in local fixture; only decoded screenshot/report is produced,
            # no BIN copy, VIN/path or uploaded content in QA artifacts.
            payload=Path(private_bin).read_bytes()
            real=BinaryImage(payload)
            old=MapDefinition('Veralteter Strukturvorschlag',0x76520,8,8,'u32','big',source='heuristic')
            manual=MapDefinition('Manuelle Definition bleibt erhalten',64,4,4,source='manual')
            window.load_state(real,[old,manual],[],'MS43 430069 · lokaler Regressionstest',None)
            window.select_map(old)
            window.open_map_tab()
            errors=[]
            with patch('ecu_studio.ui.main_window.QMessageBox.information'), patch.object(window,'warning',side_effect=lambda *args:errors.append(args)):
                window.scan_maps()
                deadline=time.monotonic()+90
                while window.scanner.isRunning() and time.monotonic()<deadline:
                    app.processEvents()
                    time.sleep(.01)
                assert not window.scanner.isRunning(),'MS43 scan timed out'
                app.processEvents()
                assert not errors,errors
                assert old not in window.maps and manual in window.maps
                assert not any(p.definition is old for p in window.map_editors)
                current=next(m for m in window.maps if m.name=='ip_cur_igc_sp__n__maf')
                assert (current.offset,current.rows,current.cols,current.dtype)==(0x76503,6,6,'u8')
                window.select_map(current)
                assert window.map_model.data(window.map_model.index(0,0))=='91.919216'
                assert window.map_model.columnCount()==6 and window.map_model.rowCount()==6
                assert window.map_model.headerData(0,Qt.Orientation.Horizontal,Qt.ItemDataRole.ToolTipRole)=='mg/stk'
                first_count=len(window.maps)
                window.scan_maps()
                deadline=time.monotonic()+90
                while window.scanner.isRunning() and time.monotonic()<deadline:
                    app.processEvents();time.sleep(.01)
                assert not window.scanner.isRunning()
                app.processEvents()
                assert len(window.maps)==first_count==857 and not errors
            window.select_map(current)
            window.filter.setText(current.name)
            app.processEvents()
            assert window.grab().save(str(out/'ms43-definition-regression.png'))
            assert real.materialize()==payload and not real.dirty_bytes
            result['real_ms43']={'sha256':real.digest,'maps':len(window.maps)-1,
                'spot_check':{'offset':'0x76503','rows':6,'cols':6,'dtype':'u8','unit':'mA'},
                'unchanged':True,'variant_verified':False}
            result['checks'].append('real MS43 worker / stale u32 replacement / manual preservation / linked axes / repeat scan')
        window.saved_fingerprint=window.project_state()
        window.close()
        app.processEvents()
    result['passed']=True
    (out/'gui-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0


if __name__=='__main__':
    import sys
    raise SystemExit(run(sys.argv[1] if len(sys.argv)>1 else 'gui-smoke'))
