"""Three recognition layers: definitions stay, code/structure fills gaps, patterns last; conflicts are listed."""
import numpy as np
from ecu_studio.core.fusion import fuse, annotate, layer_of, definition_check, disagreement, sign_matters
from ecu_studio.core.model import BinaryImage, MapDefinition


def image():
    data = bytearray(0x4000)
    y, x = np.mgrid[:8, :8]
    data[0x100:0x180] = ((10 + 3 * y + 2 * x) * 20).astype('<u2').tobytes()
    data[0x400:0x480] = bytes([0xFF]) * 0x80
    data[0x500:0x580] = ((y * 8 + x) * 1500).astype('<u2').tobytes()      # top bits set from 0x8000 on
    return BinaryImage(bytes(data))


def defined(offset=0x100, **kw):
    kw = {'rows': 8, 'cols': 8, 'dtype': 'u16', 'endian': 'little', 'source': 'xdf', **kw}
    return MapDefinition(f'Def @ {offset:X}', offset, **kw)


def detected(offset=0x100, layout='candidate:code-call', **kw):
    kw = {'rows': 8, 'cols': 8, 'dtype': 'u16', 'endian': 'little', 'source': 'heuristic',
          'record_layout': layout, **kw}
    return MapDefinition(f'Kandidat @ {offset:X}', offset, **kw)


def test_layers():
    assert layer_of(defined()) == 1
    assert layer_of(MapDefinition('m', 0, source='heuristic', verified=True)) == 1
    assert layer_of(detected()) == 2
    assert layer_of(detected(layout='candidate:nx,ny,x,y,z')) == 2
    assert layer_of(detected(layout='candidate:row-pitch')) == 3
    assert layer_of(MapDefinition('m', 0, source='ml-proposed')) == 3


def test_equal_detection_confirms_the_definition_without_a_duplicate():
    d = defined()
    r = fuse(image(), [d], [detected(rows=8, cols=8)])
    assert r.maps == [d] and r.confirmed == [d] and r.conflicts == []
    annotate(r)
    assert 'Unabhängig bestätigt' in d.notes and not d.verified


def test_disagreeing_detection_is_a_conflict_and_the_definition_stays():
    d = defined(0x500)
    r = fuse(image(), [d], [detected(0x500, dtype='s16'),
                            detected(0x500, rows=4, cols=8, layout='candidate:row-pitch')])
    assert r.maps == [d] and r.confirmed == [d]              # geometry confirmed, type contradicted
    assert sorted(c.kind for c in r.conflicts) == ['Größe', 'Vorzeichen']
    assert all(c.kept_layer == 1 for c in r.conflicts)
    assert 'widerspricht der Definition' in r.conflicts[0].text()


def test_structure_fills_gaps_and_beats_patterns():
    pattern = detected(0x200, rows=4, cols=4, layout='candidate:row-pitch')
    code = detected(0x204, rows=4, cols=4, dtype='u8', layout='candidate:code-call')
    free = detected(0x300, rows=4, cols=4, layout='candidate:row-pitch')
    r = fuse(image(), [defined()], [pattern, code, free])
    assert code in r.maps and free in r.maps and pattern not in r.maps
    (c,) = r.conflicts
    assert (c.kept_layer, c.dropped_layer, c.kind) == (2, 3, 'Start')
    assert r.counts == {'definition': 1, 'structure': 1, 'pattern': 1, 'confirmed': 0, 'conflicts': 1,
                        'definition_warnings': 0}


def test_definition_check_flags_other_software_versions():
    img = image()
    assert definition_check(img, defined()) == []
    assert 'Tabellenbereich gelöscht (nur 0xFF)' in definition_check(img, defined(0x400))
    assert any('nicht streng monoton' in w for w in
               definition_check(img, defined(axes_x=[1, 2, 2, 3, 4, 5, 6, 7])))
    assert definition_check(img, defined(0x3FF0))[0].startswith('passt nicht zur Datei')
    r = fuse(img, [defined(0x400)], [])
    annotate(r)
    assert 'Definitionsprüfung' in r.maps[0].notes and r.counts['definition_warnings'] == 1


def test_disagreement_order():
    a = defined()
    assert disagreement(a, detected(0x102)) == 'Start'
    assert disagreement(a, detected(rows=4)) == 'Größe'
    assert disagreement(a, detected(dtype='u8')) == 'Zellbreite'
    assert disagreement(a, detected(endian='big')) == 'Byte-Reihenfolge'
    assert disagreement(a, detected(dtype='s16')) == 'Vorzeichen'


def test_unproven_sign_does_not_contradict_a_definition():
    d = defined()
    r = fuse(image(), [d], [detected(dtype='s16', dtype_alternatives=['u16'])])
    assert r.confirmed == [d] and r.conflicts == []


def test_same_layer_candidates_and_record_headers_do_not_collide():
    # A record: header with the X axis in front of the cells; both come from the scanner.
    axis = detected(0x200, rows=1, cols=4, layout='candidate:code-call')
    table = detected(0x208, rows=4, cols=4, layout='candidate:code-call', candidate_region_start=0x200)
    other = detected(0x20C, rows=2, cols=2, layout='candidate:code-call')
    r = fuse(image(), [], [axis, table, other])
    assert r.maps == [axis, table, other] and r.conflicts == []
    # A definition of the axis does not swallow the table behind the header.
    d = defined(0x200, rows=1, cols=4)
    r = fuse(image(), [d], [table])
    assert table in r.maps and r.conflicts == []


def test_sign_conflict_needs_code_proof_and_differing_values():
    img = image()
    assert sign_matters(img, defined(0x500)) and not sign_matters(img, defined())
    # Values below 0x8000 read the same either way: no conflict.
    assert fuse(img, [defined()], [detected(dtype='s16')]).conflicts == []
    # A record or pattern reading never proves the sign.
    r = fuse(img, [defined(0x500)], [detected(0x500, dtype='s16', layout='candidate:curve-record')])
    assert r.conflicts == [] and len(r.confirmed) == 1
