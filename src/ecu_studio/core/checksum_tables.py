"""Self-describing checksum tables: records of (start, end, value, ~value).

Bosch ME7.x, MED9/ME9 and EDC17 store checksum blocks as four 32-bit words:
first and last address of the covered range, the checksum and its bitwise
complement. The (value, ~value) pair alone matches by chance with a probability
of 2^-32 per position. A record only counts as *verified* when one algorithm,
computed over the stated range of the UNMODIFIED file, reproduces the stored
value exactly. Nothing is assumed per family: base address (where the image
sits in the ECU address space), byte order and algorithm are tried and must be
proven by the file itself.

Algorithms are generic sums and CRC32 (no proprietary or RSA schemes); a block
that no algorithm reproduces stays "unbekannt" and is reported, not guessed.
"""
from __future__ import annotations
import zlib
from dataclasses import dataclass, asdict
import numpy as np

BASES = (0, 0x800000, 0x80000000, 0xA0000000, 0x400000, 0x1000000)
MAX_RECORDS = 400


@dataclass
class ChecksumBlock:
    record: int          # file offset of the 16-byte record
    start: int           # file offset of the first covered byte
    end: int             # file offset of the last covered byte (inclusive)
    stored: int
    endian: str
    base: int
    algorithm: str       # verified algorithm, or 'unbekannt'

    @property
    def verified(self) -> bool:
        return self.algorithm != 'unbekannt'

    def asdict(self) -> dict:
        return asdict(self)


def _algorithms(chunk: bytes):
    """(name, value) of the generic algorithms over one range (32-bit results)."""
    b = np.frombuffer(chunk, np.uint8)
    yield 'sum32-bytes', int(b.sum(dtype=np.uint64)) & 0xFFFFFFFF
    if len(chunk) % 2 == 0:
        yield 'sum32-words-le', int(np.frombuffer(chunk, '<u2').sum(dtype=np.uint64)) & 0xFFFFFFFF
        yield 'sum32-words-be', int(np.frombuffer(chunk, '>u2').sum(dtype=np.uint64)) & 0xFFFFFFFF
    if len(chunk) % 4 == 0:
        yield 'sum32-dwords-le', int(np.frombuffer(chunk, '<u4').sum(dtype=np.uint64)) & 0xFFFFFFFF
        yield 'sum32-dwords-be', int(np.frombuffer(chunk, '>u4').sum(dtype=np.uint64)) & 0xFFFFFFFF
    yield 'crc32-ieee', zlib.crc32(chunk) & 0xFFFFFFFF


def compute(data: bytes, block: ChecksumBlock, algorithm: str | None = None) -> int | None:
    """Value of the block's (or the given) algorithm over its range in ``data``."""
    name = algorithm or block.algorithm
    for alg, value in _algorithms(data[block.start:block.end + 1]):
        if alg == name:
            return value
    return None


