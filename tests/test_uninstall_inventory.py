"""Finding A5 of 1.20.0: program files an in-app update added were left behind by the old uninstaller.

From 1.20.1 the installer/uninstaller removes program files by RUNTIME_INVENTORY.json + SHA-256
(packaging/uninstall_cleanup.ps1), installations made with the installer are updated with the verified
setup.exe (packaging/updater.ps1 -Installer) and "Apps & Features" shows the installed version.
Everything here runs in temporary folders; the real installation and its registry entry are never touched
(registry tests use a throw-away key and only run on CI).
"""
import hashlib
import json
import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

import pytest

from ecu_studio.core import updates

ROOT = Path(__file__).resolve().parents[1]
CLEANUP = ROOT / 'packaging' / 'uninstall_cleanup.ps1'
UPDATER = ROOT / 'packaging' / 'updater.ps1'
ISS = ROOT / 'packaging' / 'installer.iss'
windows = pytest.mark.skipif(os.name != 'nt' or not shutil.which('powershell'), reason='Windows PowerShell nötig')
ci_registry = pytest.mark.skipif(os.name != 'nt' or not os.environ.get('GITHUB_ACTIONS'),
                                 reason='schreibt einen Wegwerf-Registry-Schlüssel: nur auf CI-Runnern')
CMD = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'cmd.exe'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(folder: Path, version: str, extra: list | None = None) -> Path:
    files = [{'path': p.relative_to(folder).as_posix(), 'size': p.stat().st_size, 'sha256': _sha(p)}
             for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'RUNTIME_INVENTORY.json'
             and not p.name.startswith('unins000')]
    target = folder / 'RUNTIME_INVENTORY.json'
    target.write_text(json.dumps({'format': 1, 'version': version, 'files': files + (extra or [])}), encoding='utf-8')
    return target


def _program(folder: Path, version: str, files: dict) -> Path:
    for relative, text in files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    _inventory(folder, version)
    return folder


def _cleanup(install: Path, *args, check=True):
    result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(CLEANUP),
                             '-InstallDir', str(install), *args],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


V1 = {'ECU-Studio-AI.exe': 'exe 1', 'VERSION.txt': '1.19.1', '_internal/app/ecu_studio/main.py': 'main 1',
      '_internal/app/ecu_studio/core/updates.py': 'updates 1'}
V2 = {'ECU-Studio-AI.exe': 'exe 2', 'VERSION.txt': '1.20.0', '_internal/app/ecu_studio/main.py': 'main 2',
      '_internal/app/ecu_studio/core/updates.py': 'updates 2',
      '_internal/app/ecu_studio/core/integrity.py': 'new in 1.20.0'}


# ---- uninstall_cleanup.ps1 ---------------------------------------------------------------------------
@windows
def test_a5_reproduced_on_old_state_and_fixed_by_inventory_cleanup(tmp_path):
    """Old state: the uninstall log knows only what the 1.19.1 installer installed. After the in-app update
    to 1.20.0 the log-based uninstall leaves the file that only 1.20.0 brought (exactly A5). The inventory
    cleanup removes it and keeps the user's own files."""
    install = tmp_path / 'ECU-Studio-AI'
    _program(install, '1.19.1', V1)
    uninstall_log = [install / p for p in V1] + [install / 'RUNTIME_INVENTORY.json']   # what Inno logged
    # in-app update (folder swap) to 1.20.0; unins000 and a user file are carried over
    shutil.rmtree(install)
    _program(install, '1.20.0', V2)
    (install / 'unins000.exe').write_text('uninstaller'); (install / 'unins000.dat').write_text('log 1.19.1')
    (install / '_internal' / 'meine_notizen.txt').write_text('vom Nutzer')

    old_state = tmp_path / 'old'; shutil.copytree(install, old_state)
    for path in uninstall_log:                                  # old uninstaller: log only
        (old_state / path.relative_to(install)).unlink(missing_ok=True)
    leftovers = sorted(p.relative_to(old_state).as_posix() for p in old_state.rglob('*') if p.is_file())
    assert '_internal/app/ecu_studio/core/integrity.py' in leftovers   # A5 reproduced

    _cleanup(install, '-Mode', 'Uninstall')                     # new uninstaller: inventory first ...
    for path in uninstall_log:                                  # ... then its own log
        path.unlink(missing_ok=True)
    left = sorted(p.relative_to(install).as_posix() for p in install.rglob('*') if p.is_file())
    assert left == ['_internal/meine_notizen.txt', 'unins000.dat', 'unins000.exe']   # Inno removes unins000.*
    assert not (install / '_internal' / 'app').exists()        # emptied folders are gone


