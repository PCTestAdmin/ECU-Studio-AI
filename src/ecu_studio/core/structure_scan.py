"""Grid-free table geometry discovery: inferred row pitch plus code-reference anchors.

Two independent evidence sources, both geometry-only (NOT map identification):

1. Row-pitch inference: a 2-D table stored row-major repeats its shape every
   ``cols`` elements, so element k and k+cols differ much less than the region's
   span. Runs of such similar row pairs give the row count without fixed grids.
2. Code references (C16x/ST10 firmware): the program loads table addresses as
   ``MOV Rw,#page`` + ``MOV Rw,#offset`` pairs. A referenced address is a strong
   *start* hint; it is not proof of a table, and code also references rows or
   cells inside tables. Observed on Siemens MS43; MS42 code uses other forms,
   where this source simply yields nothing.

Benchmarked against real MS43/MS42 images with matching XDF files (see
tools/structure_benchmark.py). Labels/units still require XDF/A2L metadata.
"""
from __future__ import annotations
import bisect
import re
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from .model import BinaryImage, MapDefinition
from .axis_arrays import scan_count_axes, axis_at, quantity_hint
from .cpu_refs import detect_cpu, GENERIC_LAYOUT

# Signed views: two's-complement tables (e.g. Bosch ME7 ignition maps) wrap around
# zero when read unsigned and look rough.
VIEWS = (("u8", 1, "big"), ("s8", 1, "big"), ("u16", 2, "little"), ("s16", 2, "little"), ("u16", 2, "big"))
COLS = range(4, 17)
MIN_ROWS = 4
PAIR_TOL = .30
SHAPE_TOL = .08
TAIL_MAX = .50
PRESCREEN_V = .45
MIN_PITCH_SCORE = 1.  # rejects small smooth-by-chance windows in random data
ANCHOR_SCORE = 10.
AXIS_LOOKBACK = 128   # code bytes between the axis loads and the table load
AXIS_PAIR_GAP = 20    # code bytes between the Y and X axis loads of one 2-D lookup
AXIS_FIT_MAX = .75
REFERENCE_LAYOUT = 'candidate:code-reference'
PITCH_LAYOUT = 'candidate:row-pitch'
_MOV_IMM = re.compile(rb"\xE6[\xF0-\xFF]..", re.S)


