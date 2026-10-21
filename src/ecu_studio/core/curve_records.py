"""Curve records ``n, X[n], W[n]`` with a 16-bit count (Bosch Cur_Xs16Ws16 / Kl_Xs16_Ws16).

One axis is weaker evidence than the two of a map record, so a curve record is
only accepted inside a chain: it must touch another record (map record, curve
record) directly or after alignment padding, as packed record lists do. The
complete EDC17CP09 A2L (development) holds 701 such records; before this
module none was found.

Geometry only: the values block W[n] and the axis X[n] become 1-D candidates
with raw values; units and names stay unknown.
"""
from __future__ import annotations
import numpy as np
from .model import BinaryImage, MapDefinition
from .axis_records import _record_axis

CURVE_LAYOUT = 'candidate:curve-record'
CURVE_AXIS_LAYOUT = 'candidate:record-axis'
MIN_POINTS, MAX_POINTS = 4, 32
GAP = 2   # alignment padding between packed records
DOMINANCE = 2.5    # 16-bit map records of one byte order must outnumber the other (EDC17CP09 4:1, ME9.2.1 3.2:1)
MIN_RECORDS = 30   # and be common: no record convention, no curve records (MS43: 18)


def _other(endian: str) -> str:
    return 'big' if endian == 'little' else 'little'


def _raw_curves(data: bytes, endian: str) -> list[tuple[int, int, list[int], bool]]:
    """(header, n, axis values, signed) for every 16-bit count followed by a plausible monotone axis."""
    fmt = ('<' if endian == 'little' else '>') + 'u2'
    out = []
    for phase in (0,):   # 16-bit records are word-aligned (TriCore, PowerPC, C167); odd starts read noise
        b = np.frombuffer(data[phase:phase + (len(data) - phase) // 2 * 2], fmt).astype(np.int64)
        idx = np.flatnonzero((b >= MIN_POINTS) & (b <= MAX_POINTS))
        for n in np.unique(b[idx]).tolist():
            h = idx[b[idx] == n]
            h = h[h + 1 + 2 * n <= len(b)]
            if not len(h):
                continue
            v = b[(h + 1)[:, None] + np.arange(n)[None, :]]
            for signed in (False, True):
                w = np.where(v >= 0x8000, v - 0x10000, v) if signed else v
                d = np.diff(w, axis=1)
                ok = np.all(d > 0, axis=1) | np.all(d < 0, axis=1)
                if signed:
                    ok &= np.any(v >= 0x8000, axis=1)
                for hh, vv in zip(h[ok].tolist(), w[ok].tolist()):
                    if _record_axis(vv):
                        out.append((phase + 2 * hh, n, vv, signed))
    return out


def scan_curve_records(image: BinaryImage, map_records: list[MapDefinition] = (), *,
                       cancelled=None) -> list[MapDefinition]:
    """Values (1 x n) and axis (1 x n) candidates of chained curve records."""
    data = image.read(0, image.size)
    out = []
    # Byte order of the image from its 2-D header records: swapped readings of
    # big-endian data look like curves too (BMW MSS54: 53 such false curves).
    wide = [m for m in map_records if m.width == 2]
    votes = {e: sum(m.endian == e for m in wide) for e in ('little', 'big')}
    allowed = [e for e in votes if votes[e] >= DOMINANCE * max(1, votes[_other(e)]) and votes[e] >= MIN_RECORDS]
    for endian in allowed:
        if cancelled and cancelled():
            return []
        raw = _raw_curves(data, endian)
        if not raw:
            continue
        ends = {h + 2 + 4 * n: (h, n) for h, n, _, _ in raw}
        axis_end = {h: h + 2 + 2 * n for h, n, _, _ in raw}   # header -> end of its axis
        heads = {h for h, _, _, _ in raw}
        for m in map_records:
            if m.endian == endian and m.candidate_region_start is not None:
                heads.add(m.candidate_region_start)
                ends.setdefault(m.offset + m.length, None)
        for h, n, axis, signed in raw:
            values = h + 2 + 2 * n
            # Axis chains (Siemens MS4x: n, X[n], m, Y[m], k, Z[k] ...): the "values" are the
            # next counted axis, not a curve. A chain needs a third axis behind that one, so a
            # curve whose first value merely looks like a count is kept.
            if values in axis_end and axis_end[values] in heads:
                continue
            end = h + 2 + 4 * n
            chained = any(end + g in heads for g in range(0, GAP + 1)) or any(h - g in ends for g in range(0, GAP + 1))
            if not chained:
                continue
            raw_w = np.frombuffer(data[values:values + 2 * n], ('<' if endian == 'little' else '>') + 'u2')
            dtype = 's16' if signed or bool(np.any(raw_w >= 0x8000)) else 'u16'
            common = dict(source='heuristic', confidence=.44, candidate_region_start=h)
            out.append(MapDefinition(f'Kennlinien-Kandidat @ 0x{values:08X}', values, 1, n, dtype, endian,
                                     record_layout=CURVE_LAYOUT, axes_x=list(axis),
                                     label_origin='Kennlinien-Datensatz: Anzahl + monotone Achse, in einer Datensatz-Kette (ungeprüft)',
                                     label_evidence=f'{n} Stützstellen @ 0x{h + 2:X}, Werte @ 0x{values:X}.',
                                     notes='Kennlinie aus Kopf-Datensatz; Einheit und Skalierung unbekannt.', **common))
            out.append(MapDefinition(f'Achse von 0x{values:08X}', h + 2, 1, n, 's16' if signed else 'u16', endian,
                                     record_layout=CURVE_AXIS_LAYOUT,
                                     label_origin='Stützstellen eines Kennlinien-Datensatzes (ungeprüft)',
                                     label_evidence=f'X-Achse des Datensatzes @ 0x{h:X} mit Anzahl-Kopf.',
                                     notes='Achsen-Hypothese aus n,X,W-Kopf; Einheit unbekannt.', **common))
    return out
