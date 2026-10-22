"""Bosch MED17/EDC17 checksum blocks: detection, verification, guarded correction.

Mechanics are proven on a SYNTHETIC image built in the real Bosch block format
(magic signature, 72-byte descriptor, 32-byte checksum structures, the three
documented algorithms). This exercises the program's logic end to end; it is not
a claim of OEM validation, which requires a real original firmware file (none is
bundled — see docs/ECU_SUPPORT.md).
"""
import struct
import json
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core import edc17_checksum as ec


def _solve_free_dword(data, start, end_incl, hole, target):
    """Return the 4 bytes at ``hole`` so crc32_edc17 over [start,end] == target.

    CRC32 is linear over GF(2) in the input, so this is a 32x32 solve, not a
    search. Test-only: production never solves CRC fields (see module docstring).
    """
    def crc_with(free):
        d = bytearray(data)
        struct.pack_into('<I', d, hole, free)
        return ec.crc32_edc17(bytes(d[start:end_incl + 1]), ec.MAGIC_A)
    base = crc_with(0)
    cols = []
    for bit in range(32):
        cols.append(crc_with(1 << bit) ^ base)
    # Solve sum(x_i * cols[i]) = target ^ base over GF(2)
    want = target ^ base
    rows = [((1 << 32) >> 0)] * 0  # placeholder
    # Gaussian elimination on 32 equations (one per output bit)
    aug = []
    for obit in range(32):
        row = 0
        for ibit in range(32):
            if (cols[ibit] >> obit) & 1:
                row |= 1 << ibit
        aug.append([row, (want >> obit) & 1])
    for col in range(32):
        piv = next((r for r in range(col, 32) if (aug[r][0] >> col) & 1), None)
        if piv is None:
            continue
        aug[col], aug[piv] = aug[piv], aug[col]
        for r in range(32):
            if r != col and (aug[r][0] >> col) & 1:
                aug[r][0] ^= aug[col][0]
                aug[r][1] ^= aug[col][1]
    x = 0
    for r in range(32):
        if aug[r][0] == 0:
            continue
        lsb = (aug[r][0] & -aug[r][0]).bit_length() - 1
        if aug[r][1]:
            x |= 1 << lsb
    return x


def _build_image(hdr=0x100, size=0x200, total=0x400, block_id=0x60, cls_seg=0x80000000,
                 break_struct2_bounds=False):
    data = bytearray(np.random.default_rng(5).integers(0, 256, total, dtype=np.uint8).tobytes())
    # Clear magic collisions from random fill is unnecessary (2^-64), proceed.
    start_mem = cls_seg | 0x10000
    end_mem_raw = start_mem + size - 4
    struct.pack_into('<I', data, hdr + 0x00, block_id)          # id low byte, bytes 1&3 zero
    struct.pack_into('<I', data, hdr + 0x04, size)
    struct.pack_into('<I', data, hdr + 0x0C, end_mem_raw)       # high byte -> block class 0x80
    struct.pack_into('<I', data, hdr + 0x2C, 3)                 # three structures
    struct.pack_into('<I', data, hdr + 0x30, 0x00000001)        # adjust (non-blank)
    struct.pack_into('<I', data, hdr + size - 4, ec.BLOCK_TERMINATOR)
    struct.pack_into('<I', data, hdr + 0x34 + 3 * 32, 0x00000001)  # final checksum (non-blank)

    def mem(fileoff):
        return start_mem + (fileoff - hdr)

    # structure ranges (file offsets, end inclusive)
    add32 = (0x200, 0x23F)
    add16 = (0x240, 0x27F)
    crc = (0x280, 0x2BF)
    for i, (algo, (s, e)) in enumerate([(0x00, crc), (0x01, add32), (0x10, add16)]):
        # structure 0 must be the CRC anchor (seed/expected carry the magic pair)
        pass
    # Lay structures: index 0 = CRC (anchor), 1 = ADD32, 2 = ADD16
    layout = [(0x00, crc, ec.MAGIC_A, ec.MAGIC_B), (0x01, add32, ec.MAGIC_A, None), (0x10, add16, ec.MAGIC_A, None)]
    for i, (algo, (s, e), seed, exp) in enumerate(layout):
        so = hdr + 0x34 + i * 32
        struct.pack_into('<I', data, so + 4, mem(s))
        struct.pack_into('<I', data, so + 8, mem(e))
        struct.pack_into('<I', data, so + 12, seed)
        struct.pack_into('<H', data, so + 28, algo)
    # CRC anchor: solve the free dword so CRC == ~CAFEAFFE, store expected=CAFEAFFE
    free = _solve_free_dword(data, crc[0], crc[1], crc[1] - 3, (~ec.MAGIC_B) & 0xFFFFFFFF)
    struct.pack_into('<I', data, crc[1] - 3, free)
    struct.pack_into('<I', data, hdr + 0x34 + 0 * 32 + 16, ec.MAGIC_B)
    # ADD32 / ADD16 expected = computed over the original content
    struct.pack_into('<I', data, hdr + 0x34 + 1 * 32 + 16, ec.add32_edc17(bytes(data[add32[0]:add32[1] + 1]), ec.MAGIC_A))
    struct.pack_into('<I', data, hdr + 0x34 + 2 * 32 + 16, ec.add16_edc17(bytes(data[add16[0]:add16[1] + 1]), ec.MAGIC_A))
    if break_struct2_bounds:
        # Point the ADD16 structure's end past the block's own bytes: it must then
        # be reported "not verifiable", never a match.
        struct.pack_into('<I', data, hdr + 0x34 + 2 * 32 + 8, mem(hdr + size + 0x40))
    return BinaryImage(bytes(data))


