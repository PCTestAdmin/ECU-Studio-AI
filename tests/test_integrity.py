"""Checksums & integrity (core/integrity.py): status, correction, copy, re-check, threads, GUI.

These tests use synthetic images. They cover the mechanics; the evidence that the
multipoint sum is the ECU's own method comes from manufacturer values in real
originals (tests/test_integrity_reference.py, local opt-in, and docs/CHECKSUMMEN.md).
"""
import json
import struct
import threading
import tracemalloc
import zlib
from pathlib import Path

import numpy as np
import pytest

from ecu_studio.core import integrity as ig
from ecu_studio.core.checksum_audit import ChecksumProfile, ChecksumSlot
from ecu_studio.core.model import BinaryImage

EPK_ME75 = b'40/1/ME7.5/5/5016.01//24f/Dst02o/220503/'
TABLE = 0x10000
BASE = 0x800000
RANGES = [(TABLE, TABLE + 0xFF), (0x1000, 0x1FFF), (0x3000, 0x37FF), (0x5000, 0x5FFF), (0x8000, 0x8FFF)]


def _multipoint(size=0x20000, endian='little', epk=EPK_ME75, ranges=RANGES, seed=3):
    """ME7-like image: one multipoint table, record 0 covers the table itself."""
    data = bytearray(np.random.default_rng(seed).integers(0, 256, size, dtype=np.uint8).tobytes())
    if epk:
        data[0x200:0x200 + len(epk)] = epk
    for i, (s, e) in enumerate(ranges):
        rec = TABLE + 16 * i
        data[rec:rec + 8] = (s + BASE).to_bytes(4, endian) + (e + BASE).to_bytes(4, endian)
        data[rec + 8:rec + 16] = ig._pair(0x12345678, endian)            # placeholder, coherent pair
    end = TABLE + 16 * len(ranges)
    data[end:end + 16] = b'\xFF' * 16
    for i, (s, e) in enumerate(ranges):  # pairs sum to a constant, so the order does not matter
        rec = TABLE + 16 * i
        data[rec + 8:rec + 16] = ig._pair(ig.reference_word_sum(bytes(data), s, e, endian), endian)
    return BinaryImage(bytes(data))


def _edit(image, offset, delta=1):
    image.write(offset, bytes([(image.byte(offset) + delta) & 0xFF]))


# --- status ------------------------------------------------------------------

def test_reference_sum_equals_vectorised_sum():
    data = np.random.default_rng(1).integers(0, 256, 4096, dtype=np.uint8).tobytes()
    for endian in ('little', 'big'):
        for s, e in ((0, 1), (2, 4095), (100, 3001)):
            assert ig._word_sum(data, s, e, endian) == ig.reference_word_sum(data, s, e, endian)


def test_unmodified_multipoint_original_is_incomplete_never_valid():
    report = ig.check_integrity(_multipoint())
    assert report.status == ig.INCOMPLETE and report.status_text == 'Unvollständige Prüfung'
    assert report.family == 'ME7.5'
    [m] = report.methods
    assert m.method == 'bosch-multipoint' and m.count(ig.OK) == len(RANGES) and m.coverage == 'vollständig'
    assert any('ROMSYS' in r for r in report.reasons)          # further ME7 checksums named
    assert report.signatures and report.signatures[0].state == 'erwartet'
    assert any('Herstellersignatur' in r for r in report.reasons)
    assert not report.errors and not report.correctable
    assert report.asdict()['flash_approved'] is False


def test_unidentified_family_stays_incomplete():
    report = ig.check_integrity(_multipoint(epk=None))
    assert report.status == ig.INCOMPLETE
    assert any('nicht eindeutig identifiziert' in r for r in report.reasons)


def test_big_endian_tables_are_found_too():
    report = ig.check_integrity(_multipoint(endian='big', epk=None))
    assert report.methods[0].method == 'bosch-multipoint'
    assert report.methods[0].regions[0].algorithm == 'sum32-words-be'


