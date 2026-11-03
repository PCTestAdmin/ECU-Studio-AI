"""Carry map names and layouts from a defined software version to a sister version.

A definition (XDF/A2L) exists for the source image; the target is a related
software version without one. Both images are aligned by anchors: 32-byte
windows that occur exactly once in each file, kept as a monotone chain. A map
moves by the shift of the nearest anchor and is only proposed when the target
confirms it:

- ``identisch``: the bytes at the new place equal the source bytes,
- ``gleicher Kopf``: a stored header (counts and axes) is equal, values changed,
- ``ähnliche Werte``: same shape, values correlate (>= MIN_CORR),
- ``gleiche Umgebung``: a flat block (zeros, one value) equal at the shifted
  place; only the neighbouring anchors place it - weakest.

Independently of the source, ``confirm_by_detection`` marks a proposal whose
target place holds a table the target's own scan found (same start, size, cell
width and byte order; any detection layer, the measured rates in
MEASURED_DETECTED cover all of them). That is a second, independent argument
for the location, not for the name, function, data type or scaling. A detected
table whose axes lie elsewhere than the moved axes does not confirm.

Axes move only where the target bytes confirm them (relocated_axis); otherwise
the source's axis values are not carried over (they would label the target
table with values it may not have) and the proposal says so.

Proposals stay unverified ("transfer-proposed"); nothing is written into the
firmware. Measured against the sister's own definition in tools/name_transfer_benchmark.
"""
from __future__ import annotations
import bisect
from dataclasses import dataclass, replace
import numpy as np
from .model import BinaryImage, MapDefinition
from .axis_groups import relocated_axis

WINDOW = 32
STEP = 16           # source window spacing
MIN_CORR = .95
MIN_DISTINCT_BYTES = 4   # fewer distinct bytes: a flat block, location not provable
EVIDENCE = ('identisch', 'gleicher Kopf', 'ähnliche Werte', 'gleiche Umgebung')


@dataclass
class Transfer:
    source: MapDefinition
    target: MapDefinition
    evidence: str
    shift: int
    detected_in_target: bool = False
    axes_dropped: tuple = ()          # 'X'/'Y': source axis not found at the moved place, values not carried over
    detection_conflict: str = ''      # target detection: same table, other axes


def _informative(w: bytes) -> bool:
    return len(set(w)) >= 6        # erased/constant/padding windows are not unique evidence


def anchors(source: bytes, target: bytes) -> list[tuple[int, int]]:
    """Monotone chain of (source offset, target offset) of windows unique in both images."""
    tpos: dict[bytes, int] = {}
    dup = set()
    for t in range(0, len(target) - WINDOW + 1, 2):
        w = target[t:t + WINDOW]
        if w in tpos:
            dup.add(w)
        else:
            tpos[w] = t
    seen: dict[bytes, int] = {}
    sdup = set()
    for s in range(0, len(source) - WINDOW + 1, STEP):
        w = source[s:s + WINDOW]
        if w in seen:
            sdup.add(w)
        seen[w] = s
    pairs = sorted((s, tpos[w]) for w, s in seen.items()
                   if w not in sdup and w in tpos and w not in dup and _informative(w))
    # Longest chain increasing in both offsets (blocks keep their order between versions).
    tails, prev, idx = [], [-1] * len(pairs), []
    for i, (_, t) in enumerate(pairs):
        k = bisect.bisect_left(tails, t)
        if k == len(tails):
            tails.append(t); idx.append(i)
        else:
            tails[k] = t; idx[k] = i
        prev[i] = idx[k - 1] if k else -1
    chain, i = [], idx[-1] if idx else -1
    while i >= 0:
        chain.append(pairs[i]); i = prev[i]
    return chain[::-1]


def _header_span(m: MapDefinition) -> int:
    """Bytes of a stored header in front of the values (0 if none known)."""
    if m.candidate_region_start is not None and m.candidate_region_start < m.offset:
        return m.offset - m.candidate_region_start
    return 0


