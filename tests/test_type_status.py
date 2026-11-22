"""Data type status per property and scaling with its source (after 1.21.0-rc1, synthetic)."""
import numpy as np
from ecu_studio.core.a2l import limit_violations, parse_a2l
from ecu_studio.core.axis_records import ENDIAN_OPEN
from ecu_studio.core.confidence import WIDTH_OPEN, dtype_doubt
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.type_status import (ALTERNATIVE, CODE, CONFIRMED, DERIVED, EQUAL, UNDETERMINED, RAW, KNOWN,
                                         CHECKED, BYTE_ORDER, SIGN, WIDTH, scaling_of, summary, type_status)


def cand(layout, **kw):
    base = dict(name='c', offset=0, rows=4, cols=4, dtype='u16', endian='little', source='heuristic',
                record_layout=layout)
    base.update(kw)
    return MapDefinition(**base)


def image(values, dtype='<u2'):
    return BinaryImage(np.asarray(values, dtype).tobytes())


def test_definition_values_are_confirmed_with_their_source():
    m = MapDefinition(name='KF', offset=0, rows=2, cols=2, dtype='s16', endian='big', source='a2l')
    st = type_status(m)
    assert [p.status for p in st.properties] == [CONFIRMED] * 3
    assert all('a2l' in p.source for p in st.properties)
    assert st.overall == CONFIRMED


def test_pattern_only_candidate_is_undetermined_in_every_property():
    m = cand('candidate:row-pitch')
    st = type_status(m, image([1, 2, 3, 4] * 4))
    assert st.get(WIDTH).status == UNDETERMINED
    assert st.get(BYTE_ORDER).status == UNDETERMINED
    assert st.overall == UNDETERMINED
    assert dtype_doubt(m)          # the "?" of the list stays


def test_open_sign_is_an_alternative_with_the_other_reading():
    m = cand('candidate:nx,ny,x,y,z', dtype_alternatives=['s16'])
    st = type_status(m, image([0x8001] * 16))
    sign = st.get(SIGN)
    assert sign.status == ALTERNATIVE and sign.alternatives == ('s16',)
    assert st.overall == ALTERNATIVE
    assert 'auch möglich: s16' in sign.describe()


def test_equal_readings_are_not_evidence_of_the_type():
    """No top bit set: both readings give the same numbers, which does not tell what the code uses."""
    m = cand('candidate:nx,ny,x,y,z')
    sign = type_status(m, image([1, 2, 3] * 5 + [4])).get(SIGN)
    assert sign.status == EQUAL and sign.status not in (CONFIRMED, CODE, DERIVED)
    assert 'nicht belegt' in sign.source


def test_code_call_sign_comes_from_the_load_instructions():
    m = cand('candidate:code-call', dtype='s16')
    sign = type_status(m, image([0xFFF0] * 16)).get(SIGN)
    assert sign.status == CODE and 'Ladebefehle' in sign.source
    assert type_status(m, image([1] * 16)).get(SIGN).status == CODE       # code evidence beats equal values


def test_disagreeing_load_instructions_are_shown_as_contradiction():
    m = cand('candidate:code-call', dtype='s16', dtype_alternatives=['u16'])
    sign = type_status(m, image([0xFFF0] * 16)).get(SIGN)
    assert sign.status == ALTERNATIVE and 'uneinig' in sign.contradiction and 'Widerspruch' in sign.describe()


def test_proposals_are_never_confirmed_and_carry_no_conversion():
    for source in ('transfer-proposed', 'xdf-preview', 'exact-reference'):
        m = MapDefinition(name='KF', offset=0, rows=2, cols=2, dtype='s16', source=source, factor=0.1, unit='Nm')
        st = type_status(m)
        assert {p.status for p in st.properties} == {DERIVED} and st.overall != CONFIRMED
        assert scaling_of(m).status == RAW
    manual = MapDefinition(name='KF', offset=0, rows=2, cols=2, source='manual_2d')
    assert type_status(manual).overall == UNDETERMINED
    reranked = cand('candidate:row-pitch', source='ml-proposed')
    assert type_status(reranked, image([1, 2, 3, 4] * 4)).overall == UNDETERMINED


