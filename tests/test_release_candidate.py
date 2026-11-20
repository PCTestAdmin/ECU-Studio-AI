"""Release candidates (1.21.0): version format, update channels, release checks and the publishing guard.

A candidate (v1.21.0-rc1) must be parsed, ordered and shown correctly everywhere, may only ever be published as a
GitHub pre-release that never becomes "Latest", and is never offered by the stable update channel of the program.
"""
import hashlib
import json
import os
import re
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest

from ecu_studio.core import app_version, updates
from ecu_studio.tools import release_guard, release_notes

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github' / 'workflows' / 'release.yml').read_text(encoding='utf-8')
REPO_URL = 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/'


# ---- version format ------------------------------------------------------------------------------------------
def test_versions_parse_order_and_derived_forms():
    rc = app_version.parse('1.21.0-rc1')
    assert (rc.text, rc.tag, rc.pep440, rc.windows, rc.base, rc.prerelease) == (
        '1.21.0-rc1', 'v1.21.0-rc1', '1.21.0rc1', '1.21.0.1', '1.21.0', True)
    stable = app_version.parse('v1.21.0')
    assert (stable.text, stable.pep440, stable.windows, stable.prerelease) == ('1.21.0', '1.21.0', '1.21.0.0', False)
    order = ['1.20.0', '1.20.1', '1.21.0-rc1', '1.21.0-rc2', '1.21.0-rc10', '1.21.0', '1.21.1-rc1', '1.21.1', '2.0.0']
    assert sorted(order[::-1], key=lambda v: app_version.parse(v).key) == order
    assert app_version.is_newer('1.21.0', '1.21.0-rc1') and app_version.is_newer('1.21.0-rc1', '1.20.1')
    assert not app_version.is_newer('1.21.0-rc1', '1.21.0') and not app_version.is_newer('1.21.0-rc1', '1.21.0-rc1')
    # Windows numbers are unique per version (not an order: rc1 = .1 > stable = .0, documented).
    assert len({app_version.windows_version(v) for v in order}) == len(order)


@pytest.mark.parametrize('bad', ['1.21.0rc1', '1.21.0-RC1', '1.21.0-rc01', '1.21.0-rc0', '1.21.0-rc', '1.21.0-beta1',
                                 '1.21', '1.21.0.1', '01.21.0', 'v1.21.0-rc1-x', '', None, 1.21])
def test_invalid_versions_are_rejected(bad):
    assert app_version.parse(bad) is None and app_version.parse_tag(bad) is None
    assert not app_version.is_newer(bad, '1.0.0') and not app_version.is_newer('9.0.0', bad)


def test_tag_form_needs_the_v_and_no_blanks():
    assert app_version.parse_tag('v1.21.0-rc1').text == '1.21.0-rc1'
    for bad in ('1.21.0-rc1', ' v1.21.0-rc1', 'v1.21.0-rc1\n', 'V1.21.0'):
        assert app_version.parse_tag(bad) is None


def test_command_line_forms(capsys):
    assert app_version.main(['1.21.0-rc1', 'windows']) == 0 and capsys.readouterr().out.strip() == '1.21.0.1'
    assert app_version.main(['v1.21.0-rc1', 'channel']) == 0 and capsys.readouterr().out.strip() == 'prerelease'
    assert app_version.main(['1.21.0', 'channel']) == 0 and capsys.readouterr().out.strip() == 'stable'
    assert app_version.main(['1.21.0-beta', 'text']) == 1
    assert app_version.main(['1.21.0', 'nonsense']) == 2


# ---- update channels -------------------------------------------------------------------------------------------
def _payload(tag, prerelease, **over):
    version = tag.lstrip('v')
    name = f'ECU-Studio-AI-{version}-windows-x64.zip'
    setup = f'ECU-Studio-AI-{version}-setup.exe'
    data = {'tag_name': tag, 'draft': False, 'prerelease': prerelease, 'body': f'## {version}\n- Neu',
            'html_url': f'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/tag/{tag}',
            'assets': [{'name': n, 'browser_download_url': f'{REPO_URL}{tag}/{n}', 'size': 5}
                       for n in (name, name + '.sha256', setup, setup + '.sha256')]}
    data.update(over)
    return data


