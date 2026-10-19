"""Focused safety and precision checks for semantic labels and reference hints."""
import csv
from pathlib import Path
import struct
import random
import numpy as np
import pytest

from ecu_studio.core.intelligence import (classify_metadata, classify_raw_without_metadata,
    suggest_reference_shapes, export_detection_report, label_from_metadata)
from ecu_studio.core.model import MapDefinition, BinaryImage, load_project, save_project
from ecu_studio.core.library import MapLibrary
from ecu_studio.core.detection_signed import scan_s16
from ecu_studio.core.extended_demo import generate_extended_demo
from ecu_studio.core.a2l import read_a2l


@pytest.mark.parametrize('name,expected', [
    ('BOOST_REQUEST','Ladedruck-Sollwert'),
    ('BOOST_PRESSURE_LIMITER','Ladedruckbegrenzung'),
    ('BOOST_CONTROL_PID','Ladedruck-Regelung'),
    ('EGR_RATE','AGR-Sollwert / Rate'),
    ('EGR_VALVE_CONTROL','AGR-Regelung'),
    ('TORQUE_MAX','Drehmomentbegrenzung'),
    ('INJECTION_QUANTITY','Einspritzmenge'),
    ('INJECTION_DURATION','Einspritzdauer'),
    ('START_OF_INJECTION','Einspritzbeginn / SOI'),
    ('PILOT_INJECTION','Voreinspritzung'),
    ('RAIL_PRESSURE_REQUEST','Raildruck-Sollwert'),
    ('RAIL_PRESSURE_LIMIT','Raildruckbegrenzung'),
    ('IGNITION_ADVANCE','Zündwinkel'),
    ('KNOCK_CONTROL','Klopfregelung'),
    ('LAMBDA_TARGET','Lambda-Sollwert'),
    ('SMOKE_LIMITER','Lambda-Begrenzung / Rauch'),
    ('WASTEGATE_REQUEST','Wastegate-Steuerung'),
    ('VTG_POSITION','VTG/VNT-Stellung'),
    ('DRIVER_WISH_PEDAL','Fahrerwunsch / Pedal'),
    ('IDLE_SPEED_REQUEST','Leerlauf-Sollwert'),
    ('RPM_LIMITER','Drehzahlbegrenzung'),
    ('THERMAL_PROTECTION','Temperaturschutz'),
    ('DPF_REGENERATION','DPF-Regeneration'),
    ('SCR_DOSING','SCR / AdBlue-Dosierung'),
    ('NOX_MODEL','NOx-Sensorik / Modell'),
    ('DIAGNOSTIC_THRESHOLD','Diagnoseschwelle / DTC'),
    ('THROTTLE_POSITION','Drosselklappe'),
])
def test_named_metadata_specific(name,expected):
    result = classify_metadata(name)
    assert result.kind == expected
    assert 0.5 < result.score < 1.0
    assert result.origin == 'Metadaten-Regel'
    assert result.evidence


def test_raw_data_no_false_semantics():
    for noise in ('random 16x16 table','data 1234', 'AGRAVATION', 'BOOSTER PUMP'):
        assert classify_metadata(noise).kind == 'Unbekannt'
    assert classify_raw_without_metadata().kind == 'Unbekannt'
    assert classify_raw_without_metadata().score == 0


def test_override_never_changes_user_verified_or_explicit_kind():
    m=MapDefinition('RAIL_PRESSURE_TARGET',0,kind='Unbekannt',verified=True)
    assert not label_from_metadata(m)
    assert m.kind == 'Unbekannt'
    m.verified=False
    assert label_from_metadata(m)
    assert m.kind == 'Raildruck-Sollwert'
    m.name='EGR_RATE'
    assert not label_from_metadata(m)
    assert m.kind == 'Raildruck-Sollwert'


def test_a2l_label_evidence_reaches_map(tmp_path):
    file,a2l = generate_extended_demo(str(tmp_path))
    linked=read_a2l(str(a2l)).link(file_size=file.stat().st_size,
                                     ecu_anchor=0x800000,file_anchor=0)
    assert len(linked.maps)==14
    kinds={m.kind for m in linked.maps}
    assert 'Ladedruck-Sollwert' in kinds and 'Raildruck-Sollwert' in kinds
    assert 'AGR-Sollwert / Rate' in kinds and 'Zündwinkel' in kinds
    assert all(m.label_origin and m.label_evidence and not m.verified for m in linked.maps)


