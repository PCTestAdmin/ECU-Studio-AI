"""Checksum research: which range and algorithm reproduce a stored value?

Idea (not code) from UniversalPatcher's checksum search (GPL-3.0, joukoy): try
range/algorithm combinations against a known storage field. Own implementation:
sums over all candidate ranges via prefix sums (O(starts x ends)), CRCs only on
a small set of ranges.

A match is a HYPOTHESIS. With many tested combinations a 16-bit value also
matches by chance, so every search reports the expected number of chance
matches, and a hypothesis is only "confirmed" when it also holds on a second,
independent file of the same software (e.g. another original read). The result
is a draft profile with ``reviewed: false``; loading it for verification still
requires a person to review and set ``reviewed: true``.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .checksum_audit import SUPPORTED, ChecksumSlot, slot_value
from .model import BinaryImage

SUM_ALGORITHMS = ('sum16-bytes', 'sum32-bytes', 'sum16-words-be', 'sum16-words-le',
                  'sum32-words-be', 'sum32-words-le', 'sum32-dwords-be', 'sum32-dwords-le')
CRC_ALGORITHMS = ('crc16-ccitt', 'crc32-ieee')
MAX_COMBINATIONS = 5_000_000


@dataclass(frozen=True)
class Hypothesis:
    algorithm: str
    start: int
    end: int
    storage_offset: int
    endian: str
    complement: str
    confirmed_on: int = 1       # number of files on which it holds

    def slot(self, name: str = 'Kandidat') -> ChecksumSlot:
        return ChecksumSlot(name, self.algorithm, self.start, self.end, self.storage_offset,
                            self.endian, (), self.complement)


def _prefix(data: bytes, algorithm: str) -> tuple[np.ndarray, int]:
    """Prefix sums of the summed units and the unit size in bytes."""
    if algorithm.endswith('-bytes'):
        units, size = np.frombuffer(data, np.uint8), 1
    else:
        size = 4 if 'dwords' in algorithm else 2
        order = '>' if algorithm.endswith('-be') else '<'
        units = np.frombuffer(data[:len(data) // size * size], order + ('u2' if size == 2 else 'u4'))
    # uint64 throughout: differences wrap modulo 2^64, which the width mask then reduces exactly.
    return np.concatenate([np.zeros(1, np.uint64), np.cumsum(units.astype(np.uint64), dtype=np.uint64)]), size


def search_checksums(data: bytes, storage_offsets: list[int], *, starts: list[int] | None = None,
                     ends: list[int] | None = None, step: int = 0x100,
                     algorithms: tuple[str, ...] = SUM_ALGORITHMS + CRC_ALGORITHMS) -> dict:
    """Hypotheses whose computed value equals the stored one at a given offset.

    ``starts``/``ends`` default to multiples of ``step`` (plus file start/end and
    the positions around each storage field). Ranges never include the field.
    """
    n = len(data)
    if not storage_offsets:
        raise ValueError('Mindestens eine Speicherposition des Prüfwerts angeben')
    grid = set(range(0, n + 1, step)) | {0, n}
    for p in storage_offsets:
        grid |= {p, p + 2, p + 4}
    starts = sorted(set(starts) if starts else {g for g in grid if g < n})
    ends = sorted(set(ends) if ends else {g for g in grid if g > 0})
    hits, tested = [], 0
    for algorithm in algorithms:
        width = SUPPORTED[algorithm]
        mask = (1 << (8 * width)) - 1
        is_sum = algorithm in SUM_ALGORITHMS
        if is_sum:
            prefix, unit = _prefix(data, algorithm)
        for p in storage_offsets:
            if not 0 <= p <= n - width:
                continue
            stored = {e: int.from_bytes(data[p:p + width], e) for e in ('big', 'little')}
            if is_sum:
                s_arr = np.array([s for s in starts if s % unit == 0], np.int64)
                e_arr = np.array([e for e in ends if e % unit == 0], np.int64)
                if not len(s_arr) or not len(e_arr):
                    continue
                si, ei = s_arr // unit, e_arr // unit
                totals = (prefix[ei][None, :] - prefix[si][:, None]) & np.uint64(mask)
                valid = (e_arr[None, :] > s_arr[:, None]) & \
                        ((e_arr[None, :] <= p) | (s_arr[:, None] >= p + width))
                tested += int(valid.sum()) * 6
                if tested > MAX_COMBINATIONS * 6:
                    raise ValueError('Zu viele Kombinationen – Bereichsraster vergrößern')
                for complement in ('none', 'ones', 'twos'):
                    if complement == 'none':
                        value = totals
                    elif complement == 'ones':
                        value = ~totals & np.uint64(mask)
                    else:
                        value = (np.uint64(mask) + np.uint64(1) - totals) & np.uint64(mask)
                    for endian, want in stored.items():
                        for i, j in zip(*np.nonzero(valid & (value == np.uint64(want)))):
                            hits.append(Hypothesis(algorithm, int(s_arr[i]), int(e_arr[j]), p, endian, complement))
            else:
                # CRCs have no prefix trick: only ranges ending at the field or at
                # the file end, starting on the grid.
                image = BinaryImage(data)
                for s in starts:
                    for e in {p, n}:
                        if e <= s or (s < p + width and e > p):
                            continue
                        for endian, want in stored.items():
                            tested += 1
                            h = Hypothesis(algorithm, s, e, p, endian, 'none')
                            if slot_value(image, h.slot()) == want:
                                hits.append(h)
    widths = {a: SUPPORTED[a] for a in algorithms}
    # Expected chance matches: each test hits a uniform value with p = 2^-bits.
    expected = tested / (2 ** (8 * min(widths.values()))) if tested else 0.
    return {'hypotheses': hits, 'tested': tested, 'expected_chance_matches': round(expected, 2)}


def confirm(hypotheses: list[Hypothesis], other_files: list[bytes]) -> list[Hypothesis]:
    """Keep hypotheses that also hold on every other file (same layout, other content)."""
    kept = []
    for h in hypotheses:
        ok = 0
        for data in other_files:
            if h.end > len(data) or h.storage_offset + SUPPORTED[h.algorithm] > len(data):
                break
            stored = int.from_bytes(data[h.storage_offset:h.storage_offset + SUPPORTED[h.algorithm]], h.endian)
            if slot_value(BinaryImage(data), h.slot()) != stored:
                break
            ok += 1
        else:
            kept.append(Hypothesis(h.algorithm, h.start, h.end, h.storage_offset, h.endian, h.complement,
                                   1 + ok))
    return kept


def draft_profile(image: BinaryImage, hypotheses: list[Hypothesis], source: str) -> dict:
    """Profile JSON for review. ``reviewed`` stays False: loading it is refused until a person checks it."""
    return {'format': 1, 'firmware_sha256': image.digest, 'source': source,
            'reviewer': '', 'reviewed': False,
            'note': 'Entwurf aus der Checksummen-Suche: Hypothesen, keine geprüften Prüfsummen. '
                    'Erst nach manueller Prüfung reviewer eintragen und reviewed auf true setzen.',
            'slots': [{'name': f'Kandidat {i + 1} (bestätigt auf {h.confirmed_on} Datei(en))',
                       'algorithm': h.algorithm, 'start': h.start, 'end': h.end,
                       'storage_offset': h.storage_offset, 'endian': h.endian,
                       'complement': h.complement} for i, h in enumerate(hypotheses)]}
