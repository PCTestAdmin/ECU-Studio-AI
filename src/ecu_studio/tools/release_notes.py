"""Release preparation checks: tag == package version, notes from CHANGELOG.md.

Usage (CI): python -m ecu_studio.tools.release_notes v1.15.0 --out notes.md
Fails when the tag does not match ecu_studio.__version__ or CHANGELOG.md has no
"## 1.15.0 ..." section – a release never ships without its change notes.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from ecu_studio import __version__
from ecu_studio.core.updates import parse_version


def notes_for(changelog: str, version: str) -> str:
    """Body of the '## <version>' section (up to the next '## ' heading)."""
    match = re.search(rf'^## {re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
    if not match or not match.group(1).strip():
        raise ValueError(f'CHANGELOG.md enthält keinen Abschnitt „## {version}“')
    return match.group(1).strip() + '\n'


FOOTER = """
---
**Installation:** `ECU-Studio-AI-<version>-windows-x64.zip` entpacken und `ECU-Studio-AI.exe` starten, oder den
Installer `ECU-Studio-AI-<version>-setup.exe` ausführen. Bestehende Installationen finden das Update unter „Einstellungen → Jetzt nach Updates suchen“ (automatisch nur, wenn eingeschaltet).

**Windows-Warnung beim ersten Start:** Die EXE ist noch nicht code-signiert. Bei „Der Computer wurde durch Windows
geschützt“ auf „Weitere Informationen“ → „Trotzdem ausführen“ klicken. Echtheit prüfen: SHA-256 gegen die
`.sha256`-Datei, Build-Herkunft mit `gh attestation verify <datei> --repo PCTestAdmin/ECU-Studio-AI`.
"""


def check_tag(tag: str, version: str = __version__) -> str:
    parsed = parse_version(tag)
    if parsed is None or not tag.startswith('v'):
        raise ValueError(f'Tag {tag!r} ist keine stabile Version der Form v1.2.3')
    if '.'.join(map(str, parsed)) != version:
        raise ValueError(f'Tag {tag} passt nicht zu ecu_studio.__version__ = {version}')
    return version


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--changelog', type=Path, default=Path(__file__).resolve().parents[3] / 'CHANGELOG.md')
    args = parser.parse_args(argv)
    try:
        version = check_tag(args.tag)
        notes = notes_for(args.changelog.read_text(encoding='utf-8'), version)
    except ValueError as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        return 1
    args.out.write_text(notes + FOOTER, encoding='utf-8')
    print(f'Release {version}: {len(notes.splitlines())} Zeilen Änderungshinweise')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
