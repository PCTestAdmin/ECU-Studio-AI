"""Numeric features of a table candidate, shared by training and inference.

Only geometry and value statistics of the candidate bytes and their immediate
surroundings; no names, no firmware identity. The same function feeds the
trainer (tools/train_candidate_model.py) and the scorer (core/candidate_model.py).
"""
from __future__ import annotations
import numpy as np
from .model import BinaryImage, MapDefinition

FEATURES = ('log_cells', 'rows', 'cols', 'width', 'signed', 'little', 'h', 'v', 'tail', 'period',
            'unique', 'span_rel', 'zero_frac', 'max_frac', 'mean_rel', 'monotone_rows',
            'edge_before', 'edge_after', 'align16', 'data_frac')


def _robust_span(a: np.ndarray) -> float:
    flat = np.sort(a.ravel())
    k = max(1, len(flat) // 20)
    s = float(flat[-1 - k] - flat[k]) if len(flat) > 2 * k else 0.
    return s if s > 0 else float(flat[-1] - flat[0])


def candidate_features(image: BinaryImage, m: MapDefinition, data_mask=None) -> list[float] | None:
    try:
        a = image.matrix(m).astype(np.float64)
    except (ValueError, IndexError):
        return None
    if a.ndim != 2 or a.size < 4:
        return None
    rows, cols = a.shape
    width = m.width
    maxv = float(2 ** (8 * width) - 1)
    s = _robust_span(a) or 1.
    h = float(np.abs(np.diff(a, axis=1)).mean() / s) if cols > 1 else 1.
    v = float(np.abs(np.diff(a, axis=0)).mean() / s) if rows > 1 else 1.
    diffs = np.concatenate([np.abs(np.diff(a, axis=1)).ravel(), np.abs(np.diff(a, axis=0)).ravel()])
    tail = float(np.percentile(diffs, 90) / s) if diffs.size else 1.
    flat_step = float(np.abs(np.diff(a.ravel())).mean()) or 1.
    period = float(np.abs(np.diff(a, axis=0)).mean() / flat_step) if rows > 1 else 1.
    row_d = np.diff(a, axis=1)
    monotone = float(np.mean(np.all(row_d >= 0, axis=1) | np.all(row_d <= 0, axis=1))) if cols > 1 else 0.

    def edge(offset):
        """Mismatch of the neighbouring row-length run against the first/last row (0 = continues smoothly)."""
        n = cols * width
        if offset < 0 or offset + n > image.size:
            return 1.
        other = MapDefinition('edge', offset, 1, cols, dtype=m.dtype, endian=m.endian)
        try:
            b = image.matrix(other).astype(np.float64).ravel()
        except (ValueError, IndexError):
            return 1.
        ref = a[0] if offset < m.offset else a[-1]
        return float(min(1., np.abs(b - ref).mean() / s))

    data_frac = float(data_mask[m.offset:m.offset + m.length].mean()) if data_mask is not None else 1.
    return [float(np.log2(a.size)), float(rows), float(cols), float(width), float(m.dtype.startswith('s')),
            float(m.endian == 'little'), h, v, tail, period,
            float(len(np.unique(a)) / a.size), float(min(1., (a.max() - a.min()) / maxv)),
            float((a == 0).mean()), float((a == maxv).mean()), float(a.mean() / maxv), monotone,
            edge(m.offset - cols * width), edge(m.offset + m.length), float(m.offset % 16 == 0), data_frac]
