"""Code/data separation for images without a known calibration window.

Calibration data changes in small steps between neighbouring bytes or 16-bit
words; machine code does not. Measured per block on MS43/MS42 with XDF
coverage as reference: data blocks have >= .36 close 16-bit neighbours (10th
percentile), code blocks <= .22 (90th percentile). Geometry hint only.
"""
from __future__ import annotations
import numpy as np

CLOSE = 8            # neighbour difference that still counts as "small"
DATA_SMOOTHNESS = .30


def block_size(size: int) -> int:
    # Small blocks keep tables that sit between code routines in small images.
    return 128 if size <= 64 * 1024 else 256


def data_mask(data: bytes, block: int | None = None) -> np.ndarray:
    """Per-byte boolean: True inside blocks that look like calibration data."""
    b = np.frombuffer(data, np.uint8).astype(np.int16)
    block = block or block_size(len(b))
    mask = np.zeros(len(b), bool)
    for s in range(0, len(b), block):
        blk = b[s:s + block]
        if len(blk) < 8 or np.all(blk == blk[0]):
            continue
        d1 = (np.abs(np.diff(blk)) <= CLOSE).mean()
        d2 = (np.abs(blk[2:] - blk[:-2]) <= CLOSE).mean()
        mask[s:s + block] = max(d1, d2) >= DATA_SMOOTHNESS
    return mask


def data_fraction(mask: np.ndarray, start: int, end: int) -> float:
    part = mask[max(0, start):max(0, end)]
    return float(part.mean()) if len(part) else 0.


def data_regions(mask: np.ndarray, *, gap: int = 0) -> list[tuple[int, int]]:
    """Contiguous [start, end) runs of data-like bytes; runs closer than gap merge."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    runs = list(zip(edges[0::2].tolist(), edges[1::2].tolist()))
    merged = []
    for s, e in runs:
        if merged and s - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged
