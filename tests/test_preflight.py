import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.preflight import run_preflight
from ecu_studio.core.confidence import apply_confidence, evidence_class


def _table(rows, cols, base):
    return np.array([[base+3*r+5*c for c in range(cols)] for r in range(rows)],np.uint8)


def _image():
    data=bytearray(np.random.default_rng(4).integers(0,256,0x4000,dtype=np.uint8).tobytes())
    t=_table(8,8,20)
    data[0x1000:0x1040]=t.tobytes()            # table
    data[0x2000:0x2040]=t.tobytes()            # identical monitoring copy
    axes=bytes([6,10,20,30,40,50,60])+bytes([4,1,2,3,4])+bytes([3,5,9,13])+bytes([3,2,4,6])
    data[0x3000:0x3000+len(axes)]=axes
    m=MapDefinition('KF',0x1000,8,8,dtype='u8')
    return BinaryImage(bytes(data)),[m]


def test_unchanged_image_is_green():
    image,maps=_image()
    assert run_preflight(image,maps).status=='grün'


def test_modifying_one_twin_only_is_red():
    image,maps=_image()
    image.write(0x1000+9,bytes([image.byte(0x1000+9)+2]))
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    assert any(f.code=='twin' and f.offset==0x2000 for f in report.findings)
    assert report.status=='rot'


def test_twin_changed_too_is_not_reported():
    image,maps=_image()
    for base in (0x1000,0x2000):
        image.write(base+9,bytes([image.byte(base+9)+2]))
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    assert not any(f.code=='twin' for f in report.findings)


def test_broken_axis_order_and_large_jump_are_flagged():
    image,maps=_image()
    image.write(0x3003,bytes([5]))                  # 10,20,5,40 ... no longer increasing
    image.write(0x1000+27,bytes([250]))             # isolated spike in the table
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    codes={f.code for f in report.findings}
    assert 'axis' in codes and 'jump' in codes


def test_change_outside_calibration_window_is_red():
    image,maps=_image()
    image.write(0x100,b'\x00')
    report=run_preflight(image,maps,cal_window=(0x1000,0x4000))
    assert any(f.code=='code' and f.level=='rot' for f in report.findings)


def test_confidence_shows_the_kind_of_evidence_never_a_rate():
    from ecu_studio.core.confidence import CODE, DATA_PATTERN, STRUCTURE, describe, is_experimental
    from ecu_studio.core.structure_scan import PRELOOKUP_ORIGIN
    table={'classes':{'pitch':{'n':210,'rate':.30,'families':['X']},     # a 1.18 rate table is ignored
                      'code:2d:axes2':{'n':227,'rate':1.0,'families':['X']}}}
    a=MapDefinition('a',0,4,4,source='heuristic',record_layout='candidate:row-pitch')
    b=MapDefinition('b',0,4,4,source='heuristic',record_layout='candidate:code-reference',axes_x=[1,2,3,4],axes_y=[1,2,3,4])
    c=MapDefinition('c',0,1,6,source='heuristic',record_layout='candidate:count-axis')
    d=MapDefinition('d',0,4,4,source='heuristic',record_layout='candidate:code-call',label_origin=PRELOOKUP_ORIGIN)
    e=MapDefinition('e',0,4,4,source='heuristic')                         # plain smoothness
    defined=MapDefinition('f',0,4,4,source='xdf')
    apply_confidence([a,b,c,d,e,defined],table,family='X')
    assert [m.evidence_tier for m in (a,b,c,d,e)]==[DATA_PATTERN,CODE,STRUCTURE,CODE,DATA_PATTERN]
    assert all(m.calibrated_rate is None for m in (a,b,c,d,e,defined)) and defined.evidence_tier==''
    assert is_experimental(d) and not any(is_experimental(m) for m in (a,b,c,e))
    assert 'experimentell' in describe(d) and 'experimentell' not in describe(b)
    for m in (a,b,c,d,e):
        assert '%' not in m.notes and 'keine Wahrscheinlichkeit' in m.notes and 'nicht unabhängig validiert' in m.notes


