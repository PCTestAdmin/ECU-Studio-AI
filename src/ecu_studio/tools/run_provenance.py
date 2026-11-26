"""Provenance and pre-check of a benchmark run (quality phase 6).

Earlier measurements were made more than once with the wrong program state: a relative PYTHONPATH that did
not resolve fell back to an installed older version, and an intermediate state was taken for a release.
Every benchmark run now records which code it measured and refuses to start when that is not the code the
caller expects:

  * ``collect()``  git commit and dirty state of the source tree, source path and import path of
    ``ecu_studio``, Python version, the detection switches (upper-case boolean module constants of the
    detection modules), a digest of all source files, benchmark version and data role;
  * ``require()``  aborts (SystemExit) when ``ecu_studio`` is imported from another path than expected, when
    the commit differs, or when the source tree has uncommitted changes (unless explicitly allowed);
  * ``unchanged()`` compares the source digest at the end of a run with the start: a run during which the code
    changed is marked as not comparable.

The record contains local paths: it stays in the local benchmark output and is never part of a tester report
(tools/tester_report.py exports aggregate counts only). Nothing here touches the network.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import platform
import subprocess
import sys
from pathlib import Path

BENCHMARK_VERSION = 1
SWITCH_MODULES = ('tricore_refs', 'scoped_scan', 'structure_scan', 'curve_records', 'axis_records', 'confidence',
                  'type_status', 'axis_arrays', 'function_id')


def package_root() -> Path:
    """Directory of the imported ``ecu_studio`` package."""
    import ecu_studio
    return Path(ecu_studio.__file__).resolve().parent


def source_digest(root: Path | None = None) -> str:
    """SHA-256 over path and content of every Python file of the package (order independent of the OS)."""
    root = root or package_root()
    h = hashlib.sha256()
    for p in sorted(root.rglob('*.py'), key=lambda q: q.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=30,
                             check=False)
    except (OSError, subprocess.SubprocessError):
        return ''
    return out.stdout.strip() if out.returncode == 0 else ''


def switches() -> dict[str, bool]:
    """Detection switches currently in effect, as module.NAME -> value."""
    out = {}
    for name in SWITCH_MODULES:
        try:
            mod = importlib.import_module(f'ecu_studio.core.{name}')
        except ImportError:
            continue
        for key, value in vars(mod).items():
            if key.isupper() and isinstance(value, bool):
                out[f'{name}.{key}'] = value
    return dict(sorted(out.items()))


def collect(role: str = '', *, extra: dict | None = None) -> dict:
    """Provenance of the code this process measures (local only: contains paths)."""
    root = package_root()
    from ecu_studio import __version__
    dirty = _git(root, 'status', '--porcelain', '--', '.')
    return {
        'benchmark_version': BENCHMARK_VERSION,
        'ecu_studio_version': __version__,
        'import_path': str(root),
        'source_root': str(root.parent),
        'git_commit': _git(root, 'rev-parse', 'HEAD'),
        'git_dirty': bool(dirty),
        'source_digest': source_digest(root),
        'python': platform.python_version(),
        'executable': sys.executable,
        'platform': platform.platform(),
        'switches': switches(),
        'data_role': role,
        **(extra or {}),
    }


def require(expected_src: str | os.PathLike | None = None, expected_commit: str | None = None, *,
            allow_dirty: bool = False) -> dict:
    """Pre-check before a measured run; returns the provenance or exits with a reason."""
    record = collect()
    root = Path(record['import_path'])
    problems = []
    if expected_src is not None:
        want = Path(expected_src).resolve()
        if want.name != 'ecu_studio':
            want = want / 'ecu_studio'
        if root != want:
            problems.append(f'ecu_studio wird aus {root} importiert, erwartet {want}')
    if expected_commit:
        if not record['git_commit']:
            problems.append('Commit des Quellbaums nicht bestimmbar')
        elif not record['git_commit'].startswith(expected_commit.lower()):
            problems.append(f"Commit {record['git_commit'][:10]} statt {expected_commit}")
    if record['git_dirty'] and not allow_dirty:
        problems.append('Quellbaum hat nicht committete Änderungen (gewertete Läufe nur auf einem Commit)')
    if problems:
        raise SystemExit('Benchmark-Vorprüfung fehlgeschlagen: ' + '; '.join(problems))
    return record


def unchanged(record: dict) -> bool:
    """Whether the source files are still those the run started with."""
    return source_digest(Path(record['import_path'])) == record['source_digest']


def comparable(a: dict, b: dict) -> list[str]:
    """Why two runs are not directly comparable (empty = comparable): benchmark version, data role, switches
    other than those the caller compares on purpose are reported, not hidden."""
    out = []
    if a.get('benchmark_version') != b.get('benchmark_version'):
        out.append('verschiedene Benchmark-Versionen')
    if a.get('data_role') != b.get('data_role'):
        out.append('verschiedene Datenrollen')
    sa, sb = a.get('switches', {}), b.get('switches', {})
    diff = sorted(k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k))
    if diff:
        out.append('abweichende Schalter: ' + ', '.join(diff))
    if a.get('source_changed') or b.get('source_changed'):
        out.append('Quellcode während des Laufs geändert')
    return out


__all__ = ['BENCHMARK_VERSION', 'collect', 'comparable', 'require', 'source_digest', 'switches', 'unchanged']
