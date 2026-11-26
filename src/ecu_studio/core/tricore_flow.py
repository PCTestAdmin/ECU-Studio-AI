"""Bounded data flow around TriCore interpolation calls (after 1.21.0-rc1, experimental).

For every call of an interpolation routine that core/tricore_refs resolved to a table, this module
decodes a short window of instructions:

- backwards from the call, the value of each input register (d4, d5: first data arguments of the
  TriCore EABI) until the instruction that sets it: a load from RAM through a known address
  (global base register, ``movh.a``/``lea`` constant, absolute address), a register copy (followed),
  a computation or a constant;
- forwards from the call, the result register d2 through copies and local arithmetic up to the
  stores into RAM.

Windows are short (BACK / FORWARD instructions) and the analysis stops, reporting an open point,
at every instruction it cannot decode, at a branch target (other paths join), at a return or jump
(path boundary), at the start of the routine, and for caller-saved registers at an intervening
call. No symbolic execution, no decompilation: a value either follows from the decoded window or
stays open. Indirect jumps are not seen (their targets are unknown) - documented limitation.

Processor-independent model and relations: core/code_flow.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
import numpy as np
from . import code_flow as C
from . import tricore_refs as T

BACK = 32           # instructions examined backwards from a call (per register chain)
FORWARD = 24        # instructions examined after a call
INPUTS = (4, 5)     # d4, d5
RESULT = 2          # d2
A = 16              # register ids: d0..d15 -> 0..15, a0..a15 -> 16..31
UPPER = frozenset(range(8, 16)) | frozenset(A + r for r in (10, 11, 12, 13, 14, 15))   # kept across calls
GLOBAL = frozenset(A + r for r in T.GLOBAL_BASES)
METHOD = f'TriCore, begrenzte Datenflussanalyse ({BACK} Befehle zurück, {FORWARD} vor)'


@dataclass(frozen=True)
class Insn:
    kind: str                 # nop copy const arith movh lea load store call ret jump branch
    writes: tuple = ()
    reads: tuple = ()
    base: int | None = None   # address register id of a memory access / lea
    off: int = 0
    absolute: int | None = None
    imm: int = 0
    width: int = 0


_SRR_COPY = {0x02: (0, 0), 0x40: (A, A), 0x80: (0, A), 0x60: (A, 0)}      # mov, mov.aa, mov.d, mov.a: (dst, src)
_SRR_ARITH = {0x42, 0xA2, 0xE2, 0x26, 0xA6, 0xC6}                             # add sub mul and or xor (d_a op= d_b)
# 16-bit forms with d15: (writes, reads) as fields a / b / 15
_D15 = {0x12: ('a', ('15', 'b')), 0x52: ('a', ('15', 'b')),          # add / sub d_a,d15,d_b
        0x1A: ('15', ('a', 'b')), 0x5A: ('15', ('a', 'b')),          # add / sub d15,d_a,d_b
        0x9A: ('15', ('a',)), 0x92: ('a', ('15',)),                  # add d15,d_a,#c / add d_a,d15,#c
        0x3A: ('15', ('a', 'b')), 0x7A: ('15', ('a', 'b')),          # eq / lt d15,d_a,d_b
        0xBA: ('15', ('a',)), 0xFA: ('15', ('a',)),                  # eq / lt d15,d_a,#c
        0x2A: ('a', ('a', '15', 'b')), 0x6A: ('a', ('a', '15', 'b')),  # cmov / cmovn d_a,d15,d_b (selection)
        0xAA: ('a', ('a', '15')), 0xEA: ('a', ('a', '15')),          # cmov / cmovn d_a,d15,#c
        0x8A: ('a', ('a', '15')), 0xCA: ('a', ('a', '15')),          # cadd / caddn d_a,d15,#c
        0x06: ('a', ('a',)), 0x86: ('a', ('a',)), 0x32: ('a', ('a',)),   # sh / sha d_a,#c; sat / rsub d_a
        0x16: ('15', ('15',)), 0x96: ('15', ('15',))}                # and / or d15,#c8
_ADDR16 = {0x30: 'a', 0xB0: 'a', 0xA0: 'a', 0x10: 'a', 0x20: '10'}   # add.a, add.a #c, mov.a #c, addsc.a, sub.a sp
_SC = {0xD8: (A + 15, 4), 0x58: (15, 4)}                              # ld.a a15 / ld.w d15, [sp]c8 (stack slot)
_SC_STORE = {0xF8, 0x78}                                              # st.a / st.w [sp]c8 (stack slot, not RAM)
_SLR_LOAD = {0xD4: (A, 4), 0x14: (0, 1), 0x94: (0, 2), 0x54: (0, 4)}        # [b]
_SLR_POST = {0xC4: (A, 4), 0x04: (0, 1), 0x84: (0, 2), 0x44: (0, 4)}        # [b+]
_SSR_STORE = {0xF4: (A, 4), 0x34: (0, 1), 0xB4: (0, 2), 0x74: (0, 4)}       # [b]
_SSR_POST = {0xE4: (A, 4), 0x24: (0, 1), 0xA4: (0, 2), 0x64: (0, 4)}        # [b+]
_SLRO_LOAD = {0xC8: (A, 4), 0x08: (0, 1), 0x88: (0, 2), 0x48: (0, 4)}       # d/a, [a15]off4
_SSRO_STORE = {0xE8: (A, 4), 0x28: (0, 1), 0xA8: (0, 2), 0x68: (0, 4)}      # [a15]off4, d/a
_SRO_LOAD = {0xCC: (A, 4), 0x0C: (0, 1), 0x8C: (0, 2), 0x4C: (0, 4)}        # d15/a15, [b]off4
_SRO_STORE = {0xEC: (A, 4), 0x2C: (0, 1), 0xAC: (0, 2), 0x6C: (0, 4)}       # [b]off4, d15/a15
_BOL_LOAD = {0x99: (A, 4), 0x19: (0, 4), 0x79: (0, 1), 0x39: (0, 1), 0xC9: (0, 2), 0xB9: (0, 2)}
_BOL_STORE = {0xB5: (A, 4), 0x59: (0, 4), 0xE9: (0, 1), 0xF9: (0, 2)}
_BO_LOAD = {0x20: (0, 1), 0x21: (0, 1), 0x22: (0, 2), 0x23: (0, 2), 0x24: (0, 4), 0x26: (A, 4)}
_BO_STORE = {0x20: (0, 1), 0x22: (0, 2), 0x24: (0, 4), 0x26: (A, 4)}
_ABS_LOAD = {(0x05, 0): (0, 1), (0x05, 1): (0, 1), (0x05, 2): (0, 2), (0x05, 3): (0, 2), (0x85, 0): (0, 4),
             (0x85, 2): (A, 4)}
_ABS_STORE = {(0x25, 0): (0, 1), (0x25, 2): (0, 2), (0xA5, 0): (0, 4), (0xA5, 2): (A, 4)}
# 32-bit forms with the destination in bits 31:28 and data sources in 11:8 (and 15:12)
_RR_ARITH = {0x0B: 2, 0x73: 2, 0x0F: 2, 0x2B: 3, 0x8B: 1, 0x53: 1, 0x8F: 1, 0x1B: 1, 0x9B: 1, 0x37: 2, 0x77: 2}
_CONST32 = {0x3B, 0x7B}       # mov d,#const16 / movh d,#const16
_STOP16 = {0x3C: 'jump', 0x5C: 'call', 0xDC: 'jump'}
_STOP32 = {0x1D: 'jump', 0x9D: 'jump', 0x6D: 'call', 0xED: 'call', 0x2D: 'call', 0x5D: 'call'}


def _abs(w: int) -> int:
    off = ((w >> 16) & 0x3F) | (((w >> 28) & 0xF) << 6) | (((w >> 22) & 0xF) << 10) | (((w >> 12) & 0xF) << 14)
    return (((off >> 14) & 0xF) << 28) | (off & 0x3FFF)


def decode(length: int, w: int) -> Insn | None:
    """The instruction at one sweep position, or None when this module does not decode it."""
    op = w & 0xFF
    if length == 2:
        a, b = (w >> 8) & 0xF, (w >> 12) & 0xF
        if w == 0:
            return Insn('nop')
        if w == 0x9000:
            return Insn('ret')
        if T.cond_target(0, 2, w) is not None or op == 0xFC:
            return Insn('branch')
        if op in _STOP16:
            return Insn(_STOP16[op])
        if op in _SRR_COPY:
            dk, sk = _SRR_COPY[op]
            return Insn('copy', (dk + a,), (sk + b,))
        if op in _SRR_ARITH:
            return Insn('arith', (a,), (a, b))
        if op in _D15:
            field = {'a': a, 'b': b, '15': 15}
            dst, srcs = _D15[op]
            return Insn('arith', (field[dst],), tuple(field[s] for s in srcs))
        if op in _ADDR16:
            return Insn('arith', (A + (a if _ADDR16[op] == 'a' else 10),), ())
        if op in _SC:
            return Insn('load', (_SC[op][0],), (A + 10,), A + 10, ((w >> 8) & 0xFF) * 4, None, 0, 4)
        if op in _SC_STORE:
            return Insn('nop')                          # into a stack slot: no register changes
        if op == 0xC2:                                  # add d_a,#const4
            return Insn('arith', (a,), (a,))
        if op == 0x82:                                  # mov d_a,#const4
            return Insn('const', (a,))
        if op == 0xDA:                                  # mov d15,#const8
            return Insn('const', (15,))
        for table, post in ((_SLR_LOAD, False), (_SLR_POST, True)):
            if op in table:
                k, width = table[op]
                return Insn('load', (k + a,) + ((A + b,) if post else ()), (A + b,), A + b, 0, None, 0, width)
        for table, post in ((_SSR_STORE, False), (_SSR_POST, True)):
            if op in table:
                k, width = table[op]
                return Insn('store', ((A + b,) if post else ()), (k + a, A + b), A + b, 0, None, 0, width)
        if op in _SLRO_LOAD:
            k, width = _SLRO_LOAD[op]
            return Insn('load', (k + a,), (A + 15,), A + 15, b * width, None, 0, width)
        if op in _SSRO_STORE:
            k, width = _SSRO_STORE[op]
            return Insn('store', (), (k + a, A + 15), A + 15, b * width, None, 0, width)
        if op in _SRO_LOAD:
            k, width = _SRO_LOAD[op]
            return Insn('load', (k + 15,), (A + b,), A + b, a * width, None, 0, width)
        if op in _SRO_STORE:
            k, width = _SRO_STORE[op]
            return Insn('store', (), (k + 15, A + b), A + b, a * width, None, 0, width)
        return None
    a, b, c = (w >> 8) & 0xF, (w >> 12) & 0xF, (w >> 28) & 0xF
    if T.cond_target(0, 4, w) is not None or op == 0xFD:
        return Insn('branch')
    if op in _STOP32:
        return Insn(_STOP32[op])
    if op == 0x91:                                      # movh.a a_c,#const16
        return Insn('movh', (A + c,), (), imm=((w >> 12) & 0xFFFF) << 16)
    if op == 0xD9:                                      # lea a_a,[a_b]off16
        return Insn('lea', (A + a,), (A + b,), A + b, T._bol_off(w))
    if op == 0xC5 and (w >> 26) & 3 == 0:              # lea a_a,off18
        return Insn('lea', (A + a,), (), None, 0, _abs(w))
    if op == 0x49 and (w >> 22) & 0x3F == 0x28:        # lea a_a,[a_b]off10 (BO)
        return Insn('lea', (A + a,), (A + b,), A + b, T._bo_off(w))
    if op == 0x01:                                      # address arithmetic (RR): mov.aa, add.a, addsc.a, ...
        op2 = (w >> 20) & 0xFF
        if op2 == 0x00:
            return Insn('copy', (A + c,), (A + b,))
        if op2 == 0x4C:                                 # mov.d d_c,a_b
            return Insn('copy', (c,), (A + b,))
        if op2 == 0x63:                                 # mov.a a_c,d_b
            return Insn('copy', (A + c,), (b,))
        if 0x40 <= op2 <= 0x49:                         # address comparisons: result in d_c
            return Insn('arith', (c,), ())
        return Insn('arith', (A + c,), (a,))
    if op == 0xBB:                                      # mov.u d_c,#const16
        return Insn('const', (c,))
    if op in (0xAB, 0x6B, 0x03):                        # cadd / sel (RCR, RRR), madd forms: dst c
        return Insn('arith', (c,), (a, (w >> 24) & 0xF) + ((b,) if op != 0xAB else ()))
    if op == 0x4B:                                      # divide / float (RR): may write the pair e_c
        return Insn('arith', (c, (c + 1) & 0xF), (a, b))
    if op in _BOL_LOAD:
        k, width = _BOL_LOAD[op]
        return Insn('load', (k + a,), (A + b,), A + b, T._bol_off(w), None, 0, width)
    if op in _BOL_STORE:
        k, width = _BOL_STORE[op]
        return Insn('store', (), (k + a, A + b), A + b, T._bol_off(w), None, 0, width)
    if op in (0x09, 0x89):
        op2 = (w >> 22) & 0x3F
        table = _BO_LOAD if op == 0x09 else _BO_STORE
        mode, low = op2 & 0x30, op2 & 0x0F
        if mode == 0x20 and op2 in table:                  # base + short offset
            k, width = table[op2]
        elif mode in (0x00, 0x10) and (0x20 | low) in table:   # post- / pre-increment: base changes
            k, width = table[0x20 | low]
            if op == 0x09:
                return Insn('load', (k + a, A + b), (A + b,), A + b, T._bo_off(w) if mode else 0, None, 0, width)
            return Insn('store', (A + b,), (k + a, A + b), A + b, T._bo_off(w) if mode else 0, None, 0, width)
        else:
            return None
        if op == 0x09:
            return Insn('load', (k + a,), (A + b,), A + b, T._bo_off(w), None, 0, width)
        return Insn('store', (), (k + a, A + b), A + b, T._bo_off(w), None, 0, width)
    key = (op, (w >> 26) & 3)
    if key in _ABS_LOAD:
        k, width = _ABS_LOAD[key]
        return Insn('load', (k + a,), (), None, 0, _abs(w), 0, width)
    if key in _ABS_STORE:
        k, width = _ABS_STORE[key]
        return Insn('store', (), (k + a,), None, 0, _abs(w), 0, width)
    if op in _CONST32:
        return Insn('const', (c,))
    if op == 0x0B and (w >> 20) & 0xFF == 0x1F:        # mov d_c,d_b (RR)
        return Insn('copy', (c,), (b,))
    if op in _RR_ARITH:
        n = _RR_ARITH[op]
        srcs = (a, b, (w >> 24) & 0xF)[:n]
        return Insn('arith', (c,), srcs)
    return None


def branch_targets(stream) -> np.ndarray:
    """Sorted file offsets that a branch, jump or loop of the sweep can reach (labels)."""
    if not stream:
        return np.zeros(0, np.int64)
    types = {'i': np.int32, 'B': np.uint8, 'I': np.uint32}
    ats, lens, words = (np.frombuffer(x, dtype=types[x.typecode]) for x in stream[:3])
    at = ats.astype(np.int64)
    w = words.astype(np.int64)
    op = w & 0xFF
    short = lens == 2
    out = []
    d4 = np.isin(op, sorted(T._COND16_DISP4)) & short
    out.append(at[d4] + 2 * ((w[d4] >> 8) & 0xF))
    d8 = (np.isin(op, sorted(T._COND16_DISP8)) | (op == 0x3C)) & short
    s8 = (w[d8] >> 8) & 0xFF
    out.append(at[d8] + 2 * np.where(s8 & 0x80, s8 - 0x100, s8))
    lp = (op == 0xFC) & short
    out.append(at[lp] - 32 + 2 * ((w[lp] >> 12) & 0xF))
    c32 = (np.isin(op, sorted(T._COND32)) | (op == 0xFD)) & ~short
    s15 = (w[c32] >> 16) & 0x7FFF
    out.append(at[c32] + 2 * np.where(s15 & 0x4000, s15 - 0x8000, s15))
    j = (op == 0x1D) & ~short
    s24 = ((w[j] >> 16) & 0xFFFF) | (((w[j] >> 8) & 0xFF) << 16)
    out.append(at[j] + 2 * np.where(s24 & 0x800000, s24 - 0x1000000, s24))
    return np.unique(np.concatenate(out)) if out else np.zeros(0, np.int64)


class _Code:
    def __init__(self, data: bytes, starts, labels, bases: dict, entries: list[int]):
        self.data, self.starts, self.labels = data, starts, labels
        self.bases = {A + r: v for r, v in bases.items()}
        self.entries = entries

    def insn(self, k: int) -> Insn | None:
        at = int(self.starts[k])
        w = int.from_bytes(self.data[at:at + 4].ljust(4, b'\0'), 'little')
        return decode(4, w) if w & 1 else decode(2, w & 0xFFFF)

    def label(self, k: int) -> bool:
        at = int(self.starts[k])
        j = int(np.searchsorted(self.labels, at))
        return j < len(self.labels) and int(self.labels[j]) == at

    def entry(self, at: int) -> int | None:
        k = bisect.bisect_right(self.entries, at) - 1
        return self.entries[k] if k >= 0 else None

    def value(self, k: int, reg: int, budget: int = BACK) -> C.Operand:
        """Value of ``reg`` right before instruction ``k`` (data: RAM/CONST/COMPUTED; address: CONST)."""
        if reg in GLOBAL and reg in self.bases:
            return C.Operand(C.CONST, self.bases[reg])
        start = self.entry(int(self.starts[k]))
        crossed_call = False
        j = k
        while budget > 0 and j > 0:
            if self.label(j):
                return C.Operand(C.OPEN, reason='Sprungziel')
            j -= 1
            budget -= 1
            if start is not None and int(self.starts[j]) < start:
                return C.Operand(C.OPEN, reason='Routinenanfang')
            ins = self.insn(j)
            if ins is None:
                return C.Operand(C.OPEN, reason='Befehl nicht dekodiert')
            if ins.kind in ('ret', 'jump'):
                return C.Operand(C.OPEN, reason='Pfadgrenze')
            if ins.kind == 'call':
                if reg == RESULT:
                    return C.Operand(C.RESULT, int(self.starts[j]))
                if reg not in UPPER:
                    return C.Operand(C.OPEN, reason='Aufruf dazwischen')
                crossed_call = True
                continue
            if reg not in ins.writes:
                continue
            if ins.kind == 'copy':
                reg = ins.reads[0]
                if reg in GLOBAL and reg in self.bases:
                    return C.Operand(C.CONST, self.bases[reg])
                continue
            if ins.kind == 'const':
                return C.Operand(C.CONST)
            if ins.kind == 'arith':
                return C.Operand(C.COMPUTED)
            if ins.kind == 'movh':
                return C.Operand(C.CONST, ins.imm)
            if ins.kind == 'lea':
                if ins.absolute is not None:
                    return C.Operand(C.CONST, ins.absolute)
                base = self.value(j, ins.base, budget)
                if base.kind == C.CONST and base.address is not None:
                    return C.Operand(C.CONST, (base.address + ins.off) & 0xFFFFFFFF)
                return C.Operand(C.OPEN, reason=base.reason or 'Adresse offen')
            if ins.kind == 'load':
                if ins.base == A + 10:
                    return C.Operand(C.OPEN, reason='Wert aus dem Stapel')
                if reg >= A:
                    return C.Operand(C.OPEN, reason='Zeiger aus dem Speicher')
                if ins.base is not None and ins.base in ins.writes:
                    return C.Operand(C.OPEN, reason='Adressregister verändert')
                if ins.absolute is not None:
                    return C.Operand(C.RAM, ins.absolute)
                base = self.value(j, ins.base, budget)
                if base.kind == C.CONST and base.address is not None:
                    return C.Operand(C.RAM, (base.address + ins.off) & 0xFFFFFFFF)
                return C.Operand(C.OPEN, reason=base.reason or 'Adresse offen')
            return C.Operand(C.OPEN, reason='Befehl nicht dekodiert')
        del crossed_call
        return C.Operand(C.OPEN, reason='Fenster erschöpft')

    def stores(self, k: int) -> tuple[list[C.Store], str]:
        """Stores of the result of the call at ``k`` (copies and local arithmetic) and why tracking ended."""
        held = {RESULT: C.COPY}
        out: list[C.Store] = []
        for j in range(k + 1, min(k + 1 + FORWARD, len(self.starts))):
            ins = self.insn(j)
            if ins is None:
                return out, 'Befehl nicht dekodiert'
            if ins.kind in ('ret', 'jump', 'call', 'branch'):
                return out, {'ret': 'Rücksprung', 'jump': 'Sprung', 'call': 'Aufruf', 'branch': 'Verzweigung'}[ins.kind]
            if ins.kind == 'store':
                src = ins.reads[0]
                if src in held:
                    if ins.absolute is not None:
                        out.append(C.Store(ins.absolute, held[src], ins.width, int(self.starts[j])))
                    else:
                        base = self.value(j, ins.base)
                        if base.kind == C.CONST and base.address is not None:
                            out.append(C.Store((base.address + ins.off) & 0xFFFFFFFF, held[src], ins.width,
                                               int(self.starts[j])))
                for r in ins.writes:
                    held.pop(r, None)
                continue
            if ins.kind == 'copy':
                src, dst = ins.reads[0], ins.writes[0]
                if src in held:
                    held[dst] = held[src]
                else:
                    held.pop(dst, None)
                continue
            if ins.kind == 'arith':
                derived = any(s in held for s in ins.reads)
                for r in ins.writes:
                    if derived:
                        held[r] = C.DERIVED
                    else:
                        held.pop(r, None)
                continue
            for r in ins.writes:
                held.pop(r, None)
            if not held:
                return out, 'Ergebnis überschrieben'
        return out, 'Fenster erschöpft'


def table_uses(data: bytes, descriptors=None) -> list[C.TableUse]:
    """One TableUse per call site of every table resolved by tricore_refs.call_descriptors.

    Empty for images that are not TriCore code with resolved table calls.
    """
    if descriptors is None:
        descriptors = T.call_descriptors(data, keep_context=True)
    context = getattr(descriptors, 'context', None)
    if not descriptors or context is None:
        return []
    sites, entries = context
    code = _Code(data, np.asarray(sites.starts), branch_targets(sites.stream), sites.bases, entries)
    out = []
    for d in sorted(descriptors):
        desc = descriptors[d]
        if desc.pointer:
            continue
        for site in desc.sites:
            k = int(np.searchsorted(code.starts, site))
            if k >= len(code.starts) or int(code.starts[k]) != site:
                continue
            use = C.TableUse(d, site, desc.callee, code.entry(site), method=METHOD)
            for reg in INPUTS:
                op = code.value(k, reg)
                use.inputs[f'd{reg}'] = op
                if op.kind == C.OPEN:
                    use.open.append(f'd{reg}: {op.reason}')
            stores, why = code.stores(k)
            use.stores = stores
            if not stores:
                use.open.append(f'Ergebnis: {why}')
            out.append(use)
    return out


def code_relations(data: bytes) -> tuple[list[C.TableUse], list[C.CodeRelation]]:
    uses = table_uses(data)
    return uses, C.relations(uses)


__all__ = ['decode', 'branch_targets', 'table_uses', 'code_relations', 'BACK', 'FORWARD', 'METHOD']