def test_rates_saved_by_older_versions_are_not_shown_after_loading(tmp_path):
    from ecu_studio.core.model import load_project, save_project
    from ecu_studio.core.confidence import DATA_PATTERN
    f=tmp_path/'fw.bin'
    f.write_bytes(bytes(range(256))*4)
    image=BinaryImage.from_file(str(f))
    old=MapDefinition('alt',0x40,4,4,source='heuristic',record_layout='candidate:row-pitch',evidence_tier='Vermutung',
                      calibrated_rate=.23,notes='Glatte Fläche. Evidenzklasse pitch: 23% Treffer (n=1135, gemessen: '
                      'alle Familien: Siemens MS43, Bosch ME9) – Vermutung. Lernmodell (familienübergreifend geprüft): '
                      'Score 0.41, gemessene Trefferquote dieses Score-Bereichs 31%. Eigene Notiz.')
    checked=MapDefinition('geprüft',0x80,4,4,source='heuristic',verified=True,calibrated_rate=.97,
                          notes='Evidenzklasse code:2d:axes2: 97% Treffer (n=227, gemessen: Siemens MS43) – gesichert.')
    save_project(str(tmp_path/'p.ecustudio'),image,[old,checked],[],'')
    _,maps,_,_=load_project(str(tmp_path/'p.ecustudio'))
    loaded,confirmed=maps
    assert loaded.calibrated_rate is None and loaded.evidence_tier==DATA_PATTERN
    assert '%' not in loaded.notes and 'Glatte Fläche.' in loaded.notes and 'Eigene Notiz.' in loaded.notes
    assert confirmed.verified and confirmed.calibrated_rate is None and '%' not in confirmed.notes


def test_no_learned_model_is_shipped_and_the_scorer_needs_cleared_data():
    from ecu_studio.core import candidate_model
    candidate_model.load_model.cache_clear()
    assert not candidate_model.DATA.exists() and candidate_model.read_model() is None
    assert candidate_model.load_model() is None and candidate_model.model_status()==candidate_model.NO_MODEL


def _code_image():
    """Code-like noise with one smooth data block holding a map at 0x1000."""
    data=bytearray(np.random.default_rng(9).integers(0,256,0x4000,dtype=np.uint8).tobytes())
    t=np.array([[20+r+c for c in range(16)] for r in range(16)],np.uint8)
    data[0x1000:0x1100]=t.tobytes()
    return BinaryImage(bytes(data)),[MapDefinition('KF',0x1000,16,16,dtype='u8')]


def test_run_partly_in_map_does_not_hide_code_bytes():
    # Regression: one contiguous edit from the map into code was judged as a whole
    # and passed because it touched the map.
    image,maps=_code_image()
    image.write(0x10F8,bytes(0x18))                   # 8 bytes map + 16 bytes code
    report=run_preflight(image,maps)
    code=[f for f in report.findings if f.code=='code']
    assert code and code[0].offset==0x1100 and code[0].detail.startswith('16 Byte')
    assert report.status=='rot'
    assert any(f.code=='unmapped' and f.title.startswith('16 ') for f in report.findings)


def test_change_crossing_calibration_window_reports_outside_bytes_only():
    image,maps=_image()
    image.write(0x0FFC,bytes(b^0xFF for b in image.original[0x0FFC:0x1004]))   # 4 before window, 4 inside
    report=run_preflight(image,maps,cal_window=(0x1000,0x4000))
    code=[f for f in report.findings if f.code=='code']
    assert len(code)==1 and code[0].offset==0x0FFC and code[0].detail.startswith('4 Byte')


def test_many_code_changes_are_counted_not_truncated():
    image,maps=_image()
    for k in range(15):
        image.write(0x100+0x20*k,bytes([image.byte(0x100+0x20*k)^0xFF]))
    report=run_preflight(image,maps,cal_window=(0x1000,0x4000))
    code=[f for f in report.findings if f.code=='code']
    assert len(code)==11 and 'insgesamt 15 Byte in 15 Bereichen' in code[-1].title


def test_changes_are_taken_from_bytes_not_edit_log():
    image,maps=_image()
    image._patches[0x200]=image.original[0x200]       # logged but identical: no change
    assert run_preflight(image,maps,cal_window=(0x1000,0x4000)).changed_bytes==0
    image.write(0x300,bytes([image.byte(0x300)^1]))
    report=run_preflight(image,maps,cal_window=(0x1000,0x4000))
    assert report.changed_bytes==1 and any(f.code=='code' and f.offset==0x300 for f in report.findings)


def test_unverified_heuristic_candidate_does_not_excuse_code_changes():
    image,_=_code_image()
    guess=MapDefinition('Kandidat',0x2000,8,8,dtype='u8',source='heuristic')
    image.write(0x2004,b'\x00')
    report=run_preflight(image,[guess])
    assert any(f.code=='code-candidate' and f.level=='gelb' for f in report.findings)


