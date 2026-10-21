"""v1.7: exact-hash identity, axis hints, map-aware diff and failure guards."""
import hashlib
import json
import struct
from pathlib import Path
import pytest

from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.compare_maps import compare_images, export_map_comparison_csv
from ecu_studio.core.axis_inference import suggest_adjacent_axes
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.identity_registry import (identify_vehicle, import_identity_manifest, identity_stats)


def test_bosch_ascii_family_hint_does_not_claim_vehicle():
    payload=bytearray(32768)
    payload[128:133]=b'BOSCH'
    payload[192:203]=b'EDC17CP20AA'
    item=identify_vehicle(BinaryImage(bytes(payload)))
    assert item.level=='text-hint'
    assert item.family=='Bosch EDC17'
    assert item.brand=='' and item.model=='' and item.software==''
    payload[128:133]=b'xxxxx'
    assert identify_vehicle(BinaryImage(bytes(payload))).level=='unknown'


def test_hash_firmware_identity_manual_review_and_family_unknown(tmp_path):
    data=bytes(range(256))*4
    binary=tmp_path/'approved.bin';binary.write_bytes(data)
    db=DefinitionCatalog(tmp_path/'catalog.sqlite')
    assert identify_vehicle(BinaryImage(data),db).level=='unknown'
    row={
        'firmware_sha256':hashlib.sha256(data).hexdigest(), 'byte_count':len(data),
        'brand':'Audi', 'model':'A4 Beispiel', 'engine':'Testmotor',
        'ecu':'Prüf-ECU', 'family':'Bosch MED/ME', 'software':'SW-123',
        'source':'Manuell geprüft: Werkstattbeispiel', 'reviewer':'Test-Bearbeiter',
        'firmware_file':'approved.bin','reviewed':True}
    manifest=tmp_path/'identities.json'
    manifest.write_text(json.dumps({'format':1,'records':[row]}),encoding='utf-8')
    assert import_identity_manifest(db,manifest)['processed']==1
    identity=identify_vehicle(BinaryImage(data),db)
    assert identity.level=='hash-reviewed' and identity.brand=='Audi'
    assert identity_stats(db)==1
    assert identify_vehicle(BinaryImage(data+b'\x00'),db).brand==''
    row['firmware_sha256']='0'*64
    manifest.write_text(json.dumps({'format':1,'records':[row]}))
    with pytest.raises(ValueError,match='SHA-256'):import_identity_manifest(db,manifest)
    assert identity_stats(db)==1


def test_no_unreviewed_bulk_identity_or_ambiguous_collision(tmp_path):
    data=b'\x13'*1024;(tmp_path/'a.bin').write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    row=dict(firmware_sha256=sha, byte_count=len(data),brand='Opel',model='Corsa',engine='',
             ecu='ECU',family='Bosch EDC16',software='S1',source='Reviewed note',reviewer='Technician',
             firmware_file='a.bin',reviewed=False)
    manifest=tmp_path/'batch.json'
    db=DefinitionCatalog(tmp_path/'db.sqlite')
    manifest.write_text(json.dumps({'format':1,'records':[row]}))
    with pytest.raises(ValueError,match='bestätigte'):import_identity_manifest(db,manifest)
    assert identity_stats(db)==0
    row['reviewed']=True
    manifest.write_text(json.dumps({'format':1,'records':[row]}))
    import_identity_manifest(db,manifest)
    row['brand']='BMW'
    manifest.write_text(json.dumps({'format':1,'records':[row]}))
    with pytest.raises(ValueError,match='Abweichende'):import_identity_manifest(db,manifest)
    assert identify_vehicle(BinaryImage(data),db).brand=='Opel'


def test_map_comparison_signed_stride_overlap_and_outside(tmp_path):
    a=bytearray(160)
    for r in range(3):
        for c in range(4):
            pos=16 +r*12+c*2
            a[pos:pos+2]=struct.pack('<h',-100+r*30+c*10)
    m=MapDefinition('Sample',16,3,4,'s16','little',factor=.1,kind='Unbekannt',
                    source='manual',minor_stride_bits=48)
    m.validate(len(a))
    b=bytearray(a)
    first=m.cell_offset(0,0);second=m.cell_offset(2,3)
    b[first:first+2]=struct.pack('<h',-90)
    b[second:second+2]=struct.pack('<h',1000)
    b[90]=7
    report=compare_images(bytes(a),bytes(b),[m])
    assert report['changed_bytes']==4  # 1 byte at first, 2nd & last, 1 outside
    assert report['changed_bytes_outside_maps']==1
    assert report['maps_changed']==1
    assert report['maps'][0]['changed_cells']==2
    assert report['maps'][0]['max_abs_raw_delta']>0
    path=tmp_path/'diff.csv';export_map_comparison_csv(report,path)
    assert 'Sample' in path.read_text(encoding='utf-8-sig')
    with pytest.raises(ValueError,match='unterschiedliche Länge'):
        compare_images(bytes(a),bytes(b)+b'0',[m])
    assert report['original_sha256']==hashlib.sha256(a).hexdigest()


def test_compare_same_and_changed_untagged_byte():
    a=bytes(100);b=bytes(100)
    r=compare_images(a,b,[])
    assert (r['changed_bytes'],r['changed_ranges_count'],r['maps_changed'])==(0,0,0)
    c=bytearray(a);c[2]=9;c[3]=6;c[42]=7
    r=compare_images(a,c)
    assert r['changed_ranges']==[(2,2),(42,1)]
    assert r['changed_bytes_outside_maps']==3


def test_axis_hints_never_auto_approve_and_no_false_meaning():
    buf=bytearray(2048)
    # Adjacent nontrivial monotonic X curve with increasing increments.
    vals=[100,102,106,114,122,134,148,164]
    for i,v in enumerate(vals):buf[256-16+i*2:256-14+i*2]=v.to_bytes(2,'big')
    for i in range(64):buf[256+i*2:258+i*2]=(1000+i*4).to_bytes(2,'big')
    m=MapDefinition('Unbekannt',256,8,8,'u16','big',source='heuristic')
    hints=suggest_adjacent_axes(BinaryImage(buf),m)
    assert hints and all(h.axis in ('X','Y','X/Y?') and h.score<=1 for h in hints)
    assert m.axes_x==[] and m.axes_y==[] and not m.verified
    assert suggest_adjacent_axes(BinaryImage(bytes(2048)),m)==[]


def test_qt_require_image_guard_if_available(monkeypatch):
    try:
        from PySide6.QtWidgets import QApplication
        from ecu_studio.ui.main_window import Window
    except ImportError:
        pytest.skip('Qt not available')
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    app=QApplication.instance() or QApplication([])
    ui=Window()
    assert ui.image is None
    ui.image=BinaryImage(b'ABCD')
    assert ui.require_image() is True
    ui.saved_fingerprint=ui.project_state()  # clean up without an interactive save prompt
    ui.close()
