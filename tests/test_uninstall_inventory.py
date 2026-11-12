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
    text = ISS.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    # No [UninstallDelete] rule at all (from 1.20.1): up to 1.20.0 {app}.backup and {app}.update-staging were
    # deleted as a whole ("filesandordirs"), including user files and changed program files kept only there.
    delete_section = text.split('\n[UninstallDelete]', 1)[1].split('\n[Code]', 1)[0]
    rules = [line for line in delete_section.splitlines() if line.strip() and not line.lstrip().startswith(';')]
    assert rules == []
    assert 'filesandordirs' not in text.replace(delete_section, '') and 'DelTree' not in text
    for section in ('[InstallDelete]', '[Dirs]'):
        assert section not in text
    # Backup and staging are cleaned file by file, compared with the still complete {app}, BEFORE {app} is cleaned.
    # First they are renamed: unins000.dat of installations set up with 1.20.0 or older still holds the old blanket
    # rules for exactly these two paths, and Inno runs them after [Code] (measured in the installer QA, Repair mode).
    def body(name):
        part = text.split(name, 1)[1].split('\nend;\n', 1)[0]
        return '\n'.join(line.split('//', 1)[0] for line in part.split('\nbegin\n', 1)[1].splitlines())

    step = body('procedure CurUninstallStepChanged')
    # Both renames come first; a folder that could not be renamed stops the uninstallation before ANY removal
    # (forced in the real uninstaller: release.yml update-test and installer QA mode Blocked).
    order = [step.index(call) for call in ("BackupFolder := ExpandConstant('{app}') + '.backup'",
                                           "StagingFolder := ExpandConstant('{app}') + '.update-staging'",
                                           'if not MoveAside(BackupFolder, Backup) then\n      StopUninstall(BackupFolder);',
                                           'if not MoveAside(StagingFolder, Staging) then',
                                           'PutBack(Backup, BackupFolder);',
                                           'StopUninstall(StagingFolder);',
                                           'RunLeftoverCleanup(Backup)',
                                           "RunLeftoverCleanup(Staging + '\\ECU-Studio-AI')",
                                           'RemoveDir(Staging)',
                                           "RunInventoryCleanup('-Mode Uninstall')")]
    assert order == sorted(order) and 'if CurUninstallStep = usUninstall then' in step
    assert step.count('MoveAside(') == 2 and step.count('StopUninstall(') == 2
    assert "'-Mode Leftover -Reference \"' + ExpandConstant('{app}') + '\"'" in text
    move = body('function MoveAside')
    assert 'function MoveAside(Folder: String; var Target: String): Boolean;' in text
    assert "Folder + '.erhalten'" in move and 'RenameFile(Folder, Target)' in move
    assert 'DirExists(Target) or FileExists(Target)' in move    # never onto an existing folder or file
    # Success means: nothing exists under the old name any more (checked AFTER the rename, never assumed).
    assert move.rstrip().endswith('Result := not (DirExists(Folder) or FileExists(Folder));')
    assert move.count('Result :=') == 1
    put_back = body('procedure PutBack')
    for code in (move, put_back):
        assert 'Delete' not in code and 'RemoveDir' not in code and 'Exec' not in code   # renames, nothing else
    assert 'RenameFile(Target, Folder)' in put_back
    # The stop removes nothing and ends with Abort (documented to end the uninstaller in usUninstall).
    stop = body('procedure StopUninstall')
    assert stop.rstrip().endswith('Abort;') and 'Log(' in stop and 'SuppressibleMsgBox(' in stop
    for call in ('Delete', 'RemoveDir', 'Exec', 'RunCleanup', 'Rename'):
        assert call not in stop
    # The script recognises only THIS application's uninstaller files: same AppId, AppName and AppPublisher.
    script = CLEANUP.read_text(encoding='utf-8-sig')
    app_id = text.split('\nAppId={', 1)[1].split('\n', 1)[0]
    assert app_id.startswith('{') and f"$AppId = '{app_id}'" in script
    assert "$AppName = 'ECU Studio AI'" in script and '\nAppName=ECU Studio AI\n' in text
    assert "$AppPublisher = 'PCTestAdmin'" in script and '\nAppPublisher=PCTestAdmin\n' in text
    assert "CleanupScript = '_internal\\uninstall_cleanup.ps1'" in text
    assert "RunInventoryCleanup('-Mode Uninstall')" in text and 'usUninstall' in text
    assert '-Mode Obsolete' in text and 'ssPostInstall' in text and 'ssInstall' in text
    # The script removes its own file in {app}: it must run from a temporary copy.
    assert "ExpandConstant('{tmp}\\uninstall_cleanup.ps1')" in text
    source = (ROOT / 'src' / 'ecu_studio' / 'tools' / 'build_portable_runtime.py').read_text(encoding='utf-8')
    assert "'uninstall_cleanup.ps1'" in source


