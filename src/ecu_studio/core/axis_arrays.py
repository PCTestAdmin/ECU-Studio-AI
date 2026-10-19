"""Count-prefixed breakpoint arrays: ``n`` followed by ``n`` increasing values.

Siemens MS42/MS43 store table axes (ldp*/ldpm* in community XDFs) as an 8-bit
count before 8-bit values, or a 16-bit little-endian count before 16-bit values,
packed back to back. Requiring a neighbouring array in such a chain removes
almost all chance matches. Geometry only: units and meaning stay unknown.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .model import MapDefinition

MIN_POINTS, MAX_POINTS = 2, 32
MIN_CHAIN = 4   # MS43/MS42 keep 592/398 true axes; 75 chance axes on old 8-bit ECUs drop to 0
AXIS_LAYOUT = 'candidate:count-axis'


@dataclass(frozen=True)
class CountAxis:
    header: int      # offset of the count
    offset: int      # offset of the first value
    count: int
    width: int       # bytes per value (= bytes of the count)
    values: tuple[int, ...]

    @property
    def end(self) -> int:
        return self.offset + self.count * self.width


def _increasing(v: np.ndarray) -> bool:
    d = np.diff(v)
    n = len(v)
    # Weakly increasing, with at most a few repeated breakpoints, and not flat.
    return bool(np.all(d >= 0) and np.sum(d > 0) >= n - 1 - n // 8 and v[-1] - v[0] >= n - 1)


def axis_at(data: bytes, header: int) -> CountAxis | None:
    """Single count-prefixed increasing array at a known header (e.g. from code).

    Values may be signed (temperature or offset breakpoints); the stored
    ``values`` are interpreted accordingly. No chain neighbour is required.
    """
    for width in (1, 2):
        if header + width > len(data):
            continue
        n = data[header] if width == 1 else data[header] | data[header + 1] << 8
        a = header + width
        if not MIN_POINTS <= n <= MAX_POINTS or a + n * width > len(data):
            continue
        raw = data[a:a + n * width]
        for kind in ('u', 'i'):
            v = np.frombuffer(raw, np.dtype(kind + '1') if width == 1 else np.dtype('<' + kind + '2')).astype(np.int64)
            if np.all(np.diff(v) > 0):
                return CountAxis(header, a, n, width, tuple(int(x) for x in v))
    return None


def _raw_arrays(data: bytes, lo: int, hi: int) -> list[CountAxis]:
    b = np.frombuffer(data, np.uint8)
    out = []
    for width in (1, 2):
        start = lo + (lo % 2 if width == 2 else 0)
        heads = np.arange(start, hi - width, width)
        if width == 1:
            counts = b[heads].astype(np.int64)
        else:
            counts = b[heads].astype(np.int64) | (b[heads + 1].astype(np.int64) << 8)
        ok = (counts >= MIN_POINTS) & (counts <= MAX_POINTS) & (heads + width + counts * width <= hi)
        found = []
        # Same test as _increasing, evaluated for all headers of one count at once.
        for n in np.unique(counts[ok]).tolist():
            h = heads[ok & (counts == n)]
            pos = (h + width)[:, None] + width * np.arange(n)[None, :]
            v = b[pos].astype(np.int64) if width == 1 else                 b[pos].astype(np.int64) | (b[pos + 1].astype(np.int64) << 8)
            d = np.diff(v, axis=1)
            good = np.all(d >= 0, axis=1) & (np.sum(d > 0, axis=1) >= n - 1 - n // 8) & (v[:, -1] - v[:, 0] >= n - 1)
            found += [(int(hh), vv) for hh, vv in zip(h[good].tolist(), v[good].tolist())]
        found.sort(key=lambda t: t[0])
        out += [CountAxis(hh, hh + width, len(vv), width, tuple(vv)) for hh, vv in found]
    return out


def scan_count_axes(data: bytes, lo: int = 0, hi: int | None = None) -> list[CountAxis]:
    """Non-overlapping chained breakpoint arrays in [lo, hi), sorted by offset."""
    hi = len(data) if hi is None else min(hi, len(data))
    raw = _raw_arrays(data, lo, hi)
    starts = {}
    ends = {}
    for ax in raw:
        starts.setdefault(ax.header, []).append(ax)
        ends.setdefault(ax.end, []).append(ax)

    def strong(axes):
        return any(a.count >= 3 for a in axes)

    chained = []
    for ax in raw:
        nxt, prv = starts.get(ax.end, []), ends.get(ax.header, [])
        if not (nxt or prv):
            continue
        # Two-point arrays are common by chance; they need a 3+ point neighbour.
        if ax.count < 3 and not (strong(nxt) or strong(prv)):
            continue
        chained.append(ax)
    chained.sort(key=lambda a: (-a.count * a.width, a.header))
    taken, chosen = [], []
    for ax in chained:
        if any(ax.header < e and s < ax.end for s, e in taken):
            continue
        taken.append((ax.header, ax.end))
        chosen.append(ax)
    chosen.sort(key=lambda a: a.header)
    # Keep only runs of MIN_CHAIN or more directly adjacent arrays: real axis
    # blocks are long, chance matches in other data rarely chain that far.
    kept, run = [], []
    for ax in chosen + [None]:
        if ax is not None and run and run[-1].end == ax.header:
            run.append(ax)
            continue
        if len(run) >= MIN_CHAIN:
            kept.extend(run)
        run = [ax] if ax is not None else []
    return kept


def quantity_hint(ax: CountAxis) -> str:
    """Ranked scaling suggestion for an axis (MS43: 58 % top-1, 78 % top-3), as text."""
    from .axis_semantics import guess_axis
    guesses = guess_axis(ax.values, ax.width)
    if not guesses:
        return ''
    return 'Vermutung: ' + ' / '.join(g.describe() for g in guesses[:2])


def axis_definitions(axes: list[CountAxis]) -> list[MapDefinition]:
    """Editable 1 x n candidates for detected breakpoint arrays."""
    return [MapDefinition(
        name=f'Achsenkandidat @ 0x{ax.offset:08X}', offset=ax.offset, rows=1, cols=ax.count,
        dtype=('s' if min(ax.values) < 0 else 'u') + ('8' if ax.width == 1 else '16'),
        endian='little', source='heuristic', confidence=.45,
        record_layout=AXIS_LAYOUT, candidate_region_start=ax.header,
        label_origin='Stützstellen-Array mit Anzahl-Präfix (ungeprüft)',
        label_evidence=(f'{ax.count} aufsteigende Werte nach Anzahl-{"Byte" if ax.width == 1 else "Wort"} '
                        f'@ 0x{ax.header:X}, in einer Kette weiterer Arrays. Achsen-Hypothese, Einheit unbekannt.'),
        notes='Vermutete Kennfeld-/Kennlinienachse (Stützstellen); Einheit und Skalierung ungeprüft.',
        axes_info=quantity_hint(ax))
        for ax in axes]