def find_checksum_tables(data: bytes) -> list[ChecksumBlock]:
    """All (start, end, value, ~value) records in ``data``, each tested against the generic algorithms."""
    n = len(data)
    out, seen = [], set()
    for endian, fmt in (('little', '<u4'), ('big', '>u4')):
        for phase in (0, 2):
            v = np.frombuffer(data[phase:phase + (n - phase) // 4 * 4], fmt).astype(np.int64)
            if len(v) < 4:
                continue
            idx = np.flatnonzero((v[3:] ^ v[2:-1]) == 0xFFFFFFFF)   # value at i+2, complement at i+3
            for i in idx.tolist():
                s, e, c = int(v[i]), int(v[i + 1]), int(v[i + 2])
                if c in (0, 0xFFFFFFFF) or e <= s or e - s > n:
                    continue
                record = phase + 4 * i
                for base in BASES:
                    a, b = s - base, e - base
                    if a < 0 or b >= n:
                        continue
                    key = (record, a, b)
                    if key in seen:
                        break
                    seen.add(key)
                    alg = next((name for name, value in _algorithms(data[a:b + 1]) if value == c), 'unbekannt')
                    out.append(ChecksumBlock(record, a, b, c, endian, base, alg))
                    break
                if len(out) >= MAX_RECORDS:
                    return out
    return sorted(out, key=lambda blk: blk.record)


MAX_PASSES = 6     # chained blocks (a table inside another block) settle within a few passes


def _self_covering(block: ChecksumBlock) -> bool:
    """The block's own stored value lies inside its range.

    For sums this is harmless: value and ~value add up to a constant in every
    word/byte, so the sum does not depend on them (seen on ME7.x, MED9, ME9).
    For CRC there is no unique correction.
    """
    return block.start <= block.record + 15 and block.record + 8 <= block.end


def _unsolvable(block: ChecksumBlock) -> bool:
    return _self_covering(block) and not block.algorithm.startswith('sum')


def original_blocks(image) -> list[ChecksumBlock]:
    """Blocks found and VERIFIED on the unmodified original of ``image``."""
    return [b for b in find_checksum_tables(image.original) if b.verified]


def _fields(block: ChecksumBlock, value: int) -> bytes:
    return value.to_bytes(4, block.endian) + (~value & 0xFFFFFFFF).to_bytes(4, block.endian)


def check_tables(image) -> dict:
    """Current state of every block that the original proves: match / mismatch per block."""
    blocks = original_blocks(image)
    data = image.read(0, image.size)
    rows = []
    for b in blocks:
        expected = compute(data, b)
        stored = data[b.record + 8:b.record + 16]
        rows.append({'record': b.record, 'start': b.start, 'end': b.end, 'algorithm': b.algorithm,
                     'match': stored == _fields(b, expected), 'self_covering': _self_covering(b)})
    bad = [r for r in rows if not r['match']]
    return {'blocks': len(rows), 'mismatches': len(bad), 'rows': rows,
            'status': 'none' if not rows else 'match' if not bad else 'mismatch'}


def plan_table_correction(image) -> list[tuple[int, bytes, bytes]]:
    """(offset, old 8 bytes, new 8 bytes) that make every proven block match again.

    Refused (ValueError) if a changed block covers its own stored value or the
    blocks do not settle; nothing is written here.
    """
    blocks = original_blocks(image)
    if not blocks:
        raise ValueError('Keine am Original bestätigten Prüfsummen-Tabellen in dieser Datei')
    data = bytearray(image.read(0, image.size))
    start = bytes(data)
    for _ in range(MAX_PASSES):
        changed = False
        for b in blocks:
            new = _fields(b, compute(bytes(data), b))
            if bytes(data[b.record + 8:b.record + 16]) != new:
                if _unsolvable(b):
                    raise ValueError(f'Block @ 0x{b.record:X} deckt seinen eigenen CRC ab – keine eindeutige Korrektur')
                data[b.record + 8:b.record + 16] = new
                changed = True
        if not changed:
            break
    else:
        raise ValueError('Prüfsummen-Tabellen kommen nicht zur Ruhe – Korrektur verweigert')
    return [(b.record + 8, start[b.record + 8:b.record + 16], bytes(data[b.record + 8:b.record + 16]))
            for b in blocks if start[b.record + 8:b.record + 16] != bytes(data[b.record + 8:b.record + 16])]


def apply_table_correction(image, steps) -> dict:
    """Write a plan from plan_table_correction, verify, roll back on any mismatch."""
    if [(o, n) for o, _, n in plan_table_correction(image)] != [(o, n) for o, _, n in steps]:
        raise ValueError('Datei hat sich seit der Planung geändert – bitte neu planen')
    for offset, _, new in steps:
        image.write(offset, new)
    result = check_tables(image)
    if result['mismatches']:
        for offset, old, _ in steps:
            image.write(offset, old)
        raise ValueError('Nach der Korrektur stimmen nicht alle Blöcke – zurückgesetzt')
    return result