def test_identified_family_without_method_is_unsupported():
    data = bytearray(0x8000)
    data[0x100:0x100 + len(EPK_ME75)] = EPK_ME75
    report = ig.check_integrity(BinaryImage(bytes(data)))
    assert report.status == ig.UNSUPPORTED and report.status_text == 'Nicht unterstützt'


def test_random_data_is_unknown():
    data = np.random.default_rng(9).integers(0, 256, 0x10000, dtype=np.uint8).tobytes()
    report = ig.check_integrity(BinaryImage(data))
    assert report.status == ig.UNKNOWN and not report.methods


def test_edit_makes_file_invalid_with_address():
    image = _multipoint()
    _edit(image, 0x3400)
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and report.status_text == 'Unterstützt und ungültig'
    [bad] = report.errors
    assert bad.storage == TABLE + 16 * 2 + 8 and bad.correctable and report.correctable


def test_generic_crc_record_never_makes_a_file_valid():
    """A self-describing record that only a generic CRC reproduces: checked, experimental, not corrected."""
    data = bytearray(np.random.default_rng(4).integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    data[0x100:0x100 + len(EPK_ME75)] = EPK_ME75
    start, end, rec = 0x1000, 0x1FFF, 0x4000
    value = zlib.crc32(bytes(data[start:end + 1])) & 0xFFFFFFFF
    data[rec:rec + 16] = struct.pack('<IIII', start, end, value, ~value & 0xFFFFFFFF)
    image = BinaryImage(bytes(data))
    report = ig.check_integrity(image)
    assert [m.method for m in report.methods] == ['tabelle-generisch']
    assert report.status == ig.INCOMPLETE
    _edit(image, 0x1800)
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and not report.correctable
    plan = ig.plan_correction(image, report)
    assert not plan.steps and plan.refused[0][0] == 'tabelle-generisch'


def test_reviewed_complete_profile_is_the_only_route_to_valid():
    data = bytearray(np.random.default_rng(6).integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    slot = ChecksumSlot('Bereich A', 'crc32-ieee', 0x100, 0x2000, 0x3000)
    data[0x3000:0x3004] = (zlib.crc32(bytes(data[0x100:0x2000])) & 0xFFFFFFFF).to_bytes(4, 'big')
    image = BinaryImage(bytes(data))
    declared = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,))
    complete = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,), complete=True)
    assert ig.check_integrity(image, profile=declared).status == ig.INCOMPLETE
    assert ig.check_integrity(image, profile=complete).status == ig.VALID
    _edit(image, 0x200)
    report = ig.check_integrity(image, profile=complete)
    assert report.status == ig.INVALID
    plan = ig.plan_correction(image, report, profile=complete)
    assert [s.method for s in plan.steps] == ['profil']
    result = ig.apply_correction(image, plan, profile=complete)
    assert result.status == ig.VALID


def test_wrong_profile_is_not_applied():
    image = _multipoint()
    other = ChecksumProfile('0' * 64, 'Test', 'Prüfer', True, (ChecksumSlot('x', 'sum16-bytes', 0, 0xFF, 0x200),))
    report = ig.check_integrity(image, profile=other)
    profile_result = [m for m in report.methods if m.method == 'profil'][0]
    assert not profile_result.regions and 'nicht anwendbar' in profile_result.notes[0]


# --- correction --------------------------------------------------------------

def test_correction_writes_only_storage_fields_and_rechecks():
    image = _multipoint()
    _edit(image, 0x3400)
    _edit(image, 0x5010, 7)
    _edit(image, 0x8FFF, 3)
    report = ig.check_integrity(image)
    plan = ig.plan_correction(image, report)
    assert len(plan.steps) == 3 and {s.method for s in plan.steps} == {'bosch-multipoint'}
    assert all(TABLE <= s.offset < TABLE + 16 * len(RANGES) for s in plan.steps)
    assert any('Herstellersignatur' in w for w in plan.warnings) and any('ROMSYS' in w for w in plan.warnings)
    before = image.read(0, image.size)
    result = ig.apply_correction(image, plan)
    after = image.read(0, image.size)
    changed = set(np.flatnonzero(np.frombuffer(before, np.uint8) != np.frombuffer(after, np.uint8)).tolist())
    assert changed and changed <= plan.positions
    assert result.status == ig.INCOMPLETE and not result.errors
    assert ig.check_integrity(image).status == ig.INCOMPLETE    # independent re-check
    image.undo()                                                # one undo step for the whole correction
    assert image.read(0, image.size) == before


