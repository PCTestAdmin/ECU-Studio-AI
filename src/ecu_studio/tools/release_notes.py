"""Release preparation checks: tag == package version, title, bilingual notes.

Usage (CI): python -m ecu_studio.tools.release_notes v1.15.0 --out notes.md --title-out title.txt
            [--package dist/ECU-Studio-AI] [--channel-out channel.txt]

Fails (exit 1) when
- the tag is not a version of the form v1.2.3 or v1.2.3-rcN (core/app_version.py) or does not match
  ecu_studio.__version__ (and pyproject.toml),
- CHANGELOG.md has no "## 1.15.0 ..." section (German notes; for a candidate "## 1.21.0-rc1 ..."),
- docs/RELEASE_NOTES_1.15.0.md is missing, names another version, or lacks a complete
  "## Deutsch" / "## English" pair (English = translation: same number of "###" sections),
- --package is given and the built folder (VERSION.txt, RUNTIME_INVENTORY.json) has another version,
- for a release candidate: the notes do not call it a pre-release in both languages ("Vorabversion" /
  "pre-release"), or they contain a percentage (no unproven quality promises in candidate notes),
- the CHANGELOG heading or the head of the release notes still says "nicht veröffentlicht" / "geplant" /
  "in Entwicklung" (placeholders of the development branch, replaced at release time).
A release never ships without its change notes in both languages.

The release body: German notes (CHANGELOG section), "---", the English section of the release notes, "---",
installation hints in German and English. Relative links become absolute links to the files at the tag. The
in-app update dialog shows only the part before the first "---" (core/updates.py parse_release).
The title is always "ECU Studio AI v1.2.3"; a candidate: "ECU Studio AI v1.21.0-rc1 (Vorabversion / Pre-release)",
and its body starts with a bilingual pre-release notice and ends with a footer for the test channel.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from ecu_studio import __version__
from ecu_studio.core import app_version

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = 'PCTestAdmin/ECU-Studio-AI'


def notes_for(changelog: str, version: str) -> str:
    """Body of the '## <version>' section (up to the next '## ' heading)."""
    # '## 1.21.0' must not match '## 1.21.0-rc1' and '## 1.21.0-rc1' not '## 1.21.0-rc10'.
    match = re.search(rf'^## {re.escape(version)}(?![\w.-])[^\n]*\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
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


PRERELEASE_NOTICE = """> **Vorabversion (Release Candidate) – nicht für den produktiven Einsatz.** Zum Testen gedacht; automatisch
> erkannte Kennfelder bleiben ungeprüfte Vorschläge. Bestehende Installationen bekommen diese Version nur über den
> ausdrücklich eingeschalteten Testkanal angeboten, der stabile Update-Kanal bietet sie nicht an.
>
> **Pre-release (release candidate) – not for production use.** Meant for testing; automatically detected maps
> remain unchecked suggestions. Existing installations are offered this version only through the explicitly enabled
> test channel; the stable update channel does not offer it."""

FOOTER_PRERELEASE = """
---
**Installation:** `ECU-Studio-AI-<version>-windows-x64.zip` entpacken und `ECU-Studio-AI.exe` starten, oder den
Installer `ECU-Studio-AI-<version>-setup.exe` ausführen. Als Update erscheint diese Vorabversion nur mit
„Einstellungen → Testkanal: Vorabversionen (Release Candidates) anbieten …“; die vorherige Version bleibt als
Sicherung erhalten („Einstellungen → Vorherige Version wiederherstellen …“).

**Windows-Warnung beim ersten Start:** Die EXE ist noch nicht code-signiert. Bei „Der Computer wurde durch Windows
geschützt“ auf „Weitere Informationen“ → „Trotzdem ausführen“ klicken. Echtheit prüfen: SHA-256 gegen die
`.sha256`-Datei, Build-Herkunft mit `gh attestation verify <datei> --repo PCTestAdmin/ECU-Studio-AI`.
"""

FOOTER_PRERELEASE_EN = """
**Installation:** unzip `ECU-Studio-AI-<version>-windows-x64.zip` and start `ECU-Studio-AI.exe`, or run the
installer `ECU-Studio-AI-<version>-setup.exe`. As an update this pre-release appears only with "Settings → Test
channel: offer pre-releases (release candidates) …"; the previous version is kept as a backup ("Settings → Restore
previous version …").

