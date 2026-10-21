"""Update check, verified download and the separate updater (updater.ps1)."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import pytest
from ecu_studio.core import updates

BASE = 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v1.15.0/'


def _payload(**over):
    name = 'ECU-Studio-AI-1.15.0-windows-x64.zip'
    data = {'tag_name': 'v1.15.0', 'draft': False, 'prerelease': False, 'body': '## Neu\n- A2L-Import',
            'html_url': 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/tag/v1.15.0',
            'assets': [{'name': name, 'browser_download_url': BASE + name, 'size': 5},
                       {'name': name + '.sha256', 'browser_download_url': BASE + name + '.sha256', 'size': 90}]}
    data.update(over)
    return data


class _Response(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data); self.url = url
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *a):
        self.close()


def _opener(files, final_host='objects.githubusercontent.com'):
    def open_(request, timeout=None):
        url = request.full_url
        if url not in files:
            raise OSError('offline')
        return _Response(files[url], url if url.endswith('.sha256') or 'api.github' in url else f'https://{final_host}/x')
    return open_


def test_versions_compare_numerically_and_ignore_prereleases():
    assert updates.is_newer('v1.15.0', '1.14.0') and updates.is_newer('1.10.0', '1.9.9')
    assert not updates.is_newer('1.14.0', '1.14.0') and not updates.is_newer('1.13.9', '1.14.0')
    assert updates.parse_version('1.15.0-rc1') is None and not updates.is_newer('2.0.0-beta', '1.0.0')


def test_release_needs_stable_tag_both_assets_and_official_urls():
    r = updates.parse_release(_payload())
    assert (r.version, r.archive_name, r.archive_size) == ('1.15.0', 'ECU-Studio-AI-1.15.0-windows-x64.zip', 5)
    assert updates.parse_release(_payload(prerelease=True)) is None
    assert updates.parse_release(_payload(draft=True)) is None
    assert updates.parse_release(_payload(assets=_payload()['assets'][:1])) is None
    foreign = _payload(); foreign['assets'][0]['browser_download_url'] = 'https://evil.example/ECU.zip'
    assert updates.parse_release(foreign) is None
    other_repo = _payload(); other_repo['assets'][0]['browser_download_url'] = 'https://github.com/x/y/releases/download/a.zip'
    assert updates.parse_release(other_repo) is None


def test_schedule_is_at_most_daily_and_skipped_version_is_respected():
    assert updates.check_due(None, now=1000)
    assert not updates.check_due(1000, now=1000 + 3600)
    assert updates.check_due(1000, now=1000 + 24 * 3600)
    assert updates.check_due(5000, now=1000)                      # clock moved back
    r = updates.parse_release(_payload())
    assert updates.update_available('1.14.0', r) and not updates.update_available('1.14.0', r, skipped='1.15.0')
    assert not updates.update_available('1.15.0', r) and not updates.update_available('1.14.0', None)


def test_offline_check_raises_quiet_update_error():
    with pytest.raises(updates.UpdateError):
        updates.fetch_latest(opener=_opener({}))
    payload = json.dumps(_payload()).encode()
    assert updates.fetch_latest(opener=_opener({updates.API_LATEST: payload})).version == '1.15.0'


def _files(blob, checksum=None, name='ECU-Studio-AI-1.15.0-windows-x64.zip'):
    digest = checksum or hashlib.sha256(blob).hexdigest()
    return {BASE + name: blob, BASE + name + '.sha256': f'{digest}  {name}\n'.encode()}


def test_download_verifies_sha256_and_cleans_up_on_mismatch(tmp_path):
    blob = b'12345'
    r = updates.parse_release(_payload())
    path, digest = updates.download(r, tmp_path, opener=_opener(_files(blob)))
    assert path.read_bytes() == blob and digest == hashlib.sha256(blob).hexdigest()
    path.unlink()
    with pytest.raises(updates.UpdateError, match='Prüfsumme'):
        updates.download(r, tmp_path, opener=_opener(_files(blob, checksum='0' * 64)))
    assert not list(tmp_path.iterdir())                            # nothing left behind


def test_download_rejects_conflicting_digest_foreign_redirect_and_wrong_size(tmp_path):
    blob = b'12345'
    good = updates.parse_release(_payload())
    conflict = updates.parse_release(_payload(assets=[dict(_payload()['assets'][0], digest='sha256:' + 'a' * 64),
                                                      _payload()['assets'][1]]))
    with pytest.raises(updates.UpdateError, match='widersprechen'):
        updates.download(conflict, tmp_path, opener=_opener(_files(blob)))
    with pytest.raises(updates.UpdateError, match='umgeleitet'):
        updates.download(good, tmp_path, opener=_opener(_files(blob), final_host='evil.example'))
    with pytest.raises(updates.UpdateError):
        updates.download(good, tmp_path, opener=_opener(_files(b'123456')))   # size 6 != 5 announced


def test_install_root_only_for_packaged_layout(tmp_path):
    (tmp_path / '_internal' / 'python').mkdir(parents=True)
    exe = tmp_path / '_internal' / 'python' / 'pythonw.exe'; exe.write_bytes(b'')
    assert updates.install_root(str(exe)) is None
    (tmp_path / 'ECU-Studio-AI.exe').write_bytes(b''); (tmp_path / '_internal' / 'updater.ps1').write_text('')
    assert updates.install_root(str(exe)) == tmp_path.resolve()
    assert updates.install_root(sys.executable) is None             # development checkout


# ---- updater.ps1 (Windows only) -----------------------------------------------------------
UPDATER = Path(__file__).resolve().parents[1] / 'packaging' / 'updater.ps1'
windows = pytest.mark.skipif(os.name != 'nt' or not shutil.which('powershell'), reason='Windows PowerShell nötig')


def _package(folder: Path, version: str, exe_source: Path):
    """An install folder whose EXE is a copy of cmd.exe (so '/c exit N' is the self-check)."""
    folder.mkdir(parents=True)
    shutil.copy2(exe_source, folder / 'ECU-Studio-AI.exe')
    (folder / 'VERSION.txt').write_text(version)
    (folder / '_internal').mkdir()
    (folder / '_internal' / 'app.py').write_text(f'print("{version}")')
    files = [{'path': p.relative_to(folder).as_posix(), 'size': p.stat().st_size,
              'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.rglob('*')) if p.is_file()]
    (folder / 'RUNTIME_INVENTORY.json').write_text(json.dumps({'format': 1, 'version': version, 'files': files}))


def _zip(folder: Path, target: Path):
    with zipfile.ZipFile(target, 'w') as z:
        for p in folder.rglob('*'):
            if p.is_file():
                z.write(p, ('ECU-Studio-AI/' + p.relative_to(folder).as_posix()))
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _run(install, archive, digest, check='/c exit 0'):
    env = dict(os.environ, ECU_UPDATER_QUIET='1')
    return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(UPDATER),
                           '-InstallDir', str(install), '-Archive', str(archive), '-Sha256', digest,
                           '-CheckArguments', check], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=240)


@pytest.fixture
def setup(tmp_path):
    cmd = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'cmd.exe'
    install = tmp_path / 'ECU-Studio-AI'
    _package(install, '1.14.0', cmd)
    (install / 'meine_notizen.txt').write_text('vom Nutzer')            # user file inside the installation
    new = tmp_path / 'new'; _package(new, '1.15.0', cmd)
    archive = tmp_path / 'update.zip'
    return install, archive, _zip(new, archive), tmp_path


@windows
def test_updater_installs_keeps_user_files_and_backup(setup):
    install, archive, digest, _ = setup
    result = _run(install, archive, digest)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.15.0'
    assert (install / 'meine_notizen.txt').read_text() == 'vom Nutzer'
    assert (install.parent / 'ECU-Studio-AI.backup' / 'VERSION.txt').read_text() == '1.14.0'


@windows
def test_updater_refuses_wrong_checksum_without_touching_installation(setup):
    install, archive, digest, _ = setup
    result = _run(install, archive, '0' * 64)
    assert result.returncode == 2 and (install / 'VERSION.txt').read_text() == '1.14.0'
    assert not (install.parent / 'ECU-Studio-AI.backup').exists()


@windows
def test_updater_refuses_tampered_file_inside_valid_archive(setup):
    install, _, _, tmp = setup
    new = tmp / 'new'
    (new / '_internal' / 'app.py').write_text('manipuliert')            # inventory no longer matches
    archive = tmp / 'tampered.zip'
    result = _run(install, archive, _zip(new, archive))
    assert result.returncode == 2 and 'beschädigt' in result.stdout
    assert (install / 'VERSION.txt').read_text() == '1.14.0'


@windows
def test_updater_rolls_back_when_new_version_fails_self_check(setup):
    install, archive, digest, _ = setup
    result = _run(install, archive, digest, check='/c exit 7')
    assert result.returncode == 3, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.14.0'
    assert (install / 'meine_notizen.txt').read_text() == 'vom Nutzer'


def test_release_notes_need_matching_tag_and_changelog_section(tmp_path):
    from ecu_studio.tools.release_notes import notes_for, check_tag, main
    log = '## Unveröffentlicht\n- x\n\n## 1.15.0 (01.11.2026)\n- Neu: Updates\n\n## 1.14.0\n- alt\n'
    assert notes_for(log, '1.15.0') == '- Neu: Updates\n'
    with pytest.raises(ValueError):
        notes_for(log, '1.16.0')
    assert check_tag('v1.15.0', '1.15.0') == '1.15.0'
    for bad in ('1.15.0', 'v1.15.0-rc1', 'v1.16.0'):
        with pytest.raises(ValueError):
            check_tag(bad, '1.15.0')
    changelog = tmp_path / 'CHANGELOG.md'; changelog.write_text(log, encoding='utf-8')
    assert main(['v9.9.9', '--out', str(tmp_path / 'n.md'), '--changelog', str(changelog)]) == 1


def test_packaged_build_ships_updater_and_stable_exe_name():
    from ecu_studio.tools import build_portable_runtime as b
    source = Path(b.__file__).read_text(encoding='utf-8')
    assert b.EXE_NAME == 'ECU-Studio-AI.exe' and "'updater.ps1'" in source
    assert b.app_version(Path(__file__).resolve().parents[1]) == __import__('ecu_studio').__version__


def test_repository_without_release_means_no_update_not_an_error():
    import urllib.error
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, 'Not Found', {}, None)
    assert updates.fetch_latest(opener=opener) is None
    def limited(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, 'rate limited', {}, None)
    with pytest.raises(updates.UpdateError, match='403'):
        updates.fetch_latest(opener=limited)


def test_package_metadata_and_runtime_version_agree():
    import re
    from ecu_studio import __version__
    toml = (Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text(encoding='utf-8')
    assert re.search(r'^version = "([^"]+)"', toml, re.M).group(1) == __version__


@windows
def test_updater_survives_foreign_powershell7_module_path(setup, tmp_path, monkeypatch):
    # GitHub runner: Windows PowerShell 5.1 started from a PowerShell 7 environment inherited
    # PSModulePath and reported "Get-FileHash is not recognized". The updater now resets the
    # module path and hashes via .NET; this test runs it with a hostile module path.
    fake = tmp_path / 'ps7modules' / 'Microsoft.PowerShell.Utility'
    fake.mkdir(parents=True)
    # Like PowerShell 7's module: claims PS 3.0, but its binary cannot load in Windows PowerShell.
    (fake / 'Microsoft.PowerShell.Utility.psd1').write_text(
        "@{ GUID = '1da87e53-152b-403e-98dc-74d7b4d63d59'; ModuleVersion = '7.9.9'; PowerShellVersion = '3.0'; "
        "NestedModules = 'Microsoft.PowerShell.Commands.Utility.dll'; "
        "CmdletsToExport = 'Get-FileHash','ConvertFrom-Json','Get-Date','Add-Type','Select-Object' }")
    (fake / 'Microsoft.PowerShell.Commands.Utility.dll').write_bytes(b'MZ not a real assembly')
    monkeypatch.setenv('PSModulePath', str(tmp_path / 'ps7modules'))
    install, archive, digest, _ = setup
    result = _run(install, archive, digest)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.15.0'


def _restore(install, check='/c exit 0'):
    env = dict(os.environ, ECU_UPDATER_QUIET='1')
    return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(UPDATER),
                           '-InstallDir', str(install), '-Restore', '-CheckArguments', check],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=240)


@windows
def test_restore_swaps_back_to_previous_version_and_forward_again(setup):
    install, archive, digest, _ = setup
    assert _run(install, archive, digest).returncode == 0
    backup = install.parent / 'ECU-Studio-AI.backup'
    result = _restore(install)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.14.0' and (backup / 'VERSION.txt').read_text() == '1.15.0'
    assert _restore(install).returncode == 0                       # and forward again
    assert (install / 'VERSION.txt').read_text() == '1.15.0'


@windows
def test_restore_keeps_current_version_when_backup_does_not_start(setup):
    install, archive, digest, _ = setup
    assert _run(install, archive, digest).returncode == 0
    result = _restore(install, check='/c exit 5')
    assert result.returncode == 3, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.15.0'
    assert (install.parent / 'ECU-Studio-AI.backup' / 'VERSION.txt').read_text() == '1.14.0'


@windows
def test_restore_without_backup_changes_nothing(setup):
    install, *_ = setup
    assert _restore(install).returncode == 2 and (install / 'VERSION.txt').read_text() == '1.14.0'


def test_dialog_notes_drop_the_generic_release_footer():
    from ecu_studio.tools.release_notes import FOOTER
    r = updates.parse_release(_payload(body='## Neu\n- A2L-Import\n' + FOOTER))
    assert r.notes == '## Neu\n- A2L-Import' and 'Windows-Warnung' not in r.notes
