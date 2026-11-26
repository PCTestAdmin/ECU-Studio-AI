"""Counterexamples for the priority of code evidence and the direct-load rule (synthetic only).

A weak pattern must not displace a code reference, an evidenced alternative must not vanish silently,
the result must not depend on the order of the input, and a value the code loads at a table start or
inside an evidenced object never removes it (scoped_scan.refuted_by_loads only touches row-pitch runs).
"""
import itertools
import random
import numpy as np
from ecu_studio.core import scoped_scan
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.precision import rank_candidates
from ecu_studio.core.structure_scan import PITCH_LAYOUT

CALL, RECORD, REF = 'candidate:code-call', 'candidate:nx,ny,x,y,z', 'candidate:code-reference'


def image():
    rng = np.random.default_rng(3)
    data = bytearray(rng.integers(0, 256, 0x3000, dtype=np.uint8).tobytes())
    for at, (r, c) in ((0x400, (8, 10)), (0x1000, (10, 12)), (0x2000, (6, 8))):
        y, x = np.mgrid[:r, :c]
        z = (900 + 37 * y + 21 * x + 2 * x * y + (at >> 8)).astype('<u2').tobytes()
        data[at:at + len(z)] = z
    return BinaryImage(bytes(data))


def cand(offset, rows, cols, layout, dtype='u16', endian='little', confidence=.3):
    return MapDefinition(name=f'c{offset:x}', offset=offset, rows=rows, cols=cols, dtype=dtype, endian=endian,
                         source='heuristic', record_layout=layout, confidence=confidence)


def key(maps):
    return [(m.offset, m.rows, m.cols, m.dtype, m.endian, m.record_layout) for m in maps]


def pool():
    return [cand(0x400, 8, 10, PITCH_LAYOUT, confidence=.45), cand(0x3F0, 8, 10, PITCH_LAYOUT),
            cand(0x400, 8, 10, PITCH_LAYOUT, endian='big'), cand(0x400, 8, 10, PITCH_LAYOUT, dtype='s16'),
            cand(0x1000, 10, 12, CALL), cand(0xFF8, 10, 12, PITCH_LAYOUT, confidence=.45),
            cand(0x1000, 10, 12, RECORD), cand(0x2000, 6, 8, REF), cand(0x2000, 6, 8, REF, dtype='s16')]


def test_result_does_not_depend_on_the_input_order():
    img = image()
    expected = key(rank_candidates(img, pool()))
    rnd = random.Random(11)
    for _ in range(12):
        shuffled = pool()
        rnd.shuffle(shuffled)
        assert key(rank_candidates(img, shuffled)) == expected
    for order in itertools.islice(itertools.permutations(range(4)), 24):   # ties of identical geometry
        part = pool()[:4]
        assert key(rank_candidates(img, [part[i] for i in order])) == key(rank_candidates(img, pool()[:4]))


def test_a_stronger_pattern_does_not_displace_a_code_call():
    out = rank_candidates(image(), [cand(0xFF8, 10, 12, PITCH_LAYOUT, confidence=.45), cand(0x1000, 10, 12, CALL, confidence=0.)])
    assert key(out) == [(0x1000, 10, 12, 'u16', 'little', CALL)]


def test_a_displaced_evidenced_alternative_is_named_on_the_winner():
    diag = {}
    out = rank_candidates(image(), [cand(0x1000, 10, 12, CALL), cand(0x1000, 10, 12, RECORD)], diagnostics=diag)
    assert [m.record_layout for m in out] == [CALL]
    assert 'Alternative mit eigenem Beleg verworfen' in out[0].notes and 'nx,ny,x,y,z' in out[0].notes
    assert diag['displaced_evidenced'] == 1


def test_a_displaced_pattern_guess_is_counted_but_not_named():
    diag = {}
    out = rank_candidates(image(), [cand(0x1000, 10, 12, CALL), cand(0x1000 + 24 * 4, 5, 12, PITCH_LAYOUT)], diagnostics=diag)
    assert 'Alternative' not in out[0].notes and diag['displaced_evidenced'] == 0
    assert diag['rejection_counts']['competing-overlapping-layout'] == 1


def test_loads_never_remove_evidenced_objects_or_runs_loaded_at_their_start():
    runs = [cand(0x400, 8, 10, PITCH_LAYOUT), cand(0x1000, 10, 12, CALL), cand(0x2000, 6, 8, RECORD)]
    loads = {0x400, 0x1010, 0x2010}       # start of the run; a field inside a code-call table and a record
    assert key(scoped_scan.refuted_by_loads(runs, loads)) == key(runs)


def test_a_load_inside_a_run_removes_it_whatever_the_order():
    runs = [cand(0x400, 8, 10, PITCH_LAYOUT), cand(0x1000, 10, 12, PITCH_LAYOUT)]
    for order in (runs, runs[::-1]):
        assert key(scoped_scan.refuted_by_loads(order, {0x1010})) == key([runs[0]])


def test_a_true_tie_is_broken_by_the_candidate_not_by_its_position():
    """No value with the top bit set: u16 and s16 read alike and score alike (a real tie)."""
    a, b = cand(0x400, 8, 10, PITCH_LAYOUT), cand(0x400, 8, 10, PITCH_LAYOUT, dtype='s16')
    first = key(rank_candidates(image(), [a, b]))
    a, b = cand(0x400, 8, 10, PITCH_LAYOUT), cand(0x400, 8, 10, PITCH_LAYOUT, dtype='s16')
    assert key(rank_candidates(image(), [b, a])) == first and len(first) == 1


def test_a_tie_between_equal_readings_keeps_the_unsigned_one():
    for order in ((0, 1), (1, 0)):
        c = [cand(0x400, 8, 10, PITCH_LAYOUT), cand(0x400, 8, 10, PITCH_LAYOUT, dtype='s16')]
        assert [m.dtype for m in rank_candidates(image(), [c[i] for i in order])] == ['u16']
