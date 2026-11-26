"""Code-backed axes (quality phase 4, synthetic images only).

axis_at and record_at accept only strictly increasing breakpoints. When a routine whose axis
width / record layout is learned from its strictly readable calls reads a header, repeated
breakpoints ("plateau") or all-equal breakpoints ("blank", unapplied) are real axes too. Such
readings are marked on the descriptor and in the evidence text; they never choose a width
by the values.
"""
import numpy as np
import pytest
from ecu_studio.core import tricore_refs
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.structure_scan import CALL_LAYOUT, CODE_AXES_NOTE
from ecu_studio.core.tricore_refs import call_descriptors, code_axis, code_record, _learned
from test_tricore_refs import record, reader, load, call, movh_a, RET, LD_BU, LD_H


@pytest.mark.parametrize('raw, width, state', [
    (bytes([4, 1, 2, 3, 4]), 1, ''),
    (bytes([4, 1, 2, 4, 4]), 1, 'plateau'),
    (bytes([4, 0, 0, 0, 0]), 1, 'blank'),
    (np.array([3, 100, 900, 900], '<u2').tobytes(), 2, 'plateau'),
    (np.array([3, -50, 0, 0], '<i2').tobytes(), 2, 'plateau'),       # falls unsigned, rises signed
])
def test_code_axis_states(raw, width, state):
    img = bytes(16) + raw + b'\xff' * 8
    got = code_axis(img, 16, width)
    assert got is not None and got[1] == state and got[0].count == raw[0] and got[0].width == width


@pytest.mark.parametrize('raw, width', [
    (bytes([4, 4, 3, 2, 1]), 1),                                         # falling
    (bytes([1, 0]), 1),                                                  # one point
    (bytes([0x40]) + bytes(0x40), 1),                                    # count beyond 32
    (bytes([8, 0]) + bytes(4), 2),                                       # runs past the end
])
def test_code_axis_rejects(raw, width):
    assert code_axis(bytes(16) + raw, 16, width) is None


def test_width_is_given_not_chosen_by_the_values():
    """08 00 + zeros: a blank 16-bit axis of 8 points, or a blank 8-bit axis of 8 zeros after count 8."""
    img = bytes(16) + bytes([8, 0]) + bytes(16) + b'\xff' * 4
    assert code_axis(img, 16, 2)[0].count == 8 and code_axis(img, 16, 2)[0].width == 2
    assert code_axis(img, 16, 1)[0].width == 1                         # the learned width decides


def test_code_record_reads_plateau_axes_with_the_learned_layout():
    z = 900 - np.arange(48).reshape(6, 8) * 3
    raw = bytes(2) + record(z, [100, 200, 300, 400, 500, 600, 800, 800], [1, 2, 3, 4, 5, 6])
    x, y, state = code_record(raw, 2, (1, 2, 1))
    assert (x.count, x.width, y.count, y.width, state) == (8, 2, 6, 1, 'plateau')
    assert code_record(raw, 2, (1, 1, 1)) is None or code_record(raw, 2, (1, 1, 1))[0].width == 1


def test_learned_needs_enough_agreeing_calls(monkeypatch):
    from collections import Counter
    assert _learned({1: Counter({2: 5}), 2: Counter({2: 4}), 3: Counter({2: 9, 1: 2})}) == {1: 2}


def plateau_record_image(n=24, plateau=(3, 7, 11)):
    """Records (falling i16 data: one reading each) from 0x8000; some with a repeated last X point."""
    img = bytearray(0x10000)
    headers, starts, pos = [], [], 0x8000
    for i in range(n):
        xs = [100, 200, 300, 400, 500, 600, 700, 800] if i not in plateau else [100, 200, 300, 400, 500, 600, 800, 800]
        z = 2000 - np.arange(48).reshape(6, 8) * 7 - i
        raw = record(z, xs, [1, 2, 3, 4, 5, 6])
        img[pos:pos + len(raw)] = raw
        headers.append(pos)
        starts.append(pos + 2 + 16 + 6)
        pos += len(raw)
    body = reader(LD_BU, LD_BU, *(LD_H,) * 10)
    img[0x7000:0x7000 + len(body)] = body
    code = bytearray()
    for h in headers:
        code += load(4, h) + call(0x100 + len(code) + 8, 0x7000) + RET
    while len(code) < 0x6000:
        code += movh_a(12, 0xD000) + RET + RET
    img[0x100:0x100 + len(code)] = code[:0x6F00]
    return bytes(img), headers, starts


