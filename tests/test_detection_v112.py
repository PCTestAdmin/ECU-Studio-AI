"""Width ambiguity, real record boundaries, linked axes and real-file regressions."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.precision import rank_candidates, narrower_storage_alias
from ecu_studio.core.axis_records import scan_axis_records
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.xdf import read_xdf
from ecu_studio.recognition.bundled_definitions import DATA, definition_candidates, matching_source


def test_repeated_smooth_bytes_do_not_become_billion_valued_u32_maps():
    y,x=np.mgrid[:8,:32]
    raw=(30+y*3+x//2).astype('u1').tobytes()
    image=BinaryImage(raw)
    for order in ('big','little'):
        m=MapDefinition('Packed bytes',0,8,8,'u32',order,source='heuristic',confidence=.4)
        assert narrower_storage_alias(image,m)
        assert rank_candidates(image,[m])==[]


@pytest.mark.parametrize('endian',['big','little'])
def test_genuine_32bit_surface_keeps_full_numeric_range(endian):
    y,x=np.mgrid[:12,:12]
    values=(2_500_000_000+177777*y+73117*x).astype('>u4' if endian=='big' else '<u4')
    image=BinaryImage(values.tobytes())
    m=MapDefinition('Actual words',0,12,12,'u32',endian,source='heuristic',confidence=.4)
    assert not narrower_storage_alias(image,m)
    result=rank_candidates(image,[m])
    assert len(result)==1
    assert image.raw_value(result[0],0,0)==2_500_000_000


@pytest.mark.parametrize('count_width,axis_width,endian,table_type',[
    (1,1,'big','u8'),(1,2,'little','u16'),(2,2,'big','s16')])
def test_axis_records_find_nonstandard_dimensions_at_unaligned_addresses(count_width,axis_width,endian,table_type):
    rows,cols=7,5
    buf=bytearray(2048)
    # Odd header and data offsets are deliberately not aligned to scanner grids.
    start=19
    counts=cols.to_bytes(count_width,endian)+rows.to_bytes(count_width,endian)
    axis_values=[10,30,60,100,150,8,20,35,55,80,110,145]
    if axis_width==2:axis_values=[v*10 for v in axis_values]
    axes=b''.join(v.to_bytes(axis_width,endian) for v in axis_values)
    offset=start+len(counts)+len(axes)
    yy,xx=np.mgrid[:rows,:cols]
    values=25+4*yy+2*xx
    if table_type=='s16':values=values-80
    storage=('>' if endian=='big' else '<')+('i2' if table_type=='s16' else 'u2' if table_type=='u16' else 'u1')
    payload=values.astype(storage).tobytes()
    buf[start:start+len(counts)+len(axes)+len(payload)]=counts+axes+payload
    image=BinaryImage(buf)
    records=scan_axis_records(image)
    exact=[m for m in records if (m.offset,m.rows,m.cols,m.dtype)==(offset,rows,cols,table_type)]
    assert exact
    assert all(not m.verified and m.kind=='Unbekannt' for m in records)
    assert any(m.axes_x==axis_values[:cols] for m in exact)
    final=scan_calibration_candidates(image)
    assert any(m.offset==offset and m.rows==rows and m.cols==cols for m in final)
    assert not image.dirty_bytes


def test_axis_record_noise_truncation_and_cancellation():
    noise=np.random.default_rng(119).integers(0,256,10000,dtype='u1').tobytes()
    assert scan_axis_records(BinaryImage(noise))==[]
    assert scan_axis_records(BinaryImage(bytes([5,7,10,20,30,40,50])))==[]
    assert scan_axis_records(BinaryImage(noise),cancelled=lambda:True)==[]


def test_linked_axis_overrides_stale_embedded_address_and_units_survive(tmp_path):
    xml='''<XDFFORMAT><XDFHEADER><CATEGORY index="4" name="Ignition"/></XDFHEADER>
    <XDFTABLE uniqueid="0x10"><title>linked points</title><XDFAXIS id="z">
    <EMBEDDEDDATA mmedaddress="0x20" mmedtypeflags="2" mmedelementsizebits="16" mmedrowcount="1" mmedcolcount="4"/>
    <MATH equation="X*32"/></XDFAXIS></XDFTABLE>
    <XDFTABLE><title>map</title><CATEGORYMEM category="5"/><XDFAXIS id="x">
    <indexcount>4</indexcount><units>rpm</units><EMBEDDEDDATA mmedaddress="0x80" mmedelementsizebits="8" mmedmajorstridebits="-32"/>
    <embedinfo type="3" linkobjid="0x10"/><MATH equation="X"/></XDFAXIS>
    <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x40" mmedelementsizebits="8" mmedrowcount="1" mmedcolcount="4"/></XDFAXIS>
    </XDFTABLE></XDFFORMAT>'''
    path=tmp_path/'linked.xdf';path.write_text(xml)
    buf=bytearray(256);buf[32:40]=np.array([20,40,60,80],dtype='<u2').tobytes()
    buf[128:144]=bytes(range(16))
    m=read_xdf(str(path),BinaryImage(buf)).maps[1]
    assert m.axes_x==[640,1280,1920,2560]
    assert m.axis_x_unit=='rpm' and m.folder=='Ignition'


def test_bundled_source_integrity_standard_variant_and_no_identity_only_acceptance():
    items=json.loads((DATA/'manifest.json').read_text())
    for item in items:
        payload=(DATA/item['file']).read_bytes()
        assert hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()==item['git_blob']
        assert item['variant']=='Standard' and 'Extended' not in item['file']
    raw=bytearray(65536);raw[8:14]=b'430069'
    image=BinaryImage(raw)
    assert matching_source(image)
    assert definition_candidates(image)==[]
    assert matching_source(BinaryImage(bytes(65536))) is None


@pytest.fixture(scope='module')
def real_image():
    path=os.environ.get('ECU_STUDIO_MS43_REGRESSION_BIN')
    if not path:pytest.skip('Opt-in private real BIN; never bundled')
    image=BinaryImage.from_file(path)
    assert image.size==524288
    assert image.digest=='76010474fe2e3a4896724b6d0244173e49464e7b38758ccc6dc1bcaa53650421'
    return image


def test_real_ms43_definitions_bounds_units_and_constant_map(real_image):
    maps=scan_calibration_candidates(real_image)
    assert len(maps)>800 and all(m.source=='bundled-definition' and not m.verified for m in maps)
    current=next(m for m in maps if m.name=='ip_cur_igc_sp__n__maf')
    assert (current.offset,current.rows,current.cols,current.dtype)==(0x76503,6,6,'u8')
    assert (current.axis_x_unit,current.axis_y_unit,current.unit)==('mg/stk','rpm','mA')
    assert np.all(real_image.matrix(current)==163)
    assert real_image.physical_value(current,0,0)==pytest.approx(91.91921591)
    vanos=next(m for m in maps if m.offset==0x7652f)
    assert vanos.axes_x[0]==pytest.approx(-20.13725495)
    assert vanos.axes_y==[704,992,1248,1504,2016,3008,4000,4992]
    assert not any(m.dtype=='u32' and m.offset<=0x76520<m.offset+m.length for m in maps)
    partial=BinaryImage(real_image.read(0x70000,65536))
    cal_maps=definition_candidates(partial)
    p=next(m for m in cal_maps if m.name==current.name)
    assert p.offset==0x6503 and p.axes_x==current.axes_x
    assert not real_image.dirty_bytes
    assert hashlib.sha256(Path(real_image.path).read_bytes()).hexdigest()==real_image.digest


def test_real_wrong_width_rejected_even_without_definitions(real_image):
    wrong=MapDefinition('Old screenshot',0x76520,8,8,'u32','big',source='heuristic',confidence=.4)
    assert narrower_storage_alias(real_image,wrong)
    assert rank_candidates(real_image,[wrong])==[]


def test_qt_rescan_preserves_manual_verified_and_source_aliases_and_raw_precision(tmp_path):
    from PySide6.QtCore import QSettings,Qt
    from PySide6.QtWidgets import QApplication
    from ecu_studio.ui.main_window import Window
    from ecu_studio.ui.views import MapTableModel
    from types import SimpleNamespace
    app=QApplication.instance() or QApplication([])
    image=BinaryImage((2745410467).to_bytes(4,'big')+bytes(65532))
    model=MapTableModel()
    raw_map=MapDefinition('Raw',0,1,1,'u32','big')
    model.set_map(image,raw_map)
    assert model.data(model.index(0,0))=='2745410467'
    assert model.data(model.index(0,0),Qt.ItemDataRole.EditRole)=='2745410467'
    assert model.setData(model.index(0,0),model.data(model.index(0,0),Qt.ItemDataRole.EditRole))
    assert not image.dirty_bytes
    settings=QSettings(str(tmp_path/'ui.ini'),QSettings.Format.IniFormat)
    with patch.object(Path,'home',return_value=tmp_path), patch('ecu_studio.ui.main_window.QSettings',return_value=settings), patch('ecu_studio.ui.main_window.QMessageBox.information'):
        window=Window()
        try:
            old=MapDefinition('Old',128,8,8,'u32','big',source='heuristic')
            manual=MapDefinition('Manual',1024,4,4,source='manual')
            checked=MapDefinition('Reviewed',2048,4,4,source='heuristic',verified=True)
            source=MapDefinition('Source A',128,6,6,'u8',source='bundled-definition')
            alias=MapDefinition('Source B',128,6,6,'u8',source='bundled-definition')
            overlaps_reviewed=MapDefinition('Do not replace reviewed',2048,4,4,source='bundled-definition')
            window.load_state(image,[old,manual,checked],[],'',None)
            window.select_map(old);window.open_map_tab()
            window.scanner=SimpleNamespace(source_digest=hashlib.sha256(image.materialize()).digest(),isRunning=lambda:False)
            window.scan_finished([source,alias,overlaps_reviewed])
            assert window.maps==[source,alias,manual,checked]
            assert not window.map_editors and window.selected is source
            window.scan_finished([source,alias])
            assert len(window.maps)==4
            # The ordinary BIN-open path starts the offline worker, without an
            # external XDF dialog. Use a synthetic marker file, no private copy.
            marker=bytearray(65536);marker[8:14]=b'430069'
            path=tmp_path/'synthetic-marker.bin';path.write_bytes(marker)
            window.saved_fingerprint=window.project_state()
            with patch('ecu_studio.ui.main_window.QFileDialog.getOpenFileName',return_value=(str(path),'')),patch.object(window,'scan_maps') as scan:
                window.open_bin()
                scan.assert_called_once()
        finally:
            window.scanner=None
            window.saved_fingerprint=window.project_state()
            window.close();app.processEvents()
