"""ME7.x checks beyond the multipoint table (core/me7_checksums.py) on synthetic images.

The synthetic images are built here from the layout described by the open-source ME7Sum; the stored values are
computed with a second, deliberately plain implementation (struct loops, zlib for the CRC table). These tests cover
the mechanics: detection, every check, edits, damaged fields, false positives, ambiguous structures and how the
integrity report treats a checked-only method. The evidence that the procedures are the ECU's own comes only from
manufacturer values in real originals (tests/test_integrity_reference.py, local opt-in, docs/CHECKSUMMEN.md).
"""
import struct
import time
import tracemalloc
import zlib

import numpy as np
import pytest

from ecu_studio.core import integrity as ig
from ecu_studio.core import me7_checksums as me7
from ecu_studio.core.model import BinaryImage

BASE = 0x800000
M32 = 0xFFFFFFFF
EPK_ME75 = b'40/1/ME7.5/5/5016.01//24f/Dst02o/220503/'
PARAM_FIELD, PARAM_START, PARAM_END = 0x1E4F0, 0x10000, 0x1FFFE
CRC_TABLE_AT = 0x1D40A
CSM_FIELD = 0x1C000
CSM_BLOCKS = [(0x10002, 0x13FFE), (0x18000, 0x1BFFF)]
BG = [(0x30000, 0x32CBB), (0x14000, 0x14247)]            # background 1, background 2 (anchor, covers itself)
BG_DESC = [0x14228, 0x14238]
MAIN_DESC = 0x29FC0
MP_RANGES = [(0x40000, 0x40FFF), (0x41000, 0x41FFF), (0x42000, 0x427FF), (0x43000, 0x433FF), (0x44000, 0x44FFF)]


# --- second, plain implementation ------------------------------------------------------------------------------

def _w(data, o):
    return struct.unpack_from('<H', data, o)[0]


def plain_sum16(data, s, e):
    return sum(_w(data, o) for o in range(s, e + 1, 2)) & M32


def plain_sum8(data, s, e):
    return sum(data[s:e + 1]) & M32


def plain_pages(data, flash_end):
    total = 0
    for lo, hi in ((0, 0xFFFF), (0x20000, flash_end)):
        for page in range(lo, hi, 0x2000):
            total += _w(data, page) + _w(data, page + 0x1FFE)
    return total & M32


def standard_crc_table() -> bytes:
    return struct.pack('<256I', *[~zlib.crc32(bytes([n]), M32) & M32 for n in range(256)])


def _put(data, at, *words):
    struct.pack_into(f'<{len(words)}I', data, at, *words)


def _pair(data, at, value):
    _put(data, at, value & M32, ~value & M32)