def test_definition_conflict_is_said_aloud_without_changing_the_status():
    m = MapDefinition(name='KF', offset=0x40, rows=2, cols=2, dtype='u16', endian='big', source='a2l')
    text = '0x40: Vorzeichen – behalten Definition „KF“, verworfen Datensatz (s16 big). Belegt: u16 big.'
    sign = type_status(m, conflicts=[text]).get(SIGN)
    assert sign.status == CONFIRMED and sign.contradiction
    assert type_status(m).get(SIGN).contradiction == ''


def test_open_width_and_byte_order_are_alternatives():
    m = cand('candidate:nx,ny,x,y,z', notes=f'{WIDTH_OPEN}. {ENDIAN_OPEN}: uneinig.')
    st = type_status(m)
    assert st.get(WIDTH).status == ALTERNATIVE and st.get(WIDTH).alternatives == ('8 Bit',)
    assert st.get(BYTE_ORDER).status == ALTERNATIVE and st.get(BYTE_ORDER).alternatives == ('big',)


def test_byte_values_have_no_byte_order_question():
    m = cand('candidate:nx,ny,x,y,z', dtype='u8')
    assert type_status(m).get(BYTE_ORDER) is None


def test_every_open_status_has_a_question_mark_in_the_list():
    cases = [cand('candidate:row-pitch'), cand('candidate:nx,ny,x,y,z', dtype_alternatives=['s16']),
             cand('candidate:nx,ny,x,y,z', notes=WIDTH_OPEN), cand('candidate:nx,ny,x,y,z', notes=ENDIAN_OPEN)]
    for m in cases:
        if type_status(m).overall in (ALTERNATIVE, UNDETERMINED):
            assert dtype_doubt(m), m


def test_candidates_never_carry_an_established_conversion():
    s = scaling_of(cand('candidate:code-call'))
    assert s.status == RAW and (s.factor, s.offset, s.unit) == (1.0, 0.0, '')
    carried = scaling_of(cand('candidate:code-call', factor=0.1, unit='Nm'))
    assert carried.status == RAW and 'ungeprüft' in carried.source


def test_checked_and_definition_scaling_keep_their_source():
    m = MapDefinition(name='KF', offset=0, factor=0.5, bias=-40, unit='°C', source='a2l',
                      scaling_source='A2L COMPU_METHOD CM_T (RAT_FUNC)')
    s = scaling_of(m)
    assert s.status == KNOWN and s.source == 'A2L COMPU_METHOD CM_T (RAT_FUNC)'
    assert 'phys = roh × 0.5 + -40 [°C]' in s.describe()
    m.verified = True
    assert scaling_of(m).status == CHECKED


def test_unsupported_a2l_conversion_stays_raw():
    m = MapDefinition(name='KF', offset=0, source='a2l', notes='Umrechnung TAB_VERB nicht unterstützt: Rohwerte.',
                      scaling_source='A2L COMPU_METHOD CM_V (TAB_VERB): TAB_VERB nicht unterstützt: Rohwerte')
    s = scaling_of(m)
    assert s.status == RAW and 'TAB_VERB' in s.source


def test_summary_has_one_line_per_property_and_the_conversion():
    lines = summary(cand('candidate:row-pitch'), image([1] * 16))
    assert len(lines) == 4 and lines[-1].startswith('Umrechnung: Unbekannt: Rohwerte')


A2L = """
/begin PROJECT P "" /begin MODULE M ""
/begin MOD_COMMON "" BYTE_ORDER MSB_LAST /end MOD_COMMON
/begin COMPU_METHOD CM_LIN "" LINEAR "%6.2" "Nm" COEFFS_LINEAR 0.5 -10 /end COMPU_METHOD
/begin COMPU_METHOD CM_VERB "" TAB_VERB "%6.2" "" /end COMPU_METHOD
/begin RECORD_LAYOUT RL_U16 FNC_VALUES 1 UWORD COLUMN_DIR DIRECT /end RECORD_LAYOUT
/begin CHARACTERISTIC V_LIN "" VAL_BLK 0x10 RL_U16 0 CM_LIN -10 100 NUMBER 4 /end CHARACTERISTIC
/begin CHARACTERISTIC V_VERB "" VAL_BLK 0x20 RL_U16 0 CM_VERB 0 3 NUMBER 2 /end CHARACTERISTIC
/end MODULE /end PROJECT
"""


