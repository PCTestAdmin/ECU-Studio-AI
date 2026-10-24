"""A cache may change work, never detection decisions or ownership of bytes."""
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.axis_records import scan_axis_records


@pytest.mark.parametrize('endian', ['little', 'big'])
@pytest.mark.parametrize('dtype', ['u8', 'u16', 's16'])
def test_cached_and_uncached_records_match_all_metadata(dtype, endian):
    data = bytearray(10000)
    order = '<' if endian == 'little' else '>'
    x = np.array([100, 200, 300, 500, 800], dtype=order+'u2')
    y = np.array([20, 40, 90, 150], dtype=order+'u2')
    values = np.array([[10+3*r+7*c if dtype != 's16' else -150+3*r+7*c for c in range(5)] for r in range(4)],
                      dtype=np.uint8 if dtype == 'u8' else order+('u2' if dtype == 'u16' else 'i2'))
    record = (5).to_bytes(2,endian)+(4).to_bytes(2,endian)+x.tobytes()+y.tobytes()+values.tobytes()
    for i in range(12):
        at = 101+i*(len(record)+4); data[at:at+len(record)] = record
    image = BinaryImage(bytes(data))
    cached = scan_axis_records(image, max_results=100)
    uncached = scan_axis_records(image, max_results=100, evidence_cache_size=0)
    assert cached and [m.asdict() for m in cached] == [m.asdict() for m in uncached]
    assert not image.dirty_bytes


def test_repeat_uses_less_work_without_hiding_any_records(monkeypatch):
    import ecu_studio.core.axis_records as records
    original = records.surface_evidence
    calls = []
    def counted(*args, **kwargs):
        calls.append(1); return original(*args, **kwargs)
    monkeypatch.setattr(records, 'surface_evidence', counted)
    data = bytes(range(256))*8
    image = BinaryImage(data)
    uncached = records.scan_axis_records(image, max_results=1000, evidence_cache_size=0)
    old_calls = len(calls); calls.clear()
    cached = records.scan_axis_records(image, max_results=1000)
    assert [m.asdict() for m in cached] == [m.asdict() for m in uncached]
    assert len(calls) < old_calls/2
    # A subsequent image mutation starts with fresh evidence, not prior bytes.
    other = records.scan_axis_records(BinaryImage(bytes(len(data))), max_results=1000)
    assert other == []


def test_cache_configuration_and_cancellation():
    image = BinaryImage(bytes(range(256))*8)
    for value in (-1, 513, None, True):
        with pytest.raises(ValueError): scan_axis_records(image, evidence_cache_size=value)
    assert scan_axis_records(image, cancelled=lambda: True) == []