def build(size=0x80000, seed=7, epk=EPK_ME75, multipoint_storage_on_page=None):
    """Synthetic C16x ME7 image with ROMSYS, CRC table, main data checksum, two background checksums, the main
    program checksum and (optionally) a multipoint table. Order matters only for values without complement."""
    rng = np.random.default_rng(seed)
    data = bytearray(rng.integers(0, 256, size, dtype=np.uint8).tobytes())
    flash_end = size - 1
    if epk:
        data[0x200:0x200 + len(epk)] = epk
    # ROMSYS header (values filled in later)
    _put(data, 0x8008, 0x20, 0x38, BASE + PARAM_FIELD, BASE + flash_end)
    _put(data, 0x8030, BASE + PARAM_START, BASE + PARAM_END, 0, 0)
    # CRC table + code reference (mov r4, #low; mov r5, #high; ... ) in the program area
    data[CRC_TABLE_AT:CRC_TABLE_AT + 1024] = standard_crc_table()
    low, high = (BASE + CRC_TABLE_AT) & 0xFFFF, (BASE + CRC_TABLE_AT) >> 16
    data[0x5000:0x500E] = bytes([0xE6, 0xF4, low & 0xFF, low >> 8, 0xE6, 0xF5, high & 0xFF, high >> 8,
                                 0xA9, 0x60, 0xC0, 0x62, 0x5C, 0x22])
    # main data blocks: start and end references, checksum location reference
    for i, (s, e) in enumerate(CSM_BLOCKS):
        a, b = BASE + s, BASE + e
        data[0x5100 + 16 * i:0x510A + 16 * i] = bytes([0xE6, 0xF8, a & 0xFF, (a >> 8) & 0xFF, 0xE6, 0xF9,
                                                       (a >> 16) & 0xFF, 0, 0xF2, 0xF4])
        data[0x5200 + 16 * i:0x520A + 16 * i] = bytes([0x10, 0x9B, 0xE6, 0xF4, b & 0xFF, (b >> 8) & 0xFF, 0xE6, 0xF5,
                                                       (b >> 16) & 0xFF, 0])
    c = BASE + CSM_FIELD
    data[0x5300:0x530C] = bytes([0xE1, 0x0C, 0xE6, 0xF4, c & 0xFF, (c >> 8) & 0xFF, 0xE6, 0xF5, (c >> 16) & 0xFF, 0,
                                 0xDA, 0])
    # background descriptors: (start, end, value, ~value); nothing valid before the first one
    data[BG_DESC[0] - 16:BG_DESC[0]] = bytes(16)
    for at, (s, e) in zip(BG_DESC, BG):
        _put(data, at, BASE + s, BASE + e, 0, M32)
    # main program descriptor
    _put(data, MAIN_DESC, BASE, BASE + 0xFBFF, BASE + 0x20000, BASE + flash_end)
    _pair(data, size - 0x20, 0)
    # optional multipoint table (records of 16 bytes: start, end, value, ~value), 0xFF terminated
    if multipoint_storage_on_page is not None:
        first = multipoint_storage_on_page - 8 - 16 * (len(MP_RANGES) - 1)
        for i, (s, e) in enumerate(MP_RANGES):
            _put(data, first + 16 * i, BASE + s, BASE + e, 0, M32)
        data[first + 16 * len(MP_RANGES):first + 16 * len(MP_RANGES) + 16] = b'\xFF' * 16
        for i, (s, e) in enumerate(MP_RANGES):
            _pair(data, first + 16 * i + 8, plain_sum16(data, s, e))
    # values: background (each pair is invariant for word sums), main data, ROMSYS, main program last
    for at, (s, e) in zip(BG_DESC, BG):
        _pair(data, at + 8, plain_sum16(data, s, e))
    _pair(data, CSM_FIELD, sum(plain_sum8(data, s, e) for s, e in CSM_BLOCKS))
    _put(data, PARAM_FIELD, (_w(data, PARAM_START) + _w(data, PARAM_END)) & M32)
    _put(data, 0x8038, (_w(data, 0x8000) + _w(data, 0xFFFE)) & M32)
    _put(data, 0x803C, plain_pages(data, flash_end))
    _pair(data, size - 0x20, (plain_sum16(data, 0, 0xFBFF) + plain_sum16(data, 0x20000, flash_end)) & M32)
    return bytes(data)


def by_kind(checks):
    return {c.name: c for c in checks}


EXPECTED = ['ROMSYS Startup', 'ROMSYS ParamPage', 'ROMSYS ProgramPages', 'CRC-Tabelle', 'Hauptdaten-Prüfsumme',
            'Hintergrund-Prüfsumme 1', 'Hintergrund-Prüfsumme 2', 'Hauptprogramm-Prüfsumme']


# --- the checks ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('size', [0x80000, 0x100000])
def test_every_check_matches_the_plain_implementation(size):
    data = build(size)
    checks = me7.check_me7(data)
    found = by_kind(checks)
    assert [c.name for c in checks if c.status == me7.OK] == EXPECTED
    assert [c.kind for c in checks if c.status == me7.NOT_FOUND] == []
    assert found['ROMSYS Startup'].stored == found['ROMSYS Startup'].calculated == struct.unpack_from('<I', data, 0x8038)[0]
    assert found['ROMSYS ProgramPages'].calculated == plain_pages(data, size - 1)
    assert found['ROMSYS ParamPage'].field_offset == PARAM_FIELD
    assert found['CRC-Tabelle'].field_offset == CRC_TABLE_AT and 'Code-Verweis' in found['CRC-Tabelle'].detail
    assert found['Hauptdaten-Prüfsumme'].ranges == CSM_BLOCKS and found['Hauptdaten-Prüfsumme'].field_offset == CSM_FIELD
    assert [found[f'Hintergrund-Prüfsumme {n}'].ranges for n in (1, 2)] == [[BG[0]], [BG[1]]]
    main = found['Hauptprogramm-Prüfsumme']
    assert main.ranges == [(0, 0xFBFF), (0x20000, size - 1)] and main.field_offset == size - 0x20
    assert main.calculated == (plain_sum16(data, 0, 0xFBFF) + plain_sum16(data, 0x20000, size - 1)) & M32


