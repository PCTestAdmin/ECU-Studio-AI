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


# ---- abstention (quality phase 3): unknown is better than a wrong function ------------------------------

def _hub(a, b, kind=AXIS, hub=('axis', 0x9000)):
    return Relation(a, b, kind, 'Achse bei 0x9000', hub=hub)


def test_rejected_hub_rule_stays_available_as_ablation(monkeypatch):
    """Ablation switch (off by default, rejected on development data): one anchor among thirty users of a
    shared axis is then no evidence for the other twenty-nine."""
    import ecu_studio.core.function_id as F
    monkeypatch.setattr(F, 'HUB_MIN_SHARE', .1)
    maps = [table('A', 0, 'FN_A', verified=True)] + [table(f'x{k}', 0x100 * (k + 1), source='heuristic')
                                                      for k in range(30)]
    users = range(len(maps))
    rels = [_hub(a, b) for a in users for b in users if a < b]
    h = identify(maps, rels)
    assert all(x.function == '' and x.status == UNKNOWN for x in h[1:])
    assert any('nur 1 von 30' in c for c in h[1].candidates)
    assert 'Funktion unbekannt' in h[1].describe()


def test_a_shared_source_votes_when_enough_of_its_users_are_anchors():
    maps = [table('A1', 0, 'FN_A', verified=True), table('A2', 0x100, 'FN_A', verified=True),
            table('x', 0x200, source='heuristic')]
    rels = [_hub(0, 1), _hub(0, 2), _hub(1, 2)]
    h = identify(maps, rels)[2]
    assert (h.function, h.status) == ('FN_A', SUSPECTED)
    assert h.missing and 'Programmcode' in h.missing[0]


def test_a_function_missing_among_the_nearest_anchors_is_held_back():
    """The calibration is laid out by module: an axis to a far table of FN_A while the tables around
    belong to FN_B and FN_C names nothing (the hidden table's true function may not be among the anchors)."""
    far = table('A', 0x100000, 'FN_A', verified=True)
    around = [table('B1', 0x1000, 'FN_B', verified=True), table('B2', 0x1100, 'FN_B', verified=True),
              table('C1', 0x1300, 'FN_C', verified=True), table('C2', 0x1400, 'FN_C', verified=True)]
    x = table('x', 0x1200, source='heuristic')
    maps = [far, *around, x]
    h = identify(maps, [Relation(0, 5, AXIS)])[5]
    assert (h.function, h.status) == ('', UNKNOWN)
    assert 'Speicherlage' in h.reasons[0] and h.candidates and h.evidence
    near = table('A2', 0x1250, 'FN_A', verified=True)
    h2 = identify(maps + [near], [Relation(0, 5, AXIS)])[5]
    assert (h2.function, h2.status) == ('FN_A', SUSPECTED)


def test_an_axis_whose_users_disagree_on_its_length_does_not_vote():
    a = table('A', 0x100, 'FN_A', verified=True, axis_x_offset=0x900)
    b = MapDefinition(name='x', offset=0x200, rows=4, cols=8, dtype='u8', source='heuristic', axis_x_offset=0x900)
    rels = relations([a, b])
    axis = [r for r in rels if r.kind == AXIS]
    assert axis and 'uneinig' in axis[0].doubt
    h = identify([a, b], rels)[1]
    assert h.function == '' and any('uneinig' in c for c in h.contradictions)


def test_identify_does_not_depend_on_the_order_of_the_tables():
    maps = [table('A', 0, 'FN_A', verified=True), table('x', 0x100, source='heuristic'),
            table('B', 0x200, 'FN_B', verified=True), table('y', 0x300, source='heuristic'),
            table('A2', 0x400, 'FN_A', verified=True)]
    rels = [Relation(0, 1, AXIS), Relation(3, 4, AXIS), Relation(2, 3, AXIS)]
    first = {maps[h.index].name: (h.function, h.status) for h in identify(maps, rels)}
    perm = [4, 3, 2, 1, 0]
    where = {old: new for new, old in enumerate(perm)}
    moved = [Relation(min(where[r.a], where[r.b]), max(where[r.a], where[r.b]), r.kind) for r in rels]
    second = {m.name: (h.function, h.status) for m, h in zip([maps[k] for k in perm],
                                                             identify([maps[k] for k in perm], moved))}
    assert first == second


# ---- self-check of relation kinds on the anchors of the same file (ablation switch, off by default) -----

