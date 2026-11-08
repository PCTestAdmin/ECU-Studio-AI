"""Safety regressions from the PR #19 review.

1. Preflight: profile match, known checksums, complete coverage, signatures and flash approval
   are separate states; a partial profile or an incomplete integrity check never looks complete.
2. Multipoint correction: offered only for an unambiguously identified ME7/ME9/MED9 family or
   on strong structural evidence in the original; never for weak or contradicting evidence.
3. Corrected copy: copy and change log stay consistent under injected failures at every step.
"""
import errno
import json

import numpy as np
import pytest

from ecu_studio.core import integrity as ig
from ecu_studio.core import storage
from ecu_studio.core.checksum_audit import ChecksumProfile, ChecksumSlot
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.preflight import run_preflight
from test_integrity import EPK_ME75, RANGES, TABLE, _edit, _multipoint


# --- 1. preflight matrix -------------------------------------------------------

def _crc_image():
    """Random file with one CRC32 slot 0x100–0x1FFF stored at 0x3000 (no multipoint tables)."""
    import zlib
    data = bytearray(np.random.default_rng(6).integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    data[0x3000:0x3004] = (zlib.crc32(bytes(data[0x100:0x2000])) & 0xFFFFFFFF).to_bytes(4, 'big')
    image = BinaryImage(bytes(data))
    slot = ChecksumSlot('Bereich A', 'crc32-ieee', 0x100, 0x2000, 0x3000)
    return image, slot


def _preflight(image, profile=None):
    return run_preflight(image, [], checksum_profile=profile, integrity=ig.check_integrity(image, profile=profile))


def _codes(report):
    return {(f.level, f.code) for f in report.findings if f.code.startswith('checksum')}


def test_match_and_complete_integrity_gives_no_checksum_warning():
    image, slot = _crc_image()
    profile = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,), complete=True)
    _edit(image, 0x2800)                                   # outside the declared (complete) coverage
    report = _preflight(image, profile)
    assert report.integrity_status == ig.VALID and report.profile_status == 'match'
    assert _codes(report) == set() and report.checksum_verified and report.known_checksums_ok
    assert 'vollständig' in report.checksum_summary and 'keine Flashfreigabe' in report.checksum_summary
    assert report.flash_validated is False and report.signatures_checked is False


def test_match_but_incomplete_integrity_is_a_visible_warning_on_an_edited_file():
    """The reviewed bug: a matching partial profile set checksum_verified and skipped the warning."""
    image, slot = _crc_image()
    profile = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,))        # complete=False
    _edit(image, 0x2800)
    report = _preflight(image, profile)
    assert report.profile_status == 'match' and report.integrity_status == ig.INCOMPLETE
    assert ('gelb', 'checksum-coverage') in _codes(report) and report.status != 'grün'
    assert not report.checksum_verified and not report.checks_passed and report.known_checksums_ok
    assert 'UNVOLLSTÄNDIG' in report.checksum_summary
    assert 'NICHT vollständig' in dict(report.stages())['Checksummenabdeckung']
    # without an integrity report the partial profile alone does not prove complete coverage either
    alone = run_preflight(image, [], checksum_profile=profile)
    assert not alone.checksum_verified and ('gelb', 'checksum-coverage') in _codes(alone)


def test_match_but_invalid_integrity_is_critical():
    image = _multipoint()
    slot = ChecksumSlot('frei', 'crc32-ieee', 0x18000, 0x19000, 0x1F000)        # end exclusive
    data = bytearray(image.original)
    import zlib
    data[0x1F000:0x1F004] = (zlib.crc32(bytes(data[0x18000:0x19000])) & 0xFFFFFFFF).to_bytes(4, 'big')
    image = BinaryImage(bytes(data))
    profile = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,))
    _edit(image, 0x3400)                                   # inside a multipoint range, outside the profile
    report = _preflight(image, profile)
    assert report.profile_status == 'match' and report.integrity_status == ig.INVALID
    assert ('rot', 'checksum-integrity') in _codes(report) and report.status == 'rot'
    assert not report.checksum_verified and not report.known_checksums_ok
    assert 'FEHLERHAFT' in report.checksum_summary


def test_mismatch_and_invalid_integrity_is_critical():
    image, slot = _crc_image()
    profile = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,), complete=True)
    _edit(image, 0x200)                                    # inside the declared slot
    report = _preflight(image, profile)
    assert report.profile_status == 'mismatch' and report.integrity_status == ig.INVALID
    assert {('rot', 'checksum'), ('rot', 'checksum-integrity')} <= _codes(report)
    assert not report.checksum_verified and 'FEHLERHAFT' in report.checksum_summary