# ---- -Mode Leftover: <app>.backup and <app>.update-staging (from 1.20.1) -------------------------------
# Up to 1.20.0 [UninstallDelete] removed both folders as a whole. Now only files of proven origin go.
APP_ID = '{F8CD5330-FC90-4891-BFDA-58E6668C93A5}'


def _inno_log(path: Path, app_id=APP_ID, app_name='ECU Studio AI', ident='Inno Setup Uninstall Log (b) 64-bit'):
    def field(text, size):
        return text.encode('ascii').ljust(size, b'\0')
    path.write_bytes(field(ident, 64) + field(app_id, 128) + field(app_name, 128) + b'\0' * 64 + os.urandom(256))
    return path


def _files(folder: Path) -> list:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file())


def _leftover(folder: Path, app: Path, *args, check=True):
    return _cleanup(folder, '-Mode', 'Leftover', '-Reference', str(app), *args, check=check)


def _after_zip_update(tmp_path):
    """In-app update 1.19.1 -> 1.20.0 (ZIP route): the old version is now <app>.backup; the updater carried
    unins000.* and the user's own file over into the new program folder."""
    app = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    backup = _program(tmp_path / 'ECU-Studio-AI.backup', '1.19.1', V1)
    _inno_log(backup / 'unins000.dat'); shutil.copy2(CMD, backup / 'unins000.exe')
    (backup / '_internal' / 'meine_notizen.txt').write_text('vom Nutzer')
    for name in ('unins000.dat', 'unins000.exe', '_internal/meine_notizen.txt'):
        shutil.copy2(backup / name, app / name)
    for folder in (app, backup):                       # the real program ships an empty folder (Inno createallsubdirs)
        (folder / EMPTY_SHIPPED).mkdir(parents=True)
    return app, backup


EMPTY_SHIPPED = '_internal/python/Lib/site-packages/numpy/random/lib'


@windows
def test_leftover_backup_after_zip_update_is_removed_completely(tmp_path):
    app, backup = _after_zip_update(tmp_path)
    app_before = {p: _sha(app / p) for p in _files(app)}
    result = _leftover(backup, app)
    assert not backup.exists(), result.stdout
    assert {p: _sha(app / p) for p in _files(app)} == app_before          # the program folder is untouched
    assert (app / EMPTY_SHIPPED).is_dir()
    assert 'Entfernt (gleiche Kopie im Programmordner): _internal\\meine_notizen.txt' in result.stdout
    assert 'Entfernt (Inventar, nichts sonst übrig): RUNTIME_INVENTORY.json' in result.stdout
    assert 'Ordner entfernt' in result.stdout
    # The user's file lives on in the program folder; the uninstall there keeps it (not in the inventory).
    _cleanup(app, '-Mode', 'Uninstall')
    assert (app / '_internal' / 'meine_notizen.txt').read_text() == 'vom Nutzer'


