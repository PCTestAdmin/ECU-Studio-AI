"""Byte ranges that are clearly not calibration tables: C-string text and pointer tables.

Both classifiers are conservative. They mark only what is proven by the bytes
themselves; everything else stays unclassified and is left to the detectors.

Text
    A run of NUL-terminated strings: each string has at least ``MIN_STRING``
    printable ASCII characters, contains letters, and does not read like a
    ramp of numbers (calibration bytes such as 0x41 0x42 0x43 ... are printable,
    but neighbouring characters of real text are rarely within +-2 of each
    other). Strings may be padded with NUL bytes to a fixed slot width
    (``"TLE8888.INJ1\\0\\0\\0\\0TLE8888.INJ2..."``). A table of calibration bytes
    without NUL terminators is never text; a table that happens to contain an
    isolated printable stretch is not text either, because coverage must be
    nearly complete (``TEXT_COVERAGE``).

Pointer table
    Only for an established architecture with a known pointer format (ARM
    Cortex-M: little-endian 32-bit, see core/architecture). A run of at least
    ``MIN_POINTERS`` aligned words, each an address inside the image's own
    flash window (around the reset vector) or its SRAM window (below the
    initial stack pointer), with NULL entries allowed but in the minority and
    at least three different targets. At least 75 % of the words must look like
    addresses: a run of words whose two 16-bit halves are alike (u16 values
    around 0x0800) or whose three low bytes are all small (u8 tables of small
    integers) is no pointer table.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .architecture import ARM, Architecture, arm_vector_table

MIN_STRING = 4
MIN_LETTERS = 2
MAX_RAMP_SHARE = .5           # share of neighbouring characters within +-2 (text ~.1-.3, ramps > .6)
MAX_PAD = 16                  # NUL bytes after a string still inside the text run (fixed-width slots)
MIN_TEXT_RUN = 2              # strings in a text run
TEXT_COVERAGE = .9            # share of a candidate's bytes inside text runs
MIN_POINTERS = 4
MAX_NULL_SHARE = .25
MIN_DISTINCT_POINTERS = 3
POINTER_COVERAGE = .9
POINTER_HALF_GAP = 0x40       # |low half - high half| of a pointer word (table values near 0x0800 have ~0)
MIN_ADDRESS_LIKE = .75        # share of address-like words in a pointer run
VECTOR_TABLE_MAX = 256        # Cortex-M: at most 16 system + 240 external vectors
ARM_CCM = (0x10000000, 0x10010000)


@dataclass(frozen=True)
class Spans:
    starts: np.ndarray
    ends: np.ndarray

    def coverage(self, lo: int, hi: int) -> float:
        """Share of [lo, hi) inside the spans."""
        if hi <= lo or not len(self.starts):
            return 0.
        k0 = max(int(np.searchsorted(self.ends, lo, 'right')), 0)
        covered = 0
        for s, e in zip(self.starts[k0:].tolist(), self.ends[k0:].tolist()):
            if s >= hi:
                break
            covered += max(0, min(e, hi) - max(s, lo))
        return covered / (hi - lo)

    def __len__(self):
        return len(self.starts)


EMPTY = Spans(np.zeros(0, np.int64), np.zeros(0, np.int64))


def _printable(b: np.ndarray) -> np.ndarray:
    return ((b >= 0x20) & (b < 0x7F)) | (b == 0x09) | (b == 0x0A) | (b == 0x0D)


def is_text_string(s: bytes) -> bool:
    """One NUL-free string that reads as text (letters, not a ramp of numbers)."""
    if len(s) < MIN_STRING:
        return False
    a = np.frombuffer(s, np.uint8)
    if not _printable(a).all():
        return False
    letters = int((((a | 0x20) >= 0x61) & ((a | 0x20) <= 0x7A)).sum())
    if letters < MIN_LETTERS:
        return False
    d = np.abs(np.diff(a.astype(np.int16)))
    return float((d <= 2).mean()) <= MAX_RAMP_SHARE


def text_spans(data: bytes) -> Spans:
    """[start, end) runs of at least MIN_TEXT_RUN NUL-terminated text strings (with their padding)."""
    b = np.frombuffer(data, np.uint8)
    if not len(b):
        return EMPTY
    pr = _printable(b)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], pr.astype(np.int8), [0]])))
    s_all, e_all = edges[0::2], edges[1::2]
    # Only NUL-terminated runs of MIN_STRING or more characters are candidates.
    keep = (e_all - s_all >= MIN_STRING) & (e_all < len(b))
    keep[keep] &= b[e_all[keep]] == 0
    runs = []
    for s, e in zip(s_all[keep].tolist(), e_all[keep].tolist()):
        if not is_text_string(data[s:e]):
            continue
        pad = e
        while pad < len(b) and pad - e < MAX_PAD and b[pad] == 0:
            pad += 1
        runs.append((s, pad))
    starts, ends, counts = [], [], []
    for s, e in runs:
        if starts and s <= ends[-1]:
            ends[-1] = max(ends[-1], e)
            counts[-1] += 1
        else:
            starts.append(s)
            ends.append(e)
            counts.append(1)
    keep = [i for i, c in enumerate(counts) if c >= MIN_TEXT_RUN]
    return Spans(np.array([starts[i] for i in keep], np.int64), np.array([ends[i] for i in keep], np.int64))


def pointer_windows(data: bytes, arch: Architecture) -> list[tuple[int, int]]:
    """Address windows a pointer of this image can point into; [] without a known pointer format.

    ARM Cortex-M: the image's own flash (around the reset vector), the SRAM
    below the initial stack pointer and the core-coupled RAM of STM32F4-class
    parts (0x1000_0000; rusEFI keeps its table objects there).
    """
    if arch.name != ARM:
        return []
    vt = arm_vector_table(data)
    if vt is None:
        return []
    sp, reset = vt
    flash = (max(0, reset - len(data)), reset + len(data))
    sram = (max(0, sp - 0x80000), sp + 0x80000)
    return [flash, sram, ARM_CCM]


def _address_words(data: bytes, arch: Architecture):
    """(words, in-window, address-like) for aligned little-endian 32-bit words; None without a pointer format."""
    windows = pointer_windows(data, arch)
    n = len(data) // 4
    if not windows or n < MIN_POINTERS:
        return None
    # The image starts at the vector table, which is at least 128-byte aligned:
    # pointers sit on file offsets divisible by 4.
    w = np.frombuffer(data[:4 * n], '<u4').astype(np.int64)
    ptr = np.zeros(n, bool)
    for lo, hi in windows:
        ptr |= (w >= lo) & (w < hi)
    # Table values can land in an address window too: a u16 table near 2048
    # (Q11 factor 1.0 = 0x0800) reads as 0x0800_0800, a u8 table of small
    # integers as 0x08_05_07_06. Address-like words have halves unlike each other
    # and not all three low bytes small (single real pointers such as 0x0801_0105
    # fail that test by chance, so runs need only a majority).
    lo16, hi16 = w & 0xFFFF, w >> 16
    small = ((w & 0xFF) < 0x20) & (((w >> 8) & 0xFF) < 0x20) & (((w >> 16) & 0xFF) < 0x20)
    distinct = (np.abs(lo16 - hi16) > POINTER_HALF_GAP) & ~small
    return w, ptr, distinct


def _merge(starts: list[int], ends: list[int]) -> Spans:
    if not starts:
        return EMPTY
    order = np.argsort(starts, kind='stable')
    ms, me = [], []
    for i in order.tolist():
        if ms and starts[i] <= me[-1]:
            me[-1] = max(me[-1], ends[i])
        else:
            ms.append(starts[i])
            me.append(ends[i])
    return Spans(np.array(ms, np.int64), np.array(me, np.int64))


def vector_table_end(data: bytes, arch: Architecture) -> int:
    """End offset of the Cortex-M vector table: up to the last handler entry before 8 non-handler words in a row.

    Reserved slots may hold other values (FOME/ChibiOS: image checksum and size in entries 7 and 8).
    """
    if arch.name != ARM:
        return 0
    vt = arm_vector_table(data)
    if vt is None:
        return 0
    reset = vt[1]
    n = min(len(data) // 4, VECTOR_TABLE_MAX)
    w = np.frombuffer(data[:4 * n], '<u4').astype(np.int64)
    last, misses = 1, 0
    for i in range(1, n):
        v = int(w[i])
        if v & 1 and abs(v - reset) < len(data) + 0x10000:
            last, misses = i, 0
        else:
            misses += 1
            if misses >= 8:
                break
    return 4 * (last + 1)


def pointer_spans(data: bytes, arch: Architecture) -> Spans:
    """[start, end) runs of aligned little-endian 32-bit pointers into the image's own windows,
    plus the Cortex-M vector table."""
    words = _address_words(data, arch)
    if words is None:
        return EMPTY
    w, ptr, distinct = words
    ok = ptr | (w == 0)
    e = np.flatnonzero(np.diff(np.concatenate([[0], ok.astype(np.int8), [0]])))
    starts, ends = [], []
    for s, t in zip(e[0::2].tolist(), e[1::2].tolist()):
        # Trim NULL entries at both ends: they belong to whatever follows.
        while s < t and w[s] == 0:
            s += 1
        while t > s and w[t - 1] == 0:
            t -= 1
        if t - s < MIN_POINTERS:
            continue
        seg = w[s:t]
        if (seg == 0).mean() > MAX_NULL_SHARE or len(set(seg[seg != 0].tolist())) < MIN_DISTINCT_POINTERS:
            continue
        if distinct[s:t][seg != 0].mean() < MIN_ADDRESS_LIKE:
            continue
        starts.append(4 * s)
        ends.append(4 * t)
    vte = vector_table_end(data, arch)
    if vte:
        starts.append(0)
        ends.append(vte)
    return _merge(starts, ends)


def address_word_spans(data: bytes, arch: Architecture) -> Spans:
    """Single aligned words inside the image's address windows (no run needed).

    Used only for small structures whose parts must all be such words, e.g. both
    axes of a header record (core/scoped_scan); never to suppress a table alone.
    Little-endian addresses 0x080Axxxx have small upper bytes, so the
    address-like test of pointer runs does not apply to single words here.
    """
    words = _address_words(data, arch)
    if words is None:
        return EMPTY
    w, ptr, distinct = words
    idx = np.flatnonzero(ptr)
    return _merge((4 * idx).tolist(), (4 * idx + 4).tolist())


def classify(lo: int, hi: int, text: Spans, pointers: Spans) -> str:
    """'text', 'pointer' or '' for the byte range [lo, hi)."""
    if text.coverage(lo, hi) >= TEXT_COVERAGE:
        return 'text'
    if pointers.coverage(lo, hi) >= POINTER_COVERAGE:
        return 'pointer'
    return ''