@windows
def test_changed_program_file_and_unknown_files_stay(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    (install / '_internal' / 'app' / 'ecu_studio' / 'main.py').write_text('vom Nutzer geändert')
    (install / '_internal' / 'app' / 'ecu_studio' / 'eigenes_plugin.py').write_text('unbekannt')
    result = _cleanup(install, '-Mode', 'Uninstall')
    assert (install / '_internal' / 'app' / 'ecu_studio' / 'main.py').read_text() == 'vom Nutzer geändert'
    assert (install / '_internal' / 'app' / 'ecu_studio' / 'eigenes_plugin.py').read_text() == 'unbekannt'
    assert not (install / 'ECU-Studio-AI.exe').exists() and not (install / '_internal' / 'app' / 'ecu_studio' / 'core').exists()
    assert 'Behalten (verändert)' in result.stdout and install.is_dir()


@windows
def test_paths_outside_the_program_folder_are_never_removed(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', {'VERSION.txt': '1.20.0'})
    outside = tmp_path / 'privat.txt'; outside.write_text('fremd')
    other = tmp_path / 'ECU-Studio-AI-Kopie'; other.mkdir(); (other / 'x.txt').write_text('x')
    bad = [{'path': p, 'size': 5, 'sha256': _sha(outside)} for p in
           ('../privat.txt', '..\\privat.txt', 'a/../../privat.txt', str(outside), str(outside).replace('\\', '/'),
            '/privat.txt', 'VERSION.txt:stream', './VERSION.txt', 'VERSION.txt.', '*.txt')]
    bad.append({'path': '../ECU-Studio-AI-Kopie/x.txt', 'size': 1, 'sha256': _sha(other / 'x.txt')})
    _inventory(install, '1.20.0', bad)
    result = _cleanup(install, '-Mode', 'Uninstall')
    assert outside.read_text() == 'fremd' and (other / 'x.txt').read_text() == 'x'
    assert result.stdout.count('Behalten (ungültiger Pfad im Inventar)') >= 9
    assert not (install / 'VERSION.txt').exists()               # the valid entry was removed


@windows
def test_junction_inside_the_program_folder_is_not_followed(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', {'VERSION.txt': '1.20.0'})
    outside = tmp_path / 'Dokumente'; outside.mkdir(); (outside / 'projekt.bin').write_text('Projekt')
    link = install / '_internal' / 'daten'
    link.parent.mkdir(parents=True, exist_ok=True)
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True, text=True)
    if made.returncode != 0:
        pytest.skip('Junction konnte nicht angelegt werden: ' + made.stdout + made.stderr)
    _inventory(install, '1.20.0', [{'path': '_internal/daten/projekt.bin', 'size': 7, 'sha256': _sha(outside / 'projekt.bin')}])
    result = _cleanup(install, '-Mode', 'Uninstall')
    assert (outside / 'projekt.bin').read_text() == 'Projekt'
    assert 'Behalten (Verweis/Junction im Pfad)' in result.stdout


@windows
def test_symbolic_link_file_is_not_removed_or_followed(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', {'VERSION.txt': '1.20.0'})
    outside = tmp_path / 'ziel.txt'; outside.write_text('Ziel')
    link = install / 'link.txt'
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f'Symbolische Links nicht erlaubt (Entwicklermodus/Admin): {exc}')
    _inventory(install, '1.20.0', [{'path': 'link.txt', 'size': 4, 'sha256': _sha(outside)}])
    _cleanup(install, '-Mode', 'Uninstall')
    assert outside.read_text() == 'Ziel' and os.path.islink(link)


@windows
@pytest.mark.parametrize('inventory', ['{kaputt', '{"format": 2, "files": []}', '{"format": 1}', ''])
def test_unreadable_or_unknown_inventory_deletes_nothing(tmp_path, inventory):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    (install / 'RUNTIME_INVENTORY.json').write_text(inventory)
    before = sorted(p for p in install.rglob('*'))
    result = _cleanup(install, '-Mode', 'Uninstall')
    assert sorted(p for p in install.rglob('*')) == before and 'nichts gelöscht' in result.stdout


@windows
def test_missing_inventory_and_invalid_program_folder(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    (install / 'RUNTIME_INVENTORY.json').unlink()
    assert 'nichts gelöscht' in _cleanup(install, '-Mode', 'Uninstall').stdout and (install / 'VERSION.txt').exists()
    for bad in ('relativ\\ordner', 'C:\\', str(tmp_path / 'fehlt')):
        result = _cleanup(Path(bad), '-Mode', 'Uninstall', check=False)
        assert result.returncode == 2 and 'nichts gelöscht' in result.stdout


@windows
def test_program_folder_that_is_a_junction_is_refused(tmp_path):
    real = _program(tmp_path / 'echt', '1.20.0', V2)
    link = tmp_path / 'ECU-Studio-AI'
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(real)], capture_output=True, text=True)
    if made.returncode != 0:
        pytest.skip('Junction konnte nicht angelegt werden')
    assert _cleanup(link, '-Mode', 'Uninstall', check=False).returncode == 2
    assert (real / 'VERSION.txt').exists()


@windows
def test_whatif_lists_but_keeps_everything_and_cleanup_is_repeatable(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    result = _cleanup(install, '-Mode', 'Uninstall', '-WhatIf')
    assert 'Entfernt: _internal\\app\\ecu_studio\\core\\integrity.py' in result.stdout
    assert (install / '_internal' / 'app' / 'ecu_studio' / 'core' / 'integrity.py').exists()
    _cleanup(install, '-Mode', 'Uninstall')
    again = _cleanup(install, '-Mode', 'Uninstall')            # interrupted uninstall started again
    assert 'Fertig: 0 Dateien entfernt' in again.stdout


@windows
def test_obsolete_mode_removes_only_unchanged_files_the_new_version_dropped(tmp_path):
    install = _program(tmp_path / 'ECU-Studio-AI', '1.20.1', {**V2, '_internal/app/ecu_studio/alt.py': 'veraltet',
                                                              '_internal/app/ecu_studio/alt2.py': 'veraltet 2'})
    previous = tmp_path / 'previous-inventory.json'; shutil.copy2(install / 'RUNTIME_INVENTORY.json', previous)
    (install / '_internal' / 'app' / 'ecu_studio' / 'alt2.py').write_text('vom Nutzer angepasst')
    # the new version no longer ships alt.py / alt2.py
    (install / '_internal' / 'app' / 'ecu_studio' / 'alt.py').rename(tmp_path / 'tmp.py')
    (install / '_internal' / 'app' / 'ecu_studio' / 'alt2.py').rename(tmp_path / 'tmp2.py')
    _inventory(install, '1.20.2')
    (tmp_path / 'tmp.py').rename(install / '_internal' / 'app' / 'ecu_studio' / 'alt.py')
    (tmp_path / 'tmp2.py').rename(install / '_internal' / 'app' / 'ecu_studio' / 'alt2.py')
    _cleanup(install, '-Mode', 'Obsolete', '-Inventory', str(previous), '-Keep', str(install / 'RUNTIME_INVENTORY.json'))
    assert not (install / '_internal' / 'app' / 'ecu_studio' / 'alt.py').exists()
    assert (install / '_internal' / 'app' / 'ecu_studio' / 'alt2.py').read_text() == 'vom Nutzer angepasst'
    assert all((install / p).exists() for p in V2)              # everything still shipped stays
    # without a readable new inventory nothing is removed
    (install / '_internal' / 'app' / 'ecu_studio' / 'alt.py').write_text('veraltet')
    result = _cleanup(install, '-Mode', 'Obsolete', '-Inventory', str(previous), '-Keep', str(tmp_path / 'fehlt.json'))
    assert (install / '_internal' / 'app' / 'ecu_studio' / 'alt.py').exists() and 'nichts gelöscht' in result.stdout


def test_installer_uses_inventory_cleanup_and_no_pattern_rule():
    text = ISS.read_text(encoding='utf-8-sig')
    delete_section = text.split('\n[UninstallDelete]', 1)[1].split('\n[Code]', 1)[0]
    rules = [line for line in delete_section.splitlines() if line.strip() and not line.lstrip().startswith(';')]
    assert rules == ['Type: filesandordirs; Name: "{app}.backup"', 'Type: filesandordirs; Name: "{app}.update-staging"']
    assert "CleanupScript = '_internal\\uninstall_cleanup.ps1'" in text
    assert "RunInventoryCleanup('-Mode Uninstall')" in text and 'usUninstall' in text
    assert '-Mode Obsolete' in text and 'ssPostInstall' in text and 'ssInstall' in text
    # The script removes its own file in {app}: it must run from a temporary copy.
    assert "ExpandConstant('{tmp}\\uninstall_cleanup.ps1')" in text
    source = (ROOT / 'src' / 'ecu_studio' / 'tools' / 'build_portable_runtime.py').read_text(encoding='utf-8')
    assert "'uninstall_cleanup.ps1'" in source


# ---- updater.ps1 -Installer -------------------------------------------------------------------------
def _package(folder: Path, version: str, extra: dict | None = None):
    folder.mkdir(parents=True)
    shutil.copy2(CMD, folder / 'ECU-Studio-AI.exe')
    (folder / 'VERSION.txt').write_text(version)
    (folder / '_internal').mkdir()
    (folder / '_internal' / 'app.py').write_text(f'print("{version}")')
    for relative, text in (extra or {}).items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True); (folder / relative).write_text(text)
    _inventory(folder, version)


@pytest.fixture
def installed(tmp_path):
    """Installation 1.20.1 made 'with the installer' + a fake setup that copies 1.20.2 over it."""
    install = tmp_path / 'ECU-Studio-AI'
    _package(install, '1.20.1')
    (install / 'unins000.exe').write_text('uninstaller'); (install / 'unins000.dat').write_text('log')
    (install / 'meine_notizen.txt').write_text('vom Nutzer')
    payload = tmp_path / 'payload'
    _package(payload, '1.20.2', {'_internal/neu.py': 'neu in 1.20.2'})
    script = tmp_path / 'fake-setup.cmd'
    script.write_text(f'@echo off\r\nxcopy /E /Y /I /Q "{payload}" "%ECU_TEST_TARGET%" >nul\r\nexit /b %ECU_TEST_EXIT%\r\n')
    setup = tmp_path / 'ECU-Studio-AI-1.20.2-setup.exe'
    shutil.copy2(CMD, setup)                                    # cmd.exe /c fake-setup.cmd <Inno arguments>
    return install, setup, script, payload, tmp_path


def _update(install, setup, script, digest=None, exit_code=0, check='/c exit 0', expected='1.20.2', key=''):
    env = dict(os.environ, ECU_UPDATER_QUIET='1', ECU_TEST_TARGET=str(install), ECU_TEST_EXIT=str(exit_code))
    return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(UPDATER),
                           '-InstallDir', str(install), '-Installer', str(setup), '-Sha256', digest or _sha(setup),
                           '-ExpectedVersion', expected, '-CheckArguments', check,
                           '-InstallerArguments', f'/c {script}', '-UninstallKey', key],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=300)


@windows
def test_installer_update_keeps_user_files_and_a_backup(installed):
    install, setup, script, _, tmp = installed
    result = _update(install, setup, script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.20.2' and (install / '_internal' / 'neu.py').exists()
    assert (install / 'meine_notizen.txt').read_text() == 'vom Nutzer' and (install / 'unins000.exe').exists()
    assert (tmp / 'ECU-Studio-AI.backup' / 'VERSION.txt').read_text() == '1.20.1'
    assert 'Update per Installer installiert' in result.stdout


@windows
@pytest.mark.parametrize('case', ['setup_fails', 'self_check_fails', 'wrong_version', 'incomplete'])
def test_installer_update_rolls_back_on_any_failure(installed, case):
    install, setup, script, payload, tmp = installed
    if case == 'incomplete':
        (payload / '_internal' / 'app.py').write_text('manipuliert')       # inventory no longer matches
    result = _update(install, setup, script, exit_code=5 if case == 'setup_fails' else 0,
                     check='/c exit 7' if case == 'self_check_fails' else '/c exit 0',
                     expected='9.9.9' if case == 'wrong_version' else '1.20.2')
    assert result.returncode == 3, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.20.1' and not (install / '_internal' / 'neu.py').exists()
    assert (install / 'meine_notizen.txt').read_text() == 'vom Nutzer' and (install / 'unins000.exe').exists()
    assert not (tmp / 'ECU-Studio-AI.update-failed').exists() and 'Rollback' in result.stdout


@windows
def test_installer_update_refuses_wrong_checksum_and_portable_copies(installed):
    install, setup, script, _, tmp = installed
    result = _update(install, setup, script, digest='0' * 64)
    assert result.returncode == 2 and (install / 'VERSION.txt').read_text() == '1.20.1'
    assert not (tmp / 'ECU-Studio-AI.backup').exists()
    (install / 'unins000.exe').unlink()                          # portable copy: no installer route
    result = _update(install, setup, script)
    assert result.returncode == 2 and 'unins000.exe fehlt' in result.stdout
    assert (install / 'VERSION.txt').read_text() == '1.20.1'


# ---- registry (throw-away key, CI only) --------------------------------------------------------------
@pytest.fixture
def test_key():
    import winreg
    sub = rf'Software\ECU-Studio-AI-Tests\{uuid.uuid4()}'
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub)
    yield sub, 'HKCU:\\' + sub
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)