def test_no_profile_and_incomplete_integrity_is_a_visible_warning():
    image = _multipoint()
    _edit(image, 0x18000)                                  # outside every table range
    report = _preflight(image)
    assert report.integrity_status == ig.INCOMPLETE and ('gelb', 'checksum') in _codes(report)
    assert report.status != 'grün'
    assert not report.checksum_verified and report.known_checksums_ok
    assert 'UNVOLLSTÄNDIG' in report.checksum_summary


@pytest.mark.parametrize('kind', ['unsupported', 'unknown'])
def test_no_profile_and_no_method_never_confirms(kind):
    if kind == 'unsupported':
        data = bytearray(0x8000)
        data[0x100:0x100 + len(EPK_ME75)] = EPK_ME75
    else:
        data = bytearray(np.random.default_rng(9).integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    image = BinaryImage(bytes(data))
    _edit(image, 0x4000)
    report = _preflight(image)
    assert report.integrity_status == {'unsupported': ig.UNSUPPORTED, 'unknown': ig.UNKNOWN}[kind]
    assert ('gelb', 'checksum') in _codes(report) and report.status != 'grün'
    assert not report.checksum_verified and not report.known_checksums_ok and not report.checks_passed
    assert report.checksum_summary == 'Checksummen NICHT verifiziert – nicht flashbereit'
    assert dict(report.stages())['Bekannte Prüfsummen'] == 'keine Prüfsumme geprüft'


def test_unchanged_original_is_green_but_never_complete_without_proof():
    report = _preflight(_multipoint())
    assert report.changed_bytes == 0 and report.status == 'grün' and not _codes(report)
    assert report.known_checksums_ok and not report.checksum_verified and not report.checks_passed
    image, slot = _crc_image()
    complete = ChecksumProfile(image.digest, 'Test', 'Prüfer', True, (slot,), complete=True)
    report = _preflight(image, complete)
    assert report.status == 'grün' and report.checks_passed and report.flash_validated is False


def test_signatures_are_named_but_never_checked():
    report = _preflight(_multipoint())
    stage = dict(report.stages())['Signaturen']
    assert stage.startswith('nicht geprüft') and 'RSA' in stage
    assert dict(report.stages())['Flashfreigabe'].startswith('keine')


def test_gui_status_and_export_text_use_the_separate_states(monkeypatch):
    """The status bar and export dialog show the same separate states (no 'stimmt' shortcut)."""
    from ecu_studio.ui import main_window
    source = open(main_window.__file__, encoding='utf-8').read()
    assert 'report.checksum_summary' in source and 'preflight.stages()' in source
    assert 'alle bekannten Prüfsummen stimmen – keine Flashfreigabe' not in source


# --- 2. multipoint correction gate --------------------------------------------

def _locked(report):
    [m] = [m for m in report.methods if m.method == 'bosch-multipoint']
    return m


def test_identified_me7_keeps_its_correction():
    image = _multipoint()
    _edit(image, 0x3400)
    report = ig.check_integrity(image)
    m = _locked(report)
    assert m.evidence['basis'] == 'familie' and not m.correction and report.correctable
    assert ig.plan_correction(image, report).steps


def test_unknown_family_with_few_proven_entries_is_check_only():
    image = _multipoint(epk=None)                          # 5 proven entries, family unknown
    _edit(image, 0x3400)
    report = ig.check_integrity(image)
    m = _locked(report)
    assert report.status == ig.INVALID and report.errors          # still checked and shown
    assert m.evidence['basis'] == 'gesperrt' and m.correction.startswith('gesperrt')
    assert 'SHA-256-gebundenes Profil' in m.correction
    assert not report.correctable
    plan = ig.plan_correction(image, report)
    assert not plan.steps and plan.refused[0][0] == 'bosch-multipoint'
    with pytest.raises(ValueError):
        ig.apply_correction(image, plan)


def test_single_coincidental_table_entry_never_unlocks_a_correction():
    image = _multipoint(epk=None, ranges=[(0x1000, 0x1FFF)])
    _edit(image, 0x1800)
    report = ig.check_integrity(image)
    assert report.status == ig.INVALID and not report.correctable
    assert _locked(report).evidence['proven_entries'] == 1


def test_unknown_family_with_strong_structural_proof_is_correctable_and_marked():
    """Like the ME9 reference (family not identified, 63 entries proven): supported, but labelled."""
    ranges = [(TABLE, TABLE + 0x2FF)] + [(0x400 * k, 0x400 * k + 0x3FF) for k in range(1, 40)]
    image = _multipoint(epk=None, ranges=ranges)
    _edit(image, 0x1400)
    report = ig.check_integrity(image)
    m = _locked(report)
    assert m.evidence['basis'] == 'struktur' and m.evidence['proven_entries'] == 40
    assert any('nur durch 40' in n for n in m.notes) and report.correctable
    assert report.status == ig.INVALID
    plan = ig.plan_correction(image, report)
    assert plan.steps and any('nicht eindeutig identifiziert' in w for w in plan.warnings)
    result = ig.apply_correction(image, plan)
    assert not result.errors and result.status == ig.INCOMPLETE      # never valid without identification


def test_family_identified_as_something_else_locks_multipoint(monkeypatch):
    from ecu_studio.core import identification
    real = identification.identify

    def as_edc17(image):
        ident = real(image)
        ident.family, ident.level = 'EDC17C46', 'eindeutig'
        return ident
    monkeypatch.setattr(identification, 'identify', as_edc17)
    ranges = [(TABLE, TABLE + 0x2FF)] + [(0x400 * k, 0x400 * k + 0x3FF) for k in range(1, 40)]
    image = _multipoint(epk=None, ranges=ranges)                     # strong structure, wrong family
    _edit(image, 0x1400)
    report = ig.check_integrity(image)
    assert 'EDC17C46' in _locked(report).correction and not report.correctable


def test_already_modified_original_needs_a_proven_majority():
    """Entries that do not hold on the opened original count as wrong only with a proven majority."""
    good = _multipoint(ranges=RANGES[:3]).original
    data = bytearray(good)
    for s, _ in RANGES[1:3]:                               # two of three ranges changed before opening
        data[s + 0x10] ^= 0xFF
    report = ig.check_integrity(BinaryImage(bytes(data)))
    m = _locked(report)
    assert m.count(ig.UNPROVEN) == 2 and not m.count(ig.BAD) and not report.correctable
    assert any('zu wenige' in r.note for r in m.regions)
    data = bytearray(_multipoint().original)                # 1 of 5 changed: majority proven
    data[RANGES[2][0] + 0x10] ^= 0xFF
    report = ig.check_integrity(BinaryImage(bytes(data)))
    assert len(report.errors) == 1 and report.correctable


# --- 3. corrected copy under failures ----------------------------------------

@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'ecu.bin'
    source.write_bytes(_multipoint().original)
    image = BinaryImage.from_file(str(source))
    _edit(image, 0x3400)
    plan = ig.plan_correction(image)
    target = tmp_path / 'out.bin'
    log = tmp_path / 'out.bin.korrektur.json'
    target.write_bytes(b'vorherige Kopie')
    log.write_bytes(b'{"vorheriges": "Protokoll"}')
    return image, plan, target, log, source


def _unchanged(case_):
    image, _, target, log, source = case_
    return (target.read_bytes() == b'vorherige Kopie' and log.read_bytes() == b'{"vorheriges": "Protokoll"}'
            and source.read_bytes() == image.original)


def _fail_on(monkeypatch, predicate, error):
    """Fail writing NEW content to matching paths; restoring the previous content still works."""
    real = storage.atomic_write

    def patched(path, data, **kwargs):
        if predicate(str(path)) and b'vorherig' not in data:
            raise error
        return real(path, data, **kwargs)
    monkeypatch.setattr(storage, 'atomic_write', patched)


def test_success_replaces_copy_and_log_consistently(case):
    image, plan, target, log, source = case
    result = ig.write_corrected_copy(image, plan, target)
    saved = json.loads(log.read_text(encoding='utf-8'))
    import hashlib
    assert saved == result and saved['sha256_output'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert (target.parent / 'out.bin.bak').read_bytes() == b'vorherige Kopie'
    assert source.read_bytes() == image.original


def test_disk_full_while_writing_the_copy(case, monkeypatch):
    image, plan, target, *_ = case
    _fail_on(monkeypatch, lambda p: p.endswith('out.bin'), OSError(errno.ENOSPC, 'Datenträger voll'))
    with pytest.raises(ig.CopyNotSaved) as err:
        ig.write_corrected_copy(image, plan, target)
    assert err.value.restored and 'Kopie schreiben' in str(err.value) and _unchanged(case)


def test_write_error_on_the_change_log(case, monkeypatch):
    image, plan, target, *_ = case
    _fail_on(monkeypatch, lambda p: p.endswith('.korrektur.json'), OSError(errno.EIO, 'Schreibfehler'))
    with pytest.raises(OSError) as err:
        ig.write_corrected_copy(image, plan, target)
    assert err.value.restored and 'Änderungsprotokoll schreiben' in str(err.value) and _unchanged(case)


def test_failed_verification_after_both_files_were_written(case, monkeypatch):
    """Copy and log written, the read-back of the log fails: both are rolled back, no log survives."""
    image, plan, target, log, _ = case
    from pathlib import Path
    real = Path.read_bytes
    calls = {'n': 0}

    def flaky(self):
        if self.name == 'out.bin.korrektur.json':
            calls['n'] += 1
            if calls['n'] == 2:                            # 1st read: the previous log before writing
                return b'{"sha256_output": "falsch"}'
        return real(self)
    monkeypatch.setattr(Path, 'read_bytes', flaky)
    with pytest.raises(ig.CopyNotSaved) as err:
        ig.write_corrected_copy(image, plan, target)
    monkeypatch.undo()
    assert err.value.restored and 'Änderungsprotokoll prüfen' in str(err.value) and _unchanged(case)


def test_stored_copy_differs_or_cannot_be_read(case, monkeypatch):
    image, plan, target, *_ = case
    from pathlib import Path
    real = Path.read_bytes
    state = {'failed': False}

    def bad_copy(self):
        data = real(self)
        if self.name == 'out.bin' and data != b'vorherige Kopie' and not state['failed']:
            state['failed'] = True                         # the read-back of the new copy
            raise OSError(errno.EIO, 'Lesefehler')
        return data
    monkeypatch.setattr(Path, 'read_bytes', bad_copy)
    with pytest.raises(ig.CopyNotSaved) as err:
        ig.write_corrected_copy(image, plan, target)
    monkeypatch.undo()
    assert err.value.restored and 'gespeicherte Kopie prüfen' in str(err.value) and _unchanged(case)


def test_interruption_restores_and_is_passed_on(case, monkeypatch):
    image, plan, target, *_ = case
    _fail_on(monkeypatch, lambda p: p.endswith('.korrektur.json'), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        ig.write_corrected_copy(image, plan, target)
    assert _unchanged(case)


def test_failed_restore_is_reported_and_never_silent(case, monkeypatch):
    image, plan, target, log, _ = case
    real = storage.atomic_write
    calls = []

    def failing(path, data, **kwargs):
        calls.append(str(path))
        if str(path).endswith('.korrektur.json') or (str(path).endswith('out.bin') and len(calls) > 1):
            raise OSError(errno.EIO, 'Datenträger getrennt')
        return real(path, data, **kwargs)
    monkeypatch.setattr(storage, 'atomic_write', failing)
    with pytest.raises(ig.CopyNotSaved) as err:
        ig.write_corrected_copy(image, plan, target)
    text = str(err.value)
    assert err.value.restored is False and 'Wiederherstellung fehlgeschlagen' in text
    assert 'nicht verwenden' in text and 'out.bin.bak' in text
    assert (target.parent / 'out.bin.bak').read_bytes() == b'vorherige Kopie'
    # whatever is left: no change log documents the unlogged copy
    assert not log.exists() or json.loads(log.read_text(encoding='utf-8')).get('vorheriges') == 'Protokoll'


def test_new_target_without_previous_files_is_removed_on_failure(tmp_path, monkeypatch):
    image = _multipoint()
    _edit(image, 0x3400)
    plan = ig.plan_correction(image)
    _fail_on(monkeypatch, lambda p: p.endswith('.korrektur.json'), OSError(errno.ENOSPC, 'Datenträger voll'))
    with pytest.raises(ig.CopyNotSaved):
        ig.write_corrected_copy(image, plan, tmp_path / 'neu.bin')
    assert not list(tmp_path.iterdir())


def test_original_is_never_a_target_or_a_log(case, tmp_path):
    image, plan, _, _, source = case
    with pytest.raises(ValueError):
        ig.write_corrected_copy(image, plan, source)
    tricky = tmp_path / 'x.bin'
    image2 = BinaryImage.from_file(str(source))
    named = tmp_path / 'x.bin.korrektur.json'
    named.write_bytes(image2.original)
    image3 = BinaryImage.from_file(str(named))
    _edit(image3, 0x3400)
    with pytest.raises(ValueError):
        ig.write_corrected_copy(image3, ig.plan_correction(image3), tricky)    # log path = the original
    assert named.read_bytes() == image2.original and source.read_bytes() == image.original
