"""Immediate address loads of further CPUs, with automatic address-map detection.

C16x is handled in structure_scan. Here: 68HC11/HC12 (LDX/LDY #addr) and 8051
(MOV DPTR,#addr), both big-endian, common in older 8-bit engine ECUs. The image
base is unknown, so each family/base pair is tested: the right one makes the
loaded addresses land in data-like blocks far more often than random addresses
do. Only a clear enrichment is accepted; otherwise nothing is returned.
Measured on ARAP.bin (16 KB): HC11 at 0xC000, 112 targets, 88 % in data blocks
vs 16 % for random addresses.

68k/CPU32 (e.g. GM P01): 32-bit absolute operands (abs.L / #imm.L) of 16-bit
opcodes. On a GM P01 image 254 of 351 XDF objects are such operand targets;
a PowerPC image (Opel E78) yields none, and the density rule rejects it.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
import numpy as np
from .data_regions import data_mask

FAMILIES = {
    'HC11': (re.compile(rb"\xCE(..)|\x18\xCE(..)", re.S),),
    '8051': (re.compile(rb"\x90(..)", re.S),),
}
MIN_TARGETS = 20
MIN_IN_DATA = .3
MIN_ENRICHMENT = 2.5
GENERIC_LAYOUT = 'candidate:code-reference-generic'
M68K_BASES = (0, 0x40000, 0x80000, 0x100000, 0x400000, 0x800000)
M68K_MIN_TARGETS = 200
M68K_MAX_SIZE = 4 * 1024 * 1024


@dataclass(frozen=True)
class CpuGuess:
    family: str
    base: int
    targets: int
    in_data: float
    baseline: float

    @property
    def enrichment(self) -> float:
        return self.in_data / max(self.baseline, 1e-6)


def _targets(data: bytes, pattern, base: int) -> set[int]:
    out = set()
    for m in pattern.finditer(data):
        raw = next(g for g in m.groups() if g is not None)
        a = int.from_bytes(raw, 'big') - base
        if 0 <= a < len(data):
            out.add(a)
    return out


def m68k_targets(data: bytes, base: int) -> set[int]:
    """Targets of 32-bit absolute operands following a 68k opcode word.

    Source or destination mode 7/1 (abs.L) or source mode 7/4 (#imm.L) in the
    opcode word, then the 32-bit big-endian operand. Opcodes sit on even offsets.
    """
    v = np.frombuffer(data[:len(data) // 2 * 2], '>u2').astype(np.int64)
    if len(v) < 3:
        return set()
    op, val = v[:-2], (v[1:-1] << 16) | v[2:]
    sel = ((op & 0x3F) == 0x39) | ((op & 0x3F) == 0x3C) | (((op >> 6) & 0x3F) == 0x0F)
    t = val[sel] - base
    return set(t[(t >= 0) & (t < len(data))].tolist())


def _m68k_guess(data: bytes, mask: np.ndarray, baseline: float):
    best = None
    for base in M68K_BASES:
        targets = m68k_targets(data, base)
        # Real code addresses thousands of objects; a few hundred chance
        # matches in megabytes of other code (PowerPC) are not enough.
        if len(targets) < max(M68K_MIN_TARGETS, len(data) // 1024):
            continue
        in_data = float(np.mean([mask[a] for a in targets]))
        guess = CpuGuess('68k', base, len(targets), round(in_data, 3), round(baseline, 3))
        if in_data >= MIN_IN_DATA and guess.enrichment >= MIN_ENRICHMENT and                 (best is None or guess.targets > best[0].targets):
            best = (guess, {a for a in targets if mask[a]})
    return best


def detect_cpu(data: bytes, mask: np.ndarray | None = None) -> tuple[CpuGuess | None, set[int]]:
    """Best (family, base) with clear enrichment, and its in-data target addresses."""
    if len(data) > M68K_MAX_SIZE:
        return None, set()
    mask = data_mask(data) if mask is None else mask
    baseline = float(mask.mean())
    if baseline <= 0 or baseline > .8:
        return None, set()      # no code to analyse (pure data EPROM) or no data
    if len(data) > 256 * 1024:
        # 8/16-bit families have a 64 KB address space; only 68k remains.
        return _m68k_guess(data, mask, baseline) or (None, set())
    best = None
    size = len(data)
    bases = sorted({0, 0x2000, 0x4000, 0x8000, 0xC000, 0xE000, max(0, 0x10000 - size)})
    reset = int.from_bytes(data[-2:], 'big')
    top = 0x10000 - size
    top_consistent = 0 <= top <= reset < 0x10000
    for family, (pattern,) in FAMILIES.items():
        for base in bases:
            # HC11 keeps its reset vector in the last word of the address space:
            # if it points into a top-mapped image, that mapping is the only one.
            if family == 'HC11' and (base == top) != top_consistent:
                continue
            targets = _targets(data, pattern, base)
            if len(targets) < MIN_TARGETS:
                continue
            in_data = float(np.mean([mask[a] for a in targets]))
            guess = CpuGuess(family, base, len(targets), round(in_data, 3), round(baseline, 3))
            if in_data >= MIN_IN_DATA and guess.enrichment >= MIN_ENRICHMENT and \
                    (best is None or (guess.enrichment, guess.targets) > (best[0].enrichment, best[0].targets)):
                best = (guess, {a for a in targets if mask[a]})
    return best if best else (None, set())