@pytest.mark.parametrize('name, offset', [
    ('ROMSYS Startup', 0xFFFE), ('ROMSYS ParamPage', PARAM_END), ('ROMSYS ProgramPages', 0x22000),
    ('CRC-Tabelle', CRC_TABLE_AT + 40), ('Hauptdaten-Prüfsumme', 0x19001), ('Hintergrund-Prüfsumme 1', 0x31001),
    ('Hintergrund-Prüfsumme 2', 0x14101), ('Hauptprogramm-Prüfsumme', 0x60001)])
def test_one_byte_edit_is_detected_by_exactly_the_covering_checks(name, offset):
    data = bytearray(build())
    data[offset] ^= 0x01
    checks = me7.check_me7(bytes(data))
    wrong = {c.name for c in checks if c.status == me7.MISMATCH}
    covering = {c.name for c in me7.check_me7(build()) if any(s <= offset <= e for s, e in c.ranges)}
    assert name in wrong and wrong == covering
    assert all(c.status == me7.OK for c in checks if c.name not in covering)


@pytest.mark.parametrize('field, name', [
    (0x8038, 'ROMSYS Startup'), (0x803C, 'ROMSYS ProgramPages'), (PARAM_FIELD, 'ROMSYS ParamPage'),
    (CSM_FIELD, 'Hauptdaten-Prüfsumme'), (CSM_FIELD + 4, 'Hauptdaten-Prüfsumme'),
    (BG_DESC[1] + 8, 'Hintergrund-Prüfsumme 2'), (BG_DESC[1] + 12, 'Hintergrund-Prüfsumme 2')])
def test_damaged_stored_value_is_a_mismatch(field, name):
    data = bytearray(build())
    data[field] ^= 0x10
    assert by_kind(me7.check_me7(bytes(data)))[name].status == me7.MISMATCH


def test_value_without_matching_complement_is_not_taken_as_a_structure():
    # main program: the pair at the end of the file; background: a predecessor descriptor ends the chain
    data = bytearray(build())
    data[0x80000 - 0x20] ^= 0x10
    data[BG_DESC[0] + 8] ^= 0x10
    found = by_kind(me7.check_me7(bytes(data)))
    assert found['Hauptprogramm-Prüfsumme'].status == me7.NOT_FOUND
    assert 'Hintergrund-Prüfsumme 2' not in found                    # only the anchor is left: it is number 1 now
    assert found['Hintergrund-Prüfsumme 1'].ranges == [BG[1]] and found['Hintergrund-Prüfsumme 1'].status == me7.MISMATCH


@pytest.mark.parametrize('data', [b'', bytes(0x80000), b'\xFF' * 0x80000, bytes(0x100000),
                                  np.random.default_rng(1).integers(0, 256, 0x80000, dtype=np.uint8).tobytes(),
                                  np.random.default_rng(2).integers(0, 256, 0x100000, dtype=np.uint8).tobytes()],
                         ids=['leer', 'nullen', 'ff', 'nullen-1M', 'zufall-512K', 'zufall-1M'])
def test_no_false_positives(data):
    assert all(c.status == me7.NOT_FOUND for c in me7.check_me7(data))
    assert not [m for m in ig.check_integrity(BinaryImage(data)).methods if m.method == 'bosch-me7']


@pytest.mark.parametrize('cut', [0x8010, 0x40000, 0x7FFFF, 0x80001])
def test_truncated_or_resized_images_never_raise_and_lose_the_size_bound_checks(cut):
    data = build()
    data = data[:cut] if cut <= len(data) else data + b'\0' * (cut - len(data))
    found = by_kind(me7.check_me7(data))
    assert found['ROMSYS Startup'].status == me7.NOT_FOUND           # header names a 512 KiB flash
    assert found['Hauptprogramm-Prüfsumme'].status != me7.OK


def test_ambiguous_structures_are_not_guessed():
    data = bytearray(build())
    data[0x2A000:0x2A010] = data[MAIN_DESC:MAIN_DESC + 16]                 # second main program descriptor
    data[0x16000:0x16010] = struct.pack('<2I', BASE + 0x14000, BASE + 0x1600F) + bytes(8)   # second anchor
    found = by_kind(me7.check_me7(bytes(data)))
    assert found['Hauptprogramm-Prüfsumme'].status == me7.NOT_FOUND
    assert by_kind(me7.check_me7(bytes(data))).get('Hintergrund-Prüfsummen').status == me7.NOT_FOUND