@windows
def test_leftover_keeps_changed_program_file_and_user_files_without_a_copy(tmp_path):
    app, backup = _after_zip_update(tmp_path)
    core = backup / '_internal' / 'app' / 'ecu_studio' / 'core'
    (core / 'updates.py').write_text('vom Nutzer geändert, nur hier')              # changed shipped file
    (backup / '_internal' / 'eigenes_plugin.py').write_text('nur im Backup')       # own file, no copy in {app}
    (backup / 'notiz.txt').write_text('Notiz A'); (app / 'notiz.txt').write_text('Notiz B')   # same name, other content
    result = _leftover(backup, app)
    assert (core / 'updates.py').read_text() == 'vom Nutzer geändert, nur hier'
    assert (backup / '_internal' / 'eigenes_plugin.py').read_text() == 'nur im Backup'
    assert (backup / 'notiz.txt').read_text() == 'Notiz A' and (app / 'notiz.txt').read_text() == 'Notiz B'
    assert (backup / 'RUNTIME_INVENTORY.json').exists()                             # other files remain
    assert _files(backup) == ['RUNTIME_INVENTORY.json', '_internal/app/ecu_studio/core/updates.py',
                              '_internal/eigenes_plugin.py', 'notiz.txt']
    assert 'Behalten (unbekannt oder verändert, keine gleiche Kopie im Programmordner): _internal\\eigenes_plugin.py' in result.stdout
    assert 'Ordner bleibt (nicht leer)' in result.stdout


@windows
def test_leftover_own_file_whose_name_a_new_version_took_stays(tmp_path):
    """The user had an own file at a path that only the new version ships. The updater does not overwrite the
    new program file, so the backup holds the ONLY copy of the user's file: it must stay."""
    app, backup = _after_zip_update(tmp_path)
    (backup / '_internal' / 'app' / 'ecu_studio' / 'core' / 'integrity.py').write_text('eigene Version des Nutzers')
    _leftover(backup, app)
    assert (backup / '_internal' / 'app' / 'ecu_studio' / 'core' / 'integrity.py').read_text() == 'eigene Version des Nutzers'
    assert backup.is_dir()


@windows
def test_leftover_inventory_listed_but_changed_file_with_identical_twin_is_a_copy(tmp_path):
    """A changed shipped file whose identical copy is in {app} (the updater carried it over): the backup copy goes,
    the program folder's copy stays (changed, so the uninstall there keeps it as well)."""
    app = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    backup = _program(tmp_path / 'ECU-Studio-AI.backup', '1.19.1', V1)
    (backup / 'VERSION.txt').write_text('angepasst'); (app / 'VERSION.txt').write_text('angepasst')
    _leftover(backup, app)
    assert not backup.exists() and (app / 'VERSION.txt').read_text() == 'angepasst'


@windows
def test_leftover_uninstaller_files_need_this_applications_identity(tmp_path):
    app = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    _inno_log(app / 'unins000.dat'); (app / 'unins000.exe').write_text('neuer Deinstaller')   # differ from the backup's
    cases = {'unins000.dat': _inno_log(tmp_path / 'ok.dat'),
             'unins001.dat': _inno_log(tmp_path / 'fremd.dat', app_id='{00000000-0000-0000-0000-000000000000}'),
             'unins002.dat': _inno_log(tmp_path / 'name.dat', app_name='Andere Anwendung'),
             'unins003.dat': _inno_log(tmp_path / 'id.dat', ident='Kein Inno Setup Log'),
             'unins004.dat': tmp_path / 'kurz.dat'}
    cases['unins004.dat'].write_bytes(b'Inno Setup Uninstall Log (b)')                  # too short
    backup = _program(tmp_path / 'ECU-Studio-AI.backup', '1.19.1', V1)
    for name, source in cases.items():
        shutil.copy2(source, backup / name)
    shutil.copy2(CMD, backup / 'unins000.exe')   # a PE file, but not this application's uninstaller
    (backup / 'unins001.exe').write_text('kein Programm')
    (backup / 'sub').mkdir(); shutil.copy2(cases['unins000.dat'], backup / 'sub' / 'unins000.dat')   # not at top level
    result = _leftover(backup, app)
    assert _files(backup) == ['RUNTIME_INVENTORY.json', 'sub/unins000.dat', 'unins000.exe', 'unins001.dat',
                              'unins001.exe', 'unins002.dat', 'unins003.dat', 'unins004.dat']
    assert 'Entfernt (Deinstallationsprotokoll dieser Anwendung): unins000.dat' in result.stdout


