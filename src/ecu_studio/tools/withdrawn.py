"""Learned data withdrawn from distribution: never again in a package, a source archive or the repository tree.

The files were part of releases 1.15.0-1.18.2 (git history unchanged). Their training or measurement data has no
documented provenance or clearance (docs/MODELLKARTE.md § 2d/§ 2e). Every published version is listed by
SHA-256, so a renamed copy is found as well; a candidate model under the known name must carry the
training-data clearance (core/candidate_model.py).

Usage: python -m ecu_studio.tools.withdrawn PATH...   (folders, .zip files, Inno Setup manifests of the installer;
       exit code 1 on a finding)
"""
from __future__ import annotations
import hashlib
import json
import sys
import zipfile
from pathlib import Path

WITHDRAWN = {
    '85ad55e56958ee784567a301ea5d6d0ac9f77d611953a0aa5d1a6e6b356bd1b8': 'candidate_model.json (1.15.0-1.17.0)',
    '582c7da303c56a34b0712da4b036775e83cf41ab89c7b93f79928461f573294b': 'candidate_model.json (1.18.0-1.18.2)',
    'e183e7f2e1147b407673c59edcee5ec5a2b8f9f00902edda2af9f52e5f33583b': 'ms43_430069_structure_model.json (1.15.0-1.18.2)',
    '50f3dbd51901457b47211db120c57afd62ad1d78f021ef9845fc5e093c6c040a': 'confidence_calibration.json (1.15.0)',
    '5dd9f1f57d47ce0ff92ae96e1460075520e628c5b441df5d64e9c61b4df026b7': 'confidence_calibration.json (1.16.0-1.18.2)',
}
WITHDRAWN_NAMES = ('ms43_430069_structure_model.json', 'confidence_calibration.json')
CANDIDATE_MODEL = 'candidate_model.json'


def _finding(name: str, data: bytes) -> str | None:
    known = WITHDRAWN.get(hashlib.sha256(data).hexdigest())
    if known:
        return f'{name}: zurückgezogene Datei {known}'
    base = name.replace('\\', '/').rsplit('/', 1)[-1]
    if base in WITHDRAWN_NAMES:
        return f'{name}: zurückgezogener Dateiname'
    if base == CANDIDATE_MODEL:
        from ecu_studio.core.candidate_model import CLEARANCE
        try:
            cleared = json.loads(data.decode('utf-8')).get(CLEARANCE) is True
        except (ValueError, UnicodeDecodeError, AttributeError):
            cleared = False
        if not cleared:
            return f'{name}: Lernmodell ohne Freigabe der Trainingsdaten'
    return None


def scan(path: Path) -> list[str]:
    """Findings in a folder (recursively), a .zip file or a single file."""
    path = Path(path)
    if path.is_dir():
        return [f for p in sorted(path.rglob('*')) if p.is_file()
                for f in [_finding(p.relative_to(path).as_posix(), p.read_bytes())] if f]
    if path.suffix.lower() == '.txt' and path.read_text(encoding='utf-8-sig', errors='replace').startswith(MANIFEST_HEADER):
        return scan_installer_manifest(path)
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as z:
            return [f for info in z.infolist() if not info.is_dir()
                    for f in [_finding(info.filename, z.read(info))] if f]
    found = _finding(path.name, path.read_bytes())
    return [found] if found else []


MANIFEST_HEADER = 'Index\tSourceFilename\t'


def scan_installer_manifest(path: Path) -> list[str]:
    """Inno Setup OutputManifestFile: one line per file compressed into the installer, with its SHA-256."""
    lines = Path(path).read_text(encoding='utf-8-sig', errors='replace').splitlines()
    head = lines[0].split('\t')
    name, digest = head.index('SourceFilename'), head.index('SHA256Sum')
    findings = []
    for line in lines[1:]:
        cells = line.split('\t')
        if len(cells) <= max(name, digest):
            continue
        source, sha = cells[name], cells[digest].lower()
        base = source.replace('\\', '/').rsplit('/', 1)[-1]
        if sha in WITHDRAWN:
            findings.append(f'{source}: zurückgezogene Datei {WITHDRAWN[sha]}')
        elif base in WITHDRAWN_NAMES or base == CANDIDATE_MODEL:
            findings.append(f'{source}: zurückgezogener Dateiname im Installer')
    return findings


def require_clean(path: Path) -> None:
    findings = scan(path)
    if findings:
        raise RuntimeError('Zurückgezogene Lerndaten im Paket:\n' + '\n'.join(findings))


if __name__ == '__main__':
    results = {p: scan(Path(p)) for p in sys.argv[1:]}
    for p, findings in results.items():
        print(f'{p}: ' + ('sauber' if not findings else '\n  ' + '\n  '.join(findings)))
    sys.exit(1 if any(results.values()) else 0)
