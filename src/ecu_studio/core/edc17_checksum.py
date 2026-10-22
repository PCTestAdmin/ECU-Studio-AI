"""Bosch MED17 / EDC17 checksum blocks (Infineon TriCore).

MED17/EDC17 firmware stores its checksums in self-describing blocks. Every block
begins with a fixed 72-byte descriptor and carries 1..8 checksum *structures*;
each structure names the covered flash range, a seed and an expected value, and
one of three algorithms:

    0x00  CRC32   reflected CRC32 (poly 0xEDB88320), seed 0xFADECAFE, the stored
                  value is the *complement* of the computed CRC (0xCAFEAFFE ->
                  0x35015001)
    0x01  ADD32   sum of little-endian dwords + seed
    0x10  ADD16   sum of 16-bit words + seed, with the final word in the high half

The block itself is anchored by the 8-byte magic pair FADECAFE / CAFEAFFE at a
fixed distance from the block start (a 1-in-2^64 marker), so blocks are located
by searching for the pair, not guessed from a family list. Flash addresses are
translated to file offsets per block; the TriCore cached (0x8xxxxxxx) and
uncached (0xAxxxxxxx) aliases of the same physical flash are folded together.

This module is deliberately limited to *checksums*. It contains no code that
reads, writes, forges or removes cryptographic signatures or other ECU security
fields, and a correct checksum is never a flash release (see verify/plan below).

Algorithm structure is the openly documented Bosch block layout, cross-checked
against the MIT-licensed medc17-checksum-tool (Connor Howell). A block only
counts as *verified* when its stored value is reproduced on the UNMODIFIED
original file: nothing is asserted from the family name alone, and a file with
no reproduced block reports "nicht nachgewiesen", never a guess.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field, asdict

# --- block descriptor layout (little-endian, offsets from block start) -------
MAGIC_A = 0xFADECAFE                       # seed, at block_start + 0x40
MAGIC_B = 0xCAFEAFFE                       # expected, at block_start + 0x44
MAGIC_PAIR = struct.pack('<II', MAGIC_A, MAGIC_B)
MAGIC_OFFSET = 0x40                        # magic A sits this far into the block
HEADER_MIN = 0x40
STRUCT_SIZE = 32                           # one checksum structure
STRUCT_BASE = 0x34                         # first structure, from block start
COUNT_OFFSET = 0x2C                        # number of checksum structures (dword)
END_ADDR_OFFSET = 0x0C                     # block end flash address (dword)
SIZE_OFFSET = 0x04                         # block size (dword)
BLOCK_TERMINATOR = 0xDEADBEEF              # last dword of a block
MAX_STRUCTS = 8                            # the Bosch loader caps structures at 8

# block identifier (low byte) -> human name
BLOCK_NAMES = {
    0x10: 'Startup Block', 0x20: 'Tuning protection', 0x30: 'Customer Block',
    0x40: 'Application software #0', 0x50: 'Application software #1',
    0x60: 'Dataset #0', 0x70: 'Dataset #1', 0x80: 'Variant dataset',
    0x90: 'Customer Tuning protection', 0xA0: 'Application software #2',
    0xB0: 'Application software #3', 0xC0: 'Absolute constants #0',
    0xD0: 'Emulation extension chip', 0xE0: 'Customer specific',
    0xF0: 'Ramloader', 0xF1: 'Application Attestation',
}
# block class byte at block_start + 0x0F: application (cached) / data (uncached)
BLOCK_CLASSES = (0x80, 0xA0)
FLASH_SEGMENT_MASK = 0x0FFFFFFF            # offset within the 256 MB flash segment
ALGO_NAMES = {0x00: 'CRC32', 0x01: 'ADD32', 0x10: 'ADD16'}
BLANK_WORDS = (0xFFFFFFFF, 0xAFAFAFAF)     # reserved/unprogrammed partition fill


def _flash_canonical(addr: int) -> int:
    """Cached-segment form, so the 0x8/0xA aliases of one physical byte match."""
    return (addr & FLASH_SEGMENT_MASK) | 0x80000000


def _is_flash_addr(addr: int) -> bool:
    return 0x80000000 <= addr <= 0x8FFFFFFF or 0xA0000000 <= addr <= 0xAFFFFFFF


# --- checksum algorithms -----------------------------------------------------

def crc32_edc17(payload: bytes, seed: int = MAGIC_A) -> int:
    """Reflected CRC32 (poly 0xEDB88320) over little-endian dwords, LSB first.

    Matches the TriCore implementation: no final XOR. The stored field holds the
    bitwise complement of this value (a correct block gives 0x35015001, i.e.
    ~0xCAFEAFFE). Trailing bytes that do not fill a dword are ignored, exactly as
    the ECU processes whole dwords.
    """
    crc = seed & 0xFFFFFFFF
    for i in range(0, len(payload) - 3, 4):
        dword = payload[i] | (payload[i + 1] << 8) | (payload[i + 2] << 16) | (payload[i + 3] << 24)
        for _ in range(32):
            if (dword ^ crc) & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
            dword >>= 1
    return crc & 0xFFFFFFFF


def add32_edc17(payload: bytes, seed: int = MAGIC_A) -> int:
    """Sum of little-endian dwords plus the seed (overflow discarded)."""
    total = seed & 0xFFFFFFFF
    for i in range(0, len(payload) - 3, 4):
        total = (total + (payload[i] | (payload[i + 1] << 8) |
                          (payload[i + 2] << 16) | (payload[i + 3] << 24))) & 0xFFFFFFFF
    return total


def add16_edc17(payload: bytes, seed: int = MAGIC_A) -> int:
    """Sum of 16-bit little-endian words plus the seed; the final word lands in
    the high half (the ECU's documented tail behaviour), so the region's last
    dword contributes its full 32-bit value.
    """
    total = seed & 0xFFFFFFFF
    n = len(payload) - (len(payload) % 2)
    if n >= 2:
        for i in range(0, n - 2, 2):
            total = (total + (payload[i] | (payload[i + 1] << 8))) & 0xFFFFFFFF
        last = payload[n - 2] | (payload[n - 1] << 8)
        total = (total + (last << 16)) & 0xFFFFFFFF
    return total


_ALGO = {0x00: crc32_edc17, 0x01: add32_edc17, 0x10: add16_edc17}


# --- parsing -----------------------------------------------------------------

@dataclass
class ChecksumStructure:
    offset: int            # file offset of this 32-byte structure
    algorithm: int         # 0x00 / 0x01 / 0x10
    start_mem: int         # covered flash range (inclusive)
    end_mem: int
    seed: int
    expected: int          # stored expected value (complement for CRC32)
    start_file: int        # resolved file offsets (end inclusive)
    end_file: int
    in_bounds: bool = True  # covered range lies within the block it belongs to
    computed: int | None = None
    valid: bool | None = None  # None: algorithm/range not evaluable

    @property
    def algo_name(self) -> str:
        return ALGO_NAMES.get(self.algorithm, f'0x{self.algorithm:02X}')


@dataclass
class Block:
    bin_start: int
    size: int
    block_id: int
    name: str
    start_mem: int
    end_mem: int
    structures: list[ChecksumStructure] = field(default_factory=list)
    unprogrammed: bool = False

    def asdict(self) -> dict:
        d = asdict(self)
        d['structures'] = [asdict(s) for s in self.structures]
        return d


def _mem_to_file(mem_addr: int, block_start_mem: int, block_start_file: int) -> int:
    return _flash_canonical(mem_addr) - _flash_canonical(block_start_mem) + block_start_file


def _parse_block(data: bytes, hdr: int) -> Block | None:
    n = len(data)
    if hdr < 0 or hdr + HEADER_MIN > n:
        return None
    block_id = struct.unpack_from('<I', data, hdr)[0] & 0xFF
    if block_id not in BLOCK_NAMES:
        return None
    if data[hdr + 1] != 0 or data[hdr + 3] != 0 or data[hdr + 0x0F] not in BLOCK_CLASSES:
        return None
    size = struct.unpack_from('<I', data, hdr + SIZE_OFFSET)[0]
    if size < HEADER_MIN or hdr + size > n:
        return None
    if struct.unpack_from('<I', data, hdr + size - 4)[0] != BLOCK_TERMINATOR:
        return None
    end_mem = struct.unpack_from('<I', data, hdr + END_ADDR_OFFSET)[0]
    if not _is_flash_addr(end_mem):
        return None
    count = struct.unpack_from('<I', data, hdr + COUNT_OFFSET)[0]
    if not 1 <= count <= MAX_STRUCTS:
        return None
    start_mem = end_mem + 5 - size - 1
    if not _is_flash_addr(start_mem):
        return None
    block = Block(hdr, size, block_id, BLOCK_NAMES[block_id], start_mem, end_mem + 3)
    block_end_file = hdr + size - 1          # last byte that belongs to this block
    for i in range(count):
        so = hdr + STRUCT_BASE + i * STRUCT_SIZE
        if so + STRUCT_SIZE > n:
            break
        algo = struct.unpack_from('<H', data, so + 28)[0] & 0xFF
        cs_start = struct.unpack_from('<I', data, so + 4)[0]
        cs_end = struct.unpack_from('<I', data, so + 8)[0]
        sf = _mem_to_file(cs_start, start_mem, hdr)
        ef = _mem_to_file(cs_end, start_mem, hdr)
        # The covered range must lie wholly inside this block's own bytes and the
        # file. A structure whose addresses map elsewhere (corrupt or unusual
        # file) is kept but marked out of bounds, so it is reported as "not
        # verifiable" and never produces a misleading match or a write target.
        in_bounds = hdr <= sf <= ef <= block_end_file < n
        block.structures.append(ChecksumStructure(
            offset=so, algorithm=algo, start_mem=cs_start, end_mem=cs_end,
            seed=struct.unpack_from('<I', data, so + 12)[0],
            expected=struct.unpack_from('<I', data, so + 16)[0],
            start_file=sf, end_file=ef, in_bounds=in_bounds))
    final = struct.unpack_from('<I', data, hdr + STRUCT_BASE + count * STRUCT_SIZE)[0] \
        if hdr + STRUCT_BASE + count * STRUCT_SIZE + 4 <= n else 0
    adjust = struct.unpack_from('<I', data, hdr + 0x30)[0]
    block.unprogrammed = final in BLANK_WORDS and adjust in BLANK_WORDS
    return block


def find_blocks(data: bytes) -> list[Block]:
    """Every Bosch MED17/EDC17 checksum block, located by its magic signature."""
    out, pos = [], 0
    while True:
        pos = data.find(MAGIC_PAIR, pos)
        if pos < 0:
            break
        block = _parse_block(data, pos - MAGIC_OFFSET)
        pos += 1
        if block is not None:
            out.append(block)
    out.sort(key=lambda b: b.bin_start)
    return out


def _evaluate(data: bytes, cs: ChecksumStructure) -> None:
    """Fill cs.computed / cs.valid for the current bytes."""
    if (cs.algorithm not in _ALGO or not cs.in_bounds
            or not (0 <= cs.start_file < cs.end_file < len(data))):
        cs.computed, cs.valid = None, None
        return
    payload = data[cs.start_file:cs.end_file + 1]
    value = _ALGO[cs.algorithm](payload, cs.seed)
    cs.computed = value
    want = (~cs.expected) & 0xFFFFFFFF if cs.algorithm == 0x00 else cs.expected
    cs.valid = value == want


# --- verification ------------------------------------------------------------

def verify(image) -> dict:
    """Verify every Bosch block against the ORIGINAL bytes of ``image``.

    Only structures proven on the original are reported as the ECU's checksums;
    nothing is inferred from the family name. A block whose structures cannot be
    reproduced is listed as unproven, not corrected.
    """
    original = image.original
    blocks = find_blocks(original)
    rows, proven, total, unverifiable = [], 0, 0, 0
    for block in blocks:
        for cs in block.structures:
            _evaluate(original, cs)
        if not block.unprogrammed:
            for cs in block.structures:
                total += 1
                if cs.valid:
                    proven += 1
                elif cs.valid is None:
                    unverifiable += 1
        rows.append({'block': block.name, 'offset': block.bin_start,
                     'unprogrammed': block.unprogrammed,
                     'structures': [{'algorithm': cs.algo_name, 'start': cs.start_file,
                                     'end': cs.end_file, 'expected': cs.expected,
                                     'computed': cs.computed, 'in_bounds': cs.in_bounds,
                                     'match': cs.valid}
                                    for cs in block.structures]})
    # Coverage distinguishes fully proven, partially proven and nothing proven,
    # so "proven" never hides structures that were not (or could not be) checked.
    coverage = 'full' if total and proven == total else 'partial' if proven else 'none'
    return {'scheme': 'bosch-med17-edc17',
            'blocks': len(blocks),
            'structures_total': total,
            'checkable': proven,                 # proven on the original
            'proven_on_original': proven,
            'unverifiable': unverifiable,        # structures whose range is out of bounds / unusable
            'coverage': coverage,
            'detected': bool(blocks),
            'proven': coverage == 'full',
            'rows': rows}


def check_current(image) -> dict:
    """State of the proven blocks on the CURRENT bytes: match / mismatch.

    A block is considered the ECU's only if it verified on the original (proving
    algorithm, range and storage); edits are then detected against that proof.
    """
    original = image.original
    data = image.read(0, image.size)
    blocks = find_blocks(original)
    mismatches, checked, total = 0, 0, 0
    rows = []
    for block in blocks:
        if block.unprogrammed:
            continue
        for cs in block.structures:
            total += 1
            _evaluate(original, cs)
            if cs.valid:                       # proven on the original
                cur = ChecksumStructure(cs.offset, cs.algorithm, cs.start_mem, cs.end_mem,
                                        cs.seed, cs.expected, cs.start_file, cs.end_file, cs.in_bounds)
                _evaluate(data, cur)
                checked += 1
                if not cur.valid:
                    mismatches += 1
                rows.append({'block': block.name, 'offset': cs.offset, 'algorithm': cs.algo_name,
                             'start': cs.start_file, 'end': cs.end_file, 'match': bool(cur.valid)})
    unproven = total - checked
    # Coverage says how much of the file this method actually vouches for, so the
    # UI can distinguish "fully checked", "partially checked" and "not checkable"
    # instead of showing a bare match for a few structures.
    coverage = 'full' if checked and not unproven else 'partial' if checked else 'none'
    return {'blocks': checked, 'mismatches': mismatches, 'rows': rows,
            'structures_total': total, 'structures_proven': checked, 'structures_unproven': unproven,
            'coverage': coverage,
            'status': 'none' if not checked else 'match' if not mismatches else 'mismatch'}


# --- correction (arithmetic sum blocks only) ---------------------------------
# Only the additive algorithms (ADD32/ADD16) are corrected automatically, and
# only via the dedicated compensation dword at the end of the checksummed range
# — the documented Bosch adjust location. CRC32 blocks are verified but NOT
# auto-corrected here: a CRC32 block's compensation dword cannot be confirmed as
# a reserved (non-live) slot without a validated original, and application
# blocks additionally carry cryptographic signatures that this module never
# touches. Correcting such a block is refused rather than guessed.

CORRECTABLE = (0x01, 0x10)


def _compensation_offset(cs: ChecksumStructure) -> int:
    """File offset of the 4-byte compensation dword (end of the range, inclusive end)."""
    return cs.end_file - 3


def _overlaps_any_structure(data: bytes, blocks: list[Block], offset: int) -> bool:
    """True if ``offset`` (4 bytes) lies inside any checksum structure's own 32 bytes
    or a block descriptor field — writing there would corrupt metadata."""
    for block in blocks:
        for cs in block.structures:
            if cs.offset <= offset + 3 and offset < cs.offset + STRUCT_SIZE:
                return True
    return False


def plan_correction(image):
    """(offset, old 4 bytes, new 4 bytes) that restore every proven ADD block.

    Refused unless the blocks verify on the unmodified original. CRC32 blocks and
    unprogrammed partitions are skipped (and named in the returned notes), never
    written blindly. Nothing is written here.
    """
    original = image.original
    data = bytearray(image.read(0, image.size))
    blocks = find_blocks(original)
    for block in blocks:
        for cs in block.structures:
            _evaluate(original, cs)
    proven = [(b, cs) for b in blocks if not b.unprogrammed
              for cs in b.structures if cs.valid]
    if not proven:
        raise ValueError('Keine am Original bestätigten EDC17/MED17-Prüfsummenblöcke in dieser Datei')
    skipped_crc = [b.name for b, cs in proven if cs.algorithm == 0x00]
    steps = []
    for block, cs in proven:
        if cs.algorithm not in CORRECTABLE:
            continue
        target = cs.expected
        off = _compensation_offset(cs)
        if not (cs.start_file <= off and off + 3 <= cs.end_file):
            raise ValueError(f'{block.name}: Kompensationswort außerhalb des Prüfbereichs – Korrektur verweigert')
        if _overlaps_any_structure(original, blocks, off):
            raise ValueError(f'{block.name}: Kompensationswort läge in Metadaten – Korrektur verweigert')
        current = _ALGO[cs.algorithm](bytes(data[cs.start_file:cs.end_file + 1]), cs.seed)
        diff = (target - current) & 0xFFFFFFFF
        old = struct.unpack_from('<I', data, off)[0]
        new = (old + diff) & 0xFFFFFFFF
        if new != old:
            struct.pack_into('<I', data, off, new)
            steps.append((off, struct.pack('<I', old), struct.pack('<I', new)))
    return steps, sorted(set(skipped_crc))


def correction_preview(steps, skipped_crc) -> str:
    lines = []
    if not steps:
        lines.append('Alle korrigierbaren (ADD32/ADD16) Blöcke stimmen bereits – nichts zu schreiben.')
    else:
        lines.append(f'{len(steps)} Kompensationswort(e) würden geschrieben (nur diese Bytes, rückgängig machbar):')
        lines.append('')
        for off, old, new in steps:
            lines.append(f'• @ 0x{off:08X}: {old.hex(" ").upper()}  →  {new.hex(" ").upper()}')
    if skipped_crc:
        lines += ['', 'Nicht automatisch korrigiert (nur geprüft): CRC32-Blöcke '
                  + ', '.join(skipped_crc) + '. Diese enthalten ggf. Signaturen/'
                  'Sicherheitsfelder; deren Korrektur ist hier bewusst nicht implementiert.']
    lines += ['', 'Nur die genannten Prüfsummen-Kompensationswörter; keine Signaturen oder weiteren '
              'ECU-Prüfungen. Keine Flashfreigabe.']
    return '\n'.join(lines)


def apply_correction(image, steps) -> dict:
    """Write a plan from plan_correction as ONE undo step, re-verify, roll back on any doubt.

    All compensation words are committed in a single transaction, so one undo
    (Ctrl+Z) reverts every field at once — correcting two blocks and undoing once
    must restore the file completely, not only the last field.
    """
    fresh, _ = plan_correction(image)
    if [(o, n) for o, _, n in fresh] != [(o, n) for o, _, n in steps]:
        raise ValueError('Datei hat sich seit der Planung geändert – bitte neu planen')
    # Per-byte (offset, before, after) edits across all steps, applied atomically.
    changes = [(off + i, old[i], new[i]) for off, old, new in steps
               for i in range(len(new)) if old[i] != new[i]]
    if not image.commit(changes, label='EDC17/MED17-Prüfsummenkorrektur'):
        return check_current(image)
    result = check_current(image)
    if result['mismatches']:
        image.undo()                       # single step reverts the whole correction
        raise ValueError('Nach der Korrektur stimmen nicht alle Blöcke – zurückgesetzt')
    return result
