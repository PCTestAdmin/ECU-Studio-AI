"""Repository hygiene: nothing private, no third-party binaries, no firmware outside examples/."""
import re
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tracked() -> list[str]:
    if not shutil.which('git') or not (ROOT / '.git').exists():
        pytest.skip('kein Git-Checkout')
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    return out.stdout.splitlines()


def test_no_executables_archives_or_firmware_outside_examples():
    bad = [p for p in _tracked()
           if re.search(r'\.(exe|dll|zip|msi|ols|kp|ori)$', p, re.I)
           or (re.search(r'\.bin$', p, re.I) and not p.startswith('examples/'))]
    assert not bad, f'nicht ins Repository: {bad}'


def test_no_local_paths_or_scratch_folders_tracked():
    # e.g. a pytest --basetemp folder that ended up in a commit
    bad = [p for p in _tracked()
           if re.search(r'(^|/)(Users|AppData|pytest-of-|pytest-\d+)', p) or '.update-staging/' in p or '.backup/' in p]
    assert not bad, f'lokale Zwischenordner im Repository: {bad}'


def test_examples_are_documented_and_root_stays_small():
    tracked = _tracked()
    assert 'examples/README.md' in tracked and 'docs/README.md' in tracked
    root_files = sorted(p for p in tracked if '/' not in p)
    allowed = {'.editorconfig', '.gitattributes', '.gitignore', 'CHANGELOG.md', 'CONTRIBUTING.md', 'LICENSE',
               'README.md', 'ROADMAP.md', 'SECURITY.md', 'build_exe_windows.bat', 'build_release.ps1', 'pyproject.toml',
               'start_windows.bat'}
    assert set(root_files) <= allowed, f'neue Dateien im Wurzelverzeichnis: {set(root_files) - allowed}'