def _set(sub, **values):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_SET_VALUE) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _get(sub, name):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as key:
        return winreg.QueryValueEx(key, name)[0]


@ci_registry
def test_zip_update_and_restore_keep_apps_and_features_in_line(installed, test_key):
    install, _, _, payload, tmp = installed
    sub, ps_key = test_key
    _set(sub, InstallLocation=str(install) + '\\', DisplayVersion='1.20.1', DisplayName='ECU Studio AI 1.20.1')
    archive = tmp / 'update.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for p in payload.rglob('*'):
            if p.is_file():
                z.write(p, 'ECU-Studio-AI/' + p.relative_to(payload).as_posix())
    env = dict(os.environ, ECU_UPDATER_QUIET='1')
    base = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(UPDATER), '-InstallDir', str(install),
            '-CheckArguments', '/c exit 0', '-UninstallKey', ps_key]
    run = lambda *a: subprocess.run(base + list(a), capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=300)
    assert run('-Archive', str(archive), '-Sha256', _sha(archive)).returncode == 0
    assert (_get(sub, 'DisplayVersion'), _get(sub, 'DisplayName')) == ('1.20.2', 'ECU Studio AI 1.20.2')
    assert run('-Restore').returncode == 0
    assert _get(sub, 'DisplayVersion') == '1.20.1'


@ci_registry
def test_entry_of_another_folder_is_not_touched_and_blocks_the_installer_route(installed, test_key):
    install, setup, script, _, tmp = installed
    sub, ps_key = test_key
    _set(sub, InstallLocation=str(tmp / 'andere-Installation') + '\\', DisplayVersion='1.0.0')
    result = _update(install, setup, script, key=ps_key)
    assert result.returncode == 2 and 'anderen Ordner' in result.stdout
    assert _get(sub, 'DisplayVersion') == '1.0.0' and (install / 'VERSION.txt').read_text() == '1.20.1'


# ---- route and version display (pure Python, all systems) --------------------------------------------
BASE = 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v1.20.2/'


def _payload(with_setup=True, setup_url=BASE):
    zip_name, setup_name = 'ECU-Studio-AI-1.20.2-windows-x64.zip', 'ECU-Studio-AI-1.20.2-setup.exe'
    assets = [{'name': zip_name, 'browser_download_url': BASE + zip_name, 'size': 5},
              {'name': zip_name + '.sha256', 'browser_download_url': BASE + zip_name + '.sha256', 'size': 90}]
    if with_setup:
        assets += [{'name': setup_name, 'browser_download_url': setup_url + setup_name, 'size': 7,
                    'digest': 'sha256:' + 'a' * 64},
                   {'name': setup_name + '.sha256', 'browser_download_url': BASE + setup_name + '.sha256', 'size': 90}]
    return {'tag_name': 'v1.20.2', 'draft': False, 'prerelease': False, 'body': 'x', 'html_url': '', 'assets': assets}


def test_release_offers_the_setup_only_from_official_urls():
    release = updates.parse_release(_payload())
    assert release.installer.name == 'ECU-Studio-AI-1.20.2-setup.exe' and release.installer.api_digest == 'sha256:' + 'a' * 64
    assert updates.parse_release(_payload(with_setup=False)).installer is None
    assert updates.parse_release(_payload(setup_url='https://example.com/')).installer is None
    assert updates.parse_release(_payload(setup_url='https://example.com/')).archive_name.endswith('.zip')


