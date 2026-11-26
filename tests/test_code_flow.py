"""Bounded data flow around interpolation calls and code relations (after 1.21.0-rc1, synthetic)."""
import numpy as np
from ecu_studio.core import code_flow as C
from ecu_studio.core import function_id as F
from ecu_studio.core import tricore_flow as TF
from ecu_studio.core.model import MapDefinition

RAM0, RAM1 = 0xD0008000, 0xD0010000


def bol(op, a, b, off):
    off &= 0xFFFF
    return 4, op | a << 8 | b << 12 | (off & 0x3F) << 16 | ((off >> 10) & 0x3F) << 22 | ((off >> 6) & 0xF) << 28


def ld_h(d, base_reg, off):          # ld.h d,[a]off (BOL)
    return bol(0xC9, d, base_reg, off)


def st_h(base_reg, off, d):          # st.h [a]off,d (BOL)
    return bol(0xF9, d, base_reg, off)


CALL = (4, 0x6D)                      # call (disp 0)
NOP = (2, 0x0000)


def mov(dst, src):                    # mov d_dst,d_src (16 bit)
    return 2, 0x02 | dst << 8 | src << 12


def add(dst, src):                    # add d_dst,d_src (16 bit)
    return 2, 0x42 | dst << 8 | src << 12


UNKNOWN16 = (2, 0x0050)               # an opcode the module does not decode


def code(*insns, labels=(), entries=(0,)):
    data, starts = bytearray(), []
    for length, w in insns:
        starts.append(len(data))
        data += int(w).to_bytes(length, 'little')
    c = TF._Code(bytes(data), np.asarray(starts, np.int64), np.asarray(sorted(labels), np.int64),
                 {0: RAM0, 1: RAM1}, list(entries))
    return c, starts


def test_decoder_knows_loads_stores_copies_and_calls():
    assert TF.decode(*ld_h(4, 0, 0x10)).kind == 'load'
    assert TF.decode(*st_h(1, 0x20, 8)).kind == 'store'
    assert TF.decode(*mov(8, 2)).kind == 'copy'
    assert TF.decode(*CALL).kind == 'call'
    assert TF.decode(2, 0x9000).kind == 'ret'
    assert TF.decode(*UNKNOWN16) is None


def test_input_and_result_are_followed_through_copies():
    c, _ = code(ld_h(9, 0, 0x10), mov(4, 9), CALL, mov(8, 2), st_h(1, 0x20, 8))
    assert c.value(2, 4) == C.Operand(C.RAM, RAM0 + 0x10)
    stores, _ = c.stores(2)
    assert [(s.address, s.how) for s in stores] == [(RAM1 + 0x20, C.COPY)]


def test_local_arithmetic_marks_the_result_derived():
    c, _ = code(CALL, add(2, 9), st_h(1, 4, 2))
    assert [(s.address, s.how) for s in c.stores(0)[0]] == [(RAM1 + 4, C.DERIVED)]


def test_unknown_instruction_stops_and_stays_open():
    c, _ = code(ld_h(4, 0, 0x10), UNKNOWN16, CALL)
    op = c.value(2, 4)
    assert op.kind == C.OPEN and 'nicht dekodiert' in op.reason
    c, _ = code(CALL, UNKNOWN16, st_h(1, 0x20, 2))
    stores, why = c.stores(0)
    assert stores == [] and 'nicht dekodiert' in why


def test_branch_target_between_load_and_call_leaves_the_input_open():
    c, starts = code(ld_h(4, 0, 0x10), NOP, CALL)
    c.labels = np.asarray([starts[1]], np.int64)          # another path joins at the nop
    assert c.value(2, 4).reason == 'Sprungziel'


def test_caller_saved_register_is_open_after_an_intervening_call_but_the_result_is_known():
    c, starts = code(ld_h(4, 0, 0x10), CALL, CALL)
    assert c.value(2, 4).reason == 'Aufruf dazwischen'
    c, starts = code(CALL, mov(4, 2), CALL)
    assert c.value(2, 4) == C.Operand(C.RESULT, starts[0])
    c, _ = code(ld_h(9, 0, 0x10), CALL, mov(4, 9), CALL)    # d9 is kept across calls
    assert c.value(3, 4) == C.Operand(C.RAM, RAM0 + 0x10)


