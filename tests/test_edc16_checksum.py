"""EDC16 checksum descriptor detection and guarded correction."""
import struct
import numpy as np
import pytest

from ecu_studio.core.model import BinaryImage
from ecu_studio.core import edc16_checksum as ec


def _image():
    data = bytearray(np.random.default_rng(12).integers(0, 256, 0x600, dtype=np.uint8).tobytes())
    start, end = 0x100, 0x3FF
    marker = start + ec.MAGIC_OFFSET
    start_addr = 0x00010000
    struct.pack_into('>I', data, marker - 8, start_addr)
    struct.pack_into('>I', data, marker - 4, start_addr + end - start)
    data[marker:marker + len(ec.MAGIC)] = ec.MAGIC
    # Last dword is the compensation word.  Fill it after summing the rest.
    struct.pack_into('>I', data, end - 3, 0)
    total = ec.sum_region(bytes(data), ec.Region(start, end, end - 3))
    struct.pack_into('>I', data, end - 3, (ec.TARGET_SUM - total) & 0xFFFFFFFF)
    return BinaryImage(bytes(data))


def test_region_is_found_and_verified():
    result = ec.verify(_image())
    assert result['detected'] and result['regions'] == 1
    assert result['coverage'] == 'full' and result['proven_on_original'] == 1
    assert result['rows'][0]['match'] is True


def test_edit_is_detected_and_can_be_planned_only_in_explicit_test_mode():
    image = _image()
    image.write(0x180, b'\x55')
    assert ec.check_current(image)['status'] == 'mismatch'
    with pytest.raises(ValueError, match='OEM-Nachweis'):
        ec.plan_correction(image)
    steps = ec.plan_correction(image, require_oem_validation=False)
    assert len(steps) == 1 and steps[0][0] == 0x3FC
    result = ec.apply_correction(image, steps, require_oem_validation=False)
    assert result['status'] == 'match'


def test_invalid_original_region_is_not_corrected():
    image = _image()
    data = bytearray(image.original)
    data[0x180] ^= 0xFF
    invalid = BinaryImage(bytes(data))
    assert ec.verify(invalid)['coverage'] == 'none'
    with pytest.raises(ValueError, match='bestätigten'):
        ec.plan_correction(invalid, require_oem_validation=False)
