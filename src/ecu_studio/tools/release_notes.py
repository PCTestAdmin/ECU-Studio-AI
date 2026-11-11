"""Release preparation checks: tag == package version, title, bilingual notes.

Usage (CI): python -m ecu_studio.tools.release_notes v1.15.0 --out notes.md --title-out title.txt
            [--package dist/ECU-Studio-AI]

Fails (exit 1) when
- the tag is not a stable version or does not match ecu_studio.__version__,
- CHANGELOG.md has no "## 1.15.0 ..." section (German notes),
- docs/RELEASE_NOTES_1.15.0.md is missing, names another version, or lacks a complete
  "## Deutsch" / "## English" pair (English = translation: same number of "###" sections),
- --package is given and the built folder (VERSION.txt, RUNTIME_INVENTORY.json) has another version.
A release never ships without its change notes in both languages.

The release body: German notes (CHANGELOG section), "---", the English section of the release notes, "---",
installation hints in German and English. Relative links become absolute links to the files at the tag. The
in-app update dialog shows only the part before the first "---" (core/updates.py parse_release).
The title is always "ECU Studio AI v1.2.3".
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from ecu_studio import __version__
from ecu_studio.core.updates import parse_version

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = 'PCTestAdmin/ECU-Studio-AI'


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

FOOTER_EN = """
**Installation:** unzip `ECU-Studio-AI-<version>-windows-x64.zip` and start `ECU-Studio-AI.exe`, or run the
installer `ECU-Studio-AI-<version>-setup.exe`. Existing installations find the update under "Settings → Check for
updates now" (automatically only if enabled).

**Windows warning on first start:** the EXE is not code-signed yet. On "Windows protected your PC" click "More info"
→ "Run anyway". Verify authenticity: SHA-256 against the `.sha256` file, build provenance with
`gh attestation verify <file> --repo PCTestAdmin/ECU-Studio-AI`.
"""


def check_tag(tag: str, version: str = __version__) -> str:
    parsed = parse_version(tag)
    if parsed is None or not tag.startswith('v'):
        raise ValueError(f'Tag {tag!r} ist keine stabile Version der Form v1.2.3')
    if '.'.join(map(str, parsed)) != version:
        raise ValueError(f'Tag {tag} passt nicht zu ecu_studio.__version__ = {version}')
    return version


def release_title(tag: str, version: str = __version__) -> str:
    """'ECU Studio AI v1.2.3' – the only accepted release title."""
    check_tag(tag, version)
    return f'ECU Studio AI {tag}'


def _section(doc: str, heading: str) -> str:
    match = re.search(rf'^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)', doc, re.M | re.S)
    if not match:
        return ''
    text = match.group(1).strip()
    if text.endswith('---'):
        text = text[:-3].rstrip()
    return text


def bilingual_sections(doc: str, version: str) -> tuple[str, str]:
    """(German, English) section of docs/RELEASE_NOTES_<version>.md; ValueError when incomplete."""
    first = doc.lstrip('﻿').split('\n', 1)[0].strip()
    match = re.fullmatch(r'# ECU Studio AI (\S+) [–-] Release Notes', first)
    if not match:
        raise ValueError(f'Release Notes: erste Zeile muss „# ECU Studio AI {version} – Release Notes“ sein, ist {first!r}')
    if match.group(1) != version:
        raise ValueError(f'Release Notes gehören zu Version {match.group(1)}, nicht zu {version}')
    german, english = _section(doc, 'Deutsch'), _section(doc, 'English')
    if not german:
        raise ValueError('Release Notes: Abschnitt „## Deutsch“ fehlt oder ist leer')
    if not english:
        raise ValueError('Release Notes: Abschnitt „## English“ fehlt oder ist leer (Übersetzung fehlt)')
    de_parts = len(re.findall(r'^### ', german, re.M))
    en_parts = len(re.findall(r'^### ', english, re.M))
    if de_parts != en_parts:
        raise ValueError(f'Release Notes: Übersetzung unvollständig ({de_parts} deutsche, {en_parts} englische Unterabschnitte)')
    return german, english


def absolute_links(text: str, tag: str, prefix: str = '', repository: str = REPOSITORY) -> str:
    """](file.md) / ](docs/x.md#a) -> https://github.com/<repo>/blob/<tag>/<prefix>file.md; web links and anchors stay."""
    base = f'https://github.com/{repository}/blob/{tag}/'
    return re.sub(r'\]\((?!https?://|#|mailto:)([^)\s]+)\)', lambda m: f']({base}{prefix}{m.group(1)})', text)


def build_body(changelog: str, doc: str, tag: str, version: str = __version__, repository: str = REPOSITORY) -> str:
    check_tag(tag, version)
    german = absolute_links(notes_for(changelog, version).strip(), tag, '', repository)     # links relative to the root
    english = absolute_links(bilingual_sections(doc, version)[1], tag, 'docs/', repository)  # relative to docs/
    footer = FOOTER.strip().removeprefix('---').strip().replace('<version>', version)
    footer_en = FOOTER_EN.strip().replace('<version>', version)
    body = f'{german}\n\n---\n\n## English\n\n{english}\n\n---\n{footer}\n\n{footer_en}\n'
    left = re.findall(r'\]\((?!https?://|#|mailto:)[^)\s]+\)', body)
    if left:
        raise ValueError(f'Relative Links im Release-Text: {left[:3]}')
    return body


def check_package(folder: Path, version: str) -> None:
    """The built program folder must carry the same version as the tag."""
    try:
        built = (folder / 'VERSION.txt').read_text(encoding='ascii').strip()
        inventory = json.loads((folder / 'RUNTIME_INVENTORY.json').read_text(encoding='utf-8')).get('version')
    except (OSError, ValueError) as exc:
        raise ValueError(f'Paket {folder} nicht lesbar: {exc}') from exc
    if built != version or inventory != version:
        raise ValueError(f'Paket hat Version {built} (Inventar {inventory}), erwartet {version}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--title-out', type=Path)
    parser.add_argument('--changelog', type=Path, default=ROOT / 'CHANGELOG.md')
    parser.add_argument('--docs', type=Path, default=ROOT / 'docs')
    parser.add_argument('--package', type=Path, help='built program folder (dist/ECU-Studio-AI) to compare')
    parser.add_argument('--repository', default=REPOSITORY)
    args = parser.parse_args(argv)
    try:
        version = check_tag(args.tag)
        doc_path = args.docs / f'RELEASE_NOTES_{version}.md'
        if not doc_path.is_file():
            raise ValueError(f'{doc_path.name} fehlt (deutsche und englische Release Notes)')
        body = build_body(args.changelog.read_text(encoding='utf-8'), doc_path.read_text(encoding='utf-8'),
                          args.tag, version, args.repository)
        if args.package:
            check_package(args.package, version)
    except ValueError as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        return 1
    args.out.write_text(body, encoding='utf-8', newline='\n')
    if args.title_out:
        args.title_out.write_text(release_title(args.tag) + '\n', encoding='utf-8', newline='\n')
    print(f'Release {version}: „{release_title(args.tag)}“, {len(body.splitlines())} Zeilen Release-Text (DE + EN)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