def test_stable_channel_never_offers_a_release_candidate():
    assert updates.parse_release(_payload('v1.21.0-rc1', True)) is None
    assert updates.parse_release(_payload('v1.21.0-rc1', False)) is None       # RC tag without the flag
    assert updates.parse_release(_payload('v1.21.0', True)) is None           # stable tag flagged as pre-release
    assert updates.parse_release(_payload('v1.21.0-rc1', 'yes')) is None
    stable = updates.parse_release(_payload('v1.21.0', False))
    assert (stable.version, stable.prerelease, stable.installer.name) == ('1.21.0', False, 'ECU-Studio-AI-1.21.0-setup.exe')


def test_test_channel_needs_tag_and_flag_to_agree():
    rc = updates.parse_release(_payload('v1.21.0-rc1', True), allow_prerelease=True)
    assert (rc.version, rc.prerelease, rc.archive_name) == ('1.21.0-rc1', True, 'ECU-Studio-AI-1.21.0-rc1-windows-x64.zip')
    assert rc.installer.name == 'ECU-Studio-AI-1.21.0-rc1-setup.exe'
    assert updates.parse_release(_payload('v1.21.0-rc1', False), allow_prerelease=True) is None
    assert updates.parse_release(_payload('v1.21.0-rc1', True, draft=True), allow_prerelease=True) is None
    assert updates.parse_release(_payload('v1.21.0rc1', True), allow_prerelease=True) is None
    foreign = _payload('v1.21.0-rc1', True)
    foreign['assets'][0]['browser_download_url'] = 'https://example.com/ECU-Studio-AI-1.21.0-rc1-windows-x64.zip'
    assert updates.parse_release(foreign, allow_prerelease=True) is None


class _Resp:
    def __init__(self, data):
        self.data = data
    def read(self, n=-1):
        return self.data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        pass


def _opener(urls):
    def open_(request, timeout=None):
        return _Resp(json.dumps(urls[request.full_url]).encode())
    return open_


def test_channels_ask_their_own_endpoint_and_pick_the_highest_version():
    listing = [_payload('v1.21.0-rc2', True), _payload('v1.21.0-rc1', True), _payload('v1.20.1', False),
               _payload('v1.22.0-rc1', False)]                     # wrongly unflagged: ignored
    opener = _opener({updates.API_LATEST: _payload('v1.20.1', False), updates.API_RELEASES: listing})
    assert updates.fetch_latest(opener).version == '1.20.1'
    newest = updates.fetch_latest(opener, channel=updates.PRERELEASE)
    assert (newest.version, newest.prerelease) == ('1.21.0-rc2', True)
    # Once the stable release exists the test channel offers it (1.21.0 > 1.21.0-rc2).
    opener = _opener({updates.API_RELEASES: [_payload('v1.21.0', False)] + listing})
    assert updates.fetch_latest(opener, channel=updates.PRERELEASE).version == '1.21.0'
    with pytest.raises(updates.UpdateError):
        updates.fetch_latest(opener, channel='beta')
    with pytest.raises(updates.UpdateError):
        updates.fetch_latest(_opener({updates.API_RELEASES: {'message': 'x'}}), channel=updates.PRERELEASE)


def test_an_installed_candidate_is_offered_its_stable_release_but_nothing_older():
    stable = updates.parse_release(_payload('v1.21.0', False))
    assert updates.update_available('1.21.0-rc1', stable)
    assert not updates.update_available('1.21.0-rc1', updates.parse_release(_payload('v1.20.1', False)))
    rc2 = updates.parse_release(_payload('v1.21.0-rc2', True), allow_prerelease=True)
    assert updates.update_available('1.21.0-rc1', rc2) and not updates.update_available('1.21.0', rc2)
    assert not updates.update_available('1.21.0-rc1', rc2, skipped='1.21.0-rc2')


def test_apps_and_features_shows_a_candidate_version(tmp_path):
    (tmp_path / 'unins000.exe').write_bytes(b'MZ')
    written = []
    entry = {'InstallLocation': str(tmp_path), 'DisplayVersion': '1.20.1', 'DisplayName': 'ECU Studio AI 1.20.1'}
    assert updates.sync_uninstall_entry(tmp_path, '1.21.0-rc1', read=lambda: entry, write=written.append)
    assert written == [{'DisplayVersion': '1.21.0-rc1', 'DisplayName': 'ECU Studio AI 1.21.0-rc1'}]
    assert not updates.sync_uninstall_entry(tmp_path, '1.21.0rc1', read=lambda: entry, write=written.append)


