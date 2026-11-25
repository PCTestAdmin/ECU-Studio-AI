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
# After 1.21.0-rc1: curve values with a top bit set were read as s16 without evidence for the sign (the axis
# rises in one reading; the values decide nothing). The unsigned reading stays open ("?"), as for records.
CURVE_SIGN_OPEN = True
# Quality phase 3 (1-D benchmark, development data): the 16-bit value width of a curve record is only fixed by
# the structure when another record begins right behind the 16-bit values. Without it the values may as well be
# 8 bit (Cur_Xs16Wu8): all wrong widths of exact curve hits were such curves (MEVD17.2 603 of 631, MSD80 877 of
# 877), none marked. Their width stays open ("?"); values, address and shape are unchanged.
CURVE_WIDTH_OPEN = True
CURVE_WIDTH_NOTE = (' Wertebreite offen: auch eine 8-Bit-Tabelle gleicher Form ist möglich '
                    '(kein Datensatzkopf direkt hinter den 16-Bit-Werten; ungeprüft).')
# Quality phase 4 (1-D error classes, development data, A2L for evaluation only): of the wrong widths that still
# carried no "?", 28 were 8-bit curves whose 16-bit reading also ends at a head (by chance, inside the next
# object) while a head or a count-prefixed axis begins right behind the 8-bit values as well (only a record
# head is used: see below); 53 were 8-bit axes
# read as 16-bit record axes whose bytes, read one by one, rise too. Both widths are then structurally possible:
# the width stays open ("?"). Marking only; values, address and shape are unchanged.
WIDTH_BOTH_OPEN = True
WIDTH_BOTH_NOTE = (' Wertebreite offen: auch eine 8-Bit-Tabelle gleicher Form ist möglich '
                   '(auch direkt hinter den 8-Bit-Werten beginnt ein Datensatz; ungeprüft).')
AXIS_WIDTH_NOTE = (' Wertebreite offen: auch eine 8-Bit-Tabelle bzw. 8-Bit-Achse ist möglich '
                   '(die Bytes steigen auch einzeln gelesen; ungeprüft).')
# Experiment (quality phase 4, off: a type change). A head right behind the 8-bit values and none behind the
# 16-bit values: read the values as 8 bit (quality phase 3 measured 16 bit wrong in all such cases, MEVD17.2
# 160, MSD80 281, none right).
CURVE_U8_BY_HEAD = False
CURVE_U8_NOTE = (' Wertebreite 1 Byte: hinter der 8-Bit-Lesart beginnt ein Datensatzkopf, hinter der 16-Bit-Lesart '
                 'keiner (Experiment; ungeprüft).')
MIN_POINTS, MAX_POINTS = 4, 32
GAP = 2   # alignment padding between packed records


def bytes_rise(data: bytes, at: int, n: int) -> bool:
    """The 2n bytes of a 16-bit axis, read one by one, rise strictly: an 8-bit axis reads the same way."""
    raw = data[at:at + 2 * n]
    return len(raw) == 2 * n and bool(np.all(np.diff(np.frombuffer(raw, np.uint8).astype(np.int16)) > 0))
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
            behind = any(end + g in heads for g in range(0, GAP + 1))
            chained = behind or any(h - g in ends for g in range(0, GAP + 1))
            if not chained:
                continue
            heads8 = any(values + n + g in heads for g in range(0, GAP + 1))
            u8 = CURVE_U8_BY_HEAD and heads8 and not behind
            if u8:
                raw_b = np.frombuffer(data[values:values + n], np.uint8)
                top = bool(np.any(raw_b >= 0x80))
                dtype, alternatives, width_note = 'u8', ['s8'] if CURVE_SIGN_OPEN and top else [], CURVE_U8_NOTE
            else:
                raw_w = np.frombuffer(data[values:values + 2 * n], ('<' if endian == 'little' else '>') + 'u2')
                top = bool(np.any(raw_w >= 0x8000))
                dtype, alternatives = 's16' if signed or top else 'u16', ['u16'] if CURVE_SIGN_OPEN and top else []
                width_note = ''
                if CURVE_WIDTH_OPEN and not behind:
                    width_note = CURVE_WIDTH_NOTE
                elif WIDTH_BOTH_OPEN and behind and heads8:
                    # Only a record head counts: with any count-prefixed axis (axis_at) behind the 8-bit values,
                    # development data gave 18 wrong widths caught for 311 right ones newly marked.
                    width_note = WIDTH_BOTH_NOTE
            common = dict(source='heuristic', confidence=.44, candidate_region_start=h)
            out.append(MapDefinition(f'Kennlinien-Kandidat @ 0x{values:08X}', values, 1, n, dtype, endian,
                                     dtype_alternatives=alternatives,
                                     record_layout=CURVE_LAYOUT, axes_x=list(axis), axis_x_offset=h + 2,
                                     label_origin='Kennlinien-Datensatz: Anzahl + monotone Achse, in einer Datensatz-Kette (ungeprüft)',
                                     label_evidence=f'{n} Stützstellen @ 0x{h + 2:X}, Werte @ 0x{values:X}.',
                                     notes='Kennlinie aus Kopf-Datensatz; Einheit und Skalierung unbekannt.'
                                     + width_note, **common))
            out.append(MapDefinition(f'Achse von 0x{values:08X}', h + 2, 1, n, 's16' if signed else 'u16', endian,
                                     record_layout=CURVE_AXIS_LAYOUT,
                                     label_origin='Stützstellen eines Kennlinien-Datensatzes (ungeprüft)',
                                     label_evidence=f'X-Achse des Datensatzes @ 0x{h:X} mit Anzahl-Kopf.',
                                     notes='Achsen-Hypothese aus n,X,W-Kopf; Einheit unbekannt.'
                                     + (AXIS_WIDTH_NOTE if WIDTH_BOTH_OPEN and bytes_rise(data, h + 2, n) else ''),
                                     **common))
    return out