def test_green_without_verified_checksum_is_never_checks_passed():
    image,maps=_image()
    report=run_preflight(image,maps)
    assert report.status=='grün' and not report.checks_passed
    assert 'nicht flashbereit' in report.text()
    image.write(0x1000+9,bytes([image.byte(0x1000+9)+1]))
    image.write(0x2000+9,bytes([image.byte(0x2000+9)+1]))
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    assert not report.checks_passed and any(f.code=='checksum' for f in report.findings)


def test_one_byte_in_identical_twin_is_not_a_full_adaptation():
    # Regression: any touched byte in the copy counted as "adapted".
    image,maps=_image()
    for k in range(0,8):
        image.write(0x1000+8+k,bytes([image.byte(0x1000+8+k)+3]))     # whole row 1 of the map
    image.write(0x2000+8,bytes([image.byte(0x2000+8)+3]))             # only one byte in the copy
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    partial=[f for f in report.findings if f.code=='twin-partial']
    assert partial and partial[0].offset==0x2000 and '7 von 64' in partial[0].detail
    assert report.status=='rot'


def test_twin_reported_once_per_pair_and_equal_change_passes():
    image,maps=_image()
    maps=maps+[MapDefinition('Kopie',0x2000,8,8,dtype='u8')]
    for base in (0x1000,0x2000):
        image.write(base+9,bytes([image.byte(base+9)+2]))
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    assert not [f for f in report.findings if f.code.startswith('twin')]


def test_similar_twins_changed_at_different_cells_are_flagged():
    image,maps=_image()
    data=bytearray(image.original)
    t=_table(8,8,20).astype(np.int16)+np.eye(8,dtype=np.int16)        # near copy, not identical
    data[0x2800:0x2840]=t.astype(np.uint8).tobytes()
    image=BinaryImage(bytes(data))
    maps=maps+[MapDefinition('Ähnlich',0x2800,8,8,dtype='u8')]
    image.write(0x1000+3,bytes([image.byte(0x1000+3)+1]))
    image.write(0x2000+3,bytes([image.byte(0x2000+3)+1]))              # keep exact twin consistent
    image.write(0x2800+40,bytes([image.byte(0x2800+40)+1]))            # other cell in the similar map
    report=run_preflight(image,maps,cal_window=(0,0x4000))
    assert any(f.code=='twin-similar-partial' for f in report.findings)


def test_status_levels_are_never_conflated():
    # Until PR #19 review a matching profile set checksum_verified even when it declared only some
    # checksums (complete=False). Now: a partial profile proves its declared slots only; complete
    # coverage needs the reviewer's completeness confirmation (or a 'gueltig' integrity report).
    from ecu_studio.core.checksum_audit import ChecksumSlot, ChecksumProfile, slot_value
    image,maps=_image()
    data=bytearray(image.original)
    slot=ChecksumSlot('cal','sum16-bytes',0x1000,0x1040,0x3FF0)
    data[0x3FF0:0x3FF2]=slot_value(BinaryImage(bytes(data)),slot).to_bytes(2,'big')
    image=BinaryImage(bytes(data))
    partial=ChecksumProfile(image.digest,'test','reviewer',True,(slot,))
    report=run_preflight(image,maps,checksum_profile=partial)
    assert report.profile_status=='match' and report.known_checksums_ok
    assert not report.checksum_verified and not report.checks_passed and report.status=='grün'
    assert 'UNVOLLSTÄNDIG' in report.checksum_summary
    complete=ChecksumProfile(image.digest,'test','reviewer',True,(slot,),complete=True)
    report=run_preflight(image,maps,checksum_profile=complete)
    assert report.checksum_verified and report.status=='grün' and report.checks_passed
    assert report.flash_validated is False and report.signatures_checked is False
    labels=[label for label,_ in report.stages()]
    assert labels==['Profil-Prüffelder','Bekannte Prüfsummen','Checksummenabdeckung','Signaturen',
                    'Preflight','Flashfreigabe']
    stages=dict(report.stages())
    assert 'nicht geprüft' in stages['Signaturen'] and stages['Flashfreigabe'].startswith('keine')
    assert 'PRÜFSTATUS' in report.text() and 'Flashfreigabe' in report.checksum_summary