def _row(n, function_of, start=0):
    """n tables in a row, 0x100 apart; function_of(k) -> function ('' = heuristic table without one)."""
    return [table(f't{k}', start + 0x100 * k, function_of(k), verified=bool(function_of(k)),
                  source='a2l' if function_of(k) else 'heuristic') for k in range(n)]


def test_a_kind_that_disagrees_with_the_anchors_of_the_file_does_not_vote(monkeypatch):
    """Shared axes that link tables of different functions in this file are no function evidence here."""
    import ecu_studio.core.function_id as F
    monkeypatch.setattr(F, 'SELF_CHECK', True)
    maps = _row(24, lambda k: f'FN_{k % 2}' if k < 23 else '')
    rels = [Relation(k, k + 1, AXIS) for k in range(22)] + [Relation(22, 23, AXIS)]
    agree, checks = F.reliability(maps, rels)[AXIS]
    assert checks >= F.MIN_CHECKS and agree < F.RELIABLE_SHARE * checks
    h = identify(maps, rels)[23]
    assert (h.function, h.status) == ('', UNKNOWN)
    assert any('unzuverlässig' in c and f'von {checks}' in c for c in h.candidates)


def test_a_kind_that_agrees_with_the_anchors_of_the_file_votes():
    import ecu_studio.core.function_id as F
    maps = _row(24, lambda k: 'FN_A' if k < 23 else '')
    rels = [Relation(k, k + 1, AXIS) for k in range(23)]
    agree, checks = F.reliability(maps, rels)[AXIS]
    assert checks >= F.MIN_CHECKS and agree == checks
    h = identify(maps, rels)[23]
    assert (h.function, h.status) == ('FN_A', SUSPECTED)


def test_an_untested_kind_follows_the_policy(monkeypatch):
    """Too few anchors to check a kind: 'none' holds it back, 'local' asks the memory layout, 'vote' votes."""
    import ecu_studio.core.function_id as F
    monkeypatch.setattr(F, 'SELF_CHECK', True)
    far = table('A', 0x100000, 'FN_A', verified=True)
    around = [table('B1', 0x1000, 'FN_B', verified=True), table('B2', 0x1100, 'FN_B', verified=True),
              table('C1', 0x1300, 'FN_C', verified=True), table('C2', 0x1400, 'FN_C', verified=True)]
    x = table('x', 0x1200, source='heuristic')
    maps, rels = [far, *around, x], [Relation(0, 5, AXIS)]
    assert F.reliability(maps, rels)[AXIS] == (0, 0)
    monkeypatch.setattr(F, 'LOCAL_CHECK', False)
    expect = {'none': '', 'local': '', 'vote': 'FN_A'}
    for policy, function in expect.items():
        monkeypatch.setattr(F, 'UNTESTED', policy)
        h = identify(maps, rels)[5]
        assert h.function == function, policy
        if policy == 'none':
            assert any('nicht prüfbar' in c for c in h.candidates)
    monkeypatch.setattr(F, 'UNTESTED', 'local')
    near = table('A2', 0x1250, 'FN_A', verified=True)
    assert identify(maps + [near], rels)[5].function == 'FN_A'


def test_self_check_uses_only_the_files_own_definitions():
    """A transferred (unchecked) name is no anchor and does not count as a check."""
    import ecu_studio.core.function_id as F
    maps = [table('A', 0, 'FN_A', verified=True),
            table('B', 0x100, 'FN_A', source='transfer', label_origin='Namensübertragung (Referenz)')]
    assert F.reliability(maps, [Relation(0, 1, AXIS)])[AXIS] == (0, 0)


def test_layout_check_by_default_only_for_one_evidence_family():
    """Default ('single'): a far function resting on one family is held back by the memory layout; with two
    independent families (shared axis and program code) it is "Stark gestützt" without the layout check."""
    import ecu_studio.core.function_id as F
    assert F.LOCAL_CHECK == 'single' and not F.SELF_CHECK
    far = table('A', 0x100000, 'FN_A', verified=True)
    around = [table('B1', 0x1000, 'FN_B', verified=True), table('B2', 0x1100, 'FN_B', verified=True),
              table('C1', 0x1300, 'FN_C', verified=True), table('C2', 0x1400, 'FN_C', verified=True)]
    maps = [far, *around, table('x', 0x1200, source='heuristic')]
    assert identify(maps, [Relation(0, 5, AXIS)])[5].function == ''
    h = identify(maps, [Relation(0, 5, AXIS), Relation(0, 5, ROUTINE)])[5]
    assert (h.function, h.status) == ('FN_A', STRONG)