def _reference_reflected_crc(payload, init):
    """Independent byte-wise reflected CRC32 (poly 0xEDB88320, no final XOR).

    For a dword-aligned payload this must agree with crc32_edc17, which consumes
    the same bytes as little-endian dwords. A second, independently written
    implementation is the cross-check the brief asks for.
    """
    crc = init & 0xFFFFFFFF
    for b in payload:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc & 0xFFFFFFFF


def test_crc32_matches_independent_reference():
    # Dword-aligned payloads: the EDC17 dword CRC equals a byte-wise reflected CRC.
    for payload, seed in [(bytes(range(16)), 0x00000000), (b'ABCD' * 7, ec.MAGIC_A),
                          (bytes(range(256)), 0xDEADBEEF)]:
        assert ec.crc32_edc17(payload, seed) == _reference_reflected_crc(payload, seed)
    # Bytes past the last whole dword are not consumed (ECU processes whole dwords).
    assert ec.crc32_edc17(b'ABCDxyz', 0) == ec.crc32_edc17(b'ABCD', 0)


def test_block_is_found_and_verified():
    img = _build_image()
    result = ec.verify(img)
    assert result['detected'] and result['blocks'] == 1
    assert result['checkable'] == 3 and result['proven_on_original'] == 3 and result['proven']
    algos = {s['algorithm'] for row in result['rows'] for s in row['structures']}
    assert algos == {'CRC32', 'ADD32', 'ADD16'}
    assert all(s['match'] for row in result['rows'] for s in row['structures'])


def test_random_data_has_no_blocks():
    rnd = np.random.default_rng(9).integers(0, 256, 1 << 16, dtype=np.uint8).tobytes()
    assert ec.find_blocks(rnd) == []
    assert ec.verify(BinaryImage(rnd))['detected'] is False


def test_edit_is_detected_on_add_blocks():
    img = _build_image()
    assert ec.check_current(img)['status'] == 'match'
    img.write(0x210, bytes([img.read(0x210, 1)[0] ^ 0xFF]))   # inside ADD32 range
    img.write(0x250, bytes([img.read(0x250, 1)[0] ^ 0xFF]))   # inside ADD16 range
    state = ec.check_current(img)
    assert state['status'] == 'mismatch' and state['mismatches'] == 2


