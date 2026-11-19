"""Publishing guard of the release workflow: stable release or pre-release, and nothing else changes.

Used by .github/workflows/release.yml (stdlib only, no Qt; runs on the Ubuntu publish job):

  plan     TAG --releases releases.json --latest LATEST_TAG --out plan.json
           Decides how the tag may be published, BEFORE anything is created. Refuses (exit 1)
           - a tag that is not v1.2.3 or v1.2.3-rcN (core/app_version.py),
           - a tag that already has a release (published files are never replaced),
           - a release candidate whose stable version is already published, or that is not newer than an existing
             candidate of the same version or than the current latest stable release.
           A candidate is ALWAYS published with --prerelease --latest=false; a stable release gets --latest only
           when it is newer than the current latest stable release (a fix for an older line never replaces it).
  verify   --plan plan.json --release view.json --latest-after TAG [--stage draft|published]
           After creating the draft and after publishing: the pre-release flag equals the plan, a candidate is not
           "Latest" and the latest stable release is unchanged (or, for a newer stable release, is this tag).
  assets   FOLDER TAG [--summary FILE]
           The workflow artifact before publishing: exactly the release files of this version with matching
           '.sha256' files, the generated title (a candidate: "... (Vorabversion / Pre-release)"), the channel file
           and bilingual notes (a candidate's notes start with the pre-release notice).
  selftest Negative test: the guard must refuse wrong versions, a candidate without the pre-release flag, a
           candidate that became "Latest", an existing tag, and must keep candidates off the stable channel of the
           program (core/updates.py). Exit 0 only if every bad case is refused.

releases.json is the output of `gh release list --json tagName,isPrerelease,isDraft --limit 200`, view.json of
`gh release view TAG --json tagName,isPrerelease,isDraft,name`; LATEST_TAG is the tag of /releases/latest or ''.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from ecu_studio.core import app_version

PRERELEASE_FLAGS = ['--prerelease', '--latest=false']


class GuardError(ValueError):
    """The tag must not be published this way; the message is shown in the workflow log (German)."""


def _version(tag: str) -> app_version.Version:
    version = app_version.parse_tag(tag)
    if version is None:
        raise GuardError(f'Tag {tag!r} ist keine Version der Form v1.2.3 oder v1.2.3-rcN')
    return version


def plan(tag: str, releases: list[dict], latest: str | None) -> dict:
    version = _version(tag)
    published = []
    for entry in releases:
        name = entry.get('tagName')
        if name == tag:
            raise GuardError(f'Release {tag} existiert bereits – veröffentlichte Dateien werden nie ersetzt')
        parsed = app_version.parse_tag(name or '')
        if parsed is not None and not entry.get('isDraft'):
            published.append(parsed)
    latest_version = app_version.parse_tag(latest) if latest else None
    if latest and (latest_version is None or latest_version.prerelease):
        raise GuardError(f'Das aktuelle „Latest“-Release {latest!r} ist keine stabile Version – erst klären')
    if version.prerelease:
        if any(p.base == version.base and not p.prerelease for p in published):
            raise GuardError(f'{version.base} ist schon stabil veröffentlicht – kein Release Candidate mehr dafür')
        newer_rc = [p.text for p in published if p.prerelease and p.base == version.base and p.rc >= version.rc]
        if newer_rc:
            raise GuardError(f'Für {version.base} gibt es schon einen gleichen oder neueren Release Candidate: {newer_rc}')
        if latest_version is not None and not version > latest_version:
            raise GuardError(f'{tag} ist nicht neuer als das stabile Release {latest}')
        flags, make_latest = list(PRERELEASE_FLAGS), False
    else:
        make_latest = latest_version is None or version > latest_version
        flags = ['--latest'] if make_latest else ['--latest=false']
    return {'tag': tag, 'version': version.text, 'prerelease': version.prerelease, 'flags': flags,
            'make_latest': make_latest, 'latest_before': latest or ''}


def verify(planned: dict, view: dict, latest_after: str | None, stage: str = 'published') -> list[str]:
    problems = []
    tag = planned['tag']
    if view.get('tagName') != tag:
        problems.append(f'Release gehört zu {view.get("tagName")!r}, nicht zu {tag}')
    if view.get('isPrerelease') is not planned['prerelease']:
        problems.append(f'Pre-Release-Kennzeichnung ist {view.get("isPrerelease")!r}, geplant {planned["prerelease"]}')
    if view.get('isDraft') is not (stage == 'draft'):
        problems.append(f'Entwurfsstatus ist {view.get("isDraft")!r} (Stufe {stage})')
    if planned['prerelease'] and not str(view.get('name', '')).endswith('(Vorabversion / Pre-release)'):
        problems.append(f'Titel eines Release Candidate ohne Kennzeichnung: {view.get("name")!r}')
    expected_latest = tag if (planned['make_latest'] and stage == 'published') else planned['latest_before']
    if (latest_after or '') != expected_latest:
        problems.append(f'„Latest“ ist {latest_after!r}, erwartet {expected_latest!r}'
                        + (' – ein Release Candidate darf nie „Latest“ werden' if planned['prerelease'] else ''))
    return problems


def expected_title(tag: str) -> str:
    version = _version(tag)
    return f'ECU Studio AI {tag}' + (' (Vorabversion / Pre-release)' if version.prerelease else '')


def check_assets(folder: Path, tag: str) -> tuple[list[str], dict[str, str]]:
    """The downloaded workflow artifact before publishing: exactly the release files of this version, each with a
    matching '.sha256', the generated title, channel and bilingual notes. Returns (problems, sha256 per file)."""
    import hashlib
    import re
    version = _version(tag)
    problems, digests = [], {}
    packages = [f'ECU-Studio-AI-{version.text}-windows-x64.zip', f'ECU-Studio-AI-{version.text}-setup.exe']
    allowed = set(packages) | {p + '.sha256' for p in packages} | {p + '.sig' for p in packages}
    allowed |= {'release-notes.md', 'release-title.txt', 'release-channel.txt'}
    present = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
    unexpected = [name for name in present if name not in allowed]
    if unexpected:
        problems.append(f'Unerwartete Dateien: {unexpected}')
    for name in packages:
        path, checksum = folder / name, folder / (name + '.sha256')
        if not path.is_file() or path.stat().st_size == 0:
            problems.append(f'{name} fehlt oder ist leer'); continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digests[name] = digest
        text = checksum.read_text(encoding='ascii').strip() if checksum.is_file() else ''
        if not re.fullmatch(rf'[0-9a-f]{{64}}  {re.escape(name)}', text):
            problems.append(f'{checksum.name} fehlt oder hat nicht das Format „<sha256>  {name}“')
        elif text.split()[0] != digest:
            problems.append(f'{name}: SHA-256 passt nicht zu {checksum.name}')
    def read(name):
        return (folder / name).read_text(encoding='utf-8').strip() if (folder / name).is_file() else None
    if read('release-title.txt') != expected_title(tag):
        problems.append(f'Titel {read("release-title.txt")!r} statt {expected_title(tag)!r}')
    channel = 'prerelease' if version.prerelease else 'stable'
    if read('release-channel.txt') != channel:
        problems.append(f'Kanal {read("release-channel.txt")!r} statt {channel!r}')
    notes = read('release-notes.md') or ''
    if not re.search(r'^## English$', notes, re.M):
        problems.append('Release-Text ohne englischen Teil')
    if version.prerelease and not notes.startswith('> **Vorabversion (Release Candidate)'):
        problems.append('Release-Text eines RC beginnt nicht mit dem Vorabversions-Hinweis')
    if not version.prerelease and 'Vorabversion (Release Candidate)' in notes:
        problems.append('Release-Text einer stabilen Version trägt den Vorabversions-Hinweis')
    return problems, digests


def _refused(action) -> bool:
    try:
        action()
    except GuardError:
        return True
    return False


def selftest() -> list[str]:
    """Bad cases the guard (and the stable update channel of the program) must refuse; returns the failures."""
    from ecu_studio.core import updates
    stable = [{'tagName': 'v1.20.1', 'isPrerelease': False, 'isDraft': False},
              {'tagName': 'v1.20.0', 'isPrerelease': False, 'isDraft': False}]
    failures = []
    for bad in ('v1.21.0rc1', 'v1.21.0-RC1', 'v1.21.0-rc01', 'v1.21.0-beta1', '1.21.0-rc1', 'v1.21', 'v1.21.0-rc'):
        if not _refused(lambda b=bad: plan(b, stable, 'v1.20.1')):
            failures.append(f'falsche Versionierung angenommen: {bad}')
    good = plan('v1.21.0-rc1', stable, 'v1.20.1')
    if good['flags'] != PRERELEASE_FLAGS or not good['prerelease'] or good['make_latest']:
        failures.append(f'RC nicht als Pre-Release geplant: {good}')
    cases = {
        'Tag existiert schon': lambda: plan('v1.20.1', stable, 'v1.20.1'),
        'RC nach stabiler Version': lambda: plan('v1.20.1-rc3', [{'tagName': 'v1.20.1', 'isPrerelease': False}], 'v1.20.1'),
        'RC nicht neuer als vorhandener RC': lambda: plan('v1.21.0-rc1', stable + [{'tagName': 'v1.21.0-rc2', 'isPrerelease': True}], 'v1.20.1'),
        'RC älter als Latest': lambda: plan('v1.19.5-rc1', stable, 'v1.20.1'),
        'Latest ist ein RC': lambda: plan('v1.21.0', stable, 'v1.21.0-rc1'),
    }
    for label, action in cases.items():
        if not _refused(action):
            failures.append(f'nicht abgelehnt: {label}')
    view = {'tagName': 'v1.21.0-rc1', 'isPrerelease': False, 'isDraft': False,
            'name': 'ECU Studio AI v1.21.0-rc1 (Vorabversion / Pre-release)'}
    if not verify(good, view, 'v1.20.1'):
        failures.append('RC ohne Pre-Release-Kennzeichnung nicht erkannt')
    view = dict(view, isPrerelease=True)
    if not verify(good, view, 'v1.21.0-rc1'):
        failures.append('RC als „Latest“ nicht erkannt')
    if not verify(good, dict(view, name='ECU Studio AI v1.21.0-rc1'), 'v1.20.1'):
        failures.append('RC-Titel ohne Kennzeichnung nicht erkannt')
    if verify(good, view, 'v1.20.1'):
        failures.append(f'korrekter RC abgelehnt: {verify(good, view, "v1.20.1")}')
    if verify(good, dict(view, isDraft=True), 'v1.20.1', stage='draft'):
        failures.append('korrekter RC-Entwurf abgelehnt')
    newer = plan('v1.21.0', stable, 'v1.20.1')
    hotfix = plan('v1.20.2', stable + [{'tagName': 'v1.21.0', 'isPrerelease': False}], 'v1.21.0')
    if newer['flags'] != ['--latest'] or hotfix['flags'] != ['--latest=false']:
        failures.append(f'„Latest“ stabiler Versionen falsch geplant: {newer["flags"]} / {hotfix["flags"]}')
    # The program's stable channel: a candidate is never offered, with or without the pre-release flag.
    asset = 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v1.21.0-rc1/ECU-Studio-AI-1.21.0-rc1-windows-x64.zip'
    payload = {'tag_name': 'v1.21.0-rc1', 'draft': False, 'prerelease': True, 'body': '', 'html_url': '', 'assets': [
        {'name': 'ECU-Studio-AI-1.21.0-rc1-windows-x64.zip', 'size': 1, 'browser_download_url': asset},
        {'name': 'ECU-Studio-AI-1.21.0-rc1-windows-x64.zip.sha256', 'size': 1, 'browser_download_url': asset + '.sha256'}]}
    if updates.parse_release(payload) is not None or updates.parse_release(dict(payload, prerelease=False)) is not None:
        failures.append('stabiler Update-Kanal würde einen Release Candidate anbieten')
    if updates.parse_release(dict(payload, prerelease=False), allow_prerelease=True) is not None:
        failures.append('Testkanal würde einen RC ohne Pre-Release-Kennzeichnung anbieten')
    if updates.parse_release(payload, allow_prerelease=True) is None:
        failures.append('Testkanal bietet einen korrekt gekennzeichneten RC nicht an')
    return failures


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('tag')
    p.add_argument('--releases', type=Path, required=True)
    p.add_argument('--latest', default='')
    p.add_argument('--out', type=Path, required=True)
    v = sub.add_parser('verify')
    v.add_argument('--plan', type=Path, required=True)
    v.add_argument('--release', type=Path, required=True)
    v.add_argument('--latest-after', default='')
    v.add_argument('--stage', choices=('draft', 'published'), default='published')
    sub.add_parser('selftest')
    a = sub.add_parser('assets')
    a.add_argument('folder', type=Path)
    a.add_argument('tag')
    a.add_argument('--summary', type=Path, help='appends file names and SHA-256 as a Markdown table')
    args = parser.parse_args(argv)
    try:
        if args.command == 'assets':
            problems, digests = check_assets(args.folder, args.tag)
            for problem in problems:
                print(f'FEHLER: {problem}', file=sys.stderr)
            for name, digest in digests.items():
                print(f'{digest}  {name}')
            if args.summary:
                rows = ''.join(f'| `{name}` | `{digest}` |\n' for name, digest in digests.items())
                with open(args.summary, 'a', encoding='utf-8') as out:
                    out.write(f'### {expected_title(args.tag)}\n\n| Datei | SHA-256 |\n|---|---|\n{rows}\n')
            return 1 if problems else 0
        if args.command == 'plan':
            result = plan(args.tag, _load(args.releases), args.latest or None)
            args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
            kind = 'Vorabversion (Pre-Release, nie „Latest“)' if result['prerelease'] else 'stabile Version'
            print(f'Plan {args.tag}: {kind}; gh-Optionen: {" ".join(result["flags"])}')
            return 0
        if args.command == 'verify':
            problems = verify(_load(args.plan), _load(args.release), args.latest_after or None, args.stage)
            for problem in problems:
                print(f'FEHLER: {problem}', file=sys.stderr)
            if not problems:
                print(f'Release {_load(args.plan)["tag"]} ({args.stage}): Kennzeichnung und „Latest“ wie geplant.')
            return 1 if problems else 0
        failures = selftest()
        for failure in failures:
            print(f'FEHLER: {failure}', file=sys.stderr)
        if not failures:
            print('Release-Wächter: alle Negativfälle abgelehnt, RC nur als Pre-Release, stabiler Kanal ohne RC.')
        return 1 if failures else 0
    except GuardError as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
