"""Header records (nx, ny, X, Y, Z) whose values carry no surface evidence, and their ranking."""
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.axis_records import scan_axis_records, _axis_pair, SHAPE_ONLY_ORIGIN
from ecu_studio.core.confidence import evidence_class
from ecu_studio.core.precision import rank_candidates
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.tools.benchmark_suite import type_agreement

X = [0, 500, 1000, 2000, 3000, 4500]
Y = [100, 200, 400, 800, 1600]


def _record(values, x=X, y=Y) -> bytes:
    """SWORD little-endian record as in Bosch EDC17 (Map_Xs16Ys16Ws16)."""
    head = np.array([len(x), len(y)] + list(x) + list(y), '<i2').tobytes()
    return head + np.asarray(values, '<i2').tobytes()


def _image(*records, at=0x200, size=0x1000):
    buf = bytearray(size)
    pos = at
    for r in records:
        buf[pos:pos + len(r)] = r
        pos += len(r)
    return BinaryImage(bytes(buf))


def _z(at=0x200, x=X, y=Y):
    return at + 4 + 2 * (len(x) + len(y))


def test_flat_record_is_found_by_header_and_axes_alone():
    image = _image(_record(np.full((5, 6), 30)))
    found = [m for m in scan_axis_records(image) if (m.offset, m.rows, m.cols) == (_z(), 5, 6)]
    assert len(found) == 1
    m = found[0]
    # Value width = axis width; no top bit set, so the unsigned reading is kept.
    assert (m.dtype, m.endian) == ('u16', 'little')
    assert m.label_origin == SHAPE_ONLY_ORIGIN and evidence_class(m) == 'header:nxny:shape'
    assert m.axes_x == X and m.axes_y == Y
    result = scan_calibration_candidates(image, use_definitions=False)
    assert any((r.offset, r.rows, r.cols) == (_z(), 5, 6) for r in result)
    # Its axes are reported as 1-D candidates too.
    assert {r.offset for r in result if r.rows == 1} >= {0x204, 0x204 + 2 * len(X)}


def test_flat_negative_values_are_read_signed():
    image = _image(_record(np.full((5, 6), -40)))
    m = next(m for m in scan_axis_records(image) if m.offset == _z())
    assert m.dtype == 's16'


def test_noisy_record_needs_a_neighbouring_record():
    noise = np.random.default_rng(7).integers(-20000, 20000, (5, 6))
    alone = _image(_record(noise))
    assert not any(m.offset == _z() for m in scan_axis_records(alone))
    # Packed record list: a flat record directly behind the noisy one.
    first = _record(noise)
    chained = _image(first, _record(np.full((5, 6), 7)))
    offsets = {m.offset for m in scan_axis_records(chained)}
    assert _z() in offsets and _z(0x200 + len(first)) in offsets


def test_index_axis_is_accepted_next_to_a_breakpoint_axis_only():
    assert _axis_pair([0, 1, 2, 3, 4, 5], Y)
    assert not _axis_pair([0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4])
    assert not _axis_pair([0, 1, 1, 3, 4, 5], Y)          # not strictly monotone
    # Byte counts and axes: both axes must be plausible (chance headers in random data).
    assert not _axis_pair([0, 1, 2, 3, 4, 5], Y, wide=False)
    assert _axis_pair(X, Y, wide=False)


def test_random_data_yields_no_header_records():
    import numpy as np
    for seed in range(3):
        data = np.random.default_rng(seed).integers(0, 256, 2 * 1024 * 1024, dtype=np.uint8).tobytes()
        assert scan_calibration_candidates(BinaryImage(data), use_definitions=False) == []


def _smooth(rows, cols, base=20):
    y, x = np.mgrid[:rows, :cols]
    return (base + 3 * y + 2 * x + (x * y) % 3).astype(np.uint8)


def test_evidenced_candidates_are_not_cut_by_the_result_limit():
    buf = bytearray(0x2000)
    cands = []
    for k in range(4):
        off = 0x100 + k * 0x200
        buf[off:off + 64] = _smooth(8, 8).tobytes()
        cands.append(MapDefinition(f'r{k}', off, 8, 8, 'u8', 'big', source='heuristic', confidence=.44,
                                   record_layout='candidate:nx,ny,x,y,z', candidate_region_start=off - 18,
                                   axes_x=list(range(0, 80, 10)), axes_y=list(range(5, 85, 10))))
    plain_at = (0x1100, 0x1300, 0x1500)
    for off in plain_at:
        buf[off:off + 64] = _smooth(8, 8, 40).tobytes()
        cands.append(MapDefinition('p', off, 8, 8, 'u8', 'big', source='heuristic', confidence=.44,
                                   record_layout='candidate:row-pitch'))
    result = rank_candidates(BinaryImage(bytes(buf)), cands, max_results=1)
    kinds = [m.record_layout for m in result]
    assert kinds.count('candidate:nx,ny,x,y,z') == 4 and kinds.count('candidate:row-pitch') == 1


def _conflict(plain_start, header):
    buf = bytearray(0x800)
    buf[0x100:0x100 + 256] = _smooth(16, 16).tobytes()
    image = BinaryImage(bytes(buf))
    plain = MapDefinition('p', plain_start, 8, 16, 'u8', 'big', source='heuristic', confidence=.45,
                          record_layout='candidate:row-pitch')
    record = MapDefinition('r', 0x140, 8, 8, 'u8', 'big', source='heuristic', confidence=.05,
                           record_layout='candidate:nx,ny,x,y,z', candidate_region_start=header,
                           axes_x=list(range(0, 80, 10)), axes_y=list(range(5, 85, 10)))
    return [m.record_layout for m in rank_candidates(image, [plain, record])]


def test_record_wins_overlap_unless_its_header_lies_inside_an_earlier_table():
    # Smoothness candidate starts behind the header (swallows axes/values): the record wins.
    assert _conflict(plain_start=0x130, header=0x12C) == ['candidate:nx,ny,x,y,z']
    # Header inside a table that starts earlier: smooth tables contain header-like runs,
    # so the stronger candidate wins, as before.
    assert _conflict(plain_start=0x100, header=0x12C) == ['candidate:row-pitch']


def test_type_agreement_counts_the_sign_only_where_the_bytes_decide_it():
    pos = np.full((4, 4), 300, '<i2').tobytes()
    neg = np.full((4, 4), -300, '<i2').tobytes()
    image = BinaryImage(pos + neg)
    ref = [MapDefinition('a', 0, 4, 4, 's16', 'little'), MapDefinition('b', 32, 4, 4, 's16', 'little')]
    unsigned = [MapDefinition('a', 0, 4, 4, 'u16', 'little'), MapDefinition('b', 32, 4, 4, 'u16', 'little')]
    assert type_agreement(image, unsigned, ref) == 1               # only the all-positive block
    swapped = [MapDefinition('a', 0, 4, 4, 's16', 'big')]
    assert type_agreement(image, swapped, ref) == 0
