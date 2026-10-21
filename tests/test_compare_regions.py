"""ORI/MOD: changes outside known maps are listed as regions; per-cell delta for the heatmap."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.compare_maps import compare_images, changed_regions, delta_matrix


def _pair():
    ori = bytearray(range(256)) * 64
    mod = bytearray(ori)
    mod[0x100:0x104] = b'\x01\x02\x03\x04'           # inside the known map
    mod[0x2000:0x2010] = bytes([0xAA]) * 16          # unknown region A (16 changed bytes)
    mod[0x2018] ^= 0xFF                               # 8 bytes later: still region A
    mod[0x3000] ^= 0xFF                               # far away: region B
    known = MapDefinition('K', 0x100, 4, 4, 'u8', 'big')
    return BinaryImage(bytes(ori)), BinaryImage(bytes(mod)), known


def test_changes_outside_maps_become_regions():
    ori, mod, known = _pair()
    report = compare_images(ori, mod, [known])
    regions = report['unmapped_regions']
    assert [(r['offset'], r['length']) for r in regions] == [(0x2000, 0x19), (0x3000, 1)]
    assert sum(r['changed_bytes'] for r in regions) == report['changed_bytes_outside_maps']


def test_region_merging_and_limit():
    mask = np.zeros(1000, bool)
    mask[[10, 20, 50, 51, 900]] = True
    assert [(r['offset'], r['length']) for r in changed_regions(mask, gap=16)] == [(10, 11), (50, 2), (900, 1)]
    assert len(changed_regions(mask, gap=16, limit=1)) == 1
    assert changed_regions(np.zeros(10, bool)) == []


def test_delta_matrix_is_mod_minus_ori():
    ori, mod, known = _pair()
    d = delta_matrix(ori, mod, known)
    assert d.shape == (4, 4)
    assert d[0, 0] == 1 - 0x00 and d[0, 1] == 2 - 0x01 and np.count_nonzero(d[1:]) == 0