def test_revert_and_recorrect_reproduces_the_original_exactly():
    image = _multipoint()
    _edit(image, 0x1234, 5)
    ig.apply_correction(image, ig.plan_correction(image))
    image.write(0x1234, bytes([image.original[0x1234]]))      # take the edit back
    assert ig.check_integrity(image).status == ig.INVALID
    ig.apply_correction(image, ig.plan_correction(image))
    assert image.materialize() == image.original


def test_file_opened_already_modified_is_invalid_and_correctable():
    """A table member that does not hold on the opened file is an error, not 'unknown'."""
    image = _multipoint()
    data = bytearray(image.original)
    data[0x5555] ^= 0xFF                                        # e.g. a tuned file with a stale checksum
    tuned = BinaryImage(bytes(data))
    report = ig.check_integrity(tuned)
    assert report.status == ig.INVALID
    [bad] = report.errors
    assert 'nicht bestätigt' in bad.note and bad.correctable
    plan = ig.plan_correction(tuned, report)
    assert len(plan.steps) == 1 and 'nicht bestätigt' in plan.steps[0].note
    assert ig.apply_correction(tuned, plan).status == ig.INCOMPLETE


def test_unchanged_file_needs_no_correction():
    image = _multipoint()
    plan = ig.plan_correction(image)
    assert not plan.steps
    with pytest.raises(ValueError):
        ig.apply_correction(image, plan)


def test_stale_plan_is_refused_and_nothing_written():
    image = _multipoint()
    _edit(image, 0x3400)
    plan = ig.plan_correction(image)
    _edit(image, 0x3401)
    snapshot = image.read(0, image.size)
    with pytest.raises(ValueError, match='geändert'):
        ig.apply_correction(image, plan)
    assert image.read(0, image.size) == snapshot


def test_recheck_rejects_bytes_outside_the_documented_positions():
    image = _multipoint()
    _edit(image, 0x3400)
    plan = ig.plan_correction(image)
    before = image.read(0, image.size)
    after = bytearray(ig.corrected_bytes(image, plan))
    after[0x7000] ^= 1
    with pytest.raises(ValueError, match='außerhalb'):
        ig.recheck(image, before, bytes(after), plan)


def test_corrected_copy_leaves_session_and_original_untouched(tmp_path):
    source = tmp_path / 'ecu.bin'
    source.write_bytes(_multipoint().original)
    image = BinaryImage.from_file(str(source))
    _edit(image, 0x3400)
    plan = ig.plan_correction(image)
    revision, current = image.revision, image.read(0, image.size)
    target = tmp_path / 'ecu_pruefsumme.bin'
    log = ig.write_corrected_copy(image, plan, target)
    assert image.revision == revision and image.read(0, image.size) == current     # session unchanged
    assert source.read_bytes() == image.original                                      # original unchanged
    copy = target.read_bytes()
    changed = set(np.flatnonzero(np.frombuffer(current, np.uint8) != np.frombuffer(copy, np.uint8)).tolist())
    assert changed == plan.positions
    saved = json.loads((tmp_path / 'ecu_pruefsumme.bin.korrektur.json').read_text(encoding='utf-8'))
    assert saved == log and saved['flash_approved'] is False and len(saved['steps']) == 1
    assert saved['sha256_output'] != saved['sha256_input']
    assert ig.check_integrity(ig.image_with(image, copy)).status == ig.INCOMPLETE
    with pytest.raises(ValueError):
        ig.write_corrected_copy(image, plan, source)                                 # never over the original
    assert source.read_bytes() == image.original


