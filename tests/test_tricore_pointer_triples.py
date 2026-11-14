"""Tables named by pointer triples in memory, unapplied axes in prelookup learning
(1.21.0, synthetic images only).

Some TriCore builds hand a table to its interpolation through a descriptor in
memory, three little-endian addresses (data, X axis header, Y axis header) in an
array of 12-byte entries. Prelookup routines are also called with unapplied axes
whose points are all equal (e.g. zero); they still name an axis lookup.
"""
import numpy as np
import pytest
from ecu_studio.core import tricore_refs
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.structure_scan import POINTER_TRIPLE_ORIGIN, CALL_LAYOUT
from ecu_studio.core.tricore_refs import (MIN_TRIPLES, blank_axis, call_descriptors, looks_like_tricore,
                                          pointer_triples)
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from test_tricore_refs import image_with, load, call, prelookup_code, RET, U8_TABLE

FLASH = 0x80000000
X, Y, BLANK = 0xC000, 0xC010, 0xC020
TRIPLES = 0xD000


def no_code(tables, base):
    return b''


def with_triples(entries, *, at=TRIPLES, stride=12):
    """image_with tables, plus one triple (data, X, Y) per entry from `at` every `stride` bytes."""
    data, tables = image_with(no_code)
    img = bytearray(data)
    for i, (d, x, y) in enumerate(entries):
        p = at + i * stride
        img[p:p + 12] = np.array([FLASH + d, FLASH + x, FLASH + y], '<u4').tobytes()
    return bytes(img), tables


def test_descriptor_array_names_tables_and_axes():
    data, tables = with_triples([(t, X, Y) for t in [0x8000 + i * 30 for i in range(24)]])
    assert looks_like_tricore(data)
    found = pointer_triples(data)
    assert set(found) == {0x8000 + i * 30 for i in range(24)}
    assert all((x.header, y.header, x.count, y.count) == (X, Y, 6, 5) for x, y, _ in found.values())
    desc = call_descriptors(data)
    assert set(desc) == set(tables) and all(d.pointer for d in desc.values())
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    named = {(m.offset, m.rows, m.cols) for m in maps if m.record_layout == CALL_LAYOUT}
    # Exactly filled gaps give the cell width; the last table (gap to the axes) stays open.
    assert named == {(t, 5, 6) for t in tables[:-1]}
    assert all(m.label_origin.startswith(POINTER_TRIPLE_ORIGIN) and not m.verified
               for m in maps if m.record_layout == CALL_LAYOUT)


def test_lone_or_overlapping_triples_are_chance_words():
    tables = [0x8000 + i * 30 for i in range(24)]
    data, _ = with_triples([(t, X, Y) for t in tables], stride=16)      # no 12-byte neighbour
    assert pointer_triples(data) == {} and call_descriptors(data) == {}


def test_arrays_of_axis_pointers_are_no_triples():
    """Data, X and Y all axes: a list of axis pointers, not a table descriptor."""
    data, _ = with_triples([(X, Y, BLANK)] * 4 + [(BLANK, X, Y)] * 4 + [(t, X, Y) for t in
                                                                          [0x8000 + i * 30 for i in range(24)]])
    img = bytearray(data)
    img[BLANK:BLANK + 7] = bytes([6]) + bytes(6)
    found = pointer_triples(bytes(img))
    assert not {X, Y, BLANK} & set(found)


def test_too_few_triples_or_switched_off_name_nothing(monkeypatch):
    tables = [0x8000 + i * 30 for i in range(24)]
    data, _ = with_triples([(t, X, Y) for t in tables[:MIN_TRIPLES - 1]])
    assert pointer_triples(data) == {} and call_descriptors(data) == {}
    data, _ = with_triples([(t, X, Y) for t in tables])
    monkeypatch.setattr(tricore_refs, 'POINTER_TRIPLES', False)
    assert call_descriptors(data) == {}


def test_triples_whose_axes_do_not_parse_or_cover_the_data_are_dropped():
    tables = [0x8000 + i * 30 for i in range(24)]
    data, _ = with_triples([(t, X, 0xE000) for t in tables])             # Y: zeros, no axis
    assert pointer_triples(data) == {}
    data, _ = with_triples([(X + 2, X, Y)] + [(t, X, Y) for t in tables])
    assert X + 2 not in pointer_triples(data)                             # data inside the X axis


@pytest.mark.parametrize('raw, blank', [(bytes([6]) + bytes(6), True), (bytes([4]) + b'\x07' * 4, True),
                                        (np.array([3, 0, 0, 0], '<u2').tobytes(), True),
                                        (bytes([4, 1, 2, 3, 4]), False), (bytes([1, 0]), False),
                                        (bytes([0x40]) + bytes(0x40), False)])
def test_blank_axis_reads_count_headers_with_equal_points(raw, blank):
    img = bytes(16) + raw + b'\xff' * 0x50
    assert blank_axis(img, 16) is blank


def half_blank_prelookups(tables, base):
    """Like prelookup_code, but every second X prelookup names an unapplied (all-zero) axis."""
    code = bytearray()
    for i, t in enumerate(tables):
        code += load(4, X if i % 2 else BLANK) + call(base + len(code) + 8, 0x7100)
        code += load(4, Y) + call(base + len(code) + 8, 0x7200)
        code += load(4, t) + call(base + len(code) + 8, 0x7300) + RET
    return bytes(code)


def blank_image():
    data, tables = image_with(half_blank_prelookups, n_tables=40, routines=U8_TABLE)
    img = bytearray(data)
    img[BLANK:BLANK + 7] = bytes([6]) + bytes(6)
    return bytes(img), tables


def test_unapplied_axes_count_towards_the_prelookup_share(monkeypatch):
    data, tables = blank_image()
    desc = call_descriptors(data)
    # Tables after the real X lookup are named; those after the blank axis have no X to read.
    assert set(desc) == set(tables[1::2])
    assert all((d.x_axis.header, d.y_axis.header, d.prelookup) == (X, Y, True) for d in desc.values())
    monkeypatch.setattr(tricore_refs, 'BLANK_AXES', False)
    assert call_descriptors(data) == {}                  # 50 % parsable axes: below PRELOOKUP_SHARE


def test_plain_prelookups_are_unchanged_by_blank_axes(monkeypatch):
    data, tables = image_with(prelookup_code, routines=U8_TABLE)
    before = call_descriptors(data)
    monkeypatch.setattr(tricore_refs, 'BLANK_AXES', False)
    assert set(call_descriptors(data)) == set(before) == set(tables)
