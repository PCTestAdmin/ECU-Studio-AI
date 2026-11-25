"""Quality phase 4: a chained curve record head inside a smoothness-only run refutes the run (synthetic only)."""
import numpy as np
from ecu_studio.core import scoped_scan
from ecu_studio.core.curve_records import CURVE_LAYOUT, scan_curve_records
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.structure_scan import PITCH_LAYOUT


def run(offset, rows=4, cols=8, layout=PITCH_LAYOUT):
    return MapDefinition(name='p', offset=offset, rows=rows, cols=cols, dtype='u16', endian='little',
                         source='heuristic', record_layout=layout)


def curve(head, n=4):
    values = head + 2 + 2 * n
    return MapDefinition(name='c', offset=values, rows=1, cols=n, dtype='u16', endian='little', source='heuristic',
                         record_layout=CURVE_LAYOUT, candidate_region_start=head)


def test_run_with_a_curve_head_inside_is_removed():
    runs = [run(0x1000), run(0x2000), run(0x3000, layout='candidate:code-reference')]
    curves = [curve(0x1010), curve(0x2000), curve(0x3010)]
    kept = scoped_scan.refuted_by_curve_heads(runs, curves)
    # 0x1010 lies inside the first run; a head at a run's own start contradicts nothing; code evidence stays
    assert [m.offset for m in kept] == [0x2000, 0x3000]


def test_switch_off_and_no_curves_keep_everything():
    runs = [run(0x1000)]
    assert scoped_scan.refuted_by_curve_heads(runs, []) == runs
    old = scoped_scan.CURVE_HEADS_REFUTE_PITCH
    scoped_scan.CURVE_HEADS_REFUTE_PITCH = False
    try:
        assert scoped_scan.refuted_by_curve_heads(runs, [curve(0x1010)]) == runs
    finally:
        scoped_scan.CURVE_HEADS_REFUTE_PITCH = old


def _record(n, x0, step, z):
    return (np.array([n, n], '<u2').tobytes() + (x0 + step * np.arange(n)).astype('<u2').tobytes()
            + (x0 + step * np.arange(n)).astype('<u2').tobytes() + np.asarray(z, '<u2').tobytes())


def test_curve_records_behind_map_records_are_found_and_count_as_heads():
    """Chained curve records (n, X[n], W[n]) right behind 2-D header records are structure, not one smooth run."""
    rng = np.random.default_rng(3)
    data = bytearray(rng.integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    at, records = 0x1000, []
    for k in range(40):   # a 16-bit record list: the byte order of the image comes from it
        n = 4
        z = 1000 + 10 * k + np.arange(n * n)
        raw = _record(n, 100 + k, 50, z)
        data[at:at + len(raw)] = raw
        records.append(MapDefinition(name='r', offset=at + 4 + 4 * n, rows=n, cols=n, dtype='u16', endian='little',
                                     source='heuristic', record_layout='candidate:nx,ny,x,y,z',
                                     candidate_region_start=at))
        at += len(raw)
    head = at
    n = 6
    raw = np.array([n], '<u2').tobytes() + (200 + 30 * np.arange(n)).astype('<u2').tobytes() \
        + (500 + 7 * np.arange(n)).astype('<u2').tobytes()
    data[head:head + len(raw)] = raw
    found = scan_curve_records(BinaryImage(bytes(data)), records)
    assert any(c.candidate_region_start == head and c.record_layout == CURVE_LAYOUT for c in found)
    smooth = run(head - 16, rows=4, cols=16)   # a smooth run reaching over the curve record
    assert scoped_scan.refuted_by_curve_heads([smooth], found) == []
