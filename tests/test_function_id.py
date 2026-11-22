"""Function membership: only from definitions and relations to known tables, never invented
(after 1.21.0-rc1, synthetic)."""
from ecu_studio.core.a2l import parse_a2l
from ecu_studio.core.function_id import (AXIS, CONFIRMED, NEIGHBOUR, ROUTINE, STRONG, SUSPECTED, UNKNOWN, Relation,
                                         counts, groups, identify, relations)
from ecu_studio.core.model import MapDefinition


def table(name, offset, function='', verified=False, source='a2l', **kw):
    return MapDefinition(name=name, offset=offset, rows=4, cols=4, dtype='u8', function=function,
                         function_source='A2L FUNCTION (DEF_CHARACTERISTIC)' if function else '',
                         verified=verified, source=source, **kw)


def test_own_checked_definition_is_confirmed_unchecked_is_strongly_supported():
    h = identify([table('A', 0, 'FN_A', verified=True), table('B', 0x100, 'FN_B')], rels=[])
    assert (h[0].function, h[0].status) == ('FN_A', CONFIRMED)
    assert (h[1].function, h[1].status) == ('FN_B', STRONG)
    assert h[0].evidence[0].source == 'A2L FUNCTION (DEF_CHARACTERISTIC)'


def test_table_without_evidence_stays_unknown_and_gets_no_name():
    h = identify([table('?', 0, source='heuristic')], rels=[])
    assert (h[0].function, h[0].status, h[0].evidence) == ('', UNKNOWN, [])


def test_one_relation_kind_is_suspected_two_kinds_strongly_supported():
    maps = [table('A', 0, 'FN_A', verified=True), table('x', 0x100, source='heuristic'),
            table('y', 0x200, source='heuristic')]
    rels = [Relation(0, 1, AXIS, 'Achse bei 0x900'), Relation(0, 2, AXIS), Relation(0, 2, ROUTINE)]
    h = identify(maps, rels)
    assert (h[1].function, h[1].status) == ('FN_A', SUSPECTED)
    assert (h[2].function, h[2].status) == ('FN_A', STRONG)
    assert [e.kind for e in h[2].evidence] == [AXIS, ROUTINE]


def test_relations_to_different_functions_are_a_contradiction():
    maps = [table('A', 0, 'FN_A', verified=True), table('B', 0x200, 'FN_B', verified=True),
            table('x', 0x100, source='heuristic')]
    h = identify(maps, [Relation(0, 2, AXIS), Relation(1, 2, AXIS)])
    assert (h[2].function, h[2].status) == ('', UNKNOWN)
    assert h[2].contradictions and 'FN_A' in ' '.join(h[2].contradictions) and 'FN_B' in ' '.join(h[2].contradictions)


def test_a_neighbour_votes_only_when_one_function_encloses_the_table():
    """A lone neighbour caused most wrong assignments under hard splits (function boundaries lie between
    neighbours); enclosed on both sides by tables of one function it still votes."""
    a, b = table('A', 0, 'FN_A', verified=True), table('B', 0x200, 'FN_B', verified=True)
    x = table('x', 0x100, source='heuristic')
    one_side = identify([a, x], [Relation(0, 1, NEIGHBOUR)])[1]
    assert (one_side.function, one_side.status) == ('', UNKNOWN)
    a2 = table('A2', 0x200, 'FN_A', verified=True)
    enclosed = identify([a, x, a2], [Relation(0, 1, NEIGHBOUR), Relation(1, 2, NEIGHBOUR)])[1]
    assert (enclosed.function, enclosed.status) == ('FN_A', SUSPECTED)
    between = identify([a, x, b], [Relation(0, 1, NEIGHBOUR), Relation(1, 2, NEIGHBOUR)])[1]
    assert between.function == ''


def test_hypotheses_never_feed_other_hypotheses():
    maps = [table('A', 0, 'FN_A', verified=True), table('x', 0x100, source='heuristic'),
            table('y', 0x200, source='heuristic')]
    h = identify(maps, [Relation(0, 1, AXIS), Relation(1, 2, AXIS)])
    assert h[1].status == SUSPECTED and h[2].status == UNKNOWN


