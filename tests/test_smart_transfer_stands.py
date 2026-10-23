"""Independent layout matrix for smart transfer.

These fixtures represent several software-stand layouts with hand-calculated
raw expectations.  They are deliberately synthetic: passing this matrix does
not establish OEM or cross-family accuracy.
"""
from dataclasses import dataclass
import struct

import pytest

from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.smart_transfer import FirmwareIdentity, apply_transfer, plan_transfer


@dataclass(frozen=True)
class StandCase:
    source_dtype: str
    source_endian: str
    source_factor: float
    source_bias: float
    target_dtype: str
    target_endian: str
    target_factor: float
    target_bias: float
    changed_cell: tuple[int, int]
    source_before: int
    source_after: int
    target_before: int
    target_after: int


CASES = (
    # 200 -> 220 at factor .5 is a +10 physical delta; target 400 at
    # factor .25/bias 10 therefore becomes 440.
    StandCase('u16', 'big', .5, 0, 'u16', 'little', .25, 10, (0, 1), 200, 220, 400, 440),
    # 20 -> 25 at factor 2 is +10; target 10 at bias 50 becomes raw 20.
    StandCase('s16', 'little', 2, -100, 's16', 'big', 1, 50, (1, 2), 20, 25, 10, 20),
    # 40 -> 46 at factor .5/bias 5 is +3; target 100 becomes 103.
    StandCase('u8', 'big', .5, 5, 'u8', 'little', 1, 0, (0, 2), 40, 46, 100, 103),
)


def _map(name, offset, *, dtype, endian, factor, bias):
    return MapDefinition(name, offset, 2, 3, dtype, endian, factor, bias,
                         unit='bar', kind='boost', verified=True,
                         axes_x=[1000, 2000, 3000], axes_y=[10, 20],
                         axis_x_unit='rpm', axis_y_unit='%')


def _fixture(case: StandCase):
    source_map = _map('Boost', 32, dtype=case.source_dtype, endian=case.source_endian,
                      factor=case.source_factor, bias=case.source_bias)
    target_map = _map('Boost', 173, dtype=case.target_dtype, endian=case.target_endian,
                      factor=case.target_factor, bias=case.target_bias)
    source_raw = bytearray([0xA5] * 512)
    target_raw = bytearray([0x5A] * 512)
    source_fmt = ('>' if source_map.endian == 'big' else '<') + {'u8': 'B', 'u16': 'H', 's16': 'h'}[source_map.dtype]
    target_fmt = ('>' if target_map.endian == 'big' else '<') + {'u8': 'B', 'u16': 'H', 's16': 'h'}[target_map.dtype]
    source_values = [case.source_before] * 6
    target_values = [case.target_before] * 6
    r, c = case.changed_cell
    source_values[r * 3 + c] = case.source_before
    for i, value in enumerate(source_values):
        struct.pack_into(source_fmt, source_raw, source_map.offset + i * source_map.width, value)
    for i, value in enumerate(target_values):
        struct.pack_into(target_fmt, target_raw, target_map.offset + i * target_map.width, value)
    source = BinaryImage(source_raw)
    target = BinaryImage(target_raw)
    source.write_physical(source_map, r, c,
                          source_map.scale_raw(case.source_after))
    return source, target, source_map, target_map, target_fmt


def _identity(image, software):
    return FirmwareIdentity(image.digest, 'synthetic-family', 'synthetic-hardware', software,
                            'independent layout matrix', True)


@pytest.mark.parametrize('case', CASES)
def test_transfer_matrix_uses_target_encoding_and_one_undo(case):
    source, target, source_map, target_map, target_fmt = _fixture(case)
    before = target.materialize()
    plan = plan_transfer(source, target, [source_map], [target_map], links={0: 0},
                         source_identity=_identity(source, 'stand-A'),
                         target_identity=_identity(target, 'stand-B'))
    assert plan.maps[0].status == 'ready'
    assert len(plan.maps[0].cells) == 1
    cell = plan.maps[0].cells[0]
    assert (cell.row, cell.col) == case.changed_cell
    assert cell.after == struct.pack(target_fmt, case.target_after)
    apply_transfer(target, plan, [0], confirmed=True)
    assert target.raw_value(target_map, *case.changed_cell) == case.target_after
    assert target.read(0, target_map.offset) == before[:target_map.offset]
    assert target.undo() and target.materialize() == before


@pytest.mark.parametrize('case', CASES)
def test_transfer_matrix_rejects_unreviewed_target_without_writes(case):
    source, target, source_map, target_map, _ = _fixture(case)
    before = target.materialize()
    target_map.verified = False
    plan = plan_transfer(source, target, [source_map], [target_map], links={0: 0},
                         source_identity=_identity(source, 'stand-A'),
                         target_identity=_identity(target, 'stand-B'))
    assert plan.maps[0].status == 'conflict' and not plan.maps[0].cells
    with pytest.raises(ValueError):
        apply_transfer(target, plan, [0], confirmed=True)
    assert target.materialize() == before
