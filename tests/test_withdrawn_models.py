"""1.19.0: learned data of 1.15.0-1.18.2 without documented provenance is withdrawn from every distribution."""
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path
import pytest
from ecu_studio.core.model import MapDefinition
from ecu_studio.tools import withdrawn

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'ecu_studio' / 'recognition' / 'data'


def test_the_repository_tree_contains_no_withdrawn_learned_data():
    for name in ('candidate_model.json', 'ms43_430069_structure_model.json', 'confidence_calibration.json'):
        assert not (DATA / name).exists(), name
    assert withdrawn.scan(ROOT / 'src') == []
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True)
    if tracked.returncode == 0:                          # source archives (GitHub) contain exactly the tracked files
        names = {p.rsplit('/', 1)[-1] for p in tracked.stdout.splitlines()}
        assert not names & {*withdrawn.WITHDRAWN_NAMES, withdrawn.CANDIDATE_MODEL}


def test_withdrawn_checksums_are_the_published_files():
    """Where the history is available (not in a shallow CI checkout), each listed hash is a blob of an old release."""
    blobs = {'c86891f': 'candidate_model.json (1.15.0-1.17.0)', '62eb523': 'candidate_model.json (1.18.0-1.18.2)',
             'bc713e5': 'ms43_430069_structure_model.json (1.15.0-1.18.2)',
             '880ca62': 'confidence_calibration.json (1.15.0)', '9bd64af': 'confidence_calibration.json (1.16.0-1.18.2)'}
    checked = 0
    for blob, label in blobs.items():
        out = subprocess.run(['git', 'cat-file', 'blob', blob], cwd=ROOT, capture_output=True)
        if out.returncode != 0:
            continue
        assert withdrawn.WITHDRAWN[hashlib.sha256(out.stdout).hexdigest()] == label
        checked += 1
    if not checked:
        pytest.skip('Git-Historie nicht verfügbar')


def test_scan_finds_renamed_copies_unknown_models_and_installer_entries(tmp_path, monkeypatch):
    fake = b'{"withdrawn": true}'
    monkeypatch.setitem(withdrawn.WITHDRAWN, hashlib.sha256(fake).hexdigest(), 'Testdatei')
    pkg = tmp_path / 'pkg'
    (pkg / 'data').mkdir(parents=True)
    (pkg / 'data' / 'harmless.json').write_bytes(fake)                       # renamed copy: found by hash
    (pkg / 'data' / 'candidate_model.json').write_text('{"features": []}', encoding='utf-8')
    (pkg / 'data' / 'confidence_calibration.json').write_text('{}', encoding='utf-8')
    (pkg / 'data' / 'ok.json').write_text('{}', encoding='utf-8')
    found = withdrawn.scan(pkg)
    assert len(found) == 3 and not any('ok.json' in f for f in found)
    with zipfile.ZipFile(tmp_path / 'p.zip', 'w') as z:
        z.write(pkg / 'data' / 'harmless.json', 'ECU-Studio-AI/x.json')
        z.writestr('ECU-Studio-AI/candidate_model.json', json.dumps({'training_data_cleared': True}))
    assert [f.split(':')[0] for f in withdrawn.scan(tmp_path / 'p.zip')] == ['ECU-Studio-AI/x.json']
    manifest = tmp_path / 'setup-manifest.txt'
    manifest.write_text('﻿Index\tSourceFilename\tSize\tSHA256Sum\n'
                        f'0\tdist\\a\\x.json\t19\t{hashlib.sha256(fake).hexdigest().upper()}\n'
                        f'1\tdist\\a\\ms43_430069_structure_model.json\t2\t{"0" * 64}\n'
                        f'2\tdist\\a\\ok.json\t2\t{"1" * 64}\n', encoding='utf-8')
    assert len(withdrawn.scan(manifest)) == 2
    with pytest.raises(RuntimeError):
        withdrawn.require_clean(pkg)
    (pkg / 'data' / 'harmless.json').unlink(); (pkg / 'data' / 'candidate_model.json').unlink()
    (pkg / 'data' / 'confidence_calibration.json').unlink()
    withdrawn.require_clean(pkg)


def test_every_package_is_checked_before_release():
    source = (ROOT / 'src/ecu_studio/tools/build_portable_runtime.py').read_text(encoding='utf-8')
    assert source.count('require_clean(') == 2                          # program folder and ZIP
    assert 'OutputManifestFile=' in (ROOT / 'packaging/installer.iss').read_text(encoding='utf-8')
    script = (ROOT / 'build_release.ps1').read_text(encoding='utf-8')
    assert '-m ecu_studio.tools.withdrawn' in script and 'setup-manifest.txt' in script


def test_the_application_starts_and_detects_without_any_learned_model(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    from ecu_studio.core import candidate_model
    from ecu_studio.core.confidence import apply_confidence
    from ecu_studio.core.model import BinaryImage
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    from ecu_studio.ui.main_window import Window
    candidate_model.load_model.cache_clear()
    assert candidate_model.model_status() == candidate_model.NO_MODEL
    image = BinaryImage((ROOT / 'examples/demo/demo_synthetic.bin').read_bytes())
    found = scan_calibration_candidates(image)
    assert {0x1000, 0x2000}.issubset({m.offset for m in found})        # rule-based detection unchanged
    app = QApplication.instance() or QApplication([])
    w = Window()
    maps = apply_confidence(found + [MapDefinition('Definiert', 0x10, 2, 2, 'u8', source='xdf')])
    w.load_state(image, maps, [], '', None)
    shown = [w.catalog_model.data(w.catalog_model.index(r, 0), role) or ''
             for r in range(w.catalog_model.rowCount())
             for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole)]
    assert shown and not any('%' in s for s in shown)                   # kind of evidence, never a percentage
    assert all(m.calibrated_rate is None for m in w.maps)
    w.saved_fingerprint = w.project_state()
    w.close()
