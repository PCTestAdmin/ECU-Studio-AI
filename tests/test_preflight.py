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


def test_confidence_uses_measured_rates_and_marks_small_samples():
    table={'classes':{'pitch':{'n':210,'rate':.30,'families':['X']},
                      'code:2d:axes2':{'n':227,'rate':1.0,'families':['X']},
                      'code:2d:axis1':{'n':12,'rate':1.0,'families':['X']}}}
    a=MapDefinition('a',0,4,4,source='heuristic',record_layout='candidate:row-pitch')
    b=MapDefinition('b',0,4,4,source='heuristic',record_layout='candidate:code-reference',axes_x=[1,2,3,4],axes_y=[1,2,3,4])
    c=MapDefinition('c',0,4,4,source='heuristic',record_layout='candidate:code-reference',axes_x=[1,2,3,4])
    apply_confidence([a,b,c],table)
    assert (a.evidence_tier,a.calibrated_rate)==('Vermutung',.3)
    assert (b.evidence_tier,b.calibrated_rate)==('gesichert',1.0)
    assert evidence_class(c)=='code:2d:axis1' and c.evidence_tier=='nicht kalibriert' and c.calibrated_rate is None


def test_family_specific_rates_take_precedence_over_pooled():
    table={'classes':{'axis:count':{'n':2263,'rate':.44,'families':['A','B']}},
           'families':{'Siemens MS43':{'axis:count':{'n':601,'rate':.98}},
                       'Unbekannt':{'axis:count':{'n':1263,'rate':.18}}}}
    a=MapDefinition('a',0,1,6,source='heuristic',record_layout='candidate:count-axis')
    b=MapDefinition('b',0,1,6,source='heuristic',record_layout='candidate:count-axis')
    c=MapDefinition('c',0,1,6,source='heuristic',record_layout='candidate:count-axis')
    apply_confidence([a],table,family='Siemens MS43')
    apply_confidence([b],table,family=None)
    apply_confidence([c],table,family='Bosch ME7')          # unmeasured family -> pooled
    assert (a.calibrated_rate,a.evidence_tier)==(.98,'gesichert')
    assert (b.calibrated_rate,b.evidence_tier)==(.18,'Vermutung')
    assert c.calibrated_rate==.44


def test_bundled_candidate_model_scores_smooth_table_above_noise():
    import numpy as np
    from ecu_studio.core.candidate_model import load_model, score
    from ecu_studio.core.candidate_features import candidate_features
    model=load_model()
    assert model is not None and model['drop_below']<.5
    rng=np.random.default_rng(3)
    data=bytearray(rng.integers(0,256,4096,dtype=np.uint8).tobytes())
    t=np.array([[30+6*r+4*c for c in range(10)] for r in range(8)],np.uint8)
    data[0x400:0x400+t.size]=t.tobytes()
    image=BinaryImage(bytes(data))
    smooth=score(candidate_features(image,MapDefinition('t',0x400,8,10,dtype='u8')),model)
    noise=score(candidate_features(image,MapDefinition('n',0x800,8,10,dtype='u8')),model)
    assert smooth>noise