def test_correction_restores_add_blocks_and_only_touches_compensation():
    img = _build_image()
    original = bytes(img.original)
    img.write(0x210, bytes([original[0x210] ^ 0x5A]))
    img.write(0x250, bytes([original[0x250] ^ 0x5A]))
    steps, skipped = ec.plan_correction(img, require_oem_validation=False)
    assert {o for o, _, _ in steps} == {0x23C, 0x27C}          # the two ADD compensation dwords
    assert skipped == ['Dataset #0']                           # CRC block only verified, not corrected
    text = ec.correction_preview(steps, skipped)
    assert '0x0000023C' in text and 'Keine Flashfreigabe' in text
    result = ec.apply_correction(img, steps, require_oem_validation=False)
    assert result['status'] == 'match' and result['mismatches'] == 0
    # Integrity (Test D): only the edited calibration bytes and bytes inside the
    # two declared compensation dwords may differ — nothing else in the file.
    current = img.read(0, img.size)
    changed = {i for i in range(img.size) if current[i] != original[i]}
    allowed = {0x210, 0x250} | set(range(0x23C, 0x240)) | set(range(0x27C, 0x280))
    assert {0x210, 0x250} <= changed <= allowed
    assert img.undo()                                          # correction is undoable


def test_stale_plan_is_refused():
    img = _build_image()
    img.write(0x210, b'\x01')
    steps, _ = ec.plan_correction(img, require_oem_validation=False)
    img.write(0x214, b'\x02')
    with pytest.raises(ValueError, match='geändert'):
        ec.apply_correction(img, steps, require_oem_validation=False)


def test_correction_refused_without_proven_blocks():
    rnd = np.random.default_rng(1).integers(0, 256, 1 << 12, dtype=np.uint8).tobytes()
    with pytest.raises(ValueError, match='bestätigten'):
        ec.plan_correction(BinaryImage(rnd))


def test_correction_requires_oem_validation_even_with_full_structure_proof():
    img = _build_image()
    img.write(0x210, bytes([img.original[0x210] ^ 0x5A]))
    with pytest.raises(ValueError, match='OEM-Nachweis'):
        ec.plan_correction(img)


def test_reviewed_oem_manifest_unlocks_exact_original_only(tmp_path, monkeypatch):
    from ecu_studio.core import checksum_validation
    from ecu_studio.core.signing import public_key, sign
    img = _build_image()
    manifest = tmp_path / 'oem.json'
    keys = tmp_path / 'keys.json'
    base = {'scheme': 'bosch-med17-edc17', 'sha256': img.digest, 'family': 'EDC17CP09',
            'software': 'test-only', 'evidence_sha256': 'a' * 64, 'source': 'lawful OEM test record',
            'validated': True, 'validated_at': '2026-10-22', 'independent_review': True}
    secrets = {'lab-a': b'a' * 32, 'lab-b': b'b' * 32}
    keys.write_text(json.dumps({'format': 1, 'keys': {
        'lab-a': {'public_key': public_key(secrets['lab-a']).hex(), 'independence_group': 'oem'},
        'lab-b': {'public_key': public_key(secrets['lab-b']).hex(), 'independence_group': 'external-review'},
    }}), encoding='utf-8')
    message = checksum_validation.attestation_message(base)
    entry = dict(base, signatures=[{'key_id': k, 'signature': sign(v, message).hex()} for k, v in secrets.items()])
    manifest.write_text(json.dumps({'format': 2, 'entries': [entry]}), encoding='utf-8')
    monkeypatch.setattr(checksum_validation, 'MANIFEST', manifest)
    monkeypatch.setattr(checksum_validation, 'TRUSTED_KEYS', keys)
    img.write(0x210, bytes([img.original[0x210] ^ 0x5A]))
    steps, _ = ec.plan_correction(img)
    assert steps


def test_validated_flag_without_two_trusted_signatures_never_unlocks(tmp_path, monkeypatch):
    from ecu_studio.core import checksum_validation
    img = _build_image()
    manifest = tmp_path / 'oem.json'
    manifest.write_text(json.dumps({'format': 2, 'entries': [{
        'scheme': 'bosch-med17-edc17', 'sha256': img.digest, 'family': 'EDC17CP09',
        'software': 'test-only', 'evidence_sha256': 'b' * 64, 'source': 'claim',
        'validated': True, 'validated_at': '2026-10-22', 'independent_review': True,
        'signatures': []
    }]}), encoding='utf-8')
    monkeypatch.setattr(checksum_validation, 'MANIFEST', manifest)
    assert not ec.verify(img)['oem_validated']


