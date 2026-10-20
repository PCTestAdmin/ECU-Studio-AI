"""Checksum algorithms against published check values, and the guarded correction."""
import json
import struct
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.checksum_audit import (ChecksumSlot, ChecksumProfile, load_checksum_profile, slot_value,
                                            verify_checksums, plan_checksum_correction,
                                            apply_checksum_correction, _checksum)


def test_algorithms_match_published_check_values():
    assert _checksum(b'123456789', 'crc32-ieee') == 0xCBF43926
    assert _checksum(b'123456789', 'crc16-ccitt') == 0x29B1          # CRC-16/CCITT-FALSE
    assert _checksum(bytes([1, 2, 3, 4]), 'sum16-words-be') == 0x0102 + 0x0304
    assert _checksum(bytes([1, 2, 3, 4]), 'sum16-words-le') == 0x0201 + 0x0403
    assert _checksum(b'\xff\xff' * 3, 'sum16-words-be') == (3 * 0xFFFF) & 0xFFFF
    assert _checksum(bytes([0, 0, 0, 1, 0, 0, 0, 2]), 'sum32-dwords-be') == 3


def _image(size=0x400):
    data = bytearray(bytes(range(256)) * (size // 256))
    return data


def _profile(img, slots):
    return ChecksumProfile(img.digest, 'synthetic test', 'test reviewer', True, tuple(slots))


def _store(data, slot):
    img = BinaryImage(bytes(data))
    data[slot.storage_offset:slot.storage_offset + slot.width] = slot_value(img, slot).to_bytes(slot.width, slot.endian)
    return BinaryImage(bytes(data))


@pytest.mark.parametrize('algorithm,complement', [('crc32-ieee', 'none'), ('crc16-ccitt', 'none'),
                                                   ('sum16-words-be', 'ones'), ('sum32-words-le', 'twos'),
                                                   ('sum32-bytes', 'none')])
def test_correction_restores_match_after_edit(algorithm, complement):
    slot = ChecksumSlot('main', algorithm, 0, 0x100, 0x3F0, 'big', ((0x200, 0x300),), complement)
    img = _store(_image(), slot)
    profile = _profile(img, [slot])
    assert verify_checksums(img, profile)['verified']
    img.write(0x210, b'\x55\xAA')
    assert verify_checksums(img, profile)['status'] == 'mismatch'
    steps = plan_checksum_correction(img, profile)
    assert len(steps) == 1 and steps[0].storage_offset == 0x3F0
    assert apply_checksum_correction(img, profile, steps)['verified']


def test_twos_complement_makes_total_zero():
    slot = ChecksumSlot('neg', 'sum16-words-be', 0, 0x100, 0x3F0, 'big', (), 'twos')
    img = _store(_image(), slot)
    total = sum(struct.unpack('>128H', img.read(0, 0x100))) + int.from_bytes(img.read(0x3F0, 2), 'big')
    assert total & 0xFFFF == 0


def test_correction_refused_when_profile_does_not_explain_original():
    slot = ChecksumSlot('main', 'crc32-ieee', 0, 0x100, 0x3F0)
    img = BinaryImage(bytes(_image()))                 # stored field was never right
    with pytest.raises(ValueError, match='Original'):
        plan_checksum_correction(img, _profile(img, [slot]))


def test_stale_plan_is_rejected_and_unchanged_file_needs_no_steps():
    slot = ChecksumSlot('main', 'sum16-bytes', 0, 0x100, 0x3F0)
    img = _store(_image(), slot)
    profile = _profile(img, [slot])
    assert plan_checksum_correction(img, profile) == []
    img.write(0x10, b'\x00')
    steps = plan_checksum_correction(img, profile)
    img.write(0x11, b'\x00')                           # edited after planning
    with pytest.raises(ValueError, match='neu planen'):
        apply_checksum_correction(img, profile, steps)


def test_chained_and_overlapping_slots_are_rejected():
    img = BinaryImage(bytes(_image()))
    a = ChecksumSlot('a', 'sum16-bytes', 0, 0x100, 0x3F0)
    b = ChecksumSlot('b', 'sum16-bytes', 0x300, 0x3F4, 0x3F8)      # covers a's field
    with pytest.raises(ValueError, match='verkettete'):
        _profile(img, [a, b]).check(img)
    c = ChecksumSlot('c', 'sum16-bytes', 0, 0x100, 0x3F0, extra_ranges=((0x80, 0x180),))
    with pytest.raises(ValueError, match='überlappen'):
        c.check(img.size)
    d = ChecksumSlot('d', 'sum16-words-be', 0, 0x101, 0x3F0)
    with pytest.raises(ValueError, match='Wortbreite'):
        d.check(img.size)


def test_profile_file_with_extra_ranges_and_complement(tmp_path):
    slot = ChecksumSlot('main', 'sum32-words-be', 0, 0x100, 0x3F0, 'big', ((0x200, 0x280),), 'ones')
    img = _store(_image(), slot)
    path = tmp_path / 'p.json'
    path.write_text(json.dumps({'format': 1, 'firmware_sha256': img.digest, 'source': 's', 'reviewer': 'r',
                                'reviewed': True, 'slots': [{'name': 'main', 'algorithm': 'sum32-words-be',
                                'start': 0, 'end': 0x100, 'storage_offset': 0x3F0, 'endian': 'big',
                                'extra_ranges': [[0x200, 0x280]], 'complement': 'ones'}]}))
    assert verify_checksums(img, load_checksum_profile(path, img))['verified']


def test_preview_lists_every_written_byte_and_correction_is_undoable():
    from ecu_studio.core.checksum_audit import correction_preview
    slot = ChecksumSlot('main', 'sum16-bytes', 0, 0x100, 0x3F0)
    img = _store(_image(), slot)
    profile = _profile(img, [slot])
    assert 'nichts zu schreiben' in correction_preview(plan_checksum_correction(img, profile))
    img.write(0x20, b'\x00')
    steps = plan_checksum_correction(img, profile)
    text = correction_preview(steps)
    assert '0x000003F0' in text and steps[0].new.hex(' ').upper() in text and 'Keine Flashfreigabe' in text
    apply_checksum_correction(img, profile, steps)
    assert img.original[0x3F0:0x3F2] != img.read(0x3F0, 2) or steps[0].old == steps[0].new
    assert img.undo()                                   # the correction is one undoable edit
    assert verify_checksums(img, profile)['status'] == 'mismatch'
