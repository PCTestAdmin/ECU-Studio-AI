"""Bosch ME7.x (C16x) checksums beyond the multipoint table: ROMSYS, CRC table, main data CRC/checksum,
background checksums and the main program checksum.

Independent Python implementation of the procedures described by the open-source ME7Sum
(https://github.com/nyetlabs/ME7Sum, file me7sum.c, commit 7095f930cd56838954d14335dd8e81c8f35d86e3 of
09.11.2026; permissive licence, see the copyright notice at the top of me7sum.c: "Permission is hereby granted,
free of charge, ... to use, copy, modify ..."). The C source was read and compared, not executed and not copied
into this project; names in comments refer to its functions so the comparison stays traceable.

CHECK ONLY. Nothing here writes to a file. A stored value that the calculation reproduces on an unmodified original
is evidence for the procedure on that variant; a value that does not match is reported, never "fixed".

Addresses: C16x, little endian, ROM mapped at BASE = 0x800000 (me7sum.c romProps "rom_firmware_start").
All ranges are inclusive file offsets.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

import numpy as np

BASE = 0x800000
ROMSYS = 0x8000                       # me7sum.c FindROMSYS: fixed
MAX_CRC_BLOCKS = 4                    # me7sum.c MAX_CRC_BLKS

OK, MISMATCH, NOT_FOUND = 'ok', 'mismatch', 'not_found'


@dataclass
class Me7Check:
    kind: str                                   # romsys-startup, romsys-param, romsys-pages, crc-table, ...
    name: str
    status: str                                 # ok | mismatch | not_found
    stored: int | None = None
    calculated: int | None = None
    field_offset: int | None = None             # where the stored value lies (file offset)
    field_size: int = 0
    ranges: list[tuple[int, int]] = field(default_factory=list)
    detail: str = ''


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from('<H', data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _sum8(data: bytes, start: int, end: int) -> int:
    return int(np.frombuffer(data, dtype=np.uint8, count=end - start + 1, offset=start).sum(dtype=np.uint64)) & 0xFFFFFFFF


def _sum16(data: bytes, start: int, end: int) -> int:
    """me7sum.c CalcChecksumBlk16: little-endian words with index start/2 .. end/2 inclusive, modulo 2^32."""
    first, last = start // 2, end // 2
    words = np.frombuffer(data, dtype='<u2', count=last - first + 1, offset=first * 2)
    return int(words.sum(dtype=np.uint64)) & 0xFFFFFFFF


def _search(data: bytes, needle: bytes, mask: bytes | None, start: int = 0, align: int = 2):
    """me7sum.c search_image/memcmp_mask: every aligned offset o with (data[o+k] & mask[k]) == (needle[k] & mask[k])."""
    n = len(needle)
    limit = len(data) - n                       # start + len < ih->len
    if limit <= start:
        return
    if mask is None:
        o = data.find(needle, start)
        while 0 <= o < limit:
            if o % align == 0:
                yield o
            o = data.find(needle, o + 1)
        return
    # The longest run of fixed bytes narrows the candidates (bytes.find); every byte is compared afterwards, so the
    # result is exactly that of the masked comparison at every aligned offset.
    best, run_start = (0, 0), None
    for k in range(n + 1):
        if k < n and mask[k] == 0xFF:
            run_start = k if run_start is None else run_start
        elif run_start is not None:
            best = max(best, (k - run_start, -run_start))
            run_start = None
    length, anchor = best[0], -best[1]
    if not length:
        raise ValueError('Suchmuster ohne festes Byte')
    fixed = needle[anchor:anchor + length]
    o = data.find(fixed, start + anchor)
    while o >= 0:
        s = o - anchor
        if s >= limit:
            return
        if s >= start and s % align == 0 and all((data[s + k] & mask[k]) == (needle[k] & mask[k]) for k in range(n)):
            yield s
        o = data.find(fixed, o + 1)


def _find_data(data: bytes, needle: bytes, mask: bytes | None, off_l: int, off_h: int):
    """me7sum.c FindData: list of (rom offset, match offset) for matches whose embedded address lies in the ROM.
    off_l/off_h are 16-bit word indices into the match; a high word with bits 0xFE00 is a segment (shift 14)."""
    found = []
    for i in _search(data, needle, mask):
        low, high = _u16(data, i + 2 * off_l), _u16(data, i + 2 * off_h)
        address = (high << (14 if high & 0xFE00 else 16)) | low
        if BASE < address and address - BASE < len(data):
            found.append((address - BASE, i))
    return found


# ---- ROMSYS (me7sum.c DoROMSYS, CheckROMSYSHeader, DoROMSYS_Startup/ParamPage/ProgramPages) ------------------
def _romsys(data: bytes) -> list[Me7Check]:
    names = ('ROMSYS Startup', 'ROMSYS ParamPage', 'ROMSYS ProgramPages')
    if len(data) < ROMSYS + 0x40:
        return [Me7Check(k, n, NOT_FOUND, detail='Datei zu kurz') for k, n in
                zip(('romsys-startup', 'romsys-param', 'romsys-pages'), names)]
    sections, checksums, param_ptr, flash_top = struct.unpack_from('<4I', data, ROMSYS + 0x08)
    param_start, param_end, startup_sum, pages_sum = struct.unpack_from('<4I', data, ROMSYS + 0x30)
    expected_top = {512 * 1024: 0x0087FFFF, 1024 * 1024: 0x008FFFFF}.get(len(data))
    if sections != 0x20 or checksums != 0x38 or expected_top is None or flash_top != expected_top:
        detail = (f'ROMSYS-Kopf passt nicht (Abschnitte 0x{sections:X}, Prüfsummen 0x{checksums:X}, '
                  f'Ende 0x{flash_top:08X}, Dateigröße {len(data)})')
        return [Me7Check(k, n, NOT_FOUND, detail=detail) for k, n in
                zip(('romsys-startup', 'romsys-param', 'romsys-pages'), names)]
    out = []
    calc = (_u16(data, 0x8000) + _u16(data, 0xFFFE)) & 0xFFFFFFFF
    out.append(Me7Check('romsys-startup', names[0], OK if calc == startup_sum else MISMATCH, startup_sum, calc,
                        ROMSYS + 0x38, 4, [(0x8000, 0x8001), (0xFFFE, 0xFFFF)], 'Wort[0x8000] + Wort[0xFFFE]'))
    if not (BASE <= param_ptr and param_ptr - BASE + 4 <= len(data)
            and BASE <= param_start <= param_end and param_end - BASE + 2 <= len(data)):
        out.append(Me7Check('romsys-param', names[1], NOT_FOUND, detail='Zeiger der Parameterseite ungültig'))
    else:
        field_at, ps, pe = param_ptr - BASE, param_start - BASE, param_end - BASE
        stored, calc = _u32(data, field_at), (_u16(data, ps) + _u16(data, pe)) & 0xFFFFFFFF
        out.append(Me7Check('romsys-param', names[1], OK if calc == stored else MISMATCH, stored, calc, field_at, 4,
                            [(ps, ps + 1), (pe, pe + 1)], f'Wort[0x{ps:X}] + Wort[0x{pe:X}]'))
    pages_end = flash_top - BASE
    calc, ranges = 0, []
    for lo, hi in ((0x0, 0xFFFF), (0x20000, pages_end)):
        for page in range(lo, hi, 0x2000):                     # addr < r->end, 8 KiB pages
            calc += _u16(data, page) + _u16(data, page + 0x1FFE)
            ranges += [(page, page + 1), (page + 0x1FFE, page + 0x1FFF)]
    calc &= 0xFFFFFFFF
    out.append(Me7Check('romsys-pages', names[2], OK if calc == pages_sum else MISMATCH, pages_sum, calc,
                        ROMSYS + 0x3C, 4, ranges, f'erstes + letztes Wort je 8-KiB-Seite, {len(ranges) // 2} Seiten'))
    return out


# ---- CRC table (me7sum.c FindCRCTab, crc_table_fallback, DoCRCTab) ---------------------------------------------
def _crc_table_entries():
    """Reflected CRC-32, polynomial 0xEDB88320 (crc32.c of ME7Sum, identical to zlib)."""
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        table.append(c)
    return struct.pack('<256I', *table)


_CRC_TABLE = _crc_table_entries()


def _crc_table(data: bytes) -> Me7Check:
    needle0 = bytes([0xe6, 0xf4, 0, 0, 0xe6, 0xf5, 0x80, 0, 0xa9, 0x60, 0xc0, 0x62, 0x5c, 0x22])
    mask0 = bytes([0xff, 0xff, 0x01, 0, 0xff, 0xff, 0xfc, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff])
    needle1 = bytes([0xe6, 0xf4, 0, 0, 0xe6, 0xf5, 0x80, 0, 0xc0, 0xc2, 0x5c, 0x22])
    mask1 = bytes([0xff, 0xff, 0x01, 0, 0xff, 0xff, 0xfc, 0xff, 0xff, 0xff, 0xff, 0xff])
    found = [o for o, _ in _find_data(data, needle0, mask0, 1, 3)]
    if not 1 <= len(found) <= 2:
        found = [o for o, _ in _find_data(data, needle1, mask1, 1, 3)]
    how = 'Code-Verweis'
    tables = [o for o in found if o + 4 <= len(data) and _u32(data, o) == 0] if 1 <= len(found) <= 2 else []
    if not 1 <= len(tables) <= 2:
        tables = list(_search(data, _CRC_TABLE[:16], None))
        how = 'Suche nach dem Tabellenanfang'
        if not 1 <= len(tables) <= 2:
            return Me7Check('crc-table', 'CRC-Tabelle', NOT_FOUND, detail='keine CRC-32-Tabelle eindeutig gefunden')
    bad = [o for o in tables if data[o:o + 1024] != _CRC_TABLE]
    if bad:
        state = f'verändert: {", ".join(f"0x{o:X}" for o in bad)}'
    else:
        state = 'gleich der CRC-32-Standardtabelle'
    return Me7Check('crc-table', 'CRC-Tabelle', MISMATCH if bad else OK, None, None, tables[0], 1024,
                    [(o, o + 1023) for o in tables], f'{len(tables)} Tabelle(n) über {how}; {state}')


# ---- Main data CRCs and checksum (me7sum.c FindMainCRCPreBlk, FindMainCRCBlks, FindMainCRCOffsets,
#      FindMainCSMOffsets, DoMainCRCs, DoMainCSMs) ---------------------------------------------------------------
def _main_data(data: bytes) -> list[Me7Check]:
    crc = [{'start': 0, 'end': 0, 'offset': 0} for _ in range(MAX_CRC_BLOCKS + 1)]
    pre = _find_data(data, bytes([0xE6, 0xFC, 0, 0, 0xE6, 0xFD, 0x80, 0, 0xE0, 0x0E, 0xDA, 0, 0, 0, 0xF6, 0xF4]),
                     bytes([0xff, 0xff, 0, 0, 0xff, 0xff, 0xf0, 0xff, 0xff, 0x0f, 0xff, 0, 0, 0, 0xff, 0xff]), 1, 3)
    if len(pre) == 1:
        offset, where = pre[0]
        crc[0].update(start=offset, end=offset + (data[where + 9] >> 4) - 1)
    starts = _find_data(data, bytes([0xE6, 0xF8, 0, 0, 0xE6, 0xF9, 0x80, 0, 0xF2, 0xF4]),
                        bytes([0xff, 0xff, 0, 0, 0xff, 0xff, 0xf0, 0xff, 0xff, 0xff]), 1, 3)
    ends = _find_data(data, bytes([0x10, 0x9B, 0xE6, 0xF4, 0, 0, 0xE6, 0xF5, 0x80, 0]),
                      bytes([0xff, 0xff, 0xff, 0xff, 0, 0, 0xff, 0xff, 0xf0, 0xff]), 2, 4)
    if 0 < len(starts) <= MAX_CRC_BLOCKS:
        for i, (o, _) in enumerate(starts):
            crc[i + 1]['start'] = o
    if 0 < len(ends) <= MAX_CRC_BLOCKS:
        for i, (o, _) in enumerate(ends):
            crc[i + 1]['end'] = o
    blocks_ok = 0 < len(starts) <= MAX_CRC_BLOCKS or 0 < len(ends) <= MAX_CRC_BLOCKS
    # (me7sum.c FindIndirectCRCBlks covers images whose blocks are given relative to a pointer; not
    #  implemented here: such images report "not found".)
    offsets = _find_data(data, bytes([0xF6, 0xF5, 0, 0, 0xE6, 0xF4, 0, 0, 0xE6, 0xF5, 0x80, 0, 0xDA, 0]),
                         bytes([0xff, 0xff, 0, 0, 0xff, 0xff, 0x01, 0, 0xff, 0xff, 0xf0, 0xff, 0xff, 0xff]), 3, 5)
    if len(offsets) == 3:
        for i, (o, _) in enumerate(offsets):
            crc[i + 1]['offset'] = o
        if crc[4]['start'] and crc[4]['end']:
            crc[4]['offset'], crc[3]['offset'] = crc[3]['offset'], 0
    csm_mask = bytes([0xff, 0xff, 0xff, 0xff, 0x01, 0, 0xff, 0xff, 0xf0, 0xff, 0xff, 0xff])
    csm = _find_data(data, bytes([0xE1, 0x0C, 0xE6, 0xF4, 0, 0, 0xE6, 0xF5, 0x80, 0, 0xDA, 0]), csm_mask, 2, 4)
    if not csm:
        csm = _find_data(data, bytes([0x04, 0x00, 0xE6, 0xF4, 0, 0, 0xE6, 0xF5, 0x80, 0, 0xDA, 0]), csm_mask, 2, 4)
    csm_offset = csm[0][0] if len(csm) == 1 else 0
    has_crc_offsets = bool(crc[1]['offset'])
    if not (blocks_ok and crc[1]['start'] and crc[1]['end'] and (has_crc_offsets or csm_offset)):
        return [Me7Check('main-data', 'Hauptdaten-CRC/Prüfsumme', NOT_FOUND,
                         detail='Bereiche oder Ablageorte nicht eindeutig gefunden')]
    out = []
    if has_crc_offsets:
        # With a pre-block the CRCs are chained: each block continues the CRC of everything before it.
        chained = bool(crc[0]['start'] and crc[0]['end'])
        seed, covered = 0, []
        for i, block in enumerate(crc):
            if not (block['start'] and block['end']) or block['start'] > block['end'] or block['end'] >= len(data):
                continue
            calc = zlib.crc32(data[block['start']:block['end'] + 1], seed) & 0xFFFFFFFF
            covered = (covered if chained else []) + [(block['start'], block['end'])]
            at = block['offset']
            if at and at + 4 <= len(data):
                stored = _u32(data, at)
                out.append(Me7Check('main-crc', f'Hauptdaten-CRC {i}', OK if stored == calc else MISMATCH, stored,
                                    calc, at, 4, list(covered), 'CRC-32' + (' (verkettet ab Vorblock)' if chained else '')))
            if chained:
                seed = calc
    if csm_offset and csm_offset + 8 <= len(data):
        ranges = [(b['start'], b['end']) for b in crc[1:] if b['start'] and b['end'] and b['start'] <= b['end'] < len(data)]
        calc = sum(_sum8(data, s, e) for s, e in ranges) & 0xFFFFFFFF
        stored, inverse = _u32(data, csm_offset), _u32(data, csm_offset + 4)
        ok = stored == calc and inverse == (~stored & 0xFFFFFFFF)
        out.append(Me7Check('main-csm', 'Hauptdaten-Prüfsumme', OK if ok else MISMATCH, stored, calc, csm_offset, 8,
                            ranges, 'Bytesumme mit Komplement'))
    return out or [Me7Check('main-data', 'Hauptdaten-CRC/Prüfsumme', NOT_FOUND, detail='keine Ablageorte')]


# ---- Main program checksum (me7sum.c FindMainProgramOffset, FindMainProgramFinal, DoMainProgramCSM) -------------
def _main_program(data: bytes) -> Me7Check:
    name = 'Hauptprogramm-Prüfsumme'
    needle = struct.pack('<4I', BASE, BASE + 0x0FBFF, BASE + 0x20000, BASE + 0xF00FF)
    mask = struct.pack('<4I', 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFF700FF)
    descriptors = list(_search(data, needle, mask))
    final = len(data) - 0x20
    if len(descriptors) != 1 or final < 0:
        return Me7Check('main-program', name, NOT_FOUND, detail=f'{len(descriptors)} Bereichsbeschreibungen gefunden')
    value, inverse = _u32(data, final), _u32(data, final + 4)
    if value != (~inverse & 0xFFFFFFFF):
        return Me7Check('main-program', name, NOT_FOUND, detail='kein Wert/Komplement am Dateiende - 0x20')
    s0, e0, s1, e1 = struct.unpack_from('<4I', data, descriptors[0])
    ranges = [(s - BASE, e - BASE) for s, e in ((s0, e0), (s1, e1))]
    if any(s < 0 or e < s or e >= len(data) for s, e in ranges):
        return Me7Check('main-program', name, NOT_FOUND, detail='Bereichsbeschreibung ungültig')
    calc = (_sum16(data, *ranges[0]) + _sum16(data, *ranges[1])) & 0xFFFFFFFF
    return Me7Check('main-program', name, OK if calc == value else MISMATCH, value, calc, final, 8, ranges,
                    f'16-Bit-Wortsumme, Beschreibung bei 0x{descriptors[0]:X}')


# ---- Background checksums (me7sum.c FindBgChecksums, BgDescOk, DoBgChecksums, DoChecksumBlk) ------------------
def _descriptor_ok(data: bytes, offset: int) -> bool:
    if offset + 16 > len(data):
        return False
    start, end, value, inverse = struct.unpack_from('<4I', data, offset)
    if value != (~inverse & 0xFFFFFFFF) or start < BASE or end < BASE:
        return False
    if start >= BASE + len(data) or end >= BASE + len(data) or start >= end:
        return False
    length = end - start + 1
    return not (length & 1) and length <= 64 * 1024


def _background(data: bytes) -> list[Me7Check]:
    # me7sum.c FindBgChecksums: descriptor at i in [0x10000, 0x20000) with start 0x814000 and end at its own last byte.
    limit = min(len(data), 0x20000)
    start_word, anchors = struct.pack('<I', BASE + 0x14000), []
    i = data.find(start_word, 0x10000, limit - 15 + 3)
    while 0 <= i < limit - 15:
        if i % 2 == 0 and struct.unpack_from('<I', data, i + 4)[0] == BASE + i + 15:
            anchors.append(i)
        i = data.find(start_word, i + 1, limit - 15 + 3)
    if len(anchors) != 1:
        return [Me7Check('background', 'Hintergrund-Prüfsummen', NOT_FOUND,
                         detail=f'{len(anchors)} Ankerbeschreibungen gefunden')]
    chain = [anchors[0]]
    while len(chain) < 4 and chain[-1] >= 0x10000 + 16 and _descriptor_ok(data, chain[-1] - 16):
        chain.append(chain[-1] - 16)
    out = []
    for n, offset in enumerate(reversed(chain), 1):
        start, end, value, inverse = struct.unpack_from('<4I', data, offset)
        s, e = start - BASE, end - BASE
        if not (0 <= s <= e < len(data)):
            out.append(Me7Check('background', f'Hintergrund-Prüfsumme {n}', NOT_FOUND, detail='Bereich ungültig'))
            continue
        calc = 0 if s == e else _sum16(data, s, e)
        ok = calc == value and inverse == (~value & 0xFFFFFFFF)
        out.append(Me7Check('background', f'Hintergrund-Prüfsumme {n}', OK if ok else MISMATCH, value, calc,
                            offset + 8, 8, [(s, e)], f'16-Bit-Wortsumme, Beschreibung bei 0x{offset:X}'))
    return out


def check_me7(data: bytes) -> list[Me7Check]:
    """All ME7 checks of this module on a C16x ME7.x image (512 KiB or 1 MiB). Read only."""
    return [*_romsys(data), _crc_table(data), *_main_data(data), *_background(data), _main_program(data)]