def test_overwritten_result_is_not_stored():
    c, _ = code(CALL, ld_h(2, 0, 0), st_h(1, 0x20, 2))
    assert c.stores(0)[0] == []


def test_routine_start_bounds_the_backward_window():
    c, starts = code(ld_h(4, 0, 0x10), CALL, entries=(0, 4))
    assert c.value(1, 4).reason == 'Routinenanfang'


def use(table, site, caller=None, inputs=None, stores=()):
    return C.TableUse(table, site, 0x500, caller, inputs or {}, list(stores), method='test')


def test_relations_flow_same_result_caller_and_shared_input():
    a = use(0x100, 10, 1, {'d4': C.Operand(C.RAM, 0xD1)}, [C.Store(0xD9, C.COPY, 2, 12)])
    b = use(0x200, 20, 1, {'d4': C.Operand(C.RAM, 0xD9)})
    c = use(0x300, 30, 2, {'d4': C.Operand(C.RAM, 0xD1)}, [C.Store(0xD9, C.DERIVED, 2, 32)])
    d = use(0x400, 40, 3, {'d4': C.Operand(C.RESULT, 30)})
    kinds = {(r.a, r.b, r.kind) for r in C.relations([a, b, c, d])}
    assert (0x100, 0x200, C.FLOW) in kinds and (0x300, 0x200, C.FLOW) in kinds
    assert (0x100, 0x300, C.SAME_RESULT) in kinds
    assert (0x100, 0x200, C.SAME_CALLER) in kinds
    assert (0x100, 0x300, C.SHARED_INPUT) in kinds
    assert (0x300, 0x400, C.FLOW) in kinds                   # result passed in a register
    derived = next(r for r in C.relations([a, b, c, d]) if (r.a, r.b, r.kind) == (0x300, 0x200, C.FLOW))
    assert derived.uncertainty


def test_a_variable_many_tables_share_links_nothing():
    uses = [use(0x100 * i, i, None, {'d4': C.Operand(C.RAM, 0xD1)}) for i in range(1, C.MAX_SHARED + 2)]
    assert not [r for r in C.relations(uses) if r.kind == C.SHARED_INPUT]


def maps(*functions):
    return [MapDefinition(name=f'T{i}', offset=0x100 * (i + 1), rows=1, cols=4, source='a2l', function=f)
            for i, f in enumerate(functions)]


def test_shared_input_never_names_a_function():
    m = maps('KF_A', '')
    rel = F.code_links(m, [C.CodeRelation(0x100, 0x200, C.SHARED_INPUT, 'gleiche Eingangsgröße', 0, 0, 'test')])
    assert F.identify(m, rel)[1].function == ''


def test_code_relations_of_one_family_are_one_argument():
    m = maps('KF_A', '')
    code = [C.CodeRelation(0x100, 0x200, k, k, 0, 0, 'test') for k in (C.SAME_CALLER, C.SAME_RESULT)]
    h = F.identify(m, F.code_links(m, code))[1]
    assert (h.function, h.status) == ('KF_A', F.SUSPECTED)
    both = F.code_links(m, code) + [F.Relation(0, 1, F.AXIS, 'Achse')]
    assert F.identify(m, both)[1].status == F.STRONG


def test_function_groups_are_numbered_and_name_no_function():
    m = maps('KF_A', '', '', '')
    rels = F.code_links(m, [C.CodeRelation(0x100, 0x200, C.SAME_CALLER, 'x', 0, 0, 'test'),
                            C.CodeRelation(0x300, 0x400, C.SAME_CALLER, 'y', 0, 0, 'test')])
    groups = F.function_groups(m, rels)
    assert [g.label for g in groups] == ['Unbekannte Funktionsgruppe 1', 'Unbekannte Funktionsgruppe 2']
    assert groups[0].functions == {'KF_A': 1} and groups[1].functions == {}
    assert all(g.code_backed and not g.contradictory for g in groups)
