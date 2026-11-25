"""Curve routines among the prelookup routines (quality phase 5, synthetic images only).

A curve record n, X[n], W[n] starts like a count-prefixed axis, so a routine that interpolates curves from their
own records is learned as a prelookup. Code-named addresses tell it apart: behind the axis of a curve record lie
exactly its n values up to the next object the code names. A routine whose distinct targets agree on one value
width is a curve routine; each of its calls names a curve (values behind the axis), unless a code-named address
lies inside the values. A routine that searches few shared axes many times stays a prelookup.
"""
import numpy as np
import pytest
from ecu_studio.core import tricore_refs
from ecu_studio.core.confidence import type_doubts
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.structure_scan import CURVE_ORIGIN
from ecu_studio.core.tricore_refs import call_descriptors
from test_tricore_refs import U8_TABLE, call, image_with, load, prelookup_code

CURVES = 0xB000
CURVE_ROUTINE = 0x7400
X = [100, 200, 400, 800, 1600, 3200]


def curve_record(values):
    return np.array([len(X)] + X, '<u2').tobytes() + np.asarray(values, '<u2').tobytes()


def curve_image(n_curves=8, inside=None):
    """Split-interpolation tables (prelookups at 0x7100/0x7200, table routine 0x7300) plus a chain of 16-bit
    curve records from CURVES, each head passed in a4 to the curve routine. ``inside``: index of a curve whose
    values contain an address that other code names."""
    heads = []

    def code(tables, base):
        out = bytearray(prelookup_code(tables, base))
        for h in heads:
            out += load(4, h) + call(base + len(out) + 8, CURVE_ROUTINE)
        if inside is not None:
            out += load(4, heads[inside] + 2 + 2 * len(X) + 4) + call(base + len(out) + 8, 0x7000)
        return bytes(out)

    pos = CURVES
    for k in range(n_curves):
        heads.append(pos)
        pos += len(curve_record([0] * len(X)))
    data, tables = image_with(code, routines=U8_TABLE)
    img = bytearray(data)
    for k, h in enumerate(heads):
        raw = curve_record([50 + k, 60 + k, 75 + k, 90 + k, 70 + k, 40 + k])
        img[h:h + len(raw)] = raw
    img[CURVE_ROUTINE:CURVE_ROUTINE + 2] = (0x9000).to_bytes(2, 'little')
    return bytes(img), tables, heads


def values_of(h):
    return h + 2 + 2 * len(X)


def test_curve_routine_calls_name_curves_and_the_last_one_only_by_the_routine():
    data, tables, heads = curve_image()
    desc = call_descriptors(data)
    curves = {d: c for d, c in desc.items() if c.curve}
    assert set(curves) == {values_of(h) for h in heads}
    assert all(c.x_axis.header == h and c.x_axis.count == len(X) and c.y_axis is None and c.cell_width == 2
               for h, c in ((h, curves[values_of(h)]) for h in heads))
    # each value block ends at the next named record head; the last one has no named object behind it
    assert [curves[values_of(h)].curve for h in heads] == ['exact'] * (len(heads) - 1) + ['routine']
    # the curve routine's sign is not taken from its loads (CURVE_ROUTINE_SIGN off)
    assert {c.cell_signed for c in curves.values()} == {None}


def test_shared_axis_searches_stay_prelookups():
    data, tables, _ = curve_image()
    desc = call_descriptors(data)
    assert all((desc[t].x_axis.header, desc[t].y_axis.header, desc[t].prelookup, desc[t].curve)
               == (0xC000, 0xC010, True, '') for t in tables if t in desc)
    assert 0x7100 not in tricore_refs.curve_routines(data, *_routine_args(data))


def _routine_args(data):
    sites, h, entries = tricore_refs._analyse(data)
    pre, _ = tricore_refs.prelookup_roles(data, sites)
    named = sorted({c.data for c in sites} | {v for _, _, regs in sites.generic for _, v in regs})
    return sites, pre, named, lambda at: tricore_refs.axis_at(data, at)


def test_a_named_address_inside_the_values_rejects_that_curve_only():
    data, _, heads = curve_image(inside=3)
    curves = {d for d, c in call_descriptors(data).items() if c.curve}
    assert values_of(heads[3]) not in curves
    assert {values_of(h) for k, h in enumerate(heads) if k not in (2, 3)} <= curves


def test_too_few_curve_targets_are_no_curve_routine():
    data, _, _ = curve_image(n_curves=tricore_refs.CODE_AXES_MIN - 1)
    assert not any(c.curve for c in call_descriptors(data).values())


def test_switch_off_restores_the_previous_result(monkeypatch):
    data, _, _ = curve_image()
    monkeypatch.setattr(tricore_refs, 'CODE_CURVES', False)
    assert not any(c.curve for c in call_descriptors(data).values())


def test_scan_marks_curves_with_their_evidence_and_the_routine_width_as_derived():
    data, _, heads = curve_image()
    maps = scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    got = {m.offset: m for m in maps if m.label_origin == CURVE_ORIGIN}
    assert set(got) == {values_of(h) for h in heads}
    assert all((m.rows, m.cols, m.dtype[1:]) == (1, len(X), '16') for m in got.values())
    last = got[values_of(heads[-1])]
    assert 'width-derived' in {k for k, _ in type_doubts(last)}
    assert 'nur aus der Kennlinienroutine abgeleitet' in last.label_evidence
    first = got[values_of(heads[0])]
    assert 'exakt' in first.label_evidence and 'width-derived' not in {k for k, _ in type_doubts(first)}
    # the axis of each accepted curve is a candidate too, read from the record head
    axes = {m.offset for m in maps if m.rows * m.cols == len(X) and m.offset + 2 * len(X) in got}
    assert {h + 2 for h in heads} <= axes


def _desc(d, callee, nx=4, ny=4):
    from ecu_studio.core.axis_arrays import CountAxis
    from ecu_studio.core.tricore_refs import CallDescriptor
    ax = lambda h, n: CountAxis(h, h + 2, n, 2, tuple(range(n)))
    return CallDescriptor(d, ax(0xC000, nx), ax(0xC100, ny), callee, (d,))


def test_a_gap_of_two_byte_tables_follows_the_routine(monkeypatch):
    """A gap exactly twice a byte table also holds two byte tables in a row: three tables of the same routine
    that only fit as bytes settle it. Without such votes the exact 16-bit fit stays (switch off: as before)."""
    routine, other = 0x7000, 0x7100
    desc = {0x1000: _desc(0x1000, routine), 0x1010: _desc(0x1010, routine), 0x1020: _desc(0x1020, routine),
            0x1040: _desc(0x1040, routine), 0x2000: _desc(0x2000, other)}
    # bytes only: 16 cells before the next object; 0x1040 and 0x2000: 32 bytes up to the next object
    bounds = list(desc) + [0x1030, 0x1060, 0x2020]
    widths = tricore_refs.cell_widths(desc, bounds)
    assert [widths[d] for d in (0x1000, 0x1010, 0x1020)] == [1, 1, 1]
    assert widths[0x1040] == 1 and widths[0x2000] == 2
    monkeypatch.setattr(tricore_refs, 'DOUBLE_GAP_WEAK', False)
    assert tricore_refs.cell_widths(desc, bounds)[0x1040] == 2