def test_failed_change_log_leaves_no_partial_output(tmp_path, monkeypatch):
    image = _multipoint()
    _edit(image, 0x3400)
    plan = ig.plan_correction(image)
    from ecu_studio.core import storage
    real = storage.atomic_write

    def failing(path, data, **kwargs):
        if str(path).endswith('.korrektur.json'):
            raise OSError('Datenträger voll')
        return real(path, data, **kwargs)
    monkeypatch.setattr(storage, 'atomic_write', failing)
    with pytest.raises(OSError):
        ig.write_corrected_copy(image, plan, tmp_path / 'out.bin')
    assert not (tmp_path / 'out.bin').exists()
    existing = tmp_path / 'old.bin'
    existing.write_bytes(b'alt')
    with pytest.raises(OSError):
        ig.write_corrected_copy(image, plan, existing)
    assert existing.read_bytes() == b'alt'


# --- incomplete, truncated, corrupt, repeated ----------------------------------

def test_truncated_and_corrupt_files_are_never_valid():
    full = _multipoint().original
    for data in (full[:TABLE + 24], full[:0x6000], full[:TABLE] + b'\x00' * (len(full) - TABLE)):
        report = ig.check_integrity(BinaryImage(data))
        assert report.status in (ig.UNKNOWN, ig.UNSUPPORTED, ig.INCOMPLETE, ig.INVALID)
        assert report.status != ig.VALID
    corrupt = bytearray(full)
    corrupt[TABLE:TABLE + 16 * len(RANGES)] = np.random.default_rng(2).integers(0, 256, 16 * len(RANGES),
                                                                                  dtype=np.uint8).tobytes()
    assert ig.check_integrity(BinaryImage(bytes(corrupt))).status == ig.UNSUPPORTED   # ME7.5 named, no table


def test_repeated_checks_are_identical():
    image = _multipoint()
    _edit(image, 0x3400)
    first = ig.check_integrity(image).asdict()
    for _ in range(3):
        again = ig.check_integrity(image).asdict()
        first['seconds'] = again['seconds'] = 0
        assert again == first


def test_different_software_versions_each_prove_their_own_table():
    a, b = _multipoint(seed=3), _multipoint(seed=11, ranges=RANGES[:3])
    ra, rb = ig.check_integrity(a), ig.check_integrity(b)
    assert len(ra.regions) == len(RANGES) and len(rb.regions) == 3
    assert ra.status == rb.status == ig.INCOMPLETE


# --- EDC17 blocks with signature structures ------------------------------------

def test_signed_edc17_block_is_reported_and_correction_stays_locked():
    from test_edc17_checksum import _build_image
    image = _build_image(block_id=0x20)                      # 'Tuning protection'
    report = ig.check_integrity(image)
    assert any(s.state == 'erkannt' and 'Tuning protection' in s.kind for s in report.signatures)
    assert report.status == ig.INCOMPLETE                     # measured method, no independent proof
    _edit(image, 0x210)                                       # inside the ADD32 range
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and not report.correctable
    plan = ig.plan_correction(image, report)
    assert not plan.steps and any('OEM' in reason for _, reason in plan.refused)
    assert any('Herstellersignatur' in w for w in plan.warnings)


def test_edc17_fast_sums_equal_plain_loops():
    from ecu_studio.core import edc17_checksum as ec

    def add32(p, seed):
        total = seed
        for i in range(0, len(p) - 3, 4):
            total = (total + int.from_bytes(p[i:i + 4], 'little')) & 0xFFFFFFFF
        return total

    def add16(p, seed):
        n = len(p) - len(p) % 2
        total = seed
        if n >= 2:
            for i in range(0, n - 2, 2):
                total = (total + int.from_bytes(p[i:i + 2], 'little')) & 0xFFFFFFFF
            total = (total + (int.from_bytes(p[n - 2:n], 'little') << 16)) & 0xFFFFFFFF
        return total
    rng = np.random.default_rng(8)
    for n in (0, 1, 2, 3, 4, 7, 64, 1001):
        p = rng.integers(0, 256, n, dtype=np.uint8).tobytes()
        assert ec.add32_edc17(p, 0xFADECAFE) == add32(p, 0xFADECAFE)
        assert ec.add16_edc17(p, 0x1234) == add16(p, 0x1234)


