"""Table lookups named by Infineon TriCore code: data, X axis and Y axis of one call.

TriCore passes pointers in address registers. Siemens MSD80 (TC1796) calls its
interpolation routines with the table data in a4, the header of the X axis in a5
and the header of the Y axis in a6 (curves: a4 data, a5 axis)::

    movh.a a4,#0xa005 ; lea a4,[a4]-1256     data
    lea    a5,[a1]-25708                     X axis header (count, values)
    lea    a6,[a1]-27192                     Y axis header
    call   <interpolation routine>

Addresses come from self-contained ``movh.a``/``lea`` pairs, or from ``lea``
relative to a global base register (a0, a1, a8, a9) whose one-time boot
initialisation (``movh.a aN`` + ``lea aN,[aN]``) is recovered from the image.
Variants of a table selected by branches (``a4`` set before an unconditional
jump to the shared axis loads) are followed through forward jumps.

Two further forms seen on MSD80:

- Axis pointers kept in stack slots (``st.a [sp]k`` early, ``ld.a a5,[sp]k``
  before the call): a reload takes the nearest preceding store of that slot in
  the same function, only in functions whose sp is set once and whose slot
  addresses never escape (see stack_slots).
- Split interpolation: one call per axis with a4 = axis header (prelookup),
  later a table call with a4 only. Routine roles come from call behaviour
  (prelookup_roles); X and Y are the last two prelookups on the same path.

This is a linear sweep with constant tracking inside straight-line code, not a
full disassembly: a call yields a descriptor only when both axis headers parse
as count-prefixed increasing arrays (see axis_arrays.axis_at), so stale or
wrongly decoded register values rarely survive. Presence-only evidence: an image
without such calls (other CPU, calibration-only dump) yields nothing.

Measured on one MSD80 (I8A0S, community XDF, development data); see
docs/ANALYSE_2026-10-30.md. Not validated on Bosch TriCore families.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import numpy as np
from .axis_arrays import axis_at, CountAxis

SEGMENTS = (0x80000000, 0xA0000000)    # PFLASH cached / uncached
GLOBAL_BASES = (0, 1, 8, 9)
MAX_JOIN = 512          # forward jump distance whose register state reaches the target
MAX_STATES = 8
MIN_CALLS = 20          # fewer resolved data calls: not a TriCore image with this convention
_BOL = {0xD9, 0x99, 0x19, 0x59, 0xB5}   # lea, ld.a, ld.w, st.w, st.a (TC1.3 BOL forms)
_LOWER = (2, 3, 4, 5, 6, 7)              # address registers not preserved across calls


@dataclass(frozen=True)
class CallSite:
    site: int            # file offset of the call instruction
    callee: int          # file offset of the called routine
    data: int            # file offset loaded into a4
    x_header: int | None
    y_header: int | None
    pre: tuple = ()      # earlier a4-only calls on this path: ((callee, a4 offset), ...), oldest first


def _bol_off(w: int) -> int:
    off = ((w >> 16) & 0x3F) | (((w >> 28) & 0xF) << 6) | (((w >> 22) & 0x3F) << 10)
    return off - 0x10000 if off & 0x8000 else off


def _halfwords(data: bytes) -> list[int]:
    return np.frombuffer(data[:len(data) // 2 * 2], '<u2').tolist()


def _sweep(h: list[int]):
    i, n = 0, len(h)
    while i < n:
        x = h[i]
        if x & 1 and i + 1 < n:
            yield i * 2, 4, x | (h[i + 1] << 16)
            i += 2
        else:
            yield i * 2, 2, x
            i += 1


MIN_RET_PER_64K = 32      # TriCore images: 130-260 16-bit ``ret``; C167, synthetic, random: <= 4
MIN_MOVHA_PER_64K = 300   # TriCore images: 620-730 ``movh.a`` opcode bytes; others <= 151


def looks_like_tricore(data: bytes) -> bool:
    """Cheap gate before the sweep: density of 16-bit ``ret`` and ``movh.a`` opcodes."""
    if len(data) < 0x10000:
        return False
    h = np.frombuffer(data[:len(data) // 2 * 2], '<u2')
    scale = 0x10000 / len(data)
    return (int((h == 0x9000).sum()) * scale >= MIN_RET_PER_64K and
            int(((h & 0xFF) == 0x91).sum()) * scale >= MIN_MOVHA_PER_64K)


def global_bases(h: list[int]) -> dict[int, int]:
    """Most frequent boot value of a0/a1/a8/a9 (``movh.a aN,#hi`` + ``lea aN,[aN]off``)."""
    seen = {r: Counter() for r in GLOBAL_BASES}
    prev = None
    for at, size, w in _sweep(h):
        if size == 4 and w & 0xFF == 0x91:
            prev = ((w >> 28) & 0xF, (w >> 12) & 0xFFFF)
            continue
        if size == 4 and w & 0xFF == 0xD9 and prev:
            a, b = (w >> 8) & 0xF, (w >> 12) & 0xF
            if a == b == prev[0] and a in seen:
                seen[a][((prev[1] << 16) + _bol_off(w)) & 0xFFFFFFFF] += 1
        prev = None
    return {r: c.most_common(1)[0][0] for r, c in seen.items() if c}


def _file(address: int | None, size: int) -> int | None:
    if address is None:
        return None
    for seg in SEGMENTS:
        if seg <= address < seg + size:
            return address - seg
    return None


def _bo_off(w: int) -> int:
    off = ((w >> 16) & 0x3F) | (((w >> 28) & 0xF) << 6)
    return off - 0x400 if off & 0x200 else off


SP = 10   # stack pointer a10

# Conditional branches (TriCore 1.3 ISA). 16-bit SBC/SBR/SBRN forms branch forward
# by disp4 (zero-extended); SB forms by a signed disp8. 32-bit BRC/BRR/BRN forms
# carry a signed disp15 in bits 30:16. Loops (LOOP, 0xFC/0xFD) only jump back.
_COND16_DISP4 = {0x1E, 0x3E, 0x5E, 0x7E, 0xCE, 0x4E, 0x8E, 0x0E, 0x76, 0xF6, 0xBC, 0x7C, 0x2E, 0xAE}
_COND16_DISP8 = {0x6E, 0xEE}
_COND32 = {0xDF, 0xBF, 0xFF, 0x9F, 0x5F, 0x3F, 0x7F, 0x1F, 0x7D, 0xBD, 0x6F}


def cond_target(at: int, length: int, w: int) -> int | None:
    """Target of a conditional branch at ``at``, or None for other instructions."""
    op = w & 0xFF
    if length == 2:
        if op in _COND16_DISP4:
            return at + 2 * ((w >> 8) & 0xF)
        if op in _COND16_DISP8:
            d = (w >> 8) & 0xFF
            return at + 2 * (d - 0x100 if d & 0x80 else d)
        return None
    if op in _COND32:
        d = (w >> 16) & 0x7FFF
        return at + 2 * (d - 0x8000 if d & 0x4000 else d)
    return None


def _walk(h: list[int], bases: dict, size: int, slots=None, entries=(), branches=True):
    """One linear sweep. Returns (call sites, stack stores, sp events, call targets).

    With ``branches`` the register state also reaches the targets of forward
    conditional branches (as for unconditional jumps): MSD80 starts table calls
    after a ``ret`` at targets of such branches (ANALYSE_2026-10-30, 11.3).

    ``stack stores`` are (at, slot, value or None) for every store to [sp]k;
    ``sp events`` are addresses where sp is changed or copied, or a slot address
    is taken. With ``slots`` ({function entry: {slot: [(at, value), ...]}}) a
    pointer loaded from a slot takes the value of the nearest preceding store.
    """
    import bisect
    states: list[dict] = [{}]
    pending: dict[int, list[dict]] = {}
    out, stores, sp_events, targets = [], [], [], set()
    func_slots: dict = {}
    k_entry = -1

    def setreg(r, v):
        for s in states:
            if v is None:
                s.pop(r, None)
            else:
                s[r] = v

    def store(at, slot, src):
        vals = {s.get(src) for s in states} if src is not None else {None}
        v = vals.pop() if len(vals) == 1 else None
        stores.append((at, slot, v[1] if v and v[0] == 'full' else None))

    def load(dst, slot, at):
        defs = func_slots.get(slot)
        v = None
        if defs:
            k = bisect.bisect_left(defs, (at,)) - 1
            v = defs[k][1] if k >= 0 else None
        setreg(dst, ('full', v) if v is not None else None)

    for at, length, w in _sweep(h):
        if slots is not None:
            k = bisect.bisect_right(entries, at) - 1
            if k != k_entry:
                k_entry = k
                func_slots = slots.get(entries[k], {}) if k >= 0 else {}
        if at in pending:
            states = states + pending.pop(at)
            uniq = []
            for s in states:
                if s not in uniq:
                    uniq.append(s)
            states = uniq[:MAX_STATES] or [{}]
        if not states:
            states = [{}]
        op = w & 0xFF
        if branches:
            target = cond_target(at, length, w)
            if target is not None:
                # Both ways continue: fall-through here, the taken branch at a nearby forward target.
                if 0 < target - at <= MAX_JOIN:
                    pending.setdefault(target, []).extend({**s} for s in states)
                continue
        jump = None
        if length == 2:
            if w == 0x9000:                         # ret
                states = []
                continue
            if op == 0x3C:                          # j disp8
                d = (w >> 8) & 0xFF
                jump = at + 2 * (d - 0x100 if d & 0x80 else d)
            elif op == 0x5C:                        # call disp8
                for r in _LOWER + (11,):
                    setreg(r, None)
                continue
            elif op == 0x40:                        # mov.aa a,b
                a, b = (w >> 8) & 0xF, (w >> 12) & 0xF
                if SP in (a, b):
                    sp_events.append(at)
                for s in states:
                    if b in s:
                        s[a] = s[b]
                    else:
                        s.pop(a, None)
                continue
            elif op == 0xD8:                        # ld.a a15,[sp]const8*4
                load(15, ((w >> 8) & 0xFF) * 4, at)
                continue
            elif op == 0xF8:                        # st.a [sp]const8*4,a15
                store(at, ((w >> 8) & 0xFF) * 4, 15)
                continue
            elif op == 0x78:                        # st.w [sp]const8*4,d15
                store(at, ((w >> 8) & 0xFF) * 4, None)
                continue
            elif op == 0x20:                        # sub.a sp,#const8
                sp_events.append(at)
                continue
            elif op == 0xD4 and (w >> 12) & 0xF == SP:   # ld.a c,[sp]
                load((w >> 8) & 0xF, 0, at)
                continue
            elif op in (0xD4, 0xC4, 0xC8, 0xA0, 0x60, 0xB0, 0x30):   # writes a[(w>>8)&15]
                if (w >> 8) & 0xF == SP:
                    sp_events.append(at)
                setreg((w >> 8) & 0xF, None)
                continue
            elif op == 0xCC:                        # ld.a a15,[b]off4
                setreg(15, None)
                continue
            else:
                continue
        else:
            if op == 0x91:                          # movh.a c,#hi  (a partial address)
                setreg((w >> 28) & 0xF, ('hi', ((w >> 12) & 0xFFFF) << 16))
                continue
            if op == 0x11:                          # addih.a c,a,#hi
                c, a, k = (w >> 28) & 0xF, (w >> 8) & 0xF, ((w >> 12) & 0xFFFF) << 16
                if c == SP:
                    sp_events.append(at)
                for s in states:
                    base = s.get(a)
                    if base is not None:
                        s[c] = (base[0], (base[1] + k) & 0xFFFFFFFF)
                    else:
                        s.pop(c, None)
                continue
            if op in _BOL:
                a, b, off = (w >> 8) & 0xF, (w >> 12) & 0xF, _bol_off(w)
                if op == 0xD9:                      # lea a,[b]off
                    if SP in (a, b):
                        sp_events.append(at)        # sp moved, or a slot address escapes
                    for s in states:
                        base = s.get(b)
                        v = base[1] if base else bases.get(b)
                        if v is None:
                            s.pop(a, None)
                        else:
                            s[a] = ('full', (v + off) & 0xFFFFFFFF)
                elif op == 0x99:                    # ld.a a,[b]off16
                    if b == SP:
                        load(a, off, at)
                    else:
                        setreg(a, None)
                elif b == SP:                       # st.w / st.a [sp]off16
                    store(at, off, a if op == 0xB5 else None)
                continue
            if op in (0x09, 0x29, 0x89, 0xA9):      # BO: increment modes change the base
                op2 = (w >> 22) & 0x3F
                a, b = (w >> 8) & 0xF, (w >> 12) & 0xF
                if op2 >> 4 in (0, 1):
                    if b == SP:
                        sp_events.append(at)
                    setreg(b, None)
                elif op == 0x09 and op2 == 0x26 and b == SP:    # ld.a a,[sp]off10
                    load(a, _bo_off(w), at)
                    continue
                elif op == 0x89 and op2 >> 4 == 2 and b == SP:  # st.* [sp]off10
                    store(at, _bo_off(w), a if op2 == 0x26 else None)
                if op in (0x09, 0x29) and op2 & 0xF in (6, 7):
                    if a == SP:
                        sp_events.append(at)
                    setreg(a, None)
                continue
            if op == 0x01:                          # RR address arithmetic: destination c
                if (w >> 28) & 0xF == SP:
                    sp_events.append(at)
                setreg((w >> 28) & 0xF, None)
                continue
            if op == 0x6D:                          # call disp24
                d = ((w >> 16) & 0xFFFF) | (((w >> 8) & 0xFF) << 16)
                callee = at + 2 * (d - 0x1000000 if d & 0x800000 else d)
                if 0 <= callee < size:
                    targets.add(callee)
                for s in states:
                    def val(r):
                        v = s.get(r)
                        return _file(v[1], size) if v and v[0] == 'full' else None
                    dat, x = val(4), val(5)
                    if dat is not None and 0 <= callee < size:
                        out.append(CallSite(at, callee, dat, x, val(6), s.get('pre', ())))
                        if x is None:
                            # A call with a4 only may be an axis prelookup whose result
                            # (kept in RAM) a later table call on this path uses.
                            s['pre'] = (s.get('pre', ()) + ((callee, dat),))[-MAX_PRE:]
                for r in _LOWER + (11,):
                    setreg(r, None)
                continue
            if op == 0x1D:                          # j disp24
                d = ((w >> 16) & 0xFFFF) | (((w >> 8) & 0xFF) << 16)
                jump = at + 2 * (d - 0x1000000 if d & 0x800000 else d)
            else:
                continue
        # unconditional jump: the state continues at a nearby forward target only
        if jump is not None and 0 < jump - at <= MAX_JOIN:
            pending.setdefault(jump, []).extend({**s} for s in states)
        states = []
    return out, stores, sp_events, targets


MAX_PRE = 6          # a4-only calls remembered per path
MAX_SP_CHANGES = 1   # one frame allocation per function; more and slot offsets drift


def stack_slots(entries: list[int], stores, sp_events) -> dict:
    """{function entry: {slot: [(at, value or None), ...]}} of the stores to each stack slot.

    A load takes the nearest preceding store of its slot in the same function
    (address order); an unknown value there stays unknown. A function is skipped
    when sp changes more than once, is copied, or a slot address is taken (a
    callee could then write the slot unseen).
    """
    import bisect

    def func(at):
        k = bisect.bisect_right(entries, at) - 1
        return entries[k] if k >= 0 else None
    events: dict = {}
    for at in sp_events:
        events[func(at)] = events.get(func(at), 0) + 1
    defs: dict = {}
    for at, slot, value in stores:
        defs.setdefault(func(at), {}).setdefault(slot, []).append((at, value))
    out = {}
    for f, by_slot in defs.items():
        if f is None or events.get(f, 0) > MAX_SP_CHANGES:
            continue
        out[f] = {k: v for k, v in by_slot.items()}
    return out


FOLLOW_BRANCHES = True
FIND_RECORDS = True


def _analyse(data: bytes, stack: bool = True) -> tuple[list[CallSite], list[int], list[int]]:
    """(call sites, halfwords, function entries) of one image."""
    h = _halfwords(data)
    bases = global_bases(h)
    sites, stores, sp_events, targets = _walk(h, bases, len(data), branches=FOLLOW_BRANCHES)
    entries = sorted(targets)
    if stack:
        slots = stack_slots(entries, stores, sp_events)
        if slots:
            sites = _walk(h, bases, len(data), slots, entries, branches=FOLLOW_BRANCHES)[0]
    return sites, h, entries


def call_sites(data: bytes, *, stack: bool = True) -> list[CallSite]:
    """Calls with a resolved a4 (and optional a5/a6), as file offsets.

    With ``stack`` a second sweep resolves pointers reloaded from stack slots
    through the nearest preceding store in their function (MSD80 keeps axis
    pointers there across long function bodies).
    """
    return _analyse(data, stack)[0]


# Loads of table cells: base+offset forms (BO, op2) and 16-bit forms (op) -> (width, signed)
_BO_LOADS = {0x00: (1, True), 0x01: (1, False), 0x02: (2, True), 0x03: (2, False),       # post-increment
             0x10: (1, True), 0x11: (1, False), 0x12: (2, True), 0x13: (2, False),       # pre-increment
             0x20: (1, True), 0x21: (1, False), 0x22: (2, True), 0x23: (2, False)}       # base + offset
_S16_LOADS = {0x14: (1, False, 'b'), 0x04: (1, False, 'b'), 0x0C: (1, False, 15), 0x08: (1, False, 'c'),
              0x94: (2, True, 'b'), 0x84: (2, True, 'b'), 0x8C: (2, True, 15), 0x88: (2, True, 'c')}
MIN_CELL_LOADS = 2
MAX_BODY = 0x1000


def cell_loads(h: list[int], entry: int, end: int) -> Counter:
    """{(width, signed): n} of loads whose base address register derives from a4.

    Inside a routine a4 is the table pointer; copies and offsets of it
    (mov.aa, addsc.a, lea, add.a) are followed linearly. Any other write to an
    address register ends its derivation.
    """
    derived = {4}
    seen: Counter = Counter()
    i = entry // 2
    while i * 2 < end and i + 1 < len(h):
        x = h[i]
        if x & 1:
            w = x | (h[i + 1] << 16)
            op = w & 0xFF
            if op in (0x09, 0x29):
                op2 = (w >> 22) & 0x3F
                if op2 in _BO_LOADS and (w >> 12) & 0xF in derived:
                    seen[_BO_LOADS[op2]] += 1
                if op2 & 0xF in (6, 7):
                    derived.discard((w >> 8) & 0xF)
            elif op == 0x01:
                op2, c = (w >> 20) & 0xFF, (w >> 28) & 0xF
                if op2 == 0x60 and (w >> 12) & 0xF in derived:           # addsc.a c,b,d,n
                    derived.add(c)
                elif op2 in (0x01, 0x02) and ((w >> 8) & 0xF in derived or (w >> 12) & 0xF in derived):
                    derived.add(c)                                       # add.a / sub.a
                else:
                    derived.discard(c)
            elif op == 0xD9:                                             # lea a,[b]off
                (derived.add if (w >> 12) & 0xF in derived else derived.discard)((w >> 8) & 0xF)
            elif op in (0x91, 0x11):
                derived.discard((w >> 28) & 0xF)
            elif op == 0x99:
                derived.discard((w >> 8) & 0xF)
            i += 2
            continue
        op = x & 0xFF
        if op & 0x3F == 0x10 or op == 0x40:                              # addsc.a a,b,d15,n / mov.aa a,b
            (derived.add if (x >> 12) & 0xF in derived else derived.discard)((x >> 8) & 0xF)
        elif op in _S16_LOADS:
            width, signed, f = _S16_LOADS[op]
            base = 15 if f == 15 else ((x >> 12) & 0xF if f == 'b' else (x >> 8) & 0xF)
            if base in derived:
                seen[(width, signed)] += 1
        elif op in (0xD4, 0xC4, 0xC8, 0xA0, 0x60, 0xB0, 0x30):
            derived.discard((x >> 8) & 0xF)
        elif op in (0xD8, 0xCC):
            derived.discard(15)
        i += 1
    return seen


def routine_cells(h: list[int], entries: list[int], routines) -> dict[int, tuple]:
    """{routine: (cell width or None, signed or None)} from its table loads.

    A width (or sign) counts only when every table load of the routine agrees
    and there are at least MIN_CELL_LOADS of them; mixed loads stay unknown.
    The routine body ends at the next function entry (at most MAX_BODY bytes).
    """
    import bisect
    out = {}
    for r in routines:
        k = bisect.bisect_right(entries, r)
        end = min(entries[k] if k < len(entries) else r + MAX_BODY, r + MAX_BODY)
        seen = cell_loads(h, r, end)
        enough = sum(seen.values()) >= MIN_CELL_LOADS
        widths = {w for w, _ in seen}
        signs = {sg for _, sg in seen}
        out[r] = (widths.pop() if enough and len(widths) == 1 else None,
                  signs.pop() if enough and len(signs) == 1 else None)
    return out


@dataclass(frozen=True)
class CallDescriptor:
    data: int
    x_axis: CountAxis
    y_axis: CountAxis | None
    callee: int
    sites: tuple[int, ...]
    prelookup: bool = False   # axes from earlier prelookup calls, not from a5/a6
    cell_width: int | None = None   # from the routine's table loads (routine_cells)
    cell_signed: bool | None = None
    record: bool = False      # the call passes a record header (counts + axes) in front of the data


MIN_ROLE_CALLS = 5       # calls before a routine's role (prelookup / table after prelookups) counts
# Both shares are set on one MSD80 file only (development data, not independently validated).
# Prelookup shares there are bimodal (none between 0.45 and 0.66), so .6 sits in a natural gap;
# table-routine shares run continuously (0.30 ... 0.71), hence the extra code check in call_descriptors.
PRELOOKUP_SHARE = .6     # a4-only calls of a prelookup routine naming a parsable axis header
POSTLOOKUP_SHARE = .6    # a4-only calls of a table routine with two prelookups on the path


def prelookup_roles(data: bytes, sites: list[CallSite]) -> tuple[set[int], set[int]]:
    """(prelookup routines, table routines after prelookups), from call behaviour only.

    Some interpolations split the work: one call per axis (a4 = axis header)
    stores the axis position, then the table call passes only a4 = table data.
    A routine is a prelookup when nearly all its a4-only calls name an axis
    header; a table routine when nearly all its a4-only calls name no axis and
    follow two prelookups on the same code path.
    """
    stats: dict[int, list[int]] = {}
    is_axis = {}
    for c in sites:
        if c.x_header is not None:
            continue
        if c.data not in is_axis:
            is_axis[c.data] = axis_at(data, c.data) is not None
        st = stats.setdefault(c.callee, [0, 0])
        st[0] += 1
        st[1] += is_axis[c.data]
    pre = {r for r, (n, ax) in stats.items() if n >= MIN_ROLE_CALLS and ax >= PRELOOKUP_SHARE * n}
    post_stats: dict[int, list[int]] = {}
    for c in sites:
        if c.x_header is not None or c.callee in pre or is_axis.get(c.data):
            continue
        st = post_stats.setdefault(c.callee, [0, 0])
        st[0] += 1
        st[1] += sum(r in pre for r, _ in c.pre) >= 2
    post = {r for r, (n, ok) in post_stats.items() if n >= MIN_ROLE_CALLS and ok >= POSTLOOKUP_SHARE * n}
    return pre, post


RECORD_SHARE = .3   # a4-only calls of a record routine whose target parses as a 2-D record
# MSD80 (development data): shares of all routines with >= 5 a4-only calls are 0.00 or
# 0.36 ... 1.00, nothing in between; .3 sits in that gap and needs no reference.


def _strict_axis(data: bytes, at: int, n: int, w: int) -> tuple | None:
    if n < MIN_RECORD_POINTS or at % w or at + n * w > len(data):
        return None
    for kind in ('u', 'i'):
        v = np.frombuffer(data[at:at + n * w], np.dtype(kind + '1') if w == 1 else np.dtype('<' + kind + '2'))
        v = v.astype(np.int64)
        if np.all(np.diff(v) > 0):
            return tuple(int(x) for x in v)
    return None


MIN_RECORD_POINTS = 2


def record_at(data: bytes, a: int) -> list[tuple[CountAxis, CountAxis]]:
    """Readings of a self-describing 2-D record at ``a``: two counts, both axes, then the data.

    Layout ``n1, n2, A1[n1], A2[n2], Z`` with 8- or 16-bit counts and 8- or 16-bit
    strictly increasing axes (MSD80 mixes them, e.g. u16 Y with u8 X). The first
    axis is X (columns): Z is stored row-major like the Bosch ``nx, ny`` records.
    Returns (x_axis, y_axis) pairs; the data starts at ``y_axis.end``.
    """
    out = []
    for cw in (1, 2):
        if a % cw or a + 2 * cw > len(data):
            continue
        n1 = int.from_bytes(data[a:a + cw], 'little')
        n2 = int.from_bytes(data[a + cw:a + 2 * cw], 'little')
        if not (MIN_RECORD_POINTS <= n1 <= 32 and MIN_RECORD_POINTS <= n2 <= 32):
            continue
        p = a + 2 * cw
        for w1 in (2, 1):
            x = _strict_axis(data, p, n1, w1)
            if x is None:
                continue
            q = p + n1 * w1
            for w2 in (2, 1):
                y = _strict_axis(data, q, n2, w2)
                if y is not None:
                    out.append((CountAxis(a, p, n1, w1, x), CountAxis(a + cw, q, n2, w2, y)))
    return out


def record_roles(data: bytes, sites: list[CallSite]) -> set[int]:
    """Routines whose a4-only calls pass self-describing 2-D records (see record_at)."""
    stats: dict[int, list[int]] = {}
    seen: dict[int, bool] = {}
    for c in sites:
        if c.x_header is not None:
            continue
        if c.data not in seen:
            seen[c.data] = bool(record_at(data, c.data))
        st = stats.setdefault(c.callee, [0, 0])
        st[0] += 1
        st[1] += seen[c.data]
    return {r for r, (n, ok) in stats.items() if n >= MIN_ROLE_CALLS and ok >= RECORD_SHARE * n}


def _layout(x: CountAxis, y: CountAxis) -> tuple[int, int, int]:
    """(count width, X width, Y width) of one record reading."""
    return y.header - x.header, x.width, y.width


def _record_layouts(sites, records, readings) -> dict[int, tuple]:
    """{routine: layout} from its unambiguous record calls (one routine reads one layout)."""
    votes: dict[int, Counter] = {}
    for c in sites:
        r = readings.get(c.data) if c.callee in records and c.x_header is None else None
        if r and len(r) == 1:
            votes.setdefault(c.callee, Counter())[_layout(*next(iter(r)))] += 1
    return {k: v.most_common(1)[0][0] for k, v in votes.items()}


RECORD_MIN_LOADS = 8      # loads besides the two counts before a record routine's cell type counts
RECORD_DOMINANT = .75     # share of those loads in one (width, sign) class
# MSD80 record routines: dominant shares 0.80 ... 1.00 (the rest are axis loads); wrappers
# that only read the counts and call on have no further loads and stay unknown.


def record_cells(h: list[int], entries: list[int], routines: dict[int, int]) -> dict[int, tuple]:
    """{routine: (cell width, signed) or (None, None)} for record routines.

    ``routines`` maps each routine to the width of its records' counts. The two
    count loads are removed; the cells are the dominant remaining load class
    (axis loads are fewer: an interpolation reads up to four cells per axis pair).
    """
    import bisect
    out = {}
    for r, cw in routines.items():
        k = bisect.bisect_right(entries, r)
        end = min(entries[k] if k < len(entries) else r + MAX_BODY, r + MAX_BODY)
        seen = cell_loads(h, r, end)
        seen[(cw, False)] -= 2
        seen = Counter({key: n for key, n in seen.items() if n > 0})
        total = sum(seen.values())
        best = seen.most_common(1)[0] if seen else None
        ok = best is not None and total >= RECORD_MIN_LOADS and best[1] >= RECORD_DOMINANT * total
        out[r] = best[0] if ok else (None, None)
    return out


class Descriptors(dict):
    """{data offset: CallDescriptor}; ``named`` holds every data address the code passes
    in a4 to one of the descriptors' routines, with or without resolved axes."""
    named: frozenset = frozenset()


def call_descriptors(data: bytes, lo: int = 0, hi: int | None = None) -> dict[int, CallDescriptor]:
    """{data offset: descriptor} for calls naming table data plus parsable axis headers.

    Axes come from a5/a6 of the call; from a record header passed in a4 whose
    counts and axes precede the data (record routines, see record_roles); or for
    routines working after axis
    prelookups (see prelookup_roles) from the last two prelookups on the same
    path: the earlier one is X, the later one Y. Such descriptors are marked
    ``prelookup`` and accepted only with an exactly fitting cell width.
    A table whose data lies inside one of the named axes, or calls that name the
    same data with different axes, are dropped: such reads are not one table.
    The result also lists all data addresses passed to the same routines
    (``Descriptors.named``): neighbours whose axes stay unresolved still bound
    a table (MSD80: two tables only fit exactly once their neighbour counts).
    """
    hi = len(data) if hi is None else hi
    if not looks_like_tricore(data):
        return {}
    sites, h, entries = _analyse(data)
    pre, post = prelookup_roles(data, sites)
    # The share threshold for table routines has no natural gap on MSD80 (shares
    # 0.30 ... 0.71 run continuously); a table routine must also read table cells
    # of one width through a4 (code evidence, see routine_cells).
    post = {r for r, (width, _) in routine_cells(h, entries, post).items() if width is not None}
    records = record_roles(data, sites) if FIND_RECORDS else set()
    record_readings = {c.data: set(record_at(data, c.data)) for c in sites
                       if c.x_header is None and c.callee in records and lo <= c.data < hi}
    layouts = _record_layouts(sites, records, record_readings)
    found: dict[int, list] = {}
    for c in sites:
        if not lo <= c.data < hi:
            continue
        if c.x_header is None and c.callee in records:
            readings = record_readings[c.data]
            if len(readings) > 1:
                # Data after the axes may read as a longer axis: the routine's own layout decides.
                readings = {r for r in readings if _layout(*r) == layouts.get(c.callee)}
            if len(readings) == 1:
                x, y = next(iter(readings))
                if lo <= y.end < hi:
                    found.setdefault(y.end, []).append((x, y, c.callee, c.site, False, True))
            continue
        x_header, y_header, via = c.x_header, c.y_header, False
        if x_header is None and c.callee in post:
            axes = [a for r, a in c.pre if r in pre]
            if len(axes) >= 2 and axes[-2] != axes[-1]:
                x_header, y_header, via = axes[-2], axes[-1], True
        x = axis_at(data, x_header) if x_header is not None else None
        if x is None:
            continue
        y = axis_at(data, y_header) if y_header is not None else None
        if via and y is None:
            continue
        found.setdefault(c.data, []).append((x, y, c.callee, c.site, via, False))
    if len({d for d in found}) < MIN_CALLS:
        return {}
    cells = routine_cells(h, entries, {r[2] for readings in found.values() for r in readings if not r[5]})
    count_width: dict[int, Counter] = {}
    for readings in found.values():
        for x, y, callee, *_, rec in readings:
            if rec:
                count_width.setdefault(callee, Counter())[y.header - x.header] += 1
    rec_cells = record_cells(h, entries, {r: c.most_common(1)[0][0] for r, c in count_width.items()})
    cells.update({r: (None, None) for r in rec_cells if r not in cells})
    out = Descriptors()
    out.named = frozenset(c.data for c in sites if c.callee in cells and lo <= c.data < hi)
    for d, readings in found.items():
        shapes = {(x.header, y.header if y else None) for x, y, *_ in readings}
        if len(shapes) != 1:
            continue
        x, y, callee, _, via, rec = readings[0]
        if any(ax.header <= d < ax.end for ax in (x, y) if ax):
            continue
        # A record routine also reads the counts through a4: those loads are left out (record_cells).
        cell = rec_cells[callee] if rec else cells[callee]
        out[d] = CallDescriptor(d, x, y, callee, tuple(sorted({r[3] for r in readings})),
                                all(r[4] for r in readings), *cell, record=rec)
    return out


MAX_PAD = 3   # alignment bytes allowed between a table and the next object


def cell_widths(descriptors: dict[int, CallDescriptor], boundaries: list[int]) -> dict[int, int]:
    """Cell width (1 or 2 bytes) per table, without any reference.

    The next known object (another named table or an axis header) bounds the
    table. A width whose rows x cols cells fill that gap exactly (up to MAX_PAD
    alignment bytes) decides; otherwise a width is possible when the table fits
    and is aligned, and a single possible width decides. Remaining ambiguity is
    settled by the interpolation routine: a routine handles one cell type, so
    the width its decided calls agree on (all of them, at least three) is used.

    A width known from the routine's own table loads (``cell_width``) comes
    first: it is used when the table fits before the next object. MSD80: in 22
    of 832 tables the gap was exactly twice the table, two equal byte tables in
    a row, while the routine reads bytes. Prelookup tables still need the exact
    fit, now of that width.
    """
    import bisect
    bounds = sorted(set(boundaries))
    options = {}
    for d, desc in descriptors.items():
        cells = desc.x_axis.count * (desc.y_axis.count if desc.y_axis else 1)
        k = bisect.bisect_right(bounds, d)
        nxt = bounds[k] if k < len(bounds) else None
        fits = [w for w in (1, 2) if d % w == 0 and (nxt is None or d + cells * w <= nxt)]
        exact = [w for w in fits if nxt is not None and nxt - (d + cells * w) <= MAX_PAD]
        if desc.cell_width is not None:
            w = desc.cell_width
            ok = w in (exact if desc.prelookup else fits)
            options[d] = [w] if ok else []
            continue
        if desc.prelookup:
            # Axes linked through RAM results: only an exact fit confirms the shape.
            options[d] = exact if len(exact) == 1 else []
            continue
        options[d] = exact if len(exact) == 1 else fits
    votes: dict[int, Counter] = {}
    for d, opts in options.items():
        if len(opts) == 1 and not descriptors[d].prelookup:
            votes.setdefault(descriptors[d].callee, Counter())[opts[0]] += 1
    routine = {c: v.most_common(1)[0][0] for c, v in votes.items()
               if len(v) == 1 and sum(v.values()) >= 3}
    out = {}
    for d, opts in options.items():
        if len(opts) == 1:
            out[d] = opts[0]
        elif len(opts) == 2 and descriptors[d].callee in routine:
            out[d] = routine[descriptors[d].callee]
    return out
