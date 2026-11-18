"""Side-by-side readings of a table whose data type is not established (1.21.0).

For each open question (value width, sign, byte order) the same bytes are read in every
remaining type, so a tuner sees what each reading would mean before editing. Only raw
values are shown (minimum, maximum, cell count): no score and no probability. The chosen
reading comes first.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .confidence import BYTE_ORDER, SIGN, WIDTH, type_doubts
from .model import BinaryImage, MapDefinition


@dataclass(frozen=True)
class Reading:
    dtype: str
    endian: str
    cells: int
    low: float
    high: float
    chosen: bool

    def describe(self) -> str:
        order = f' {self.endian}' if self.dtype[1:] != '8' else ''
        mark = ' (gewählt)' if self.chosen else ''
        return f'{self.dtype}{order}: {self.low:g} … {self.high:g}{mark}'


def _values(image: BinaryImage, offset: int, cells: int, dtype: str, endian: str):
    width = int(dtype[1:]) // 8
    raw = image.read(offset, cells * width)
    if len(raw) < cells * width or not cells:
        return None
    kind = {'u': 'u', 's': 'i', 'f': 'f'}[dtype[0]]
    return np.frombuffer(raw, ('>' if endian == 'big' else '<') + kind + str(width))


def readings(image: BinaryImage, m: MapDefinition) -> list[Reading]:
    """The chosen reading and every alternative the open questions of ``m`` leave (empty when none is open)."""
    keys = {key for key, _ in type_doubts(m)}
    if not keys & {WIDTH, SIGN, BYTE_ORDER}:
        return []
    cells = m.rows * m.cols
    options = [(m.dtype, m.endian)]
    if SIGN in keys:
        options += [(d, m.endian) for d in m.dtype_alternatives]
    if BYTE_ORDER in keys:
        other = 'little' if m.endian == 'big' else 'big'
        options += [(d, other) for d, _ in list(options)]
    if WIDTH in keys and m.dtype[1:] == '16':
        options += [(m.dtype[0] + '8', 'big')]
    out, seen = [], set()
    for dtype, endian in options:
        key = (dtype, endian if dtype[1:] != '8' else '')
        if key in seen or dtype[1:] not in ('8', '16', '32'):
            continue
        seen.add(key)
        values = _values(image, m.offset, cells, dtype, endian)
        if values is None:
            continue
        out.append(Reading(dtype, endian, cells, float(values.min()), float(values.max()),
                           (dtype, endian) == (m.dtype, m.endian)))
    return out