def _values(raw: bytes, width: int, endian: str, signed: bool = False) -> np.ndarray:
    kind = "i" if signed else "u"
    dt = np.dtype(kind + "1") if width == 1 else np.dtype(("<" if endian == "little" else ">") + kind + "2")
    return np.frombuffer(raw[:len(raw) // width * width], dtype=dt).astype(np.float64)


def _runs_forward(good: np.ndarray, c: int) -> np.ndarray:
    """run[p] = consecutive similar row pairs starting at p with pitch c."""
    n = len(good)
    g = np.concatenate([good, np.zeros((-n) % c, bool)]).reshape(-1, c)
    run = np.zeros(g.shape, np.int32)
    acc = np.zeros(c, np.int32)
    for k in range(g.shape[0] - 1, -1, -1):
        acc = np.where(g[k], acc + 1, 0)
        run[k] = acc
    return run.reshape(-1)[:n]


def _interleaved_constant(raw: bytes) -> bool:
    """Every other byte identical: 16-bit data, not an 8-bit table."""
    b = np.frombuffer(raw, np.uint8)
    return len(b) >= 8 and bool(np.all(b[0::2] == b[0]) or np.all(b[1::2] == b[1]))


def _p90(a: np.ndarray) -> np.ndarray:
    flat = a.reshape(len(a), -1)
    k = int(.9 * (flat.shape[1] - 1))
    return np.partition(flat, k, axis=1)[:, k]


def _rough_stack(blocks: np.ndarray, with_tail: bool = True):
    """(h, v, tail) per block of a (n, rows, cols) stack, relative to a robust
    span: a few outliers must neither inflate the span nor hide in a mean."""
    flat = blocks.reshape(len(blocks), -1)
    k = max(1, flat.shape[1] // 20)
    part = np.partition(flat, (k, flat.shape[1] - 1 - k), axis=1)
    s = part[:, flat.shape[1] - 1 - k] - part[:, k]
    s = np.where(s > 0, s, flat.max(1) - flat.min(1)).astype(np.float64)
    dh = np.abs(np.diff(blocks, axis=2))
    dv = np.abs(np.diff(blocks, axis=1))
    with np.errstate(divide='ignore', invalid='ignore'):
        h = dh.mean(axis=(1, 2)) / s
        v = dv.mean(axis=(1, 2)) / s
        tail = (_p90(dh) + _p90(dv)) / (2 * s) if with_tail else np.zeros_like(s)
    return h, v, tail, s


def _phase_costs(blocks: np.ndarray) -> np.ndarray:
    h, v, _, s = _rough_stack(blocks, with_tail=False)
    return np.where(s > 0, h + v, np.inf)


def _roughness(m: np.ndarray):
    """(h, v, tail) for one block, or None for constant blocks."""
    h, v, tail, s = _rough_stack(m[None])
    return None if s[0] <= 0 else (float(h[0]), float(v[0]), float(tail[0]))


def _redundant_signed(dtype: str, block: np.ndarray) -> bool:
    """A signed reading without negative values duplicates the unsigned one."""
    return dtype[0] == 's' and block.size > 0 and block.min() >= 0


def _block_cost(m: np.ndarray) -> float | None:
    r = _roughness(m)
    return None if r is None else r[0] + r[1]


def pitch_candidates(buf: bytes, base: int = 0, *, cancelled=None) -> list[tuple]:
    """(score, offset, rows, cols, dtype, endian, width) from row-pitch runs."""
    out = []
    for dtype, w, endian in VIEWS:
        x = _values(buf, w, endian, dtype[0] == "s")
        n = len(x)
        maxv = 255 if w == 1 else 65535
        for c in COLS:
            if cancelled and cancelled():
                return []
            if n < 3 * c:
                continue
            win = sliding_window_view(x, 2 * c)
            span = win.max(1) - win.min(1)
            d = x[c:] - x[:-c]
            pair = sliding_window_view(np.abs(d), c).sum(1)[:len(span)] / c
            # Rows offset by a near-constant step (monotone grids) share their shape.
            dm = sliding_window_view(d, c).mean(1)[:len(span)]
            dsd = np.sqrt(np.maximum(sliding_window_view(d * d, c).mean(1)[:len(span)] - dm * dm, 0))
            similar = (pair <= PAIR_TOL * span) | ((dsd <= SHAPE_TOL * span) & (np.abs(dm) <= .6 * span))
            good = (span >= (6 if w == 1 else 12)) & similar & ((win == maxv).mean(1) < .5)
            good = np.concatenate([good, np.zeros(n - len(good), bool)])
            run = _runs_forward(good, c)
            prev = np.concatenate([np.zeros(c, bool), good[:-c]])
            covered, covered_stop = -1, -1
            for p0 in np.flatnonzero(good & ~prev & (run >= MIN_ROWS - 1)):
                stop = int(p0) + (int(run[p0]) + 1) * c
                # Starts within the first row of a searched run are its phase
                # shifts, unless their run reaches further.
                if p0 < covered and stop <= covered_stop:
                    continue
                covered, covered_stop = int(p0) + c, stop
                # Cheap pre-screen before the robust per-phase evaluation: runs
                # whose rows differ on average by far more than the final limit
                # (v <= .30 of a span never larger than this one) are skipped.
                # Generous factor; benchmarks unchanged (MS43/MS42/ME7).
                seg = x[int(p0):stop]
                plain = seg.max() - seg.min()
                if plain <= 0 or np.abs(seg[c:] - seg[:-c]).mean() > PRESCREEN_V * plain:
                    continue
                # Column phase: a wrong start puts the row-wrap jump inside rows.
                # All shifts are compared on the same row count, in one pass.
                common = (stop - int(p0) - (c - 1)) // c
                if common >= MIN_ROWS:
                    blocks = x[int(p0) + np.arange(c)[:, None] + np.arange(common * c)[None, :]]
                    shift = int(np.argmin(_phase_costs(blocks.reshape(c, common, c))))
                else:
                    shift = 0
                p = int(p0) + shift
                rows = (stop - p) // c
                if rows < MIN_ROWS:
                    continue
                rough = _roughness(x[p:p + rows * c].reshape(rows, c))
                if rough is None:
                    continue
                h, v, tail = rough
                if h > .25 or v > .30 or tail > TAIL_MAX:
                    continue
                if w == 1 and _interleaved_constant(buf[p:p + min(64, rows * c)]):
                    continue
                score = (1 - min(1., 2 * (h + v))) * np.log2(rows * c)
                if score < MIN_PITCH_SCORE or _redundant_signed(dtype, x[p:p + rows * c]):
                    continue
                out.append((float(score), int(p) * w + base, rows, c, dtype, endian, w))
    return out


def c16x_reference_positions(data: bytes, lo: int, hi: int) -> dict[int, list[int]]:
    """{address in [lo, hi): code positions} from nearby MOV Rw,#page / MOV Rw,#offset loads."""
    imm = [(m.start(), data[m.start() + 2] | data[m.start() + 3] << 8) for m in _MOV_IMM.finditer(data)]
    pages = range(lo >> 14, ((hi - 1) >> 14) + 1)
    found: dict[int, set[int]] = {}
    for i, (pos, val) in enumerate(imm):
        if val not in pages:
            continue
        # Only the directly neighbouring load: with several tables on one page,
        # wider pairing mixes page and offset of different lookups.
        for j in (i - 1, i + 1):
            if 0 <= j < len(imm) and abs(imm[j][0] - pos) <= 8:
                p2, v2 = imm[j]
                a = (val << 14) | (v2 & 0x3FFF)
                if lo <= a < hi:
                    found.setdefault(a, set()).add(min(pos, p2))
    return {a: sorted(p) for a, p in found.items()}


def c16x_reference_anchors(data: bytes, lo: int, hi: int) -> list[int]:
    """Addresses in [lo, hi) built by nearby MOV Rw,#page / MOV Rw,#offset loads."""
    return sorted(c16x_reference_positions(data, lo, hi))


_LOOKUP = re.compile(rb"\xE6\xFC(..)\xE6\xFD(..)\xE6\xFE(..)\xE6\xFF(..)", re.S)


def lookup_descriptors(data: bytes, lo: int, hi: int) -> dict[int, tuple]:
    """{table: (x_axis, y_axis or None)} from C16x lookup calls (Bosch ME7 style).

    MOV R12/R13 carry the table address, MOV R14/R15 the address of its axis
    data: a count-prefixed X axis, often followed directly by the Y axis.
    """
    found = {}
    for m in _LOOKUP.finditer(data):
        off, page, aoff, apage = (int.from_bytes(g, 'little') for g in m.groups())
        table, desc = (page << 14) | (off & 0x3FFF), (apage << 14) | (aoff & 0x3FFF)
        if not (lo <= table < hi and lo <= desc < hi) or table in found:
            continue
        x_axis = axis_at(data, desc)
        if x_axis:
            found[table] = (x_axis, axis_at(data, x_axis.end))
    return found


def _fixed_cols_fit(data: bytes, a: int, cols: int, end: int):
    """Best (cost, rows, width, endian, dtype) for a known column count at a."""
    best = None
    for dtype, w, endian in VIEWS:
        if a % w:
            continue
        raw = data[a:min(end, a + 64 * cols * w)]
        if w == 1 and _interleaved_constant(raw[:64]):
            continue
        x = _values(raw, w, endian, dtype[0] == "s")
        rows = _rows_from(x, cols, len(x) // cols) if len(x) >= 2 * cols else 0
        if rows < 2 or _redundant_signed(dtype, x[:rows * cols]):
            continue
        cost = _block_cost(x[:rows * cols].reshape(rows, cols))
        if cost is not None and cost < AXIS_FIT_MAX and (best is None or cost < best[0]):
            best = (cost, rows, w, endian, dtype)
    return best


def referenced_axes(address: int, refs: dict[int, list[int]], axes_by_header: dict) -> tuple | None:
    """(x_axis, y_axis or None) for a referenced table or curve.

    MS43 lookups load Y, then X, then the table: the closest axis load before
    the table is X, and Y follows a few instructions earlier. A farther second
    axis belongs to other code, so the object is a curve with one axis.
    """
    for q in refs.get(address, ()):
        before = sorted(((p - q, ax) for h, ax in axes_by_header.items() for p in refs.get(h, ())
                         if -AXIS_LOOKBACK <= p - q < 0), key=lambda t: -t[0])
        if not before:
            continue
        x_rel, x_axis = before[0]
        y_rel, y_axis = next(((rel, ax) for rel, ax in before[1:] if ax != x_axis), (None, None))
        return x_axis, y_axis, y_axis is not None and x_rel - y_rel <= AXIS_PAIR_GAP
    return None


def _axis_fit(data: bytes, a: int, rows: int, cols: int, end: int):
    """Best (cost, width, endian, dtype) for an axis-given shape at a, or None."""
    best = None
    for dtype, w, endian in VIEWS:
        if a % w or a + rows * cols * w > end:
            continue
        if w == 1 and _interleaved_constant(data[a:a + min(64, rows * cols)]):
            continue
        x = _values(data[a:a + rows * cols * w], w, endian, dtype[0] == "s")
        if _redundant_signed(dtype, x):
            continue
        if rows == 1:
            span = x.max() - x.min()
            cost = float(np.abs(np.diff(x)).mean() / span) if span > 0 else None
        else:
            cost = _block_cost(x.reshape(rows, cols))
        if cost is None:
            cost = 0.   # constant tables are valid when the axes define the shape
        if cost < AXIS_FIT_MAX and (best is None or cost < best[0]):
            best = (cost, w, endian, dtype)
    return best


def _rows_from(x: np.ndarray, c: int, maxrows: int, tol: float = PAIR_TOL) -> int:
    r = 1
    while r < maxrows:
        a, b = x[(r - 1) * c:r * c], x[r * c:(r + 1) * c]
        if len(b) < c:
            break
        pair = np.concatenate([a, b])
        span = pair.max() - pair.min()
        if span > 0 and np.abs(b - a).mean() > tol * span:
            break
        r += 1
    return r


def anchored_fit(data: bytes, a: int, b: int):
    """Best (cost, rows, cols, width, endian, dtype) starting exactly at anchor a."""
    length = b - a
    best = None
    for dtype, w, endian in VIEWS:
        if a % w:
            continue
        raw = data[a:a + min(length, 1200)]
        if w == 1 and _interleaved_constant(raw[:64]):
            continue
        x = _values(raw, w, endian, dtype[0] == "s")
        n = len(x)
        if _redundant_signed(dtype, x):
            continue
        for c in range(4, 25):
            # A gap exactly filled by r x c explains packed neighbouring tables.
            if n % c == 0 and n // c >= 4 and n * w == length:
                cost = _block_cost(x.reshape(-1, c))
                if cost is not None and cost < .45:
                    cand = (cost - .08, n // c, c, w, endian, dtype)
                    best = cand if best is None or cand < best else best
            r = _rows_from(x, c, n // c)
            if r >= 4:
                cost = _block_cost(x[:r * c].reshape(r, c))
                if cost is not None and cost < .45:
                    cand = (cost, r, c, w, endian, dtype)
                    best = cand if best is None or cand < best else best
    return best


def scan_structures(image: BinaryImage, start: int = 0, end: int | None = None, *,
                    max_results: int = 400, cancelled=None, axes=None,
                    regions: list[tuple[int, int]] | None = None) -> list[MapDefinition]:
    """Non-overlapping table-shaped regions in [start, end); offsets are absolute.

    ``regions`` limits the smoothness-only (row-pitch) search, e.g. to data-like
    blocks of an image without a known calibration window.

    ``axes`` are count-prefixed breakpoint arrays (see axis_arrays), scanned here
    when not given. They fix the shape of code-referenced tables and are never
    reported as 2-D tables themselves.
    """
    end = image.size if end is None else min(end, image.size)
    if end - start < 64:
        return []
    data = image.read(0, image.size)
    if axes is None:
        axes = scan_count_axes(data, start, end)
    refs = c16x_reference_positions(data, start, end)
    descriptors = lookup_descriptors(data, start, end)
    # Other CPUs (HC11, 8051): address loads with an auto-detected memory map.
    cpu, generic = detect_cpu(data)
    generic_only = {a for a in generic if start <= a < end} - set(refs) - set(descriptors)
    anchors = sorted(set(refs) | set(descriptors) | generic_only)
    axes_by_header = {ax.header: ax for ax in axes}
    axis_spans = sorted((ax.header, ax.end) for ax in axes)

    def in_axis(a):
        k = bisect.bisect_right(axis_spans, (a, float('inf'))) - 1
        return k >= 0 and axis_spans[k][0] <= a < axis_spans[k][1]

    proposals = []   # (score, offset, rows, cols, dtype, endian, width, (x_axis, y_axis) | None)
    for a, b in zip(anchors, anchors[1:] + [end]):
        if cancelled and cancelled():
            return []
        if in_axis(a) or a in generic_only:
            continue    # other-CPU references only confirm data-found tables (below)
        if a in descriptors:
            # Lookup call names the axis data: X fixes the columns; the rows come
            # from the following axis or the data, whichever reads smoother.
            x_axis, y_axis = descriptors[a]
            options = []
            if y_axis:
                f = _axis_fit(data, a, y_axis.count, x_axis.count, end)
                if f:
                    cost, w, endian, dtype = f
                    options.append((cost, y_axis.count, w, endian, dtype, (x_axis, y_axis)))
            f = _fixed_cols_fit(data, a, x_axis.count, end)
            if f:
                cost, r, w, endian, dtype = f
                options.append((cost, r, w, endian, dtype, (x_axis, None)))
            if options:
                cost, r, w, endian, dtype, pair = min(options, key=lambda o: o[0])
                proposals.append((ANCHOR_SCORE + 1.8 - cost, a, r, x_axis.count, dtype, endian, w, pair))
                continue
        found = referenced_axes(a, refs, axes_by_header)
        x_axis, y_axis, adjacent = found if found else (None, None, False)
        # Competing readings of one referenced address, strongest evidence first:
        # both axes loaded together > both axes, Y farther away > data fit > curve.
        if y_axis:
            f = _axis_fit(data, a, y_axis.count, x_axis.count, end)
            if f:
                cost, w, endian, dtype = f
                bonus = 2. if adjacent else 1.5
                proposals.append((ANCHOR_SCORE + bonus - cost, a, y_axis.count, x_axis.count, dtype, endian, w,
                                  (x_axis, y_axis)))
                if adjacent:
                    continue
        f = anchored_fit(data, a, b) if b - a >= 16 else None
        if f:
            cost, r, c, w, endian, dtype = f
            # A nearby axis matching the fitted width is still X of this table.
            x_only = (x_axis, None) if x_axis and x_axis.count == c else None
            proposals.append((ANCHOR_SCORE + 1 - cost, a, r, c, dtype, endian, w, x_only))
        if x_axis and not adjacent:
            f = _axis_fit(data, a, 1, x_axis.count, end)
            if f:
                cost, w, endian, dtype = f
                proposals.append((ANCHOR_SCORE + .5 - cost / 2, a, 1, x_axis.count, dtype, endian, w, (x_axis, None)))
    pitched = []
    for lo, hi in (regions or [(start, end)]):
        lo, hi = max(lo, start), min(hi, end)
        if hi - lo >= 64:
            # Even start keeps 16-bit views aligned with the image.
            lo -= lo % 2
            pitched += pitch_candidates(data[lo:hi], lo, cancelled=cancelled)
    generic_sorted = sorted(generic_only)
    generic_confirmed = set()
    for score, off, rows, c, dtype, endian, w in pitched:
        k = bisect.bisect_left(generic_sorted, off - 2)
        if k < len(generic_sorted) and generic_sorted[k] <= off + 2 and generic_sorted[k] % w == 0:
            # A code load of (almost) this start confirms the table and fixes its start.
            off, score = generic_sorted[k], score + 1.
            generic_confirmed.add(off)
        i = bisect.bisect_right(anchors, off)
        if i < len(anchors) and anchors[i] < off + rows * c * w:
            # A referenced address inside the run usually starts the next table.
            rows = (anchors[i] - off) // (c * w)
            if rows < MIN_ROWS:
                continue
        proposals.append((score, off, rows, c, dtype, endian, w, None))
    if cancelled and cancelled():
        return []
    # Code also references single rows inside tables; a curve reading there must
    # not displace the table, so curves only fill space no 2-D reading claimed.
    proposals.sort(key=lambda p: (p[2] == 1, -p[0]))
    taken, chosen = list(axis_spans), []
    for score, off, rows, c, dtype, endian, w, pair in proposals:
        stop = off + rows * c * w
        k = bisect.bisect_left(taken, (off, off))
        if (k < len(taken) and taken[k][0] < stop) or (k > 0 and taken[k - 1][1] > off):
            continue
        taken.insert(k, (off, stop))
        referenced = score >= ANCHOR_SCORE
        if pair and pair[1]:
            evidence = ('Startadresse im Programmcode referenziert; Größe aus den zuvor geladenen Achsen '
                        f'X @ 0x{pair[0].header:X} ({pair[0].count} Punkte) und '
                        f'Y @ 0x{pair[1].header:X} ({pair[1].count} Punkte).')
            origin = 'Code-Referenz + Achsen (ungeprüft)'
        elif pair and rows == 1:
            evidence = ('Startadresse im Programmcode referenziert; Kennlinie mit der zuvor geladenen Achse '
                        f'X @ 0x{pair[0].header:X} ({pair[0].count} Punkte).')
            origin = 'Code-Referenz + Achse (ungeprüft)'
        elif pair:
            evidence = ('Startadresse im Programmcode referenziert; Spaltenzahl passt zur zuvor geladenen Achse '
                        f'X @ 0x{pair[0].header:X}, Zeilenzahl aus Datenwiederholung abgeleitet.')
            origin = 'Code-Referenz + X-Achse (ungeprüft)'
        elif off in generic_confirmed:
            evidence = (f'Startadresse von {cpu.family}-Ladebefehlen referenziert (Speicherbasis '
                        f'0x{cpu.base:04X}, automatisch erkannt; Prozessorfamilie nicht kalibriert); '
                        f'Zeilenabstand {c} Werte aus Datenwiederholung abgeleitet.')
            origin = f'{cpu.family}-Code-Referenz + Zeilenabstand (ungeprüft)'
        else:
            evidence = ('Startadresse im Programmcode referenziert (Seite+Offset-Ladebefehle); '
                        if referenced else '') + f'Zeilenabstand {c} Werte aus Datenwiederholung abgeleitet.'
            origin = 'Code-Referenz + Zeilenabstand (ungeprüft)' if referenced else 'Zeilenabstand-Analyse (ungeprüft)'
        m = MapDefinition(
            name=f'Strukturkandidat @ 0x{off:08X}', offset=off, rows=rows, cols=c, dtype=dtype, endian=endian,
            source='heuristic', confidence=round(min(.45, .45 * (score - ANCHOR_SCORE if referenced else score / 8)), 3),
            record_layout=(GENERIC_LAYOUT if off in generic_confirmed else
                           REFERENCE_LAYOUT if referenced else PITCH_LAYOUT),
            label_origin=origin,
            label_evidence=evidence + ' Geometrie-Hypothese, KEIN identifiziertes Kennfeld.',
            notes=evidence)
        if pair:
            m.axes_x = [float(v) for v in pair[0].values]
            m.axes_y = [float(v) for v in pair[1].values] if pair[1] else []
            hints = [f'X {quantity_hint(pair[0])}'] + ([f'Y {quantity_hint(pair[1])}'] if pair[1] else [])
            m.axes_info = (f'Rohachsen aus Code-Referenz: X @ 0x{pair[0].offset:X}'
                           + (f', Y @ 0x{pair[1].offset:X}' if pair[1] else '')
                           + '; Einheiten und Skalierung ungeprüft. '
                           + ' · '.join(h for h in hints if not h.endswith(' ')))
        chosen.append(m)
        if len(chosen) >= max_results:
            break
    return sorted(chosen, key=lambda m: m.offset)
