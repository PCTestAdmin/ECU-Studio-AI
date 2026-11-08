"""Opt-in: checksums written by the manufacturer into real, unmodified originals.

The originals stay local and never enter the repository. Point
``ECU_STUDIO_CHECKSUM_REFERENCES`` at a JSON list of entries

    {"name", "bin", "sha256", "method", "regions", "unproven"}

(see docs/CHECKSUMMEN.md). The independent oracle is the file itself: its stored
values come from the manufacturer's toolchain, not from this code. A correction is
correct when it reproduces those bytes exactly: after damaging stored fields, or
after editing and reverting covered data, the corrected file must be bit-identical
to the original.
"""
import hashlib
import json
import os

import numpy as np
import pytest

from ecu_studio.core import integrity as ig
from ecu_studio.core.model import BinaryImage

MANIFEST = os.environ.get('ECU_STUDIO_CHECKSUM_REFERENCES')
ENTRIES = json.load(open(MANIFEST, encoding='utf-8')) if MANIFEST and os.path.isfile(MANIFEST) else []
pytestmark = pytest.mark.skipif(not ENTRIES, reason='lokale Referenz-Originale nicht konfiguriert')
MULTIPOINT = [e for e in ENTRIES if e['method'] == 'bosch-multipoint']


def _load(entry) -> bytes:
    data = open(entry['bin'], 'rb').read()
    assert hashlib.sha256(data).hexdigest() == entry['sha256'], 'Referenzdatei verändert'
    return data


def _method(report, method):
    return next(m for m in report.methods if m.method == method)


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['name'])
def test_original_reproduces_the_manufacturer_values(entry):
    report = ig.check_integrity(BinaryImage(_load(entry)))
    m = _method(report, entry['method'])
    assert m.count(ig.OK) == entry['regions'] and m.count(ig.BAD) == 0
    assert m.count(ig.UNPROVEN) == entry['unproven']
    assert report.status == ig.INCOMPLETE          # never "valid": further checks / no independent proof


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['name'])
def test_repeated_and_truncated(entry):
    data = _load(entry)
    a, b = ig.check_integrity(BinaryImage(data)).asdict(), ig.check_integrity(BinaryImage(data)).asdict()
    a['seconds'] = b['seconds'] = 0
    assert a == b
    for cut in (len(data) // 2, len(data) // 3):
        assert ig.check_integrity(BinaryImage(data[:cut])).status != ig.VALID


@pytest.mark.parametrize('entry', MULTIPOINT, ids=lambda e: e['name'])
def test_damaged_fields_are_restored_to_the_manufacturer_bytes(entry):
    data = _load(entry)
    image = BinaryImage(data)
    regions = _method(ig.check_integrity(image), 'bosch-multipoint').regions
    picked = regions[::max(1, len(regions) // 8)][:8]
    for r in picked:
        endian = 'little' if r.algorithm.endswith('le') else 'big'
        image.write(r.storage, ig._pair(r.stored ^ 0x5A5A5A5A, endian))   # coherent but wrong
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and {e.storage for e in report.errors} == {r.storage for r in picked}
    plan = ig.plan_correction(image, report)
    assert len(plan.steps) == len(picked)
    ig.apply_correction(image, plan)
    assert image.materialize() == data             # bit-identical to the manufacturer's values


@pytest.mark.parametrize('entry', MULTIPOINT, ids=lambda e: e['name'])
def test_edit_correct_revert_correct_gives_the_original(entry):
    data = _load(entry)
    image = BinaryImage(data)
    regions = _method(ig.check_integrity(image), 'bosch-multipoint').regions
    records = [(r.storage - 8, r.storage + 8) for r in regions]
    target = max(regions, key=lambda r: r.end - r.start)
    offset = (target.start + target.end) // 2 & ~1
    while any(a <= offset < b for a, b in records):
        offset += 2
    image.write(offset, bytes([data[offset] ^ 0x01]))
    report = ig.check_integrity(image)
    covering = {r.storage for r in regions if r.start <= offset <= r.end}
    assert report.status == ig.INVALID and {e.storage for e in report.errors} == covering
    before = image.read(0, image.size)
    plan = ig.plan_correction(image, report)
    result = ig.apply_correction(image, plan)
    after = image.read(0, image.size)
    changed = set(np.flatnonzero(np.frombuffer(before, np.uint8) != np.frombuffer(after, np.uint8)).tolist())
    assert changed == plan.positions and all(any(r.storage <= p < r.storage + 8 for r in regions) for p in changed)
    assert not result.errors
    for r in regions:                              # second, plain implementation
        e = 'little' if r.algorithm.endswith('le') else 'big'
        assert after[r.storage:r.storage + 8] == ig._pair(ig.reference_word_sum(after, r.start, r.end, e), e)
    image.write(offset, bytes([data[offset]]))
    ig.apply_correction(image, ig.plan_correction(image))
    assert image.materialize() == data


@pytest.mark.parametrize('entry', [e for e in ENTRIES if e['method'] != 'bosch-multipoint'], ids=lambda e: e['name'])
def test_measured_methods_detect_edits_but_stay_locked(entry):
    data = _load(entry)
    image = BinaryImage(data)
    region = next(r for r in _method(ig.check_integrity(image), entry['method']).regions if r.state == ig.OK)
    offset = (region.start + region.end) // 2 & ~3
    image.write(offset, bytes([data[offset] ^ 0x01]))
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and not report.correctable
    plan = ig.plan_correction(image, report)
    assert not plan.steps and plan.refused
