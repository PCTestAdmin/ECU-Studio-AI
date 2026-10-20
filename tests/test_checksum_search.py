import json
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.checksum_audit import ChecksumSlot, slot_value, load_checksum_profile
from ecu_studio.core.checksum_search import search_checksums, confirm, draft_profile


def _file(seed, slot):
    data = bytearray(np.random.default_rng(seed).integers(0, 256, 0x1000, dtype=np.uint8).tobytes())
    data[slot.storage_offset:slot.storage_offset + slot.width] = \
        slot_value(BinaryImage(bytes(data)), slot).to_bytes(slot.width, slot.endian)
    return bytes(data)


SLOT = ChecksumSlot('x', 'sum16-words-be', 0x100, 0x800, 0x900, 'big', (), 'twos')


def test_search_finds_true_layout_and_reports_chance_level():
    result = search_checksums(_file(1, SLOT), [0x900], step=0x100)
    assert any((h.algorithm, h.start, h.end, h.complement, h.endian) ==
               ('sum16-words-be', 0x100, 0x800, 'twos', 'big') for h in result['hypotheses'])
    assert result['tested'] > 1000 and result['expected_chance_matches'] > 0


def test_second_file_removes_chance_matches():
    first = search_checksums(_file(1, SLOT), [0x900], step=0x100)['hypotheses']
    kept = confirm(first, [_file(2, SLOT), _file(3, SLOT)])
    assert [(h.algorithm, h.start, h.end, h.complement) for h in kept
            if h.algorithm == 'sum16-words-be'] == [('sum16-words-be', 0x100, 0x800, 'twos')]
    assert all(h.confirmed_on == 3 for h in kept)


def test_crc_hypothesis_on_range_before_field():
    slot = ChecksumSlot('c', 'crc32-ieee', 0x200, 0x900, 0x900)
    hits = search_checksums(_file(4, slot), [0x900], step=0x100, algorithms=('crc32-ieee',))['hypotheses']
    assert [(h.start, h.end) for h in hits] == [(0x200, 0x900)]


def test_draft_profile_cannot_be_loaded_until_reviewed(tmp_path):
    data = _file(1, SLOT)
    hyps = confirm(search_checksums(data, [0x900], step=0x100)['hypotheses'], [_file(2, SLOT)])
    image = BinaryImage(data)
    draft = draft_profile(image, hyps, 'Checksummen-Suche, Test')
    path = tmp_path / 'draft.json'
    path.write_text(json.dumps(draft))
    with pytest.raises(ValueError, match='manuell'):
        load_checksum_profile(path, image)
    draft.update(reviewer='Prüfer', reviewed=True)
    path.write_text(json.dumps(draft))
    assert load_checksum_profile(path, image).slots[0].start == 0x100


def test_search_requires_a_storage_position():
    with pytest.raises(ValueError):
        search_checksums(b'\0' * 64, [])
