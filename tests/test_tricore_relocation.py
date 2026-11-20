"""Calibration linked at an address outside the image (1.21.0, synthetic images only).

Development builds may link the calibration at its own flash address (e.g. 0xA0800000)
while the image carries it at another file offset. The code then names every table and
axis outside the image; the placement is inferred from axis headers and records alone.
"""
import numpy as np
from ecu_studio.core import tricore_refs
from ecu_studio.core.tricore_refs import call_descriptors, infer_relocation, RELOC_MIN_HITS
from test_tricore_refs import movh_a, lea, call, u8_axis, u16_axis, RET

LINKED = 0xA0800000      # where the code believes the calibration is
SIZE = 0x40000


def load_abs(reg, addr):
    hi = (addr + 0x8000) >> 16
    return movh_a(reg, hi) + lea(reg, reg, addr - (hi << 16))


def calibration(n=24):
    """(bytes, [(data, x header, y header)]) with own axes per table, relative to its start."""
    blob, tables = bytearray(), []
    for i in range(n):
        x = u8_axis([5 + i, 9 + i, 20 + i, 40 + i, 60 + i, 90 + i])
        y = u16_axis([500 + 7 * i, 1000 + 7 * i, 2000 + 7 * i, 3000 + 7 * i, 4000 + 7 * i])
        xh = len(blob)
        blob += x + b'\x00' * (len(x) & 1)
        yh = len(blob)
        blob += y
        d = len(blob)
        yy, xx = np.mgrid[:5, :6]
        blob += ((10 + 3 * yy + 2 * xx + i) * 40).astype('<u2').tobytes()
        tables.append((d, xh, yh))
    return bytes(blob), tables


def image(cal_at=(0x10000,), linked=LINKED, n=24):
    img = bytearray(SIZE)
    blob, tables = calibration(n)
    for at in cal_at:
        img[at:at + len(blob)] = blob
    code, pos = bytearray(), 0
    for d, xh, yh in tables:
        block = load_abs(4, linked + d) + load_abs(5, linked + xh) + load_abs(6, linked + yh)
        block += call(pos + len(block), 0x9100) + RET
        code += block
        pos += len(block)
    while len(code) < 0x9000:
        code += movh_a(12, 0xD000) + RET + RET
    img[:len(code)] = code
    img[0x9100:0x9102] = RET
    return bytes(img), tables


def test_calibration_linked_elsewhere_is_placed_by_its_axes():
    data, tables = image()
    desc = call_descriptors(data)
    assert set(desc) == {0x10000 + d for d, _, _ in tables}
    for d, xh, yh in tables:
        got = desc[0x10000 + d]
        assert (got.x_axis.header, got.y_axis.header) == (0x10000 + xh, 0x10000 + yh)
        assert got.x_axis.count == 6 and got.y_axis.count == 5


def test_both_flash_aliases_map_to_the_inferred_window():
    data, _ = image()
    sites, _, _ = tricore_refs._analyse(data)
    windows = {(lo, delta) for lo, _, delta in sites.relocation}
    assert windows == {(0x80800000, 0x80800000 - 0x10000), (0xA0800000, 0xA0800000 - 0x10000)}
    assert tricore_refs._file(0x80800010, SIZE, sites.relocation) == 0x10010
    assert tricore_refs._file(0xA0800010, SIZE, sites.relocation) == 0x10010


def test_ambiguous_placement_relocates_nothing():
    """Two identical copies of the calibration: no position is decisive, no table is named."""
    data, _ = image(cal_at=(0x10000, 0x30000))
    assert tricore_refs._analyse(data)[0].relocation == ()
    assert call_descriptors(data) == {}


def test_too_few_references_or_no_axes_relocate_nothing():
    data, tables = image()
    calls = [(LINKED + xh, LINKED + yh) for _, xh, yh in tables]
    assert infer_relocation(data, calls[:RELOC_MIN_HITS // 2 - 1]) == ()
    assert infer_relocation(bytes(SIZE), calls) == ()                  # nothing parses anywhere
    assert infer_relocation(data, [(0xD0001000, 0xD0002000)] * 40) == ()   # RAM, not flash


def test_images_addressed_inside_keep_the_plain_mapping():
    data, tables = image(linked=0xA0010000)          # code names the calibration where it is
    sites, _, _ = tricore_refs._analyse(data)
    assert sites.relocation == ()
    assert set(call_descriptors(data)) == {0x10000 + d for d, _, _ in tables}


def test_relocation_switch_restores_the_old_behaviour(monkeypatch):
    data, _ = image()
    monkeypatch.setattr(tricore_refs, 'RELOCATE', False)
    assert call_descriptors(data) == {}