def test_installer_download_is_verified_like_the_zip(tmp_path):
    import io
    data = b'setup!!'
    release = updates.parse_release(_payload())
    release = updates.Release(*[getattr(release, f) for f in ('version', 'notes', 'page_url', 'archive_name', 'archive_url',
                                                            'archive_size', 'checksum_url', 'api_digest', 'signature_url')],
                              installer=updates.Asset(release.installer.name, release.installer.url, len(data),
                                                      release.installer.checksum_url, None))

    class R(io.BytesIO):
        def __init__(self, d, u): super().__init__(d); self.u = u
        def geturl(self): return self.u
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    good = hashlib.sha256(data).hexdigest()
    files = {release.installer.url: data, release.installer.checksum_url: f'{good}  {release.installer.name}\r\n'.encode()}
    opener = lambda req, timeout=None: R(files[req.full_url], 'https://objects.githubusercontent.com/x')
    path, digest = updates.download(release, tmp_path, opener=opener, installer=True)
    assert path.name == release.installer.name and digest == good
    files[release.installer.checksum_url] = f'{"0" * 64}  {release.installer.name}'.encode()
    with pytest.raises(updates.UpdateError):
        updates.download(release, tmp_path / 'x', opener=opener, installer=True)
    assert not list((tmp_path / 'x').glob('*.exe'))
    with pytest.raises(updates.UpdateError, match='keinen Installer'):
        updates.download(updates.parse_release(_payload(with_setup=False)), tmp_path, opener=opener, installer=True)


def test_update_route_needs_uninstaller_matching_entry_and_setup(tmp_path):
    root = tmp_path / 'ECU-Studio-AI'; root.mkdir()
    release, no_setup = updates.parse_release(_payload()), updates.parse_release(_payload(with_setup=False))
    entry = lambda location: (lambda: {'InstallLocation': location, 'DisplayVersion': '1.20.1'})
    assert updates.update_route(root, release, entry(str(root) + '\\')) == 'archive'      # no unins000.exe
    (root / 'unins000.exe').write_text('u')
    assert updates.update_route(root, release, entry(str(root) + '\\')) == 'installer'
    assert updates.update_route(root, release, entry(str(root).upper())) == 'installer'   # case-insensitive path
    assert updates.update_route(root, release, entry(str(tmp_path / 'andere'))) == 'archive'
    assert updates.update_route(root, release, lambda: None) == 'archive'
    assert updates.update_route(root, no_setup, entry(str(root))) == 'archive'
    assert updates.update_route(None, release, entry(str(root))) == 'archive'


def test_apps_and_features_version_follows_the_installed_version(tmp_path):
    root = tmp_path / 'ECU-Studio-AI'; root.mkdir()
    written = []
    entry = {'InstallLocation': str(root) + '\\', 'DisplayVersion': '1.16.3', 'DisplayName': 'ECU Studio AI 1.16.3'}
    assert updates.sync_uninstall_entry(root, '1.20.1', lambda: entry, written.append) is True
    assert written == [{'DisplayVersion': '1.20.1', 'DisplayName': 'ECU Studio AI 1.20.1'}]
    written.clear()
    assert updates.sync_uninstall_entry(root, '1.20.1', lambda: {**entry, 'DisplayVersion': '1.20.1'}, written.append) is False
    assert updates.sync_uninstall_entry(root, '1.20.1', lambda: {**entry, 'InstallLocation': str(tmp_path)}, written.append) is False
    assert updates.sync_uninstall_entry(root, '1.20.1', lambda: None, written.append) is False
    assert updates.sync_uninstall_entry(root, 'kaputt', lambda: entry, written.append) is False
    assert written == []


def test_controller_hands_the_installer_route_to_the_updater(tmp_path, monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QWidget
    from ecu_studio.ui import updates as ui
    QApplication.instance() or QApplication([])
    w = QWidget(); w.settings = QSettings(str(tmp_path / 's.ini'), QSettings.Format.IniFormat); w.close = lambda: None
    root = tmp_path / 'ECU-Studio-AI'; (root / '_internal').mkdir(parents=True); (root / '_internal' / 'updater.ps1').write_text('')
    monkeypatch.setattr(ui.updates, 'install_root', lambda exe: root)
    monkeypatch.setattr(ui, 'data_dir', lambda: tmp_path / 'data')
    started = []
    monkeypatch.setattr(ui.subprocess, 'Popen', lambda cmd, **k: started.append(cmd))
    c = ui.UpdateController(w)
    c.pending = ('update', tmp_path / 'ECU-Studio-AI-1.20.2-setup.exe', 'ab' * 32, 'installer', '1.20.2')
    assert c.launch_pending() is True
    cmd = started[0]
    assert cmd[cmd.index('-Installer') + 1].endswith('setup.exe') and cmd[cmd.index('-ExpectedVersion') + 1] == '1.20.2'
    assert '-Archive' not in cmd
    c.pending = ('update', tmp_path / 'a.zip', 'cd' * 32)              # older pending tuple: ZIP route
    assert c.launch_pending() is True and '-Archive' in started[1] and '-Installer' not in started[1]
