"""QA ONLY: give the checked-out source a test version number before a QA build on a runner.

Never used for a release and never committed: the workflow runs it on the runner's checkout, builds, and throws the
checkout away. It lets the installer QA prove updates between two versions that do not exist yet, e.g. the
candidate 1.21.0-rc1 and a derived "next" 1.21.0-rc2, without a tag, a release or a version change in the repository.

  python qa_version.py <repo root> <version> [--add <module>] [--remove <module>]

<version> is 1.2.3 or a release candidate 1.2.3-rcN (ecu_studio/core/app_version.py). __version__ and
pyproject.toml get it (the release checks compare both). A version without real release notes gets minimal QA notes
(docs/RELEASE_NOTES_<version>.md, runner only); for a candidate they call it a pre-release in both languages, as the
release checks demand. --add/--remove create or delete src/ecu_studio/<module>.py, a marker file that one package
ships and the other one does not (proves that the installer removes files a new version no longer ships, and
installs new ones).
"""
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('version')
parser.add_argument('--add', action='append', default=[])
parser.add_argument('--remove', action='append', default=[])
args = parser.parse_args()
match = re.fullmatch(r'(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})(-rc[1-9]\d?)?', args.version)
if not match:
    raise SystemExit(f'invalid version {args.version!r}')
candidate = bool(match.group(4))

init = args.root / 'src' / 'ecu_studio' / '__init__.py'
text = init.read_text(encoding='utf-8')
text, count = re.subn(r'^__version__ = "[^"]+"', f'__version__ = "{args.version}"', text, flags=re.M)
if count != 1:
    raise SystemExit('__version__ not found')
init.write_text(text, encoding='utf-8')
pyproject = args.root / 'pyproject.toml'
text, count = re.subn(r'^version = "[^"]+"', f'version = "{args.version}"', pyproject.read_text(encoding='utf-8'), flags=re.M)
if count != 1:
    raise SystemExit('version in pyproject.toml not found')
pyproject.write_text(text, encoding='utf-8')

changelog = args.root / 'CHANGELOG.md'
kind = 'Vorabversion (Release Candidate), ' if candidate else ''
# 1.21.0-rc1: release_notes refuses placeholders ("nicht veröffentlicht", "geplant") in the heading of the
# tagged version, so the QA heading is a final one, as at release time.
section = (f'## {args.version} (QA-Testversion)\n\n'
           f'Nur für den isolierten Installer-Test auf einem GitHub-Runner: {kind}Kandidat mit der Testversion '
           f'{args.version}. Kein Tag, kein Release.\n\n')
changelog.write_text(section + changelog.read_text(encoding='utf-8'), encoding='utf-8')

# Since the release checks (tools/release_notes.py) every built version needs bilingual release notes. A QA-only
# test version (e.g. the derived NEXT) has none: write a minimal QA note on the runner. Real notes are never touched.
notes = args.root / 'docs' / f'RELEASE_NOTES_{args.version}.md'
if notes.exists():
    # Real notes of a candidate: their head says "geplant, noch nicht veröffentlicht" until release time. On
    # the runner only, replace the head (before "## Deutsch") as the release commit would; the body stays.
    doc = notes.read_text(encoding='utf-8')
    head, sep, body = doc.partition('\n## Deutsch')
    title = head.split('\n', 1)[0]
    head = (f'{title}\n\n**QA-Testversion {args.version} (Vorabversion) – nur für den isolierten Installer-Test.**\n'
            f'**QA test version {args.version} (pre-release) – isolated installer test only.**\n')
    notes.write_text(head + sep + body, encoding='utf-8')
else:
    de = 'Vorabversion (Release Candidate). ' if candidate else ''
    en = 'Pre-release (release candidate). ' if candidate else ''
    notes.write_text(f'# ECU Studio AI {args.version} – Release Notes\n\n'
                     f'## Deutsch\n\n### QA-Testversion\n\n{de}Nur für den isolierten Installer-Test auf einem '
                     'GitHub-Runner. Kein Tag, kein Release.\n\n'
                     f'## English\n\n### QA test version\n\n{en}Only for the isolated installer test on a GitHub '
                     'runner. No tag, no release.\n', encoding='utf-8')

package = args.root / 'src' / 'ecu_studio'
for name in args.add:
    (package / f'{name}.py').write_text(f'"""QA marker module ({name}), only in QA test packages."""\n', encoding='utf-8')
for name in args.remove:
    (package / f'{name}.py').unlink()
print(f'QA version {args.version}; added {args.add}, removed {args.remove}')
