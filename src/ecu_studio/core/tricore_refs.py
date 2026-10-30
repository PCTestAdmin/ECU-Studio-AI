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


def call_sites(data: bytes) -> list[CallSite]:
    """Calls with a resolved a4 (and optional a5/a6), as file offsets."""
    h = _halfwords(data)
    bases = global_bases(h)
    size = len(data)
    states: list[dict] = [{}]
    pending: dict[int, list[dict]] = {}
    out = []

    def setreg(r, v):
        for s in states:
            if v is None:
                s.pop(r, None)
            else:
                s[r] = v

    for at, length, w in _sweep(h):
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
                for s in states:
                    if b in s:
                        s[a] = s[b]
                    else:
                        s.pop(a, None)
                continue
            elif op in (0xD4, 0xC4, 0xC8, 0xA0, 0x60, 0xB0, 0x30):   # writes a[(w>>8)&15]
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
                    for s in states:
                        base = s.get(b)
                        v = base[1] if base else bases.get(b)
                        if v is None:
                            s.pop(a, None)
                        else:
                            s[a] = ('full', (v + off) & 0xFFFFFFFF)
                elif op in (0x99,):                 # ld.a: loaded pointer is unknown
                    setreg(a, None)
                continue
            if op in (0x09, 0x29, 0x89, 0xA9):      # BO: increment modes change the base
                op2 = (w >> 22) & 0x3F
                if op2 >> 4 in (0, 1):
                    setreg((w >> 12) & 0xF, None)
                if op in (0x09, 0x29) and op2 & 0xF in (6, 7):
                    setreg((w >> 8) & 0xF, None)
                continue
            if op == 0x01:                          # RR address arithmetic: destination c
                setreg((w >> 28) & 0xF, None)
                continue
            if op == 0x6D:                          # call disp24
                d = ((w >> 16) & 0xFFFF) | (((w >> 8) & 0xFF) << 16)
                callee = at + 2 * (d - 0x1000000 if d & 0x800000 else d)
                for s in states:
                    def val(r):
                        v = s.get(r)
                        return _file(v[1], size) if v and v[0] == 'full' else None
                    dat = val(4)
                    if dat is not None and 0 <= callee < size:
                        out.append(CallSite(at, callee, dat, val(5), val(6)))
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
    return out


@dataclass(frozen=True)
class CallDescriptor:
    data: int
    x_axis: CountAxis
    y_axis: CountAxis | None
    callee: int
    sites: tuple[int, ...]


def call_descriptors(data: bytes, lo: int = 0, hi: int | None = None) -> dict[int, CallDescriptor]:
    """{data offset: descriptor} for calls naming table data plus parsable axis headers.

    A table whose data lies inside one of the named axes, or calls that name the
    same data with different axes, are dropped: such reads are not one table.
    """
    hi = len(data) if hi is None else hi
    if not looks_like_tricore(data):
        return {}
    sites = call_sites(data)
    found: dict[int, list] = {}
    for c in sites:
        if not lo <= c.data < hi:
            continue
        x = axis_at(data, c.x_header) if c.x_header is not None else None
        if x is None:
            continue
        y = axis_at(data, c.y_header) if c.y_header is not None else None
        found.setdefault(c.data, []).append((x, y, c.callee, c.site))
    if len({d for d in found}) < MIN_CALLS:
        return {}
    out = {}
    for d, readings in found.items():
        shapes = {(x.header, y.header if y else None) for x, y, _, _ in readings}
        if len(shapes) != 1:
            continue
        x, y, callee, _ = readings[0]
        if any(ax.header <= d < ax.end for ax in (x, y) if ax):
            continue
        out[d] = CallDescriptor(d, x, y, callee, tuple(sorted({s for *_, s in readings})))
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
        options[d] = exact if len(exact) == 1 else fits
    votes: dict[int, Counter] = {}
    for d, opts in options.items():
        if len(opts) == 1:
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