def transfer_names(source: BinaryImage, target: BinaryImage, maps: list[MapDefinition], *,
                   cancelled=None) -> list[Transfer]:
    src, dst = source.read(0, source.size), target.read(0, target.size)
    chain = anchors(src, dst)
    if not chain:
        return []
    starts = [s for s, _ in chain]
    out = []
    for m in maps:
        if cancelled and cancelled():
            return []
        k = bisect.bisect_right(starts, m.offset) - 1
        options = []
        for j in (k, k + 1):
            if 0 <= j < len(chain):
                options.append(chain[j][1] - chain[j][0])
        best = None
        for shift in dict.fromkeys(options):
            t = m.offset + shift
            if t < 0 or t + m.length > len(dst):
                continue
            a, b = src[m.offset:m.offset + m.length], dst[t:t + m.length]
            if len(set(a)) < MIN_DISTINCT_BYTES:
                # Flat blocks (zeros, one value) match anywhere: only the neighbouring
                # anchors place them - the weakest class.
                if a == b:
                    best = best or ('gleiche Umgebung', shift)
                continue
            if a == b:
                best = ('identisch', shift); break
            head = _header_span(m)
            if head and src[m.offset - head:m.offset] == dst[t - head:t]:
                best = best or ('gleicher Kopf', shift); continue
            moved = replace(m, offset=t)
            try:
                x = source.matrix(m).astype(float).ravel(); y = target.matrix(moved).astype(float).ravel()
            except (ValueError, IndexError):
                continue
            if np.ptp(x) > 0 and np.ptp(y) > 0 and np.corrcoef(x, y)[0, 1] >= MIN_CORR:
                if best is None or EVIDENCE.index(best[0]) > EVIDENCE.index('ähnliche Werte'):
                    best = ('ähnliche Werte', shift)
        if best is None:
            continue
        evidence, shift = best
        note = (f'Name aus dem Schwesterstand übernommen ({evidence}, Verschiebung {shift:+d} Byte). '
                'Ungeprüft: Funktion und Skalierung am Zielstand bestätigen.')
        # Axes and a stored header move with the map only where the target confirms them.
        region = m.candidate_region_start
        ax = relocated_axis(source, target, m.axis_x_offset, m.cols, shift)
        ay = relocated_axis(source, target, m.axis_y_offset, m.rows, shift)
        dropped = tuple(name for name, old, new in (('X', m.axis_x_offset, ax), ('Y', m.axis_y_offset, ay))
                        if old is not None and new is None)
        if dropped:
            note += (' ' + '/'.join(dropped) + '-Achse am Zielort nicht bestätigt (Bytes abweichend): '
                     'Achswerte des Schwesterstands nicht übernommen.')
        moved = replace(m, offset=m.offset + shift, source='transfer-proposed', verified=False,
                        candidate_region_start=region + shift if region is not None and region + shift >= 0 else None,
                        axis_x_offset=ax, axis_y_offset=ay,
                        axes_x=[] if 'X' in dropped else m.axes_x, axes_y=[] if 'Y' in dropped else m.axes_y,
                        label_origin=f'Namensübertragung · {evidence}', label_evidence=note,
                        notes=(m.notes + ' ' + note).strip())
        out.append(Transfer(m, moved, evidence, shift, axes_dropped=dropped))
    return out


# The share of correct transfers per evidence class was measured only on development data of unclear provenance
# (MED17.1.62, MSD80 sister versions); the numbers stay in docs/VALIDIERUNG_1.19.0.md § 7 as history and are not
# shown as a rate for other files. Evidence classes are listed from strongest to weakest (EVIDENCE).
NOT_VALIDATED = ('Belegarten von stark nach schwach: identisch, gleicher Kopf, ähnliche Werte, gleiche Umgebung. '
                 'Trefferquoten nur an Entwicklungsdaten gemessen, nicht unabhängig validiert.')


def _axes_differ(t: MapDefinition, hit: MapDefinition) -> list[str]:
    """Axes both readings place, at different addresses (orientation-independent)."""
    mine = {o for o in (t.axis_x_offset, t.axis_y_offset) if o is not None}
    theirs = {o for o in (hit.axis_x_offset, hit.axis_y_offset) if o is not None}
    if not mine or not theirs or mine & theirs == mine or mine & theirs == theirs:
        return []
    return [f'0x{o:X}' for o in sorted(theirs - mine)]


def confirm_by_detection(transfers: list[Transfer], detected: list[MapDefinition]) -> int:
    """Flag transfers that land on a table the target's own detection found; returns their number."""
    tables = {(m.offset, tuple(sorted((m.rows, m.cols))), m.width): m for m in detected}
    count = 0
    for tr in transfers:
        t = tr.target
        hit = tables.get((t.offset, tuple(sorted((t.rows, t.cols))), t.width))
        if hit is None or (t.width > 1 and hit.endian != t.endian):
            continue
        other = _axes_differ(t, hit)
        if other:
            tr.detection_conflict = 'Erkennung im Zielstand: dieselbe Tabelle, Achsen aber bei ' + ', '.join(other)
            note = tr.detection_conflict + ' – Achsen prüfen.'
            if note not in t.notes:
                t.notes = (t.notes + ' ' + note).strip()
            continue
        tr.detected_in_target = True
        count += 1
        note = f'Lage unabhängig bestätigt: die Erkennung im Zielstand findet hier dieselbe Tabelle ({hit.label_origin or hit.record_layout}).'
        if note not in t.notes:
            t.notes = (t.notes + ' ' + note).strip()
            t.label_evidence = (t.label_evidence + ' ' + note).strip()
    return count


def definition_maps(path: str, image: BinaryImage) -> list[MapDefinition]:
    """Maps of an XDF/A2L/RomRaider/CSV definition for the image it belongs to."""
    from ecu_studio.tools.structure_benchmark import _reference
    return [m for m in _reference(path, image) if m.rows * m.cols >= 2]