def test_shape_hints_not_equal_verification(tmp_path):
    rng=np.random.default_rng(2)
    # Distinctive structured 2D surface, different positions and modified amplitude.
    x=np.linspace(-1,1,16)[None,:]
    y=np.linspace(-1,1,16)[:,None]
    surface=np.round(1700 + 230*np.sin(x*3) + 150*np.cos(y*4) + 105*x*y).astype('>u2')
    ref=BinaryImage(surface.tobytes()+b'\xff'*80)
    base=MapDefinition('VTG_POSITION',0,16,16,'u16','big',kind='VTG/VNT-Stellung',verified=True)
    library=MapLibrary(tmp_path/'shapes.json')
    library.add(ref,base)
    shifted=np.round(surface.astype(float)*1.2 + 55).astype('>u2')
    image=BinaryImage(b'\xff'*500+shifted.tobytes()+b'\xff'*100)
    candidate=MapDefinition('Kandidat',500,16,16,'u16','big',source='heuristic')
    assert suggest_reference_shapes(image,[candidate],library.signatures)==1
    assert candidate.kind=='VTG/VNT-Stellung'
    assert candidate.label_origin == 'Referenzform (ungeprüft)'
    assert not candidate.verified and candidate.type_score < .7


def test_linear_surface_does_not_imply_reference_type(tmp_path):
    arr=np.fromfunction(lambda r,c:500+12*r+21*c,(16,16)).astype('>u2')
    img=BinaryImage(arr.tobytes())
    m=MapDefinition('linear',0,16,16,'u16','big',kind='Ladedruck-Sollwert',verified=True)
    lib=MapLibrary(tmp_path/'linear.json');lib.add(img,m)
    target=MapDefinition('unbekannt',0,16,16,'u16','big',source='heuristic')
    assert suggest_reference_shapes(img,[target],lib.signatures)==0
    assert target.kind=='Unbekannt'


def test_signed_negative_map_detected():
    data=bytearray(random.Random(53).randbytes(8000))
    for r in range(16):
        for c in range(16):
            struct.pack_into('>h',data,0x800+(r*16+c)*2,-1800+40*r+22*c)
    found=scan_s16(BinaryImage(bytes(data)),max_results=25,scan_mb=1)
    assert any(m.offset==0x800 and m.dtype=='s16' and not m.verified for m in found)


def test_detection_report_and_persistence(tmp_path):
    img_path=tmp_path/'demo.bin';img_path.write_bytes(b'\x00'*512)
    img=BinaryImage.from_file(str(img_path))
    m=MapDefinition('BOOST_REQUEST',8,4,4,kind='Ladedruck-Sollwert',label_origin='Metadaten-Regel',
                    label_evidence='BOOST_REQUEST',type_score=.8,type_alternatives=['Ladedruck / Boost'])
    report=tmp_path/'report.csv'
    export_detection_report(str(report),[m])
    with report.open(encoding='utf-8-sig',newline='') as file:
        rows=list(csv.DictReader(file,delimiter=';'))
    assert rows[0]['Typ / Vorschlag']=='Ladedruck-Sollwert'
    project=tmp_path/'calibration.ecuproject'
    save_project(str(project),img,[m],[],'')
    _,maps,_,_=load_project(str(project))
    assert maps[0].type_score==.8 and maps[0].type_alternatives==['Ladedruck / Boost']


def test_a2l_unknown_category_can_take_unique_exact_reference_only():
    from ecu_studio.core.intelligence import enrich_with_exact_references
    m=MapDefinition('KFX_9847',100,8,16,kind='Unbekannt',source='a2l')
    ref=MapDefinition('Rail',100,8,16,kind='Raildruck-Sollwert',source='exact-reference')
    assert enrich_with_exact_references([m],[ref])==1
    assert m.kind=='Raildruck-Sollwert' and not m.verified
    assert 'ungeprüft' in m.label_origin.lower()
    second=MapDefinition('EGR',100,8,16,kind='AGR-Sollwert / Rate',source='exact-reference')
    fresh=MapDefinition('Unknown',100,8,16,source='a2l')
    assert enrich_with_exact_references([fresh],[ref,second])==0
    assert fresh.kind=='Unbekannt'
    confirmed=MapDefinition('Confirmed',100,8,16,kind='Manuell',verified=True)
    assert enrich_with_exact_references([confirmed],[ref])==0
