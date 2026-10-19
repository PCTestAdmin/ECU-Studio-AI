"""Plot coordinate helpers: preserve non-uniform XDF/A2L axis spacing."""
from __future__ import annotations
import math


def sampled_axis_positions(axis: list[float], total: int, step: int) -> tuple[list[float], bool]:
    """Normalized 0..1 coordinates for the same sampled cells as MapTableModel.

    If XDF/A2L axis data is incomplete or degenerate, return index positions
    with a flag so callers never claim physical axis spacing was applied.
    """
    if total <= 0 or step <= 0:
        raise ValueError('Ungültige Achsendimension')
    indices=list(range(0,total,step))
    fallback=[i/max(1,len(indices)-1) for i in range(len(indices))]
    if len(axis)!=total or not all(math.isfinite(x) for x in axis):
        return fallback, False
    vals=[axis[i] for i in indices]
    if len(vals)<2 or vals[-1] <= vals[0] or any(vals[i+1]<vals[i] for i in range(len(vals)-1)):
        return fallback, False
    span=vals[-1]-vals[0]
    return [(x-vals[0])/span for x in vals], True
