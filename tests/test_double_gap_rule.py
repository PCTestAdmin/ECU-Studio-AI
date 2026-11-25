"""Counterexamples for the double-gap rule (tricore_refs.DOUBLE_GAP_WEAK, quality phase 5; synthetic, phase 6).

A gap exactly twice a byte table fits one 16-bit table and also two byte tables in a row. The exact 16-bit fit
is therefore a weak vote: it follows the routine only when at least three other calls of the same routine
agree unanimously on a width from their own gaps (strong votes). These tests pin down where the rule must NOT
change a width, and the one known limitation (agreeing wrong votes).
"""
from ecu_studio.core import tricore_refs
from ecu_studio.core.axis_arrays import CountAxis
from ecu_studio.core.tricore_refs import CallDescriptor

R, OTHER = 0x7000, 0x7100


def desc(d, callee=R, nx=4, ny=4, **kw):
    ax = lambda h, n: CountAxis(h, h + 2, n, 2, tuple(range(n)))   # noqa: E731
    return CallDescriptor(d, ax(0xC000, nx), ax(0xC100, ny), callee, (d,), **kw)


def widths(descs, extra_bounds):
    d = {x.data: x for x in descs}
    return tricore_refs.cell_widths(d, list(d) + list(extra_bounds))


def byte_votes(start, n=3, callee=R):
    """n tables of 16 cells, each followed directly by the next object: only 1 byte fits (strong votes)."""
    return [desc(start + 16 * i, callee) for i in range(n)], [start + 16 * n]


def test_real_16_bit_tables_without_byte_votes_stay_16_bit():
    # every exact 16-bit fit is weak, but weak votes never decide: nothing to follow, the exact fit stays
    tables = [desc(0x1000 + 32 * i) for i in range(5)]
    out = widths(tables, [0x1000 + 32 * 5])
    assert set(out.values()) == {2}


def test_routine_table_loads_decide_before_the_gap():
    # width from the routine's own loads (cell_width) is never weak
    votes, bounds = byte_votes(0x1000)
    real = desc(0x2000, cell_width=2)
    out = widths(votes + [real], bounds + [0x2020])
    assert out[0x2000] == 2


def test_two_adjacent_byte_tables_follow_three_agreeing_byte_votes():
    votes, bounds = byte_votes(0x1000)
    out = widths(votes + [desc(0x2000)], bounds + [0x2020])
    assert out[0x2000] == 1


def test_byte_table_with_alignment_padding_votes_and_follows():
    # 16 cells + 2 padding bytes: still an exact byte fit (MAX_PAD) and a strong vote
    padded = [desc(0x1000 + 18 * i) for i in range(3)]          # d % 2 == 0 for all
    double_with_pad = desc(0x2000)                              # 32 + 2 bytes: exact 16-bit fit with padding
    out = widths(padded + [double_with_pad], [0x1000 + 18 * 3, 0x2022])
    assert [out[t.data] for t in padded] == [1, 1, 1]
    assert out[0x2000] == 1


def test_16_bit_table_with_an_apparent_object_inside_is_cut_not_followed():
    # an apparent object (e.g. a misread axis header) in the middle of a real 16-bit table makes it an exact
    # byte fit; that is a strong byte vote of its own, independent of the rule
    out = widths([desc(0x1000)], [0x1010, 0x1020])
    assert out[0x1000] == 1
    # one such vote alone does not move the weak 16-bit tables of the same routine
    out = widths([desc(0x1000), desc(0x2000), desc(0x3000)], [0x1010, 0x2020, 0x3020])
    assert (out[0x2000], out[0x3000]) == (2, 2)


def test_mixed_widths_in_one_routine_decide_nothing():
    votes, bounds = byte_votes(0x1000)
    sixteen = desc(0x3000, cell_width=2)                        # a strong 16-bit vote of the same routine
    out = widths(votes + [sixteen, desc(0x2000)], bounds + [0x2020, 0x3020])
    assert out[0x2000] == 2


def test_contradicting_votes_keep_the_exact_fit():
    a, b1 = byte_votes(0x1000, n=3)
    c = [desc(0x4000, cell_width=2), desc(0x4100, cell_width=2), desc(0x4200, cell_width=2)]
    out = widths(a + c + [desc(0x2000)], b1 + [0x2020, 0x4020, 0x4120, 0x4220])
    assert out[0x2000] == 2


def test_too_few_votes_keep_the_exact_fit():
    votes, bounds = byte_votes(0x1000, n=2)
    out = widths(votes + [desc(0x2000)], bounds + [0x2020])
    assert out[0x2000] == 2


def test_votes_of_another_routine_do_not_count():
    votes, bounds = byte_votes(0x1000, callee=OTHER)
    out = widths(votes + [desc(0x2000)], bounds + [0x2020])
    assert out[0x2000] == 2


def test_different_layouts_of_one_routine_still_vote_together():
    shapes = [(4, 4), (8, 2), (2, 8)]
    votes = [desc(0x1000 + 16 * i, nx=nx, ny=ny) for i, (nx, ny) in enumerate(shapes)]
    weak = desc(0x2000, nx=6, ny=3)                             # 18 cells: 36 bytes = two byte tables of 18
    out = widths(votes + [weak], [0x1030, 0x2024])
    assert out[0x2000] == 1


def test_prelookup_tables_neither_vote_nor_follow():
    pre = [desc(0x1000 + 16 * i, prelookup=True) for i in range(3)]
    out = widths(pre + [desc(0x2000)], [0x1030, 0x2020])
    assert out[0x2000] == 2


def test_known_limit_three_agreeing_wrong_votes_are_followed():
    """Known limitation (documented, not hidden): when three calls of one routine are all cut by apparent objects
    in the middle of real 16-bit tables, their byte votes agree and a weak 16-bit table of that routine follows
    them. Real routines read one cell type, so agreeing wrong votes need three independent misreadings; in the
    benchmark data no such case was found (development 0 changes, holdout: only the regression fixed)."""
    cut = [desc(0x1000 + 0x100 * i) for i in range(3)]
    bounds = [0x1010, 0x1110, 0x1210]                           # apparent objects in the middle
    out = widths(cut + [desc(0x2000)], bounds + [0x2020])
    assert out[0x2000] == 1


def test_switch_off_restores_the_exact_fit():
    import pytest
    votes, bounds = byte_votes(0x1000)
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(tricore_refs, 'DOUBLE_GAP_WEAK', False)
        assert widths(votes + [desc(0x2000)], bounds + [0x2020])[0x2000] == 2
    finally:
        mp.undo()