**Windows warning on first start:** the EXE is not code-signed yet. On "Windows protected your PC" click "More info"
→ "Run anyway". Verify authenticity: SHA-256 against the `.sha256` file, build provenance with
`gh attestation verify <file> --repo PCTestAdmin/ECU-Studio-AI`.
"""


def pyproject_version(root: Path = ROOT) -> str | None:
    match = re.search(r'^version = "([^"]+)"', (root / 'pyproject.toml').read_text(encoding='utf-8'), re.M)
    return match.group(1) if match else None


def check_tag(tag: str, version: str = __version__) -> str:
    parsed = app_version.parse_tag(tag)
    if parsed is None:
        raise ValueError(f'Tag {tag!r} ist keine Version der Form v1.2.3 oder v1.2.3-rcN')
    if parsed.text != version:
        raise ValueError(f'Tag {tag} passt nicht zu ecu_studio.__version__ = {version}')
    return version


def is_prerelease(tag: str) -> bool:
    parsed = app_version.parse_tag(tag)
    if parsed is None:
        raise ValueError(f'Tag {tag!r} ist keine Version der Form v1.2.3 oder v1.2.3-rcN')
    return parsed.prerelease


def release_title(tag: str, version: str = __version__) -> str:
    """'ECU Studio AI v1.2.3', for a candidate 'ECU Studio AI v1.2.3-rcN (Vorabversion / Pre-release)'."""
    check_tag(tag, version)
    return f'ECU Studio AI {tag}' + (' (Vorabversion / Pre-release)' if is_prerelease(tag) else '')


def check_prerelease_notes(german: str, english: str) -> None:
    """A candidate's notes name it a pre-release in both languages and make no percentage claims."""
    if not re.search(r'Vorabversion|Release Candidate', german):
        raise ValueError('Release Notes eines RC: der deutsche Teil nennt ihn nicht „Vorabversion“ / „Release Candidate“')
    if not re.search(r'pre-release|release candidate', english, re.I):
        raise ValueError('Release Notes eines RC: der englische Teil nennt ihn nicht „pre-release“ / „release candidate“')
    for label, text in (('deutsch', german), ('englisch', english)):
        if '%' in text or re.search(r'\bProzent\b|\bpercent\b', text, re.I):
            raise ValueError(f'Release Notes eines RC ({label}): keine Prozentangaben (Kennzahlen gehören in den '
                             'Entwicklungsbericht)')


# Placeholders of the development branch that must be gone in the commit that is tagged (1.21.0-rc1).
UNRELEASED = re.compile(r'nicht veröffentlicht|in Entwicklung|\bgeplant\b|not published|unreleased|in development',
                        re.I)


def check_release_time(changelog: str, doc: str, version: str) -> None:
    """The CHANGELOG heading of ``version`` and the head of its release notes (before "## Deutsch") are final.

    On the development branch both say "geplant, nicht veröffentlicht"; they are set at release time only
    (docs/RELEASE.md). A tag on such a commit would publish the placeholder.
    """
    heading = re.search(rf'^## {re.escape(version)}(?![\w.-])([^\n]*)', changelog, re.M)
    if heading and UNRELEASED.search(heading.group(1)):
        raise ValueError(f'CHANGELOG.md: Überschrift „## {version}{heading.group(1)}“ ist noch ein Platzhalter '
                         '(beim Release Datum statt „nicht veröffentlicht“ eintragen)')
    head = re.split(r'^## Deutsch', doc, maxsplit=1, flags=re.M)[0]
    found = UNRELEASED.search(head)
    if found:
        raise ValueError(f'Release Notes {version}: Kopf enthält noch „{found.group(0)}“ (beim Release ersetzen)')


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
    prerelease = is_prerelease(tag)
    german_raw, english_raw = notes_for(changelog, version).strip(), bilingual_sections(doc, version)[1]
    if prerelease:
        check_prerelease_notes(german_raw + '\n' + bilingual_sections(doc, version)[0], english_raw)
    german = absolute_links(german_raw, tag, '', repository)          # links relative to the root
    english = absolute_links(english_raw, tag, 'docs/', repository)   # relative to docs/
    footer_de, footer_en_text = (FOOTER_PRERELEASE, FOOTER_PRERELEASE_EN) if prerelease else (FOOTER, FOOTER_EN)
    footer = footer_de.strip().removeprefix('---').strip().replace('<version>', version)
    footer_en = footer_en_text.strip().replace('<version>', version)
    # The in-app dialog shows the part before the first '---': for a candidate it starts with the notice.
    head = PRERELEASE_NOTICE + '\n\n' if prerelease else ''
    body = f'{head}{german}\n\n---\n\n## English\n\n{english}\n\n---\n{footer}\n\n{footer_en}\n'
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
    parser.add_argument('--channel-out', type=Path, help='writes "prerelease" for a release candidate, else "stable"')
    parser.add_argument('--repository', default=REPOSITORY)
    args = parser.parse_args(argv)
    try:
        version = check_tag(args.tag)
        declared = pyproject_version(ROOT)
        if declared != version:
            raise ValueError(f'pyproject.toml hat Version {declared}, ecu_studio.__version__ = {version}')
        doc_path = args.docs / f'RELEASE_NOTES_{version}.md'
        if not doc_path.is_file():
            raise ValueError(f'{doc_path.name} fehlt (deutsche und englische Release Notes)')
        changelog, doc = args.changelog.read_text(encoding='utf-8'), doc_path.read_text(encoding='utf-8')
        check_release_time(changelog, doc, version)
        body = build_body(changelog, doc, args.tag, version, args.repository)
        if args.package:
            check_package(args.package, version)
    except ValueError as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        return 1
    args.out.write_text(body, encoding='utf-8', newline='\n')
    if args.title_out:
        args.title_out.write_text(release_title(args.tag) + '\n', encoding='utf-8', newline='\n')
    if args.channel_out:
        args.channel_out.write_text(('prerelease' if is_prerelease(args.tag) else 'stable') + '\n',
                                    encoding='utf-8', newline='\n')
    print(f'Release {version}: „{release_title(args.tag)}“, {len(body.splitlines())} Zeilen Release-Text (DE + EN)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
