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

Proposals stay unverified ("transfer-proposed"); nothing is written into the
firmware. Measured against the sister's own definition in tools/name_transfer_benchmark.
"""
from __future__ import annotations
import bisect
from dataclasses import dataclass, replace
import numpy as np
from .model import BinaryImage, MapDefinition

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
        moved = replace(m, offset=m.offset + shift, source='transfer-proposed', verified=False,
                        label_origin=f'Namensübertragung · {evidence}', label_evidence=note,
                        notes=(m.notes + ' ' + note).strip())
        out.append(Transfer(m, moved, evidence, shift))
    return out


# Measured share of correct transfers per evidence class (tools/name_transfer_benchmark,
# MED17.1.62 404A/H/L in five directions and MSD80 sister versions, 21.10.2026).
MEASURED = {'identisch': '98–100 %', 'gleicher Kopf': 'nicht gemessen', 'ähnliche Werte': '87–100 %',
            'gleiche Umgebung': '66–100 %'}


def definition_maps(path: str, image: BinaryImage) -> list[MapDefinition]:
    """Maps of an XDF/A2L/RomRaider/CSV definition for the image it belongs to."""
    from ecu_studio.tools.structure_benchmark import _reference
    return [m for m in _reference(path, image) if m.rows * m.cols >= 2]
