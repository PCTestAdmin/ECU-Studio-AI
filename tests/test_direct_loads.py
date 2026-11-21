"""Values the TriCore code loads directly through a global base register start objects of their own
(after 1.21.0-rc1, synthetic). A smooth run across such an address is not one table."""
import numpy as np
from ecu_studio.core import scoped_scan, tricore_refs
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.structure_scan import scan_structures, PITCH_LAYOUT
from ecu_studio.core.tricore_refs import Descriptors, call_descriptors, direct_loads, global_bases, _halfwords
from test_tricore_refs import SEG, build, lea, movh_a


def bol(op, a, b, off):
    """A BOL instruction (ld.bu 0x39, ld.hu 0xB9, ld.w 0x19, lea 0xD9 ...) with a 16-bit offset."""
    off &= 0xFFFF
    w = op | a << 8 | b << 12 | (off & 0x3F) << 16 | ((off >> 10) & 0x3F) << 22 | ((off >> 6) & 0xF) << 28
    return w.to_bytes(4, 'little')


BASE = 0x9000          # file offset the global base register a1 points to
LOADED = (BASE + 0x40, BASE - 0x22, BASE + 0x2F00)


def boot_a1():
    addr = SEG + BASE
    hi = (addr + 0x8000) >> 16
    return movh_a(1, hi) + lea(1, 1, addr - (hi << 16))


def image_with_direct_loads():
    code = boot_a1() + bol(0xB9, 2, 1, 0x40) + bol(0x39, 3, 1, -0x22) + bol(0x19, 4, 1, 0x2F00)
    data, *_ = build(extra_code=code)
    return data


def starts(data):
    return np.asarray(tricore_refs._stream(data)[3])


def test_direct_loads_through_a_global_base_are_object_starts():
    data = image_with_direct_loads()
    bases = global_bases(_halfwords(data))
    assert bases.get(1) == SEG + BASE
    found = direct_loads(data, starts(data), bases)
    assert set(LOADED) <= set(found)
    # the boot ``lea a1,[a1]off`` initialises the register; it loads nothing
    assert BASE not in found
    assert set(LOADED) <= call_descriptors(data).loaded


def test_instructions_inside_data_blocks_do_not_count():
    data = image_with_direct_loads()
    bases = global_bases(_halfwords(data))
    everything_data = np.ones(len(data), bool)
    assert direct_loads(data, starts(data), bases, code_only=everything_data) == []


def test_addresses_outside_the_image_are_dropped():
    data = image_with_direct_loads()
    assert direct_loads(data, starts(data), {1: 0xD0000000}) == []     # RAM base: no file offset
    assert direct_loads(data, starts(data), {}) == []


def test_switch_off_leaves_no_loaded_addresses():
    data = image_with_direct_loads()
    old = tricore_refs.DIRECT_LOADS
    tricore_refs.DIRECT_LOADS = False
    try:
        assert call_descriptors(data).loaded == frozenset()
    finally:
        tricore_refs.DIRECT_LOADS = old


def pitch(offset, rows=4, cols=8, layout=PITCH_LAYOUT):
    return MapDefinition(name='p', offset=offset, rows=rows, cols=cols, dtype='u16', endian='little',
                         source='heuristic', record_layout=layout)


def test_smooth_run_across_a_directly_loaded_value_is_removed():
    runs = [pitch(0x1000), pitch(0x2000), pitch(0x3000, layout='candidate:nx,ny,x,y,z')]
    kept = scoped_scan.refuted_by_loads(runs, {0x1010, 0x2000, 0x3010})
    # 0x1010 lies inside the first run; 0x2000 is the start of the second; records are not pattern guesses
    assert [m.offset for m in kept] == [0x2000, 0x3000]


def test_rule_switch_and_empty_load_list_keep_everything():
    runs = [pitch(0x1000)]
    assert scoped_scan.refuted_by_loads(runs, ()) == runs
    old = scoped_scan.LOADED_REFUTES_PITCH
    scoped_scan.LOADED_REFUTES_PITCH = False
    try:
        assert scoped_scan.refuted_by_loads(runs, {0x1010}) == runs
    finally:
        scoped_scan.LOADED_REFUTES_PITCH = old


def test_pitch_search_does_not_drop_runs_itself():
    """The removal happens after ranking: inside the search a dropped run would free its result slot
    for a weaker reading elsewhere."""
    rng = np.random.default_rng(7)
    data = bytearray(rng.integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    y, x = np.mgrid[:12, :16]
    z = (1000 + 40 * y + 25 * x + 3 * x * y).astype('<u2').tobytes()
    data[0x1000:0x1000 + len(z)] = z
    calls = Descriptors()
    calls.loaded = frozenset({0x1100})
    found = scan_structures(BinaryImage(bytes(data)), calls=calls)
    assert any(m.record_layout == PITCH_LAYOUT and m.offset < 0x1100 < m.offset + m.length for m in found)