def test_a2l_link_records_the_conversion_source_and_limits():
    cat = parse_a2l(A2L)
    assert {c.name: c.limits for c in cat.characteristics} == {'V_LIN': (-10.0, 100.0), 'V_VERB': (0.0, 3.0)}
    data = bytearray(0x40)
    data[0x10:0x18] = np.array([0, 20, 40, 220], '<u2').tobytes()
    res = cat.link(file_size=len(data), data=bytes(data), raw_unsupported_conversions=True)
    by = {m.name: m for m in res.maps}
    assert by['V_LIN'].scaling_source == 'A2L COMPU_METHOD CM_LIN (LINEAR)'
    assert scaling_of(by['V_LIN']).status == KNOWN
    assert 'TAB_VERB' in by['V_VERB'].scaling_source and scaling_of(by['V_VERB']).status == RAW


def test_limits_can_only_contradict():
    assert limit_violations([-10, 0, 99.9, 100.2], (-10.0, 100.0), factor=0.5) == 0    # within half a step
    assert limit_violations([-10, 101], (-10.0, 100.0), factor=0.5) == 1
    assert limit_violations([1e9], None) == 0                                          # no limits: no statement


def axis(values, dtype='s16', layout='candidate:count-axis'):
    return cand(layout, rows=1, cols=len(values), dtype=dtype), image(values, '<i2' if dtype == 's16' else '<u2')


def test_axis_sign_follows_from_the_only_rising_reading():
    from ecu_studio.core.type_status import open_axis_signs
    m, img = axis([-20, -10, 0, 10, 20])          # rises signed only
    assert open_axis_signs(img, [m]) == 0 and m.dtype_alternatives == []
    sign = type_status(m, img).get(SIGN)
    assert sign.status == DERIVED and 'steigende' in sign.source


def test_axis_rising_in_both_readings_keeps_the_sign_open():
    from ecu_studio.core.type_status import open_axis_signs
    m, img = axis([-40, -30, -20, -10])           # all negative: u16 rises as well
    assert open_axis_signs(img, [m]) == 1 and m.dtype_alternatives == ['u16']
    assert type_status(m, img).get(SIGN).status == ALTERNATIVE and dtype_doubt(m)


def test_axis_switch_off_changes_nothing():
    from ecu_studio.core import type_status as ts
    m, img = axis([-40, -30, -20, -10])
    old = ts.AXIS_SIGN_OPEN
    ts.AXIS_SIGN_OPEN = False
    try:
        assert ts.open_axis_signs(img, [m]) == 0 and m.dtype_alternatives == []
    finally:
        ts.AXIS_SIGN_OPEN = old


def test_curve_values_with_top_bit_keep_the_unsigned_reading_open():
    from ecu_studio.core import curve_records
    from ecu_studio.core.curve_records import CURVE_LAYOUT, scan_curve_records
    rec = np.array([4, 100, 200, 400, 800, 0xFFF0, 0xFFF8, 5, 9], '<u2').tobytes()   # n, rising axis, values
    img = BinaryImage(bytes(64) + rec + bytes(0x400))
    # 30 header records of the image (byte-order vote); the first starts right after the curve (chain)
    heads = [MapDefinition(name='h', offset=90 + 40 * i, rows=2, cols=2, dtype='u16', endian='little',
                           source='heuristic', record_layout='candidate:nx,ny,x,y,z',
                           candidate_region_start=82 + 40 * i) for i in range(30)]
    curve = [c for c in scan_curve_records(img, heads) if c.record_layout == CURVE_LAYOUT]
    assert [(c.dtype, c.dtype_alternatives) for c in curve] == [('s16', ['u16'])]
    assert dtype_doubt(curve[0])
    old = curve_records.CURVE_SIGN_OPEN
    curve_records.CURVE_SIGN_OPEN = False
    try:
        assert [c.dtype_alternatives for c in scan_curve_records(img, heads) if c.record_layout == CURVE_LAYOUT] == [[]]
    finally:
        curve_records.CURVE_SIGN_OPEN = old