@windows
def test_leftover_twin_held_open_by_the_uninstaller_is_judged_by_the_other_rules(tmp_path):
    """Installer QA, Rollback mode: {app}\\unins000.dat is held open by the running uninstaller. An unreadable copy
    proves nothing; the backup's own uninstall log is then recognised by its header (this application) instead."""
    app, backup = _after_zip_update(tmp_path)
    _inno_log(backup / 'unins000.dat'); shutil.copy2(backup / 'unins000.dat', app / 'unins000.dat')
    (backup / '_internal' / 'fremd.txt').write_text('gleich'); (app / '_internal' / 'fremd.txt').write_text('gleich')
    with open(app / 'unins000.dat', 'ab'), open(app / '_internal' / 'fremd.txt', 'ab'):   # write handles, as Inno
        result = _leftover(backup, app)
    assert 'Entfernt (Deinstallationsprotokoll dieser Anwendung): unins000.dat' in result.stdout
    assert 'zählt nicht als gleich' in result.stdout
    assert _files(backup) == ['RUNTIME_INVENTORY.json', '_internal/fremd.txt']    # no other proof: kept


@windows
def test_leftover_does_not_follow_junctions_and_keeps_the_folder(tmp_path):
    app, backup = _after_zip_update(tmp_path)
    outside = tmp_path / 'Dokumente'; outside.mkdir(); (outside / 'projekt.bin').write_text('Projekt')
    (app / 'daten').mkdir(); (app / 'daten' / 'projekt.bin').write_text('Projekt')    # identical twin in {app}
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(backup / 'daten'), str(outside)], capture_output=True, text=True)
    if made.returncode != 0:
        pytest.skip('Junction konnte nicht angelegt werden: ' + made.stdout + made.stderr)
    result = _leftover(backup, app)
    assert (outside / 'projekt.bin').read_text() == 'Projekt' and (backup / 'daten').is_dir()
    assert 'Behalten (Verweis/Junction): daten' in result.stdout
    assert _files(outside) == ['projekt.bin'] and (backup / 'RUNTIME_INVENTORY.json').exists()


@windows
def test_leftover_twin_behind_a_junction_in_the_program_folder_does_not_count(tmp_path):
    app, backup = _after_zip_update(tmp_path)
    elsewhere = tmp_path / 'anderswo'; elsewhere.mkdir(); (elsewhere / 'notiz.txt').write_text('gleich')
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(app / 'extern'), str(elsewhere)], capture_output=True, text=True)
    if made.returncode != 0:
        pytest.skip('Junction konnte nicht angelegt werden: ' + made.stdout + made.stderr)
    (backup / 'extern').mkdir(); (backup / 'extern' / 'notiz.txt').write_text('gleich')
    _leftover(backup, app)
    assert (backup / 'extern' / 'notiz.txt').read_text() == 'gleich'


@windows
def test_leftover_refuses_invalid_calls_and_deletes_nothing(tmp_path):
    app, backup = _after_zip_update(tmp_path)
    before = _files(backup)
    for args in ([], ['-Reference', 'relativ\\ordner'], ['-Reference', 'C:\\'], ['-Reference', str(tmp_path / 'fehlt')],
                 ['-Reference', str(backup)], ['-Reference', str(tmp_path)], ['-Reference', str(backup / '_internal')]):
        result = _cleanup(backup, '-Mode', 'Leftover', *args, check=False)
        assert result.returncode == 2 and 'nichts gelöscht' in result.stdout, args
    assert _files(backup) == before
    link = tmp_path / 'ECU-Studio-AI.update-staging'
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(backup)], capture_output=True, text=True)
    if made.returncode == 0:                                                       # the folder itself is a junction
        assert _leftover(link, app, check=False).returncode == 2
        assert _files(backup) == before


@pytest.mark.parametrize('inventory', ['{kaputt', '{"format": 2, "files": []}', None])
@windows
def test_leftover_without_valid_inventory_removes_only_proven_copies(tmp_path, inventory):
    app, backup = _after_zip_update(tmp_path)
    (backup / 'nur_hier.txt').write_text('unbekannt')
    if inventory is None:
        (backup / 'RUNTIME_INVENTORY.json').unlink()
    else:
        (backup / 'RUNTIME_INVENTORY.json').write_text(inventory)
    _leftover(backup, app)
    left = _files(backup)
    assert 'nur_hier.txt' in left
    assert ('RUNTIME_INVENTORY.json' in left) == (inventory is not None)          # an invalid inventory stays
    # V1 files differ from V2 and are not proven without the inventory; identical carried-over files are copies.
    assert '_internal/app/ecu_studio/main.py' in left and '_internal/meine_notizen.txt' not in left