def test_crc_table_found_by_fallback_and_modified_table_is_reported():
    data = bytearray(build())
    data[0x5000:0x500E] = bytes(14)                                       # no code reference
    found = by_kind(me7.check_me7(bytes(data)))['CRC-Tabelle']
    assert found.status == me7.OK and 'Tabellenanfang' in found.detail
    data[CRC_TABLE_AT + 100] ^= 0xFF
    assert by_kind(me7.check_me7(bytes(data)))['CRC-Tabelle'].status == me7.MISMATCH


def test_runtime_and_memory():
    data = build(0x100000)
    tracemalloc.start()
    started = time.perf_counter()
    me7.check_me7(data)
    seconds = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert seconds < 2.0 and peak < 8 * 1024 * 1024


# --- integrity report ----------------------------------------------------------------------------------------

def _me7_method(report):
    return next(m for m in report.methods if m.method == 'bosch-me7')


def test_report_checks_only_and_never_claims_valid():
    report = ig.check_integrity(BinaryImage(build()))
    m = _me7_method(report)
    background = ['Hintergrund-Prüfsumme 1', 'Hintergrund-Prüfsumme 2']
    assert [r.name for r in m.regions if r.state == ig.OK] == [n for n in EXPECTED if n not in background]
    assert m.count(ig.BAD) == 0 and m.count(ig.UNPROVEN) == 0
    # background descriptors are multipoint records (same field, same word sum): reported there only, never twice
    mp = next(x for x in report.methods if x.method == 'bosch-multipoint')
    assert {r.storage for r in mp.regions} >= {BG_DESC[0] + 8, BG_DESC[1] + 8}
    assert all(any(n in note and 'Multipoint-Eintrag' in note for note in m.notes) for n in background)
    storages = [(r.storage, r.start, r.end) for r in report.regions]
    assert len(storages) == len(set(storages))
    assert m.correction.startswith('gesperrt') and m.info.validation == 'gemessen'
    assert report.status == ig.INCOMPLETE and report.status != ig.VALID
    assert any('ohne unabhängigen Nachweis' in r for r in report.reasons)
    # what ME7 has beyond these checks stays listed as unchecked; the RSA signature stays "expected"
    assert report.unchecked == ['Haupt-Daten-CRC32 (nicht gefunden; indirekte CRC-Blöcke werden nicht unterstützt)']
    assert [(s.kind, s.state) for s in report.signatures] == [('RSA-Signatur über Programmbereiche (ME7.x)', 'erwartet')]
    assert report.asdict()['flash_approved'] is False


def test_edit_is_invalid_not_correctable_and_refused_with_a_reason():
    image = BinaryImage(build())
    image.write(0x60101, bytes([image.byte(0x60101) ^ 1]))               # only the main program covers it
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and not report.correctable
    assert [(e.method, e.name) for e in report.errors] == [('bosch-me7', 'Hauptprogramm-Prüfsumme')]
    plan = ig.plan_correction(image, report)
    assert not plan.steps and plan.refused[0][0] == 'bosch-me7' and 'gesperrt' in plan.refused[0][1]


def test_original_that_does_not_match_stays_unconfirmed_never_valid():
    data = bytearray(build())
    data[0x31001] ^= 1                         # "original" already modified: background 1 + main program stale
    report = ig.check_integrity(BinaryImage(bytes(data)))
    m = _me7_method(report)
    assert {r.name for r in m.regions if r.state == ig.UNPROVEN} == {'Hauptprogramm-Prüfsumme'}
    mp = next(x for x in report.methods if x.method == 'bosch-multipoint')
    assert {r.storage for r in mp.regions if r.state == ig.UNPROVEN} == {BG_DESC[0] + 8}     # background 1
    assert report.status == ig.INCOMPLETE and not report.errors
    # the family entry is not taken as checked while one of its checks is unconfirmed
    assert 'Hintergrund- und Hauptprogramm-Prüfsummen' in report.unchecked


def test_changed_structure_in_the_current_file_is_an_error():
    image = BinaryImage(build())
    image.write(MAIN_DESC + 4, struct.pack('<I', BASE + 0xFBFD))       # main program descriptor changed
    report = ig.check_integrity(image)
    bad = {r.name: r.note for r in report.errors if r.method == 'bosch-me7'}
    assert 'Struktur' in bad.get('Hauptprogramm-Prüfsumme', '')
    image.undo()
    image.write(BG_DESC[0], struct.pack('<I', BASE + 0x30002))          # background 1 (a multipoint record)
    report = ig.check_integrity(image)
    assert [(e.method, e.note) for e in report.errors if e.storage == BG_DESC[0] + 8] == [
        ('bosch-multipoint', 'Tabelleneintrag (Adressen) verändert')]


