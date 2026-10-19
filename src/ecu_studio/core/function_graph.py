"""Map function graph: which tables are read by the same code routine or share axes.

Routines are approximated by the span between two C16x return instructions
(RET/RETS/RETI). A table referenced inside a routine belongs to that routine's
group. Return opcodes can also occur as operand bytes, so a group boundary is a
structural hint, not a disassembly-proven function boundary.
"""
from __future__ import annotations
import bisect
import re
from dataclasses import dataclass, field
from .model import BinaryImage, MapDefinition
from .structure_scan import c16x_reference_positions

_RETURN = re.compile(rb"\xCB\x00|\xDB\x00|\xFB\x88")


@dataclass
class FunctionGroup:
    routine_start: int
    routine_end: int
    members: list[int] = field(default_factory=list)      # indices into the map list

    @property
    def size(self) -> int:
        return len(self.members)


def _axes_key(m: MapDefinition):
    return (tuple(m.axes_x), tuple(m.axes_y)) if m.axes_x else None


def build_function_graph(image: BinaryImage, maps: list[MapDefinition], lo: int = 0,
                         hi: int | None = None) -> dict:
    """Groups by consuming routine plus shared-axis relations, for C16x images."""
    data = image.read(0, image.size)
    hi = image.size if hi is None else hi
    refs = c16x_reference_positions(data, lo, hi)
    returns = [m.start() for m in _RETURN.finditer(data)]
    by_routine: dict[int, FunctionGroup] = {}
    for i, m in enumerate(maps):
        for pos in refs.get(m.offset, ()):
            k = bisect.bisect_right(returns, pos)
            start = returns[k - 1] + 2 if k else 0
            end = returns[k] if k < len(returns) else len(data)
            group = by_routine.setdefault(start, FunctionGroup(start, end))
            if i not in group.members:
                group.members.append(i)
    groups = sorted((g for g in by_routine.values() if g.size >= 2), key=lambda g: (-g.size, g.routine_start))
    shared: dict[tuple, list[int]] = {}
    for i, m in enumerate(maps):
        key = _axes_key(m)
        if key and min(m.rows, m.cols) > 1:
            shared.setdefault(key, []).append(i)
    axis_groups = [members for members in shared.values() if len(members) >= 2]
    return {'groups': groups, 'shared_axes': axis_groups, 'referenced': sum(1 for m in maps if m.offset in refs)}


def related_maps(graph: dict, index: int) -> dict[str, list[int]]:
    """Indices related to one map: same routine, same axes."""
    same_routine = sorted({j for g in graph['groups'] if index in g.members for j in g.members} - {index})
    same_axes = sorted({j for members in graph['shared_axes'] if index in members for j in members} - {index})
    return {'routine': same_routine, 'axes': same_axes}