def test_unprogrammed_block_is_skipped():
    img = _build_image()
    data = bytearray(img.original)
    # Blank the final checksum and adjust -> reserved/unprogrammed, not a failure.
    struct.pack_into('<I', data, 0x100 + 0x30, 0xFFFFFFFF)
    struct.pack_into('<I', data, 0x100 + 0x34 + 3 * 32, 0xFFFFFFFF)
    result = ec.verify(BinaryImage(bytes(data)))
    assert result['blocks'] == 1 and result['checkable'] == 0 and result['rows'][0]['unprogrammed']


def test_audit_export_surfaces_edc17_blocks():
    from ecu_studio.core.checksum_audit import audit_export
    img = _build_image()
    report = audit_export(img, [])
    assert report['edc17_blocks']['status'] == 'match' and report['edc17_blocks']['blocks'] == 3
    img.write(0x210, bytes([img.original[0x210] ^ 0x5A]))      # break an ADD block
    report = audit_export(img, [])
    assert report['edc17_blocks']['status'] == 'mismatch'
    assert any(i['code'] == 'edc17-block-mismatch' for i in report['issues'])
    assert report['flash_approved'] is False


def test_single_undo_reverts_all_corrections():
    # Issue #1: two corrected fields must be reverted by ONE undo, not just the last.
    img = _build_image()
    img.write(0x210, bytes([img.original[0x210] ^ 0x5A]))    # edit ADD32 range
    img.write(0x250, bytes([img.original[0x250] ^ 0x5A]))    # edit ADD16 range
    after_edits = img.read(0, img.size)                       # before any checksum correction
    steps, _ = ec.plan_correction(img, require_oem_validation=False)
    assert len(steps) == 2
    ec.apply_correction(img, steps, require_oem_validation=False)
    assert ec.check_current(img)['status'] == 'match'
    assert img.undo() is True                                 # a single undo
    # Both compensation dwords are back; only the two calibration edits remain.
    assert img.read(0, img.size) == after_edits
    assert ec.check_current(img)['status'] == 'mismatch'


def test_coverage_full_partial_and_unverifiable():
    # Issue #2 / #3: explicit full vs partial, and out-of-block structures are unverifiable.
    full = ec.verify(_build_image())
    assert full['coverage'] == 'full' and full['proven'] and full['unverifiable'] == 0
    assert full['structures_total'] == 3 and full['proven_on_original'] == 3

    part = ec.verify(_build_image(break_struct2_bounds=True))
    assert part['coverage'] == 'partial' and part['proven'] is False
    assert part['proven_on_original'] == 2 and part['unverifiable'] == 1
    # The out-of-bounds structure is flagged, not silently matched.
    s2 = part['rows'][0]['structures'][2]
    assert s2['in_bounds'] is False and s2['match'] is None

    cur = ec.check_current(_build_image(break_struct2_bounds=True))
    assert cur['coverage'] == 'partial' and cur['structures_unproven'] == 1 and cur['status'] == 'match'


def test_out_of_bounds_structure_is_never_corrected():
    # Issue #3: a structure whose range leaves the block is not a write target.
    img = _build_image(break_struct2_bounds=True)
    with pytest.raises(ValueError, match='nur 2 von 3'):
        ec.plan_correction(img, require_oem_validation=False)


def test_validate_pair_measures_edc17_checksums():
    # Issue #4: the validation tool reports real EDC17 checksum coverage.
    from ecu_studio.tools.validate_pair import checksum_summary
    cs = checksum_summary(_build_image())
    assert cs['edc17_blocks'] == 1 and cs['edc17_structures_total'] == 3
    assert cs['edc17_proven'] == 3 and cs['edc17_coverage'] == 'full' and cs['edc17_unverifiable'] == 0