def test_other_family_is_not_checked_with_me7_procedures():
    data = build()
    assert ig._me7('ME7.5', data, data) is not None and ig._me7(None, data, data) is not None
    for family in ('MED9.1', 'ME9', 'EDC17CP09', 'MS43', 'MED17.5'):
        assert ig._me7(family, data, data) is None


# --- interaction with the multipoint correction ---------------------------------------------------------------

def test_multipoint_correction_that_would_break_a_matching_me7_checksum_is_refused():
    """The multipoint field lies on a word that ROMSYS ProgramPages sums (first word of an 8 KiB page): correcting
    it would turn the matching ROMSYS checksum into a wrong one, so the whole correction is refused."""
    data = build(multipoint_storage_on_page=0x22000)
    image = BinaryImage(data)
    assert ig.check_integrity(image).status == ig.INCOMPLETE
    image.write(MP_RANGES[4][0] + 0x10, bytes([data[MP_RANGES[4][0] + 0x10] ^ 1]))
    report = ig.check_integrity(image)
    mp = next(m for m in report.methods if m.method == 'bosch-multipoint')
    assert mp.count(ig.BAD) == 1 and not mp.correction                  # multipoint alone would be correctable
    plan = ig.plan_correction(image, report)
    assert not plan.steps
    assert any(method == 'bosch-multipoint' and 'ROMSYS ProgramPages' in reason for method, reason in plan.refused)
    with pytest.raises(ValueError):
        ig.apply_correction(image, plan)
    assert image.read(0, image.size) != data and image.byte(0x22000) == data[0x22000]   # nothing written


def test_multipoint_correction_leaves_checked_only_me7_errors_visible():
    data = build(multipoint_storage_on_page=0x22050)                     # no field on a summed word
    image = BinaryImage(data)
    offset = MP_RANGES[4][0] + 0x10
    image.write(offset, bytes([data[offset] ^ 1]))
    report = ig.check_integrity(image)
    plan = ig.plan_correction(image, report)
    assert len(plan.steps) == 1 and plan.steps[0].method == 'bosch-multipoint'
    assert any('stimmen nicht und werden nicht korrigiert' in w and 'Hauptprogramm-Prüfsumme' in w
               for w in plan.warnings)
    result = ig.apply_correction(image, plan)
    assert result.status == ig.INVALID
    assert [(e.method, e.name) for e in result.errors] == [('bosch-me7', 'Hauptprogramm-Prüfsumme')]
    image.write(offset, bytes([data[offset]]))                           # revert the edit, correct again
    ig.apply_correction(image, ig.plan_correction(image))
    assert image.materialize() == data and not ig.check_integrity(image).errors


def test_fast_search_equals_the_plain_masked_comparison_at_every_offset():
    rng = np.random.default_rng(11)
    data = bytearray(rng.integers(0, 4, 0x6000, dtype=np.uint8).tobytes())   # few symbols: many near misses
    needle = bytes([0x01, 0x02, 0, 0, 0x01, 0x03, 0x80, 0])
    mask = bytes([0xff, 0xff, 0x01, 0, 0xff, 0xff, 0xfc, 0xff])
    for at in (0x10, 0x101, 0x2000, 0x5FF0, 0x6000 - 9):
        data[at:at + 8] = bytes([0x01, 0x02, 0x02, 0x77, 0x01, 0x03, 0x81, 0])
    plain = [o for o in range(0, len(data) - len(needle)) if o % 2 == 0
             and all((data[o + k] & mask[k]) == (needle[k] & mask[k]) for k in range(len(needle)))]
    assert list(me7._search(bytes(data), needle, mask)) == plain and plain
    assert list(me7._search(bytes(data), needle, None)) == [
        o for o in range(0, len(data) - len(needle), 2) if bytes(data[o:o + len(needle)]) == needle]


def test_background_anchor_search_equals_the_plain_scan():
    data = bytearray(build())
    data[0x1A000:0x1A008] = struct.pack('<2I', BASE + 0x14000, BASE + 0x1A000 + 15)     # second anchor
    data[0x1B001:0x1B009] = struct.pack('<2I', BASE + 0x14000, BASE + 0x1B001 + 15)     # odd offset: ignored
    plain = [i for i in range(0x10000, 0x20000 - 15, 2)
             if struct.unpack_from('<2I', data, i) == (BASE + 0x14000, BASE + i + 15)]
    assert plain == [BG_DESC[1], 0x1A000]
    assert by_kind(me7.check_me7(bytes(data)))['Hintergrund-Prüfsummen'].detail == '2 Ankerbeschreibungen gefunden'