def test_records_with_plateau_axes_are_named_and_marked(monkeypatch):
    plateau = (3, 7, 11)
    data, headers, starts = plateau_record_image(plateau=plateau)
    desc = call_descriptors(data)
    assert set(desc) == set(starts)
    assert {i for i, s in enumerate(starts) if desc[s].axis_state} == set(plateau)
    assert all(desc[starts[i]].axis_state == 'plateau' for i in plateau)
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = {m.offset: m for m in maps if m.record_layout == CALL_LAYOUT}
    assert CODE_AXES_NOTE.strip() in called[starts[3]].label_evidence and not called[starts[3]].verified
    assert CODE_AXES_NOTE.strip() not in called[starts[0]].label_evidence
    monkeypatch.setattr(tricore_refs, 'CODE_AXES', False)
    assert set(call_descriptors(data)) == set(starts) - {starts[i] for i in plateau}


def test_routine_with_too_few_strict_calls_learns_no_layout():
    """Most records plateau: the strictly readable calls are too few to fix the layout - nothing new."""
    data, headers, starts = plateau_record_image(n=24, plateau=tuple(range(20)))
    desc = call_descriptors(data)
    assert not any(d.axis_state for d in desc.values())


# --- Prelookups of the routine (PRE_FUNCTION) ---------------------------------------------------------------

from test_tricore_refs import image_with, prelookup_code, U8_TABLE   # noqa: E402

X_HDR, X2_HDR, Y_HDR = 0xC000, 0xC008, 0xC010


def j24(at, target):
    disp = ((target - at) // 2) & 0xFFFFFF
    return (0x1D | (disp >> 16) << 8 | (disp & 0xFFFF) << 16).to_bytes(4, 'little')


def far_jump_code(tables, base, *, special=6, heads=(X_HDR, Y_HDR), ret_between=False):
    """Most tables as prelookup_code; the last `special` ones in routines of their own (called from stubs) whose
    two prelookups sit before a far jump, so the table call's own path holds none."""
    normal, spec = tables[:-special], tables[-special:]
    code = bytearray(prelookup_code(normal, base))
    stubs = base + len(code)
    block_len = 12 * len(heads) + 4 + (2 if ret_between else 0) + 12 + 2
    first = stubs + 4 * special + 2
    for k in range(special):
        code += call(base + len(code), first + k * block_len)
    code += RET
    for t in spec:
        start = base + len(code)
        for i, hdr in enumerate(heads):
            code += load(4, hdr) + call(base + len(code) + 8, 0x7100 if i == 0 else 0x7200)
        if ret_between:
            code += RET
        code += j24(base + len(code), base + 0x5800)     # beyond MAX_JOIN: the path state ends here
        code += load(4, t) + call(base + len(code) + 8, 0x7300) + RET
        assert base + len(code) - start == block_len
    return bytes(code)


def test_table_call_after_a_far_jump_takes_the_two_prelookups_of_its_routine(monkeypatch):
    data, tables = image_with(far_jump_code, n_tables=30, routines=U8_TABLE)
    desc = call_descriptors(data)
    spec = tables[-6:]
    assert set(desc) == set(tables)
    for t in spec:
        d = desc[t]
        assert (d.x_axis.header, d.y_axis.header, d.prelookup, d.pre_scope) == (X_HDR, Y_HDR, True, 'function')
    assert all(desc[t].pre_scope == '' for t in tables[:-6])
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    called = {m.offset: m for m in maps if m.record_layout == CALL_LAYOUT}
    from ecu_studio.core.structure_scan import PRE_FUNCTION_NOTE
    assert PRE_FUNCTION_NOTE.strip() in called[spec[0]].label_evidence and not called[spec[0]].verified
    monkeypatch.setattr(tricore_refs, 'PRE_FUNCTION', False)
    assert set(call_descriptors(data)) == set(tables[:-6])


def test_three_prelookup_axes_in_the_routine_leave_the_call_open():
    data, tables = image_with(lambda t, b: far_jump_code(t, b, heads=(X_HDR, X2_HDR, Y_HDR)), n_tables=30,
                              routines=U8_TABLE)
    assert set(call_descriptors(data)) == set(tables[:-6])


def test_a_return_between_prelookups_and_call_leaves_the_call_open():
    data, tables = image_with(lambda t, b: far_jump_code(t, b, ret_between=True), n_tables=30, routines=U8_TABLE)
    assert set(call_descriptors(data)) == set(tables[:-6])