# --- background work ------------------------------------------------------------

def test_cancel_and_progress():
    image = _multipoint()
    with pytest.raises(ig.Cancelled):
        ig.check_integrity(image, cancelled=lambda: True)
    seen = []
    ig.check_integrity(image, progress=lambda pct, text: seen.append(pct))
    assert seen == sorted(seen) and seen[-1] == 100


def test_parallel_checks_on_snapshots_while_editing():
    image = _multipoint()
    clean = image.snapshot()
    _edit(image, 0x3400)
    edited = image.snapshot()
    results, errors = [], []

    def run(snap, expected):
        try:
            for _ in range(5):
                results.append(ig.check_integrity(snap).status == expected)
        except Exception as exc:          # pragma: no cover - reported below
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(clean, ig.INCOMPLETE)) for _ in range(3)]
    threads += [threading.Thread(target=run, args=(edited, ig.INVALID)) for _ in range(3)]
    for t in threads:
        t.start()
    for i in range(50):                   # the window keeps editing meanwhile
        _edit(image, 0x5000 + i)
    for t in threads:
        t.join()
    assert not errors and len(results) == 30 and all(results)
    assert clean.dirty_bytes == 0 and edited.dirty_bytes == 1


def test_no_firmware_is_kept_between_checks():
    image = _multipoint(size=0x80000)
    ig.check_integrity(image)
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    for _ in range(5):
        ig.check_integrity(image)
    grown = tracemalloc.get_traced_memory()[0] - base
    tracemalloc.stop()
    assert grown < 256 * 1024


# --- GUI -----------------------------------------------------------------------

def test_gui_panel_check_preview_and_export_hint(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app = QApplication.instance() or QApplication([])
    from ecu_studio.ui.main_window import Window
    w = Window()
    image = _multipoint()
    w.load_state(image, [], [], '', None)

    def wait():
        for _ in range(400):
            app.processEvents()
            if w.integrity_worker is not None and w.integrity_worker.isFinished() and w._integrity_fresh():
                app.processEvents()
                return
            w.integrity_worker and w.integrity_worker.wait(20)
        raise AssertionError('Prüfung nicht beendet')
    w._auto_integrity()
    wait()
    assert 'Unvollständige Prüfung' in w.integrity_info.text()
    assert 'Bosch-Multipoint' in w.integrity_info.text() and 'Signatur' in w.integrity_info.text()
    assert w.checksum_chip.text() == 'CHECKSUMME: UNVOLLSTÄNDIG'
    assert not w.integrity_preview_button.isEnabled()
    _edit(image, 0x3400)
    w.on_edited()
    assert 'veraltet' in w.integrity_info.text() or 'läuft' in w.integrity_info.text()
    w._auto_integrity()
    wait()
    assert 'Unterstützt und ungültig' in w.integrity_info.text() and '0x10028' in w.integrity_info.text()
    assert w.integrity_preview_button.isEnabled()
    # the preview's plan is what the dialog would apply
    plan = ig.plan_correction(w.image, w.integrity_report)
    assert len(plan.steps) == 1
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.close()


def test_preflight_reports_integrity_errors_and_incomplete_checks():
    from ecu_studio.core.preflight import run_preflight
    image = _multipoint()
    _edit(image, 0x3400)
    report = run_preflight(image, [], integrity=ig.check_integrity(image))
    finding = next(f for f in report.findings if f.code == 'checksum-integrity')
    assert finding.level == 'rot' and finding.offset == TABLE + 16 * 2 + 8
    assert not report.checksum_verified
    ig.apply_correction(image, ig.plan_correction(image))
    report = run_preflight(image, [], integrity=ig.check_integrity(image))
    assert not any(f.code == 'checksum-integrity' for f in report.findings)
    finding = next(f for f in report.findings if f.code == 'checksum')
    assert finding.level == 'gelb' and 'Unvollständige Prüfung' in finding.detail
    assert not report.checksum_verified and not report.checks_passed
