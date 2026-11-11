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
from ecu_studio.core import me7_checksums as me7
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
    # Since 1.20.1 the ME7 checks (core/me7_checksums.py) see the edit too. Expected independently from the ME7
    # ranges on the original: exactly the matching ME7 checks whose ranges contain the edited byte.
    me7_hit = {c.field_offset for c in me7.check_me7(data)
               if c.status == me7.OK and any(s <= offset <= e for s, e in c.ranges)}
    assert report.status == ig.INVALID
    assert {e.storage for e in report.errors if e.method == 'bosch-multipoint'} == covering
    assert {(e.method, e.storage) for e in report.errors if e.method != 'bosch-multipoint'} == {
        ('bosch-me7', s) for s in me7_hit}
    before = image.read(0, image.size)
    plan = ig.plan_correction(image, report)
    result = ig.apply_correction(image, plan)
    after = image.read(0, image.size)
    changed = set(np.flatnonzero(np.frombuffer(before, np.uint8) != np.frombuffer(after, np.uint8)).tolist())
    assert changed == plan.positions and all(any(r.storage <= p < r.storage + 8 for r in regions) for p in changed)
    assert not [e for e in result.errors if e.method == 'bosch-multipoint']
    # Checked-only ME7 checksums are never corrected and never hidden: they stay wrong, the file stays invalid.
    assert {e.storage for e in result.errors} == me7_hit
    assert (result.status == ig.INVALID) == bool(me7_hit)
    assert bool(me7_hit) == any('stimmen nicht und werden nicht korrigiert' in w for w in plan.warnings)
    for r in regions:                              # second, plain implementation
        e = 'little' if r.algorithm.endswith('le') else 'big'
        assert after[r.storage:r.storage + 8] == ig._pair(ig.reference_word_sum(after, r.start, r.end, e), e)
    image.write(offset, bytes([data[offset]]))
    ig.apply_correction(image, ig.plan_correction(image))
    assert image.materialize() == data
    assert not ig.check_integrity(image).errors


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


def test_all_manufacturer_multipoint_values_are_reproduced_by_both_implementations():
    """Every stored multipoint value of the references (199 in the documented set) is reproduced by the
    vectorised sum AND by the plain second implementation."""
    total = 0
    for entry in MULTIPOINT:
        data = _load(entry)
        for r in _method(ig.check_integrity(BinaryImage(data)), 'bosch-multipoint').regions:
            e = 'little' if r.algorithm.endswith('le') else 'big'
            assert r.state == ig.OK and r.stored == ig.reference_word_sum(data, r.start, r.end, e) == r.computed
            total += 1
    assert total == sum(e['regions'] for e in MULTIPOINT)


@pytest.mark.parametrize('entry', MULTIPOINT, ids=lambda e: e['name'])
def test_multipoint_correction_basis_is_established_and_named(entry):
    """PR #19 review: correction needs an identified family or strong structural proof – the references
    keep their correction (ME9 is not identified and passes on its 63 proven entries)."""
    image = BinaryImage(_load(entry))
    report = ig.check_integrity(image)
    m = _method(report, 'bosch-multipoint')
    assert m.evidence['inferred_entries'] == 0 and m.evidence['proven_entries'] == entry['regions']
    assert m.evidence['basis'] == ('familie' if report.family else 'struktur') and not m.correction


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['name'])
def test_signatures_are_reported_never_valid(entry):
    report = ig.check_integrity(BinaryImage(_load(entry)))
    assert all(s.state in ('erwartet', 'erkannt', 'unbekannt') for s in report.signatures)
    if entry['method'] == 'bosch-edc17':
        assert any(s.state == 'erkannt' for s in report.signatures)


@pytest.mark.parametrize('entry', MULTIPOINT, ids=lambda e: e['name'])
def test_corrected_copy_of_a_real_file_is_consistent(entry, tmp_path):
    data = _load(entry)
    source = tmp_path / 'original.bin'
    source.write_bytes(data)
    image = BinaryImage.from_file(str(source))
    r = max(_method(ig.check_integrity(image), 'bosch-multipoint').regions, key=lambda r: r.end - r.start)
    endian = 'little' if r.algorithm.endswith('le') else 'big'
    image.write(r.storage, ig._pair(r.stored ^ 0x1, endian))
    log = ig.write_corrected_copy(image, ig.plan_correction(image), tmp_path / 'kopie.bin')
    copy = (tmp_path / 'kopie.bin').read_bytes()
    assert copy == data and hashlib.sha256(copy).hexdigest() == log['sha256_output']
    assert json.loads((tmp_path / 'kopie.bin.korrektur.json').read_text(encoding='utf-8')) == log
    assert source.read_bytes() == data