def test_transferred_function_stays_suspected_and_conflicts_are_listed():
    moved = table('T', 0x100, 'FN_T', source='transfer-proposed', label_origin='Namensübertragung · Achsen')
    assert identify([moved], rels=[])[0].status == SUSPECTED
    anchor = table('A', 0, 'FN_A', verified=True)
    h = identify([anchor, moved], [Relation(0, 1, AXIS)])
    assert h[1].status == UNKNOWN and h[1].contradictions


def test_own_definition_keeps_its_function_and_reports_conflicting_relations():
    maps = [table('A', 0, 'FN_A', verified=True), table('B', 0x100, 'FN_B', verified=True)]
    h = identify(maps, [Relation(0, 1, AXIS)])
    assert h[1].function == 'FN_B' and h[1].status == CONFIRMED and h[1].contradictions


def test_relations_from_shared_axes_and_neighbourhood():
    a = table('A', 0x100, axis_x_offset=0x900)
    b = table('B', 0x110, axis_x_offset=0x900)            # directly after A (A ends at 0x110)
    c = table('C', 0x400, axis_x_offset=0x3F8)            # own record axis right in front of the values
    d = table('D', 0x408, axis_x_offset=0x380)            # own axis far in front (outside its record)
    e = table('E', 0x600, axis_x_offset=0x5F0)            # own record axis: the record starts at 0x5F0
    rels = relations([a, b, c, d, e])
    kinds = {(r.a, r.b, r.kind) for r in rels}
    assert (0, 1, AXIS) in kinds and (0, 1, NEIGHBOUR) in kinds
    assert not any(r.kind == AXIS for r in rels if {r.a, r.b} & {2, 3, 4})   # own axes are not shared
    assert (1, 2, NEIGHBOUR) not in kinds  # gap of several hundred bytes
    assert (3, 4, NEIGHBOUR) not in kinds  # D ends at 0x418, E's record starts at its axis 0x5F0
    # a record whose own axis starts right after the previous table is its neighbour
    f = table('F', 0x620, axis_x_offset=0x612)            # E ends at 0x610, F's record starts at 0x612
    assert (4, 5, NEIGHBOUR) in {(r.a, r.b, r.kind) for r in relations([a, b, c, d, e, f])}


def test_groups_are_structural_and_unnamed():
    maps = [table('A', 0), table('B', 0x100), table('C', 0x200)]
    assert groups(maps, [Relation(0, 1, AXIS), Relation(1, 2, NEIGHBOUR)]) == [[0, 1]]


def test_counts_cover_every_status():
    h = identify([table('A', 0, 'FN_A', verified=True), table('?', 0x100, source='heuristic')], rels=[])
    assert counts(h) == {CONFIRMED: 1, STRONG: 0, SUSPECTED: 0, UNKNOWN: 1}


def test_a2l_function_membership_is_read_from_def_characteristic():
    cat = parse_a2l("""
/begin PROJECT P "" /begin MODULE M ""
/begin RECORD_LAYOUT RL FNC_VALUES 1 UBYTE COLUMN_DIR DIRECT /end RECORD_LAYOUT
/begin CHARACTERISTIC K1 "" VAL_BLK 0x10 RL 0 NO_COMPU_METHOD 0 255 NUMBER 4 /end CHARACTERISTIC
/begin CHARACTERISTIC K2 "" VAL_BLK 0x20 RL 0 NO_COMPU_METHOD 0 255 NUMBER 4 /end CHARACTERISTIC
/begin FUNCTION FN_LAMBDA "Lambda"
  /begin DEF_CHARACTERISTIC K1 /end DEF_CHARACTERISTIC
  /begin REF_CHARACTERISTIC K2 /end REF_CHARACTERISTIC
/end FUNCTION
/end MODULE /end PROJECT
""")
    assert cat.functions == {'K1': ('FN_LAMBDA',)}
    res = cat.link(file_size=0x40, data=bytes(0x40))
    by = {m.name: m for m in res.maps}
    assert by['K1'].function == 'FN_LAMBDA' and by['K1'].function_source.startswith('A2L FUNCTION')
    assert by['K2'].function == ''        # only read by the function (REF), not defined by it