# ---- program side: the test channel is a confirmed opt-in -------------------------------------------------------
@pytest.fixture
def controller(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QWidget
    from ecu_studio.ui import updates as ui
    QApplication.instance() or QApplication([])
    window = QWidget()
    window.settings = QSettings(str(tmp_path / 's.ini'), QSettings.Format.IniFormat)
    return ui, ui.UpdateController(window)


def test_test_channel_is_off_by_default_and_needs_confirmation(controller, monkeypatch):
    ui, c = controller
    assert c.channel() == updates.STABLE
    assert c.set_test_channel(True, confirm=lambda: False) is False and c.channel() == updates.STABLE
    c.settings.setValue(ui.KEY_SKIP, '1.21.0-rc1')
    assert c.set_test_channel(True, confirm=lambda: True) is True and c.channel() == updates.PRERELEASE
    assert c.settings.value(ui.KEY_SKIP) is None                    # a skip of the other channel is forgotten
    asked = []
    assert c.set_test_channel(False, confirm=lambda: asked.append(1)) is False   # switching off never asks
    assert not asked and c.channel() == updates.STABLE
    c.settings.setValue(ui.KEY_CHANNEL, 'nightly')                  # unknown stored value: stable
    assert c.channel() == updates.STABLE
    seen = []

    class Worker:
        def __init__(self, channel):
            seen.append(channel)
            self.finished_check = type('S', (), {'connect': lambda s, fn: None})()
        def isRunning(self):
            return False
        def start(self):
            pass
    monkeypatch.setattr(ui, 'CheckWorker', Worker)
    c.check(manual=True)
    c.set_test_channel(True, confirm=lambda: True)
    c.check(manual=True)
    assert seen == [updates.STABLE, updates.PRERELEASE]


def test_dialog_marks_a_candidate_and_the_warning_names_the_risks(controller):
    ui, c = controller
    from PySide6.QtWidgets import QLabel
    rc = updates.parse_release(_payload('v1.21.0-rc1', True), allow_prerelease=True)
    labels = ' '.join(l.text() for l in ui.UpdateDialog(rc, True).findChildren(QLabel))
    assert 'Vorabversion (Release Candidate)' in labels and 'nicht für den produktiven Einsatz' in labels
    stable = updates.parse_release(_payload('v1.21.0', False))
    assert 'Vorabversion' not in ' '.join(l.text() for l in ui.UpdateDialog(stable, True).findChildren(QLabel))
    for words in ('Vorabversionen', 'nicht für den produktiven Einsatz', 'ungeprüfte Vorschläge', 'SHA-256', 'ausschalten'):
        assert words in ui.CHANNEL_WARNING


def test_new_texts_are_translated():
    texts = json.loads((ROOT / 'src/ecu_studio/recognition/data/i18n/en.json').read_text(encoding='utf-8'))['entries']
    from ecu_studio.ui import updates as ui
    for text in ('Testkanal: Vorabversionen (Release Candidates) anbieten …', 'Testkanal (Vorabversionen)',
                 ui.CHANNEL_WARNING, 'Vorabversion (Release Candidate) aus dem Testkanal – zum Testen, nicht für den '
                 'produktiven Einsatz.'):
        assert texts.get(text), text


# ---- release checks: tag, title, notes -------------------------------------------------------------------------
CHANGELOG = ('## 1.21.0 (in Entwicklung)\n\n- stabil\n\n## 1.21.0-rc1 – Release Candidate (Vorabversion)\n\n'
             '- Neu: TriCore\n\n## 1.20.1\n- alt\n')
DOC_RC = ('# ECU Studio AI 1.21.0-rc1 – Release Notes\n\n## Deutsch\n\nVorabversion (Release Candidate).\n\n### Neu\n- A\n\n'
          '## English\n\nPre-release (release candidate).\n\n### New\n- A\n')


def test_release_candidate_tags_titles_and_changelog_sections():
    assert release_notes.check_tag('v1.21.0-rc1', '1.21.0-rc1') == '1.21.0-rc1'
    for tag, version in (('v1.21.0-rc1', '1.21.0'), ('v1.21.0', '1.21.0-rc1'), ('v1.21.0rc1', '1.21.0rc1'),
                         ('1.21.0-rc1', '1.21.0-rc1'), ('v1.21.0-rc2', '1.21.0-rc1')):
        with pytest.raises(ValueError):
            release_notes.check_tag(tag, version)
    assert release_notes.release_title('v1.21.0-rc1', '1.21.0-rc1') == 'ECU Studio AI v1.21.0-rc1 (Vorabversion / Pre-release)'
    assert release_notes.release_title('v1.21.0', '1.21.0') == 'ECU Studio AI v1.21.0'
    assert release_guard.expected_title('v1.21.0-rc1') == release_notes.release_title('v1.21.0-rc1', '1.21.0-rc1')
    # '## 1.21.0' and '## 1.21.0-rc1' are different sections.
    assert release_notes.notes_for(CHANGELOG, '1.21.0-rc1') == '- Neu: TriCore\n'
    assert release_notes.notes_for(CHANGELOG, '1.21.0') == '- stabil\n'
    with pytest.raises(ValueError):
        release_notes.notes_for(CHANGELOG.replace('## 1.21.0-rc1', '## 1.21.0-rc10'), '1.21.0-rc1')


def test_candidate_body_starts_with_the_notice_and_footer_names_the_test_channel():
    body = release_notes.build_body(CHANGELOG, DOC_RC, 'v1.21.0-rc1', '1.21.0-rc1')
    assert body.startswith('> **Vorabversion (Release Candidate) – nicht für den produktiven Einsatz.**')
    assert 'Testkanal' in body and 'Test channel' in body.replace('\n', ' ')
    assert 'ECU-Studio-AI-1.21.0-rc1-setup.exe' in body and 'Jetzt nach Updates suchen' not in body
    # The in-app dialog shows the notice and the German notes.
    notes = updates.parse_release(dict(_payload('v1.21.0-rc1', True), body=body), allow_prerelease=True).notes
    assert notes.startswith('> **Vorabversion') and 'TriCore' in notes and 'English' not in notes
    stable_doc = DOC_RC.replace('1.21.0-rc1', '1.21.0')
    assert not release_notes.build_body(CHANGELOG, stable_doc, 'v1.21.0', '1.21.0').startswith('>')


@pytest.mark.parametrize('doc, message', [
    (DOC_RC.replace('Vorabversion (Release Candidate).', 'Neue Version.'), 'deutsche Teil'),
    (DOC_RC.replace('Pre-release (release candidate).', 'New version.'), 'englische Teil'),
    (DOC_RC.replace('- A\n\n## English', '- 30 % mehr Treffer\n\n## English'), 'Prozent'),
    (DOC_RC.replace('### New\n- A', '### New\n- 30 percent more hits'), 'Prozent'),
])
def test_candidate_notes_must_say_pre_release_and_make_no_percentage_claims(doc, message):
    with pytest.raises(ValueError, match=message):
        release_notes.build_body(CHANGELOG, doc, 'v1.21.0-rc1', '1.21.0-rc1')


def test_command_writes_the_channel_and_checks_pyproject(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, 'check_tag', lambda tag, version=None: '1.21.0-rc1')
    monkeypatch.setattr(release_notes, 'release_title', lambda tag, version=None: 'T')
    changelog = tmp_path / 'CHANGELOG.md'; changelog.write_text(CHANGELOG, encoding='utf-8')
    docs = tmp_path / 'docs'; docs.mkdir()
    (docs / 'RELEASE_NOTES_1.21.0-rc1.md').write_text(DOC_RC, encoding='utf-8')
    monkeypatch.setattr(release_notes, 'pyproject_version', lambda root=None: '1.21.0-rc1')
    monkeypatch.setattr(release_notes, 'build_body', lambda *a, **k: 'body\n')
    args = ['v1.21.0-rc1', '--out', str(tmp_path / 'n.md'), '--changelog', str(changelog), '--docs', str(docs),
            '--channel-out', str(tmp_path / 'c.txt')]
    assert release_notes.main(args) == 0 and (tmp_path / 'c.txt').read_text() == 'prerelease\n'
    monkeypatch.setattr(release_notes, 'pyproject_version', lambda root=None: '1.20.1')
    assert release_notes.main(args) == 1 and 'pyproject.toml' in capsys.readouterr().err
    # A commit that still carries the placeholders of the development branch is refused.
    monkeypatch.setattr(release_notes, 'pyproject_version', lambda root=None: '1.21.0-rc1')
    changelog.write_text(CHANGELOG.replace('## 1.21.0-rc1', '## 1.21.0-rc1 (geplant, nicht veröffentlicht)', 1),
                         encoding='utf-8')
    assert release_notes.main(args) == 1 and 'Platzhalter' in capsys.readouterr().err


@pytest.mark.parametrize('heading, head, refused', [
    ('## 1.21.0-rc1 (19.11.2026)', '', False),
    ('## 1.21.0-rc1 – Release Candidate (Vorabversion; geplant, nicht veröffentlicht)', '', True),
    ('## 1.21.0-rc1 (in Entwicklung)', '', True),
    ('## 1.21.0-rc1 (19.11.2026)', '**Release candidate – planned, not published yet.**\n', True),
    ('## 1.21.0-rc1 (19.11.2026)', '**Vorabversion – geplant.**\n', True),
    # Text BELOW "## Deutsch" may mention unpublished things (e.g. the later stable version).
    ('## 1.21.0-rc1 (19.11.2026)', '', False)])
def test_release_time_entries_must_replace_the_placeholders(heading, head, refused):
    changelog = f'{heading}\n\n- A\n\n## 1.21.0 (in Entwicklung, nicht veröffentlicht)\n\n- B\n'
    doc = (f'# ECU Studio AI 1.21.0-rc1 – Release Notes\n\n{head}\n## Deutsch\n\n1.21.0 ist noch nicht '
           'veröffentlicht.\n\n## English\n\nnot published\n')
    if refused:
        with pytest.raises(ValueError):
            release_notes.check_release_time(changelog, doc, '1.21.0-rc1')
    else:
        release_notes.check_release_time(changelog, doc, '1.21.0-rc1')     # the 1.21.0 heading is not checked


# ---- publishing guard ------------------------------------------------------------------------------------------
STABLE = [{'tagName': 'v1.20.1', 'isPrerelease': False, 'isDraft': False},
          {'tagName': 'v1.20.0', 'isPrerelease': False, 'isDraft': False}]


def test_guard_selftest_refuses_every_bad_case():
    assert release_guard.selftest() == []
    assert release_guard.main(['selftest']) == 0


def test_guard_plans_a_candidate_only_as_pre_release_that_never_becomes_latest():
    plan = release_guard.plan('v1.21.0-rc1', STABLE, 'v1.20.1')
    assert plan['flags'] == ['--prerelease', '--latest=false'] and plan['prerelease'] and not plan['make_latest']
    view = {'tagName': 'v1.21.0-rc1', 'isPrerelease': True, 'isDraft': False,
            'name': 'ECU Studio AI v1.21.0-rc1 (Vorabversion / Pre-release)'}
    assert release_guard.verify(plan, view, 'v1.20.1') == []
    assert release_guard.verify(plan, dict(view, isDraft=True), 'v1.20.1', stage='draft') == []
    assert any('Pre-Release' in p for p in release_guard.verify(plan, dict(view, isPrerelease=False), 'v1.20.1'))
    assert any('Latest' in p for p in release_guard.verify(plan, view, 'v1.21.0-rc1'))
    assert any('Entwurf' in p for p in release_guard.verify(plan, dict(view, isDraft=True), 'v1.20.1'))
    # A draft of a candidate with the right flags still must not move "Latest".
    assert any('Latest' in p for p in release_guard.verify(plan, dict(view, isDraft=True), '', stage='draft'))


@pytest.mark.parametrize('tag, releases, latest, message', [
    ('v1.21.0-rc1', STABLE + [{'tagName': 'v1.21.0-rc1', 'isPrerelease': True}], 'v1.20.1', 'existiert bereits'),
    ('v1.20.1-rc1', STABLE, 'v1.20.1', 'schon stabil'),
    ('v1.21.0-rc1', STABLE + [{'tagName': 'v1.21.0-rc1', 'isPrerelease': True, 'isDraft': True}], 'v1.20.1',
     'existiert bereits'),                                           # also a draft of the same tag
    ('v1.21.0-rc2', STABLE + [{'tagName': 'v1.21.0-rc5', 'isPrerelease': True, 'isDraft': True},
                              {'tagName': 'v1.21.0-rc3', 'isPrerelease': True}], 'v1.20.1', 'neueren'),
    ('v1.19.9-rc1', STABLE, 'v1.20.1', 'nicht neuer'),
    ('v1.21.0', STABLE, 'v1.21.0-rc1', 'keine stabile'),
    ('v1.21.0-rc1x', STABLE, 'v1.20.1', 'keine Version'),
])
def test_guard_refuses(tag, releases, latest, message):
    with pytest.raises(release_guard.GuardError, match=message):
        release_guard.plan(tag, releases, latest)


def test_guard_latest_rules_for_stable_releases():
    assert release_guard.plan('v1.21.0', STABLE, 'v1.20.1')['flags'] == ['--latest']
    assert release_guard.plan('v1.20.2', STABLE + [{'tagName': 'v1.21.0', 'isPrerelease': False}], 'v1.21.0')['flags'] == ['--latest=false']
    assert release_guard.plan('v1.0.0', [], '')['flags'] == ['--latest']


def _artifact(folder: Path, tag: str, notes: str | None = None):
    version = tag.lstrip('v')
    folder.mkdir()
    for name in (f'ECU-Studio-AI-{version}-windows-x64.zip', f'ECU-Studio-AI-{version}-setup.exe'):
        (folder / name).write_bytes(name.encode())
        (folder / (name + '.sha256')).write_text(f'{hashlib.sha256(name.encode()).hexdigest()}  {name}\n', encoding='ascii')
    (folder / 'release-title.txt').write_text(release_guard.expected_title(tag) + '\n', encoding='utf-8')
    rc = app_version.parse_tag(tag).prerelease
    (folder / 'release-channel.txt').write_text(('prerelease' if rc else 'stable') + '\n', encoding='utf-8')
    default = (release_notes.PRERELEASE_NOTICE + '\n\n' if rc else '') + '- Neu\n\n---\n\n## English\n\n- New\n'
    (folder / 'release-notes.md').write_text(notes if notes is not None else default, encoding='utf-8')


def test_guard_checks_the_artifact_before_publishing(tmp_path, capsys):
    good = tmp_path / 'good'
    _artifact(good, 'v1.21.0-rc1')
    problems, digests = release_guard.check_assets(good, 'v1.21.0-rc1')
    assert problems == [] and len(digests) == 2
    summary = tmp_path / 'summary.md'
    assert release_guard.main(['assets', str(good), 'v1.21.0-rc1', '--summary', str(summary)]) == 0
    assert 'v1.21.0-rc1 (Vorabversion / Pre-release)' in summary.read_text(encoding='utf-8')
    # Wrong version files, a stale checksum, an extra file, a stable title or channel, notes without notice.
    (good / 'ECU-Studio-AI-1.20.1-windows-x64.zip').write_bytes(b'x')
    (good / 'release-title.txt').write_text('ECU Studio AI v1.21.0-rc1\n', encoding='utf-8')
    (good / 'release-channel.txt').write_text('stable\n', encoding='utf-8')
    (good / 'ECU-Studio-AI-1.21.0-rc1-setup.exe').write_bytes(b'changed')
    (good / 'release-notes.md').write_text('- Neu\n\n## English\n', encoding='utf-8')
    problems, _ = release_guard.check_assets(good, 'v1.21.0-rc1')
    text = ' | '.join(problems)
    for part in ('Unerwartete Dateien', 'SHA-256 passt nicht', 'Titel', 'Kanal', 'Vorabversions-Hinweis'):
        assert part in text, (part, text)
    stable = tmp_path / 'stable'
    _artifact(stable, 'v1.21.0', notes=release_notes.PRERELEASE_NOTICE + '\n\n## English\n')
    assert any('stabilen Version' in p for p in release_guard.check_assets(stable, 'v1.21.0')[0])


# ---- workflow, installer, build and updater -------------------------------------------------------------------
def test_workflow_publishes_a_candidate_only_as_pre_release_after_the_guard():
    publish = WORKFLOW[WORKFLOW.index('\n  publish:\n'):]
    assert 'release_guard selftest' in WORKFLOW and 'release_guard plan' in publish
    assert publish.index('release_guard plan') < publish.index('gh release create')
    create = publish[publish.index('gh release create'):].split('\n', 1)[0]
    assert '"${draft_flags[@]}"' in create and '--verify-tag' in create and '--prerelease' not in create
    assert 'draft_flags=(--draft)' in publish and 'draft_flags+=(--prerelease)' in publish   # pre-release from the plan
    assert publish.index('--stage draft') < publish.index('gh release edit') < publish.index('Verify the published release')
    assert 'diff others-before.json others-after.json' in publish
    assert 'release_guard assets dist' in publish and 'gh attestation verify' in publish
    # The dry run plans with read-only rights and never creates anything.
    plan_job = WORKFLOW[WORKFLOW.index('\n  publish-plan:\n'):WORKFLOW.index('\n  publish:\n')]
    assert "if: github.ref_type != 'tag'" in plan_job and 'permissions' not in plan_job
    assert 'gh release create' not in plan_job.replace('`gh release create', '') and 'gh release edit $TAG' in plan_job
    # The tag decides the channel, file version and PEP 440 metadata before anything is built.
    assert 'app_version $tag channel' in WORKFLOW and 'app_version $tag windows' in WORKFLOW
    assert "m.version('ecu-studio-ai')" in WORKFLOW and '/DAppFileVersion=' in WORKFLOW
    assert 'FilePrivatePart' in WORKFLOW and "'dist\\ECU-Studio-AI\\ECU-Studio-AI.exe'" in WORKFLOW
    # The update test still starts from the last STABLE release.
    assert WORKFLOW.count('--exclude-pre-releases') == 2


def test_installer_needs_a_numeric_file_version_for_a_candidate():
    iss = (ROOT / 'packaging' / 'installer.iss').read_text(encoding='utf-8-sig')
    assert '#if Pos("-", AppVersion) > 0' in iss and 'VersionInfoVersion={#AppFileVersion}' in iss
    assert 'VersionInfoProductTextVersion={#AppVersion}' in iss and 'AppVerName=ECU Studio AI {#AppVersion}' in iss
    build = (ROOT / 'build_release.ps1').read_text(encoding='utf-8-sig')
    assert 'ecu_studio.core.app_version $version windows' in build and '/DAppFileVersion=$fileVersion' in build


def test_starter_version_resource_and_source_version_of_a_candidate(tmp_path):
    from ecu_studio.tools import build_portable_runtime as b
    source = b.version_source('1.21.0-rc1')
    assert 'AssemblyFileVersion("1.21.0.1")' in source and 'AssemblyInformationalVersion("1.21.0-rc1")' in source
    assert 'AssemblyFileVersion("1.20.1.0")' in b.version_source('1.20.1')
    init = tmp_path / 'src' / 'ecu_studio' / '__init__.py'
    init.parent.mkdir(parents=True)
    init.write_text('__version__ = "1.21.0-rc1"\n', encoding='utf-8')
    assert b.app_version(tmp_path) == '1.21.0-rc1'
    for bad in ('1.21.0rc1', '1.21.0-beta'):
        init.write_text(f'__version__ = "{bad}"\n', encoding='utf-8')
        with pytest.raises(RuntimeError):
            b.app_version(tmp_path)


def test_updater_shows_a_candidate_in_apps_and_features():
    script = (ROOT / 'packaging' / 'updater.ps1').read_text(encoding='utf-8-sig')
    pattern = re.search(r"\$version -notmatch '([^']+)'", script).group(1)
    assert pattern == '^(0|[1-9]\\d{0,3})\\.(0|[1-9]\\d{0,3})\\.(0|[1-9]\\d{0,3})(-rc[1-9]\\d?)?$'
    for good in ('1.20.1', '1.21.0-rc1', '1.21.0-rc12'):
        assert re.fullmatch(pattern.strip('^$'), good)
    for bad in ('1.21.0rc1', '1.21.0-rc01', '1.21.0-beta', '1.21'):
        assert not re.fullmatch(pattern.strip('^$'), bad)