@windows
def test_leftover_whatif_removes_nothing(tmp_path):
    app, backup = _after_zip_update(tmp_path)
    before = {p: _sha(backup / p) for p in _files(backup)}
    result = _leftover(backup, app, '-WhatIf')
    assert {p: _sha(backup / p) for p in _files(backup)} == before
    assert 'Entfernt (gleiche Kopie im Programmordner)' in result.stdout and 'Ordner entfernt' not in result.stdout


@windows
def test_leftover_interrupted_update_staging(tmp_path):
    """A staging folder left by an interrupted update: an unchanged new version (own inventory) is removed;
    any other file in the staging root keeps that folder (RemoveDir in installer.iss only removes empty ones)."""
    app = _program(tmp_path / 'ECU-Studio-AI', '1.20.0', V2)
    staging = tmp_path / 'ECU-Studio-AI.update-staging'
    _program(staging / 'ECU-Studio-AI', '1.20.1', {**V2, 'VERSION.txt': '1.20.1'})
    (staging / 'ECU-Studio-AI' / '_internal' / 'eigene.txt').write_text('fremd')
    result = _leftover(staging / 'ECU-Studio-AI', app)
    assert _files(staging) == ['ECU-Studio-AI/RUNTIME_INVENTORY.json', 'ECU-Studio-AI/_internal/eigene.txt']
    (staging / 'ECU-Studio-AI' / '_internal' / 'eigene.txt').unlink()
    result = _leftover(staging / 'ECU-Studio-AI', app)
    assert not (staging / 'ECU-Studio-AI').exists() and staging.is_dir() and 'Ordner entfernt' in result.stdout


# ---- updater.ps1 -Installer -------------------------------------------------------------------------
def _package(folder: Path, version: str, extra: dict | None = None):
    folder.mkdir(parents=True)
    shutil.copy2(CMD, folder / 'ECU-Studio-AI.exe')
    (folder / 'VERSION.txt').write_text(version)
    (folder / '_internal').mkdir()
    (folder / '_internal' / 'app.py').write_text(f'print("{version}")')
    shutil.copy2(CLEANUP, folder / '_internal' / 'uninstall_cleanup.ps1')          # shipped like in the real package
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
    assert 'Rollback' in result.stdout
    # The failed new version is cleaned file by file against the restored installation, never deleted as a whole.
    failed = tmp / 'ECU-Studio-AI.update-failed'
    if case == 'incomplete':
        # The setup wrote a file that matches neither its inventory nor the restored installation: its origin is not
        # proven, so it stays (with the inventory that describes the folder) - and nothing else.
        assert _files(failed) == ['RUNTIME_INVENTORY.json', '_internal/app.py']
        assert (failed / '_internal' / 'app.py').read_text() == 'manipuliert'
    else:
        assert not failed.exists(), _files(failed)
    assert not list(tmp.glob('*.erhalten*')) and not (tmp / 'ECU-Studio-AI.update-staging').exists()


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


# ---- updater.ps1: existing folders are never deleted as a whole (from 1.20.1) ---------------------------
def _tree(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): _sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def _names(tmp: Path) -> list:
    return sorted(p.name for p in tmp.iterdir() if p.name != 'update.zip')     # the archive of the ZIP route


def _old_backup(tmp: Path) -> Path:
    """<app>.backup left by an earlier update: version 1.20.0 plus a file of the user and a program file the user
    changed - the backup may hold the ONLY copy of both."""
    old = tmp / 'ECU-Studio-AI.backup'
    _package(old, '1.20.0')
    (old / '_internal' / 'app.py').write_text('vom Nutzer angepasst')
    (old / 'eigene.txt').write_text('nur in der Sicherung')
    return old


