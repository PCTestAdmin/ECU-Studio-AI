"""Conservative Bosch EDC16 checksum blocks (MPC5xx).

EDC16U1/U31/U34-style files carry a descriptor before each protected region:
big-endian start/end addresses followed by ``FADECAFECAFEAFFE`` at
``region_start + 0x3c``.  The protected region is a big-endian dword sum whose
target is ``0xD01FE500``; its last dword is the compensation word.

This implementation is adapted from the GPL-3.0 ZedSuite EDC16 calculator and
is deliberately stricter than a family-name guess: every region must reproduce
the target on the unmodified original, all regions must be proven before a
correction is planned, and production correction additionally requires a
reviewed OEM record keyed to the exact original SHA-256.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .checksum_validation import validation_record

MAGIC = bytes.fromhex('FADECAFECAFEAFFE')
MAGIC_OFFSET = 0x3C
REGION_ALIGNMENT = 0x100
TARGET_SUM = 0xD01FE500
SCHEME = 'bosch-edc16'


@dataclass(frozen=True)
class Region:
    start: int
    end: int
    checksum_offset: int


@dataclass(frozen=True)
class RegionStatus:
    region: Region
    total: int
    stored: int
    expected: int
    valid: bool


def _u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from('>I', data, offset)[0]


def find_regions(data: bytes) -> list[Region]:
    """Find coherent EDC16 descriptors, rejecting accidental magic bytes."""
    out: list[Region] = []
    pos = 0
    while True:
        pos = data.find(MAGIC, pos)
        if pos < 8:
            if pos < 0:
                break
            pos += 1
            continue
        start_addr, end_addr = _u32be(data, pos - 8), _u32be(data, pos - 4)
        start = pos - MAGIC_OFFSET
        end = start + (end_addr - start_addr)
        if (0 <= start < end < len(data) and start % REGION_ALIGNMENT == 0 and
                (end + 1) % REGION_ALIGNMENT == 0 and (end + 1 - start) % 4 == 0):
            region = Region(start, end, end + 1 - 4)
            if region not in out:
                out.append(region)
        pos += 1
    return sorted(out, key=lambda r: (r.start, r.end))


def sum_region(data: bytes, region: Region) -> int:
    total = 0
    for pos in range(region.start, region.end + 1, 4):
        total = (total + _u32be(data, pos)) & 0xFFFFFFFF
    return total


def analyze(data: bytes) -> list[RegionStatus]:
    """Analyze all descriptors without modifying ``data``."""
    statuses = []
    for region in find_regions(data):
        total = sum_region(data, region)
        stored = _u32be(data, region.checksum_offset)
        expected = (stored + TARGET_SUM - total) & 0xFFFFFFFF
        statuses.append(RegionStatus(region, total, stored, expected, total == TARGET_SUM))
    return statuses


def verify(image) -> dict:
    """Verify descriptors against the immutable original bytes."""
    statuses = analyze(image.original)
    valid = sum(s.valid for s in statuses)
    total = len(statuses)
    coverage = 'full' if total and valid == total else 'partial' if valid else 'none'
    record = validation_record(image, SCHEME)
    return {
        'scheme': SCHEME, 'detected': bool(statuses), 'regions': total,
        'regions_total': total, 'proven_on_original': valid,
        'coverage': coverage, 'proven': coverage == 'full',
        'oem_validated': record is not None, 'oem_validation': record,
        'rows': [{'start': s.region.start, 'end': s.region.end,
                  'checksum_offset': s.region.checksum_offset, 'sum': s.total,
                  'stored': s.stored, 'expected': s.expected, 'match': s.valid}
                 for s in statuses],
    }


def check_current(image) -> dict:
    """Check current bytes, but only for regions proven on the original."""
    original = analyze(image.original)
    current = image.read(0, image.size)
    proven = [s for s in original if s.valid]
    mismatches = sum(sum_region(current, s.region) != TARGET_SUM for s in proven)
    total, checked = len(original), len(proven)
    coverage = 'full' if total and checked == total else 'partial' if checked else 'none'
    return {
        'regions': checked, 'regions_total': total,
        'regions_proven': checked, 'regions_unproven': total - checked,
        'mismatches': mismatches, 'coverage': coverage,
        'status': 'none' if not checked else 'match' if not mismatches else 'mismatch',
        'oem_validated': validation_record(image, SCHEME) is not None,
    }


def plan_correction(image, *, require_oem_validation: bool = True) -> list[tuple[int, bytes, bytes]]:
    """Plan compensation-word edits only after full and OEM-backed proof."""
    proof = verify(image)
    if not proof['detected'] or not proof['proven_on_original']:
        raise ValueError('Keine am Original bestätigten EDC16-Prüfsummenbereiche in dieser Datei')
    if proof['coverage'] != 'full':
        raise ValueError(f'EDC16-Korrektur verweigert: nur {proof["proven_on_original"]} von '
                         f'{proof["regions_total"]} Bereichen am Original bestätigt')
    if require_oem_validation and not proof['oem_validated']:
        raise ValueError('EDC16-Korrektur verweigert: kein geprüfter OEM-Nachweis für diese Originaldatei')
    data = bytearray(image.read(0, image.size))
    steps = []
    for status in analyze(image.original):
        if status.valid:
            current = sum_region(bytes(data), status.region)
            new = (status.stored + TARGET_SUM - current) & 0xFFFFFFFF
            old_bytes = bytes(data[status.region.checksum_offset:status.region.checksum_offset + 4])
            new_bytes = struct.pack('>I', new)
            if new_bytes != old_bytes:
                data[status.region.checksum_offset:status.region.checksum_offset + 4] = new_bytes
                steps.append((status.region.checksum_offset, old_bytes, new_bytes))
    return steps


def apply_correction(image, steps, *, require_oem_validation: bool = True) -> dict:
    fresh = plan_correction(image, require_oem_validation=require_oem_validation)
    if [(o, n) for o, _, n in fresh] != [(o, n) for o, _, n in steps]:
        raise ValueError('Datei hat sich seit der Planung geändert – bitte neu planen')
    changes = [(off + i, old[i], new[i]) for off, old, new in steps
               for i in range(4) if old[i] != new[i]]
    if not image.commit(changes, label='EDC16-Prüfsummenkorrektur'):
        return check_current(image)
    result = check_current(image)
    if result['mismatches']:
        image.undo()
        raise ValueError('Nach der EDC16-Korrektur stimmen nicht alle Bereiche – zurückgesetzt')
    return result
