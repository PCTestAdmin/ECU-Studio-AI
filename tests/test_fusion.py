"""Three recognition layers: definitions stay, code/structure fills gaps, patterns last; conflicts are listed."""
import numpy as np
from ecu_studio.core.fusion import (fuse, annotate, layer_of, definition_check, definition_hints, definition_mismatch,
                                   disagreement, sign_matters)
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
    assert r.counts == {'definition': 1, 'structure': 1, 'pattern': 1, 'confirmed': 0, 'supported_by_pattern': 0,
                        'conflicts': 1, 'definition_warnings': 0, 'axis_reversal_share': None}


def test_definition_check_flags_other_software_versions():
    img = image()
    assert definition_check(img, defined()) == []
    assert definition_check(img, defined(0x400)) == []                    # erased: a hint, no warning
    assert definition_hints(img, defined(0x400)) == ['Tabellenbereich gelöscht (nur 0xFF)']
    assert any('nicht monoton' in w for w in
               definition_check(img, defined(axes_x=[1, 3, 2, 4, 5, 6, 7, 8])))
    assert definition_check(img, defined(axes_x=[1, 1, 1, 3, 4, 5, 6, 7])) == []   # padded breakpoints
    assert definition_check(img, defined(0x3FF0))[0].startswith('passt nicht zur Datei')
    assert definition_check(img, defined(axes_x=[0.] * 8)) == []          # undefined axis, no warning
    r = fuse(img, [defined(0x400), defined(axes_x=[1, 3, 2, 4, 5, 6, 7, 8])], [])
    annotate(r)
    assert r.counts['definition_warnings'] == 1 and 'Definitionsprüfung' in r.maps[1].notes
    assert 'Hinweis: Tabellenbereich gelöscht' in r.maps[0].notes and 'Definitionsprüfung' not in r.maps[0].notes


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


def test_a_data_pattern_only_supports_a_definition():
    """Regression 1.19 QA: a layer 3 match was reported as an independent confirmation."""
    strong, weak = defined(0x100), defined(0x500)
    r = fuse(image(), [strong, weak], [detected(0x100), detected(0x500, layout='candidate:row-pitch')])
    assert r.counts['confirmed'] == 1 and r.counts['supported_by_pattern'] == 1
    annotate(r)
    assert 'bestätigt durch Programmcode/Struktur' in strong.notes
    assert 'gestützt durch Datenmuster' in weak.notes and 'Unabhängig bestätigt' not in weak.notes


def test_a_definition_for_another_file_is_flagged_as_a_whole():
    """Regression 1.19 QA: per-table hints only; a wrong XDF (other version/family) was accepted silently.
    Measured: right definitions 0.1-0.8 % reversed axes, wrong ones 87-97 %."""
    img = image()
    up, mixed = [1, 2, 3, 4, 5, 6, 7, 8], [5, 1, 7, 2, 8, 3, 6, 4]
    right = [defined(0x100 + 2 * i, axes_x=up) for i in range(30)]
    assert definition_mismatch(img, right) == (0.0, '')
    one_off = right[:29] + [defined(axes_x=mixed)]
    assert definition_mismatch(img, one_off)[1] == ''                       # 3 % stays below the threshold
    wrong = [defined(0x100 + 2 * i, axes_x=mixed if i % 2 else up) for i in range(30)]
    share, text = definition_mismatch(img, wrong)
    assert share == .5 and 'passt vermutlich nicht' in text
    assert definition_mismatch(img, wrong[:10]) == (None, '')               # too few for a statement
    assert fuse(img, wrong, []).mismatch == text


def test_address_window_finds_exactly_the_pairwise_overlaps():
    """fuse looks up overlaps in an address window (was pairwise: seconds in the UI thread); same result."""
    from ecu_studio.core.fusion import _overlap
    rng = np.random.default_rng(7)
    layouts = ('candidate:code-call', 'candidate:row-pitch')
    defs = [defined(int(o), rows=int(r), cols=int(c), dtype='u8')
            for o, r, c in zip(rng.integers(0, 0x3000, 40), rng.integers(1, 40, 40), rng.integers(1, 9, 40))]
    cands = [detected(int(o), layout=layouts[i % 2], rows=int(r), cols=int(c), dtype='u8')
             for i, (o, r, c) in enumerate(zip(rng.integers(0, 0x3000, 300), rng.integers(1, 12, 300),
                                                 rng.integers(1, 12, 300)))]
    result = fuse(image(), defs, cands)
    kept = list(defs)
    for m in sorted(cands, key=lambda m: (layer_of(m), m.offset)):
        if not any(layer_of(k) < layer_of(m) and _overlap(m, k) for k in kept):
            kept.append(m)
    assert [id(m) for m in result.maps] == [id(m) for m in kept]
    assert result.conflicts and len(result.maps) < len(defs) + len(cands)


def test_scan_merge_overlap_finder_equals_the_pairwise_rule():
    """The scan merge's 50 % rule against curated maps, via an address index (pairwise froze the GUI)."""
    from ecu_studio.ui.main_window import Window
    rng = np.random.default_rng(11)

    def table(offset, rows, cols):
        return MapDefinition(f'T{offset}', int(offset), int(rows), int(cols), 'u8')

    curated = [table(o, r, c) for o, r, c in zip(rng.integers(0, 4000, 200), rng.integers(0, 30, 200),
                                                 rng.integers(1, 6, 200))]
    probes = [table(o, r, c) for o, r, c in zip(rng.integers(0, 4100, 2000), rng.integers(0, 20, 2000),
                                                rng.integers(1, 6, 2000))]
    probes += [table(x.offset + x.length, 4, 1) for x in curated[:50]]          # touching ends
    probes += [table(x.offset, 0, 1) for x in curated[:50]]                     # empty, on a start
    finder = Window._overlap_finder(curated)
    expected = [any(Window._overlaps(m, x) for x in curated) for m in probes]
    assert [finder(m) for m in probes] == expected and 0 < sum(expected) < len(probes)
    assert not Window._overlap_finder([])(probes[0])
