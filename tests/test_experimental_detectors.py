"""Synthetic format mechanics and negative controls, never OEM validation."""
import zlib
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.experimental_detectors import (scan_pointer_chains, scan_aligned_records,
                                                    combine_conservatively)


def pointer_fixture(width=1, start=0x801, count=4):
    data = bytearray(np.random.default_rng(14).integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    x, y = 0x101, 0x181
    data[x:x+7] = bytes([6, 5, 25, 45, 70, 100, 140])
    data[y:y+5] = bytes([4, 10, 35, 70, 120])
    maps, headers = [], []
    for i in range(count):
        h = start + i*(4+24*width); at = h+4; headers.append(h)
        data[h:h+4] = x.to_bytes(2, 'little') + y.to_bytes(2, 'little')
        # Flat values deliberately cannot fix geometry by their surface.
        values = np.full(24, 88+i*3 if width == 1 else 1200+i*500, dtype='u1' if width == 1 else '<u2')
        data[at:at+values.nbytes] = values.tobytes()
        maps.append(MapDefinition(f'public-synthetic-{i}', at, 4, 6, dtype='u8' if width == 1 else 'u16', endian='little'))
    return BinaryImage(bytes(data)), maps, headers


def aligned_fixture(wx=2, wy=1, width=2, start=0x801, count=4):
    data = bytearray(np.random.default_rng(41).integers(0, 256, 0x5000, dtype=np.uint8).tobytes())
    h, headers, maps = start, [], []
    for i in range(count):
        headers.append(h); data[h:h+2] = bytes([5, 4]); p = h+2
        for n, w in ((5, wx), (4, wy)):
            if w == 2 and p % 2: data[p] = 0; p += 1
            vals = np.array([10, 25, 50, 85, 120][:n] if w == 1 else [1000, 2500, 5000, 8500, 12000][:n],
                            dtype='u1' if w == 1 else '<u2')
            data[p:p+vals.nbytes] = vals.tobytes(); p += vals.nbytes
        if width == 2 and p % 2: data[p] = 0; p += 1
        vals = np.full(20, 71+i if width == 1 else 1700+i*100, dtype='u1' if width == 1 else '<u2')
        data[p:p+vals.nbytes] = vals.tobytes()
        maps.append(MapDefinition(f'synthetic-aligned-{i}', p, 4, 5, dtype='u8' if width == 1 else 'u16', endian='little'))
        h = p+vals.nbytes
    # MOV R4,#page; MOV R5,#offset, the existing scanner's C16x address form.
    code = b''.join(bytes([0xe6, 0xf4, (h >> 14) & 255, h >> 22, 0xe6, 0xf5, h & 255, (h >> 8) & 63]) for h in headers)
    data[0x100:0x100+len(code)] = code
    return BinaryImage(bytes(data)), maps, headers


def shapes(maps): return [(m.offset, m.rows, m.cols, m.dtype) for m in maps]


@pytest.mark.parametrize('width', [1, 2])
@pytest.mark.parametrize('start', [0x800, 0x801])
def test_pointer_chain_recovers_packed_boundaries_shared_axes_and_cell_width(width, start):
    image, truth, headers = pointer_fixture(width, start)
    found = scan_pointer_chains(image)
    assert shapes(found) == shapes(truth[:-1])
    assert all((m.axis_x_offset, m.axis_y_offset) == (0x102, 0x182) for m in found)
    assert all(not m.verified and m.calibrated_rate is None and m.confidence == 0 for m in found)
    assert shapes(scan_pointer_chains(image)) == shapes(found) and not image.dirty_bytes


@pytest.mark.parametrize('wx,wy', [(1, 2), (2, 1), (2, 2)])
@pytest.mark.parametrize('width', [1, 2])
def test_aligned_mixed_axes_need_code_and_exact_next_record(wx, wy, width):
    image, truth, _ = aligned_fixture(wx, wy, width)
    found = scan_aligned_records(image)
    # With two wide axes only the odd first header needs padding. The following
    # packed uniform records already belong to the existing decoder's scope.
    expected = truth[:1] if wx == wy else truth[:-1]
    assert shapes(found) == shapes(expected)
    assert all(m.axis_x_offset is not None and m.axis_y_offset is not None and not m.verified for m in found)
    raw = bytearray(image.original); raw[0x100:0x140] = bytes(64)
    assert scan_aligned_records(BinaryImage(bytes(raw))) == []
    assert shapes(scan_aligned_records(image)) == shapes(found) and not image.dirty_bytes


def test_pointer_direction_byte_order_alias_and_overlap_rejected():
    image, _, headers = pointer_fixture()
    for replacement in (b'\xff\xff\x81\x01', b'\x01\x01\x01\x01', b'\x01\x01\x03\x01', b'\x01\x01\x01\x81'):
        raw = bytearray(image.original)
        for h in headers: raw[h:h+4] = replacement
        assert scan_pointer_chains(BinaryImage(bytes(raw))) == []
    # Two headers alone cannot establish a run, and an unrelated smooth grid cannot substitute.
    short, _, _ = pointer_fixture(count=2)
    assert scan_pointer_chains(short) == []


def test_signed_word_axes_and_competing_cell_widths():
    image, _, headers = pointer_fixture(width=2)
    raw = bytearray(image.original)
    axis = [6, -100, -50, 0, 20, 50, 80]
    raw[0x101:0x10f] = np.array(axis, '<i2').tobytes()
    found = scan_pointer_chains(BinaryImage(bytes(raw)))
    assert len(found) == 3 and found[0].axes_x == axis[1:]
    assert found[0].axis_x_offset == 0x103
    # A plausible extra header at the byte-width boundary contradicts the
    # word-width boundary; the first table must lose its unique interpretation.
    middle = headers[0]+4+24
    raw[middle:middle+4] = raw[headers[0]:headers[0]+4]
    d = {}; found = scan_pointer_chains(BinaryImage(bytes(raw)), diagnostics=d)
    assert all(m.offset != headers[0]+4 for m in found) and d['ambiguous'] >= 1


def test_anchor_budget_never_emits_partial_results(monkeypatch):
    import ecu_studio.core.experimental_detectors as experiment
    monkeypatch.setattr(experiment, 'c16x_reference_anchors', lambda *args: list(range(20_001)))
    d = {}
    assert scan_aligned_records(BinaryImage(bytes(100)), diagnostics=d) == []
    assert d['incomplete']


def test_truncation_cancellation_limits_and_scope():
    image, maps, headers = pointer_fixture()
    assert scan_pointer_chains(BinaryImage(image.original[:headers[1]])) == []
    assert scan_pointer_chains(image, cancelled=lambda: True) == []
    d = {}; assert scan_pointer_chains(image, max_results=1, diagnostics=d) == [] and d['incomplete']
    d = {}; assert scan_pointer_chains(BinaryImage(bytes(65537)), diagnostics=d) == [] and not d['applicable']
    image, _, _ = aligned_fixture()
    assert scan_aligned_records(image, cancelled=lambda: True) == []
    d = {}; assert scan_aligned_records(image, max_results=1, diagnostics=d) == [] and d['incomplete']
    for scan in (scan_aligned_records, scan_pointer_chains):
        with pytest.raises(ValueError): scan(image, max_results=0)


@pytest.mark.parametrize('kind', ['empty', 'erased', 'random', 'compressed', 'repeated', 'ramps', 'code', 'wrong-family', 'truncated'])
def test_negative_controls(kind):
    random = np.random.default_rng(932).integers(0, 256, 65536, dtype=np.uint8).tobytes()
    data = {'empty': bytes(65536), 'erased': b'\xff'*65536, 'random': random,
            'compressed': zlib.compress(random[:30000]), 'repeated': b'\x04\x08\x10\x20'*16384,
            'ramps': bytes(range(256))*256, 'code': b'\xe6\xf4\x01\x00\xe6\xf5\x00\x40'*8192,
            'wrong-family': b'EDC17CP09 PowerPC MSD85'+random[23:], 'truncated': b'\x04\x04\x01'}[kind]
    for scan in (scan_pointer_chains, scan_aligned_records):
        assert scan(BinaryImage(data)) == []


def test_combination_preserves_baseline_and_explains_conflicts():
    base = MapDefinition('baseline', 100, 4, 4, dtype='u8')
    before = base.asdict()
    conflicting = MapDefinition('overlap', 110, 4, 4, dtype='u8')
    a = MapDefinition('A', 200, 4, 4, dtype='u8')
    b = MapDefinition('B', 205, 4, 4, dtype='u8')
    independent = MapDefinition('C', 300, 4, 4, dtype='u8')
    d = {}; result = combine_conservatively([base], [conflicting, a, b, independent], diagnostics=d)
    assert result == [base, independent] and result[0] is base and base.asdict() == before
    assert d == {'duplicate': 0, 'conflict': 3, 'added': 1}