def _zip_update(install, payload, tmp, check='/c exit 0'):
    archive = tmp / 'update.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for p in payload.rglob('*'):
            if p.is_file():
                z.write(p, 'ECU-Studio-AI/' + p.relative_to(payload).as_posix())
    env = dict(os.environ, ECU_UPDATER_QUIET='1')
    return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(UPDATER),
                           '-InstallDir', str(install), '-Archive', str(archive), '-Sha256', _sha(archive),
                           '-CheckArguments', check, '-UninstallKey', ''],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=300)


def _route(route, install, setup, script, payload, tmp, fail=False):
    if route == 'installer':
        return _update(install, setup, script, expected='9.9.9' if fail else '1.20.2')
    return _zip_update(install, payload, tmp, check='/c exit 7' if fail else '/c exit 0')


@windows
@pytest.mark.parametrize('route', ['installer', 'zip'])
def test_update_cleans_existing_backup_file_by_file_and_keeps_user_and_changed_files(installed, route):
    install, setup, script, payload, tmp = installed
    _old_backup(tmp)
    result = _route(route, install, setup, script, payload, tmp)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.20.2'
    assert (tmp / 'ECU-Studio-AI.backup' / 'VERSION.txt').read_text() == '1.20.1'   # the new backup
    kept = tmp / 'ECU-Studio-AI.backup.erhalten'                                   # the old one, file by file
    assert _files(kept) == ['RUNTIME_INVENTORY.json', '_internal/app.py', 'eigene.txt'], result.stdout
    assert (kept / '_internal' / 'app.py').read_text() == 'vom Nutzer angepasst'
    assert (kept / 'eigene.txt').read_text() == 'nur in der Sicherung'
    assert 'Beiseitegelegt (nichts gelöscht)' in result.stdout


@windows
def test_zip_update_cleans_an_interrupted_staging_folder_file_by_file(installed):
    install, setup, script, payload, tmp = installed
    left = tmp / 'ECU-Studio-AI.update-staging'
    _package(left / 'ECU-Studio-AI', '1.20.2')                    # an interrupted earlier update
    (left / 'ECU-Studio-AI' / '_internal' / 'eigene.txt').write_text('fremd')
    result = _zip_update(install, payload, tmp)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.20.2' and not left.exists()
    assert _files(tmp / 'ECU-Studio-AI.update-staging.erhalten') == [
        'ECU-Studio-AI/RUNTIME_INVENTORY.json', 'ECU-Studio-AI/_internal/eigene.txt']


@windows
@pytest.mark.parametrize('route', ['installer', 'zip'])
def test_locked_existing_backup_stops_the_update_before_any_change(installed, route):
    install, setup, script, payload, tmp = installed
    old = _old_backup(tmp)
    staging = tmp / 'ECU-Studio-AI.update-staging'
    (staging / 'ECU-Studio-AI').mkdir(parents=True); (staging / 'ECU-Studio-AI' / 'eigene.txt').write_text('fremd')
    before = {folder.name: _tree(folder) for folder in (install, old, staging)}
    names = _names(tmp)
    with open(old / 'eigene.txt', 'rb'):                           # open without delete sharing: rename impossible
        result = _route(route, install, setup, script, payload, tmp)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'beiseitelegen' in result.stdout and 'nichts wurde verändert' in result.stdout
    assert {folder.name: _tree(folder) for folder in (install, old, staging)} == before
    assert _names(tmp) == names          # no *.erhalten, no staging/backup copy left


@windows
@pytest.mark.parametrize('route', ['installer', 'zip'])
def test_rollback_puts_the_existing_backup_back_and_leaves_an_existing_failed_folder_alone(installed, route):
    install, setup, script, payload, tmp = installed
    old = _old_backup(tmp)
    earlier = tmp / 'ECU-Studio-AI.update-failed'                  # left by someone or something earlier
    earlier.mkdir(); (earlier / 'eigene.txt').write_text('nicht von diesem Lauf')
    before = {folder.name: _tree(folder) for folder in (install, old, earlier)}
    names = _names(tmp)
    result = _route(route, install, setup, script, payload, tmp, fail=True)
    assert result.returncode == 3, result.stdout + result.stderr
    assert {folder.name: _tree(folder) for folder in (install, old, earlier)} == before
    assert _names(tmp) == names, result.stdout   # update-failed-2 cleaned, nothing aside
    assert 'Zurückbenannt' in result.stdout


