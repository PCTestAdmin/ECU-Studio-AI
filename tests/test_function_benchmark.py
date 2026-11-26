"""Hard splits and counts for the function layer (tools/function_benchmark, synthetic)."""
import pytest
from ecu_studio.core.model import MapDefinition
from ecu_studio.tools import function_benchmark as B


def table(offset, function, size=32):
    return MapDefinition(name=f'T{offset:X}', offset=offset, rows=1, cols=size // 2, dtype='u16', endian='little',
                         source='a2l', function=function)


def chain(functions, gap=0, size=32, start=0x1000):
    """Back-to-back tables (direct neighbours) with the given functions."""
    return [table(start + i * (size + gap), f, size) for i, f in enumerate(functions)]


def test_splits_are_deterministic_and_only_take_tables_with_a_function():
    maps = chain(['A'] * 50 + [''] * 5 + ['B'] * 50)
    for mode in B.MODES:
        first = B.split(maps, mode, .25, salt='x')
        assert first == B.split(maps, mode, .25, salt='x')
        assert all(maps[i].function for i in first)
    assert B.split(maps, 'table', 0.) == set() and B.split(maps, 'block', 0.) == set()


def test_alternate_split_is_every_second_table_by_address():
    maps = chain(['A'] * 6)
    assert B.split(maps, 'alternate') == {0, 2, 4}


def test_block_split_keeps_whole_blocks_together():
    maps = chain(['A'] * 400)               # 400 x 32 bytes over several 4-KiB blocks
    anchors = B.split(maps, 'block', .5, salt='s')
    for block in {m.offset // B.BLOCK for m in maps}:
        side = {i in anchors for i, m in enumerate(maps) if m.offset // B.BLOCK == block}
        assert len(side) == 1


def test_function_split_hides_whole_functions_so_every_assignment_is_wrong():
    maps = chain(['A', 'A', 'A', 'B', 'B', 'B', 'C', 'C'])
    anchors = B.split(maps, 'function', .5, salt='k')
    hidden_functions = {maps[i].function for i in range(len(maps)) if i not in anchors}
    assert not hidden_functions & {maps[i].function for i in anchors}
    s = B.score(maps, anchors)
    assert s.correct == 0 and s.reachable == 0
    assert s.evaluable == len(maps) - len(anchors)
    assert s.withheld == s.unknown and s.withheld + s.wrong == s.evaluable


def test_score_counts_correct_wrong_and_unknown_with_the_evaluable_total():
    maps = chain(['A', 'A', 'A', 'B']) + [table(0x9000, 'C')]      # C stands alone: no relation
    s = B.score(maps, {0, 2})
    assert s.evaluable == 3 and s.correct + s.wrong + s.unknown == 3
    assert s.correct == 1          # second A: enclosed by two anchors of A
    assert s.unknown == 2          # B: one-sided neighbour of A (no vote); C: no relation to an anchor
    assert s.by_status['Vermutet', 'correct'] == 1
    assert s.precision == 1.0 and s.coverage == round(1 / 3, 4)
    assert s.as_dict()['precision'] == 1.0


def test_without_anchors_nothing_is_named():
    maps = chain(['A'] * 10)
    s = B.score(maps, set())
    assert s.correct == s.wrong == 0 and s.unknown == 10


def test_group_purity_and_relation_precision():
    from ecu_studio.core import function_id as F
    maps = chain(['A', 'A', 'B'])
    rels = [F.Relation(0, 1, F.AXIS), F.Relation(1, 2, F.AXIS)]
    assert B.relation_precision(maps, rels)['axis'] == {'same': 1, 'different': 1}
    pur = B.group_purity(maps, rels)
    assert pur['groups'] == 1 and pur.get('pure', 0) == 0 and pur['majority_members'] == 2


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        B.split([], 'nearest')
