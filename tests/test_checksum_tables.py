"""Self-describing checksum tables (start, end, value, ~value): proven on the original, then corrected."""
import zlib
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.checksum_tables import (find_checksum_tables, check_tables, plan_table_correction,
                                             apply_table_correction, ChecksumBlock)
from ecu_studio.core.checksum_audit import audit_export

BASE = 0x800000          # ME7-style address space
TABLE = 0x3F00


def _sum_words(chunk: bytes) -> int:
    return int(np.frombuffer(chunk, '<u2').sum(dtype=np.uint64)) & 0xFFFFFFFF


def _record(start, end, value):
    return b''.join(int(x).to_bytes(4, 'little') for x in (start + BASE, end + BASE, value, ~value & 0xFFFFFFFF))


def _image():
    data = bytearray(np.random.default_rng(3).integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    ranges = [(0x0000, 0x0FFF), (0x1000, 0x1FFF), (0x2000, 0x3FFF)]   # last one covers the table itself
    for k, (a, b) in enumerate(ranges[:2]):
        data[TABLE + 16 * k:TABLE + 16 * k + 16] = _record(a, b, _sum_words(bytes(data[a:b + 1])))
    a, b = ranges[2]
    data[TABLE + 32:TABLE + 48] = _record(a, b, 0)                      # placeholder, then the real value
    data[TABLE + 32:TABLE + 48] = _record(a, b, _sum_words(bytes(data[a:b + 1])))
    return BinaryImage(bytes(data))


def test_tables_are_found_and_proven():
    blocks = find_checksum_tables(_image().original)
    assert [(b.start, b.end, b.algorithm, b.base) for b in blocks] == [
        (0x0000, 0x0FFF, 'sum32-words-le', BASE), (0x1000, 0x1FFF, 'sum32-words-le', BASE),
        (0x2000, 0x3FFF, 'sum32-words-le', BASE)]
    assert check_tables(_image())['status'] == 'match'


def test_edit_is_detected_and_corrected_including_self_covering_block():
    image = _image()
    image.write(0x0100, b'\x12\x34')        # inside block 1
    image.write(0x2100, b'\x56')            # inside the self-covering block 3
    state = check_tables(image)
    assert state['mismatches'] == 2
    steps = plan_table_correction(image)
    assert {o for o, _, _ in steps} == {TABLE + 8, TABLE + 40}
    result = apply_table_correction(image, steps)
    assert result['mismatches'] == 0 and result['blocks'] == 3
    image.undo()                             # writes stay undoable
    assert audit_export(image, [])['checksum_tables']['mismatches'] >= 1


def test_stale_plan_is_refused():
    image = _image(); image.write(0x0100, b'\x01')
    steps = plan_table_correction(image)
    image.write(0x1100, b'\x02')
    with pytest.raises(ValueError, match='geändert'):
        apply_table_correction(image, steps)


def test_random_data_and_unproven_records_are_ignored():
    rnd = np.random.default_rng(8).integers(0, 256, 1 << 20, dtype=np.uint8).tobytes()
    assert find_checksum_tables(rnd) == []
    data = bytearray(_image().original)
    data[TABLE + 8] ^= 1; data[TABLE + 12] ^= 1                     # value/complement still paired, but wrong
    blocks = find_checksum_tables(bytes(data))
    assert blocks[0].algorithm == 'unbekannt' and not blocks[0].verified
    assert check_tables(BinaryImage(bytes(data)))['blocks'] == 2      # only proven blocks are handled


def test_crc_block_covering_itself_is_not_corrected():
    blk = ChecksumBlock(record=0x10, start=0, end=0x40, stored=0, endian='little', base=0, algorithm='crc32-ieee')
    from ecu_studio.core.checksum_tables import _unsolvable
    assert _unsolvable(blk) and not _unsolvable(ChecksumBlock(0x10, 0, 0x40, 0, 'little', 0, 'sum32-words-le'))