@windows
@pytest.mark.parametrize('problem', ['missing', 'changed'])
def test_without_a_verified_cleanup_script_the_old_backup_is_kept_completely(installed, problem):
    install, setup, script, payload, tmp = installed
    old = _old_backup(tmp)
    before = _tree(old)
    shipped = install / '_internal' / 'uninstall_cleanup.ps1'
    if problem == 'missing':
        shipped.unlink()
    else:
        shipped.write_text(shipped.read_text(encoding='utf-8-sig') + '\n# verändert\n', encoding='utf-8')
    result = _update(install, setup, script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _tree(tmp / 'ECU-Studio-AI.backup.erhalten') == before
    assert 'bleibt vollständig erhalten' in result.stdout


@windows
def test_restore_never_reuses_or_removes_an_existing_swap_folder(installed):
    install, setup, script, payload, tmp = installed
    assert _update(install, setup, script).returncode == 0
    swap = tmp / 'ECU-Studio-AI.restore-swap'
    swap.mkdir(); (swap / 'eigene.txt').write_text('nicht von diesem Lauf')
    env = dict(os.environ, ECU_UPDATER_QUIET='1')
    result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(UPDATER),
                             '-InstallDir', str(install), '-Restore', '-CheckArguments', '/c exit 0', '-UninstallKey', ''],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / 'VERSION.txt').read_text() == '1.20.1'
    assert (tmp / 'ECU-Studio-AI.backup' / 'VERSION.txt').read_text() == '1.20.2'
    assert _files(swap) == ['eigene.txt'] and not (tmp / 'ECU-Studio-AI.restore-swap-2').exists()


def test_updater_deletes_no_existing_folder_as_a_whole():
    text = UPDATER.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    code = '\n'.join(line.split('#', 1)[0] for line in text.split('\n#>', 1)[1].splitlines())
    # No recursive delete anywhere; folders go only through Remove-PlainTree (no links followed) ...
    assert '-Recurse -Force' not in code.replace('Copy-Item -LiteralPath $InstallDir -Destination $backup -Recurse -Force', '')
    for line in code.splitlines():
        if 'Remove-Item' in line:
            assert '-Recurse' not in line, line
    assert code.count('Remove-PlainTree $') == 2            # the recursion itself and Remove-OwnFolder
    own = code.split('function Remove-OwnFolder', 1)[1].split('\n}\n', 1)[0]
    assert 'if (-not $script:own.Contains($path))' in own and 'Remove-PlainTree $path' in own
    # ... and only folders this run created: registered right after proving the path is free.
    adds = [line.strip() for line in code.splitlines() if '$script:own.Add(' in line]
    assert adds == ['$script:own.Add($backup)', '$script:own.Add($staging)']
    for name in ('backup', 'staging'):
        before = code.split(f'$script:own.Add(${name})', 1)[0].rstrip().splitlines()[-1]
        assert f'if (Test-Path -LiteralPath ${name}) {{ Fail 2' in before
    # The backup copy stops being disposable as soon as it is complete (it is then the way back).
    assert code.index('[void]$script:own.Remove($backup)') > code.index('if ($before -ne $copied)')
    # Existing folders: moved aside before use, rollback/swap targets always on a free name.
    assert code.count('Move-Aside $backup') == 2 and code.count('Move-Aside $staging') == 1
    assert "Get-FreeName ($InstallDir + '.update-failed')" in code and "Get-FreeName ($InstallDir + '.restore-swap')" in code
    leftover = code.split('function Invoke-Leftover', 1)[1].split('\n}\n', 1)[0]
    assert "'-Mode', 'Leftover', '-Reference', $reference" in leftover
    init = code.split('function Initialize-Cleanup', 1)[1].split('\n}\n', 1)[0]
    assert "'_internal/uninstall_cleanup.ps1'" in init and '(Get-Sha256 $copy) -ne' in init


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
