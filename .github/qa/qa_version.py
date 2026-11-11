"""QA ONLY: give the checked-out source a test version number before a QA build on a runner.

Never used for a release and never committed: the workflow runs it on the runner's checkout, builds, and throws the
checkout away. It lets the installer QA prove updates between two versions that do not exist yet, e.g. the
candidate 1.20.1 and a derived "next" 1.20.2, without a tag, a release or a version change in the repository.

  python qa_version.py <repo root> <version> [--add <module>] [--remove <module>]

--add/--remove create or delete src/ecu_studio/<module>.py, a marker file that one package ships and the other one
does not (proves that the installer removes files a new version no longer ships, and installs new ones).
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
if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
    raise SystemExit(f'invalid version {args.version!r}')

init = args.root / 'src' / 'ecu_studio' / '__init__.py'
text = init.read_text(encoding='utf-8')
text, count = re.subn(r'^__version__ = "[^"]+"', f'__version__ = "{args.version}"', text, flags=re.M)
if count != 1:
    raise SystemExit('__version__ not found')
init.write_text(text, encoding='utf-8')

changelog = args.root / 'CHANGELOG.md'
section = (f'## {args.version} (QA-Testversion, nicht veröffentlicht)\n\n'
           f'Nur für den isolierten Installer-Test auf einem GitHub-Runner: Kandidat mit der Testversion '
           f'{args.version}. Kein Tag, kein Release.\n\n')
changelog.write_text(section + changelog.read_text(encoding='utf-8'), encoding='utf-8')

package = args.root / 'src' / 'ecu_studio'
for name in args.add:
    (package / f'{name}.py').write_text(f'"""QA marker module ({name}), only in QA test packages."""\n', encoding='utf-8')
for name in args.remove:
    (package / f'{name}.py').unlink()
print(f'QA version {args.version}; added {args.add}, removed {args.remove}')
