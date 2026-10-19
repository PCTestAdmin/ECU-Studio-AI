"""Bounded raw-file 2D samples, independent of map definitions.

No attempt to identify ECU semantics. All returned addresses are file offsets.
Samples are sampled per window, not across the entire file, so a large BIN
never requires a multi-million point render or allocation.
"""
from __future__ import annotations

import struct

try:
    import numpy as np
except ImportError:  # Core tests can still run without NumPy.
    np = None
from dataclasses import dataclass

from .model import BinaryImage, FORMATS


@dataclass(frozen=True)
class RawTrace:
    start: int
    end: int  # exclusive, byte position
    width: int
    dtype: str
    points: tuple[tuple[int, int], ...]  # (byte-offset, signed/unsigned raw value)
    low: int
    high: int


def raw_trace(image: BinaryImage, start: int = 0, count: int = 2048,
              dtype: str = 'u16', endian: str = 'big', max_points: int = 2400) -> RawTrace:
    if dtype not in FORMATS or dtype == 'f32':
        raise ValueError('Datentyp nicht unterstützt')
    if endian not in ('big', 'little'):
        raise ValueError('Bytefolge muss big oder little sein')
    if count < 1 or count > 65536 or max_points < 4:
        raise ValueError('Ungültige Fenstergröße')
    code, width, _, _ = FORMATS[dtype]
    complete = image.size // width
    if not complete:
        return RawTrace(0, 0, width, dtype, (), 0, 0)
    # Enforce word alignment and a full sample at EOF.
    start = max(0, min(int(start) // width, complete - 1)) * width
    n = min(count, complete - start // width)
    payload = image.read(start, n * width)
    fmt = ('>' if endian == 'big' else '<') + code
    if np is not None:
        np_dtype = np.dtype(('>' if endian == 'big' else '<') + {'B':'u1','b':'i1','H':'u2','h':'i2','I':'u4','i':'i4'}[code])
        values = np.frombuffer(payload, dtype=np_dtype)
        lo, hi = int(values.min()), int(values.max())
    else:
        values = [v[0] for v in struct.iter_unpack(fmt, payload)]
        lo, hi = min(values), max(values)
    # Preserve low/high spikes within buckets (a naive n-th sample loses maps).
    if n <= max_points:
        indices = list(range(n))
    else:
        bucket = max(1, (n + max(1, max_points // 2) - 1) // max(1, max_points // 2))
        if np is not None:
            # One vectorized min/max pass: no Python-level loop over ~1200
            # buckets for each scrollbar movement. Preserve extrema and order.
            extra = (-n) % bucket
            padded = np.pad(values, (0, extra), mode='edge') if extra else values
            blocks = padded.reshape(-1, bucket)
            base = np.arange(blocks.shape[0], dtype=np.int64) * bucket
            lowest = base + blocks.argmin(axis=1)
            highest = base + blocks.argmax(axis=1)
            indices = np.sort(np.unique(np.concatenate((lowest, highest, np.array([0, n-1])))))
            indices = indices[indices < n].tolist()
        else:
            indices = []
            for left in range(0, n, bucket):
                right = min(n, left + bucket)
                section = values[left:right]
                minimum = left + section.index(min(section))
                maximum = left + section.index(max(section))
                indices.extend(sorted(set((minimum, maximum))))
        if indices[0] != 0:
            indices.insert(0, 0)
        if indices[-1] != n-1:
            indices.append(n-1)
    points = tuple((start + i * width, values[i]) for i in indices)
    return RawTrace(start, start + n * width, width, dtype, points, lo, hi)
