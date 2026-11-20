"""Test runs, the smoke test and the screenshot tools never write into the installed program's settings.

Until 1.19.1 the main window used QSettings("ECU Studio", "ECU Studio AI"). That constructor ignores
QSettings.setDefaultFormat, so every test run, `--smoke-test` and the screenshot tools wrote window layout, theme
and update-check time into HKEY_CURRENT_USER of the developer's real ECU Studio AI installation.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path


def _window():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ecu_studio.ui.main_window import Window
    return app, Window()


def test_window_settings_stay_in_the_test_folder(tmp_path):
    app, w = _window()
    try:
        location = Path(w.settings.fileName())
        assert not w.settings.fileName().startswith('\\HKEY_')
        assert Path(os.environ['USERPROFILE']) in location.parents
        w.set_theme('light')
        w.settings.sync()
        assert 'theme=light' in location.read_text(encoding='utf-8')
    finally:
        w.close()


def test_language_read_from_the_same_redirected_settings():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from ecu_studio import main
    app = QApplication.instance() or QApplication([])
    QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, 'ECU Studio', 'ECU Studio AI').setValue('language', 'en')
    try:
        assert main.apply_language(app) == 'en'
    finally:
        from ecu_studio.ui import i18n_qt
        i18n_qt.install(app, 'de')


def test_installed_program_still_uses_the_registry():
    """Without a redirect (the real program) the settings stay where 1.19.1 and older keep them."""
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.Format.NativeFormat)
    try:
        settings = QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, 'ECU Studio', 'ECU Studio AI')
        expected = QSettings('ECU Studio', 'ECU Studio AI')                 # read-only: nothing is written
        assert settings.fileName() == expected.fileName()
    finally:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)


# ---- 1.21.0: isolation also in child processes, guarded test profile, self-check, registry watch --------------
import subprocess
import sys
import pytest

SRC = str(Path(__file__).resolve().parents[1] / 'src')


def _child(code, env=None):
    run_env = dict(os.environ, PYTHONPATH=SRC, **(env or {}))
    for name, value in list(run_env.items()):
        if value is None:
            del run_env[name]
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=run_env, timeout=120)


def test_child_processes_inherit_the_settings_folder():
    out = _child('from ecu_studio.app_settings import app_settings; print(app_settings().fileName())')
    assert out.returncode == 0, out.stderr
    location = Path(out.stdout.strip())
    assert 'HKEY_' not in out.stdout
    assert Path(os.environ['ECU_STUDIO_SETTINGS_DIR']) in location.parents


def test_test_profile_without_settings_folder_refuses_the_real_settings(monkeypatch):
    from ecu_studio import app_settings as a
    monkeypatch.delenv(a.SETTINGS_DIR)
    with pytest.raises(a.SettingsIsolationError):
        a.app_settings()
    env = {k: v for k, v in os.environ.items() if k != a.SETTINGS_DIR}
    out = subprocess.run([sys.executable, '-c', 'from ecu_studio.app_settings import app_settings; app_settings()'],
                         capture_output=True, text=True, env=dict(env, PYTHONPATH=SRC), timeout=120)
    assert out.returncode != 0 and 'SettingsIsolationError' in out.stderr


def test_program_without_redirect_still_uses_the_registry(monkeypatch):
    """The installed program (no test profile, no redirect) keeps its settings where 1.20.1 has them."""
    from PySide6.QtCore import QSettings
    from ecu_studio import app_settings as a
    monkeypatch.delenv(a.SETTINGS_DIR)
    monkeypatch.delenv(a.TEST_PROFILE)
    QSettings.setDefaultFormat(QSettings.Format.NativeFormat)
    try:
        settings = a.app_settings()                       # read-only: nothing is written
        assert a.is_registry(settings) == (os.name == 'nt')
    finally:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)


def test_self_check_after_an_update_keeps_the_users_layout(tmp_path):
    """--self-check (run by the updater) used to save its offscreen window layout into the real settings."""
    user = tmp_path / 'user-settings'
    out = _child('import sys; from ecu_studio import main; sys.exit(main.self_check())',
                 env={'ECU_STUDIO_SETTINGS_DIR': str(user)})
    assert out.returncode == 0, out.stderr
    ini = user / 'ECU Studio' / 'ECU Studio AI.ini'
    assert not ini.exists() or 'geometry' not in ini.read_text(encoding='utf-8')


def test_no_update_check_and_no_visible_windows_in_the_test_profile():
    assert os.environ.get('ECU_STUDIO_NO_UPDATE_CHECK') and os.environ.get('ECU_STUDIO_TEST_PROFILE')
    assert os.environ.get('QT_QPA_PLATFORM') in ('offscreen', 'minimal')


def test_registry_watch_names_the_test_that_changed_a_value(monkeypatch):
    import conftest
    snapshots = iter([{'k|a': '1'}, {'k|a': '2'}])
    monkeypatch.setattr(conftest, '_registry_snapshot', lambda: next(snapshots))
    state = {'last': None, 'changes': []}
    monkeypatch.setattr(conftest, '_registry', state)
    state['last'] = conftest._registry_snapshot()
    conftest.pytest_runtest_logfinish('tests/x.py::test_y', None)
    assert state['changes'] == [('tests/x.py::test_y', ['a'])]


def test_uninstall_entry_is_never_written_in_the_test_profile(monkeypatch):
    """The installed program updates its "Apps & Features" version at start; a test run must not."""
    import pytest
    from ecu_studio.core import updates
    from ecu_studio.app_settings import SettingsIsolationError
    calls = []
    try:
        import winreg
        monkeypatch.setattr(winreg, 'OpenKey', lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(OSError()))
    except ImportError:
        pass
    with pytest.raises(SettingsIsolationError):
        updates._write_uninstall_entry({'DisplayVersion': '0.0.0'})
    assert calls == []          # refused before the registry was opened


def test_installed_version_sync_is_skipped_in_the_test_profile(monkeypatch, tmp_path):
    from ecu_studio.core import updates
    from ecu_studio.ui import updates as ui_updates
    seen = []
    monkeypatch.setattr(updates, 'install_root', lambda exe: tmp_path)
    monkeypatch.setattr(updates, 'sync_uninstall_entry', lambda *a: seen.append(a))
    ui_updates.UpdateController.sync_installed_version(object())
    assert seen == []


def test_registry_writes_only_in_the_known_places():
    """Static guard: registry writes and QSettings outside app_settings need a review (and an isolation test)."""
    import re
    root = Path(__file__).resolve().parents[1] / 'src' / 'ecu_studio'
    allowed = {('core/updates.py', 'SetValueEx')}
    found = set()
    for path in root.rglob('*.py'):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding='utf-8')
        for api in ('SetValueEx', 'CreateKey', 'DeleteValue', 'DeleteKey'):
            if re.search(r'\bwinreg\.' + api, text):
                found.add((rel, api))
        if rel != 'app_settings.py' and re.search(r'QSettings\(\s*QSettings\.defaultFormat|QSettings\(\s*["\']ECU Studio', text):
            found.add((rel, 'QSettings'))
    assert found == allowed


def test_opening_the_window_writes_no_settings():
    """Only closing (layout) or a user choice writes; starting the program leaves stored settings alone."""
    from ecu_studio.app_settings import app_settings
    seed = app_settings()
    seed.setValue('ui/theme', 'light')
    seed.sync()
    before = Path(seed.fileName()).read_bytes()
    app, w = _window()
    try:
        w.settings.sync()
        assert Path(w.settings.fileName()).read_bytes() == before
    finally:
        w.close()


# ---- 1.21.0 phase 5: aborted runs, simulated faults, clean-up ------------------------------------------------
NESTED_TESTS = '''
import os, json
import conftest

def test_writes_settings_then_fails():
    from ecu_studio.app_settings import app_settings, is_registry
    s = app_settings()
    s.setValue('ui/theme', 'dark')
    s.sync()
    with open(os.environ['ECU_MARKER'], 'w', encoding='utf-8') as f:
        json.dump({'file': s.fileName(), 'registry': is_registry(s),
                   'run': os.path.dirname(conftest._run['settings']), 'profile': os.environ['ECU_STUDIO_TEST_PROFILE']}, f)
    assert False, 'simulated failure'

def test_interrupted():
    raise KeyboardInterrupt
'''


def test_failed_and_interrupted_run_leaves_no_settings_and_no_registry_change(tmp_path):
    """A nested test run (same conftest) writes settings, fails and is interrupted: the run folder and the test's
    settings file are gone afterwards, the settings never were in the registry, the registry is unchanged."""
    import json
    import shutil
    import conftest
    nested = tmp_path / 'nested'
    nested.mkdir()
    shutil.copy2(Path(__file__).with_name('conftest.py'), nested / 'conftest.py')
    (nested / 'test_abort.py').write_text(NESTED_TESTS, encoding='utf-8')
    marker = tmp_path / 'marker.json'
    before = conftest._registry_snapshot()
    env = dict(os.environ, PYTHONPATH=SRC, ECU_MARKER=str(marker))
    out = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp',
                          str(tmp_path / 'basetemp'), str(nested)], capture_output=True, text=True, env=env,
                         cwd=str(nested), timeout=300)
    assert out.returncode not in (0, 5), out.stdout + out.stderr          # failed / interrupted, not "passed"
    seen = json.loads(marker.read_text(encoding='utf-8'))
    assert not seen['registry'] and 'HKEY_' not in seen['file']
    assert seen['profile'] and seen['profile'] != os.environ['ECU_STUDIO_TEST_PROFILE']   # its own run profile
    assert not Path(seen['file']).exists()                  # the failed test's settings file was removed
    assert not Path(seen['run']).exists()                   # the run folder too, despite failure and interrupt
    assert conftest._registry_snapshot() == before


def test_settings_folder_that_cannot_be_created_never_falls_back_to_the_registry(monkeypatch, tmp_path):
    """Simulated fault: the redirect points at a file. Opening settings fails loudly instead of using the registry."""
    from ecu_studio import app_settings as a
    blocker = tmp_path / 'kein-ordner'
    blocker.write_text('x')
    monkeypatch.setenv(a.SETTINGS_DIR, str(blocker))
    with pytest.raises(OSError):
        a.app_settings()
    monkeypatch.setenv(a.SETTINGS_DIR, '')                  # empty redirect in a test profile: refused
    with pytest.raises(a.SettingsIsolationError):
        a.app_settings()


def test_window_start_with_a_broken_settings_folder_fails_without_touching_the_registry(monkeypatch, tmp_path):
    import conftest
    from ecu_studio import app_settings as a
    blocker = tmp_path / 'kein-ordner'
    blocker.write_text('x')
    monkeypatch.setenv(a.SETTINGS_DIR, str(blocker))
    before = conftest._registry_snapshot()
    with pytest.raises(OSError):
        _window()
    assert conftest._registry_snapshot() == before


def test_stale_run_folders_of_killed_runs_are_removed_but_running_ones_stay(tmp_path):
    import conftest
    import time
    old = tmp_path / (conftest.RUN_PREFIX + 'alt')
    (old / 'settings').mkdir(parents=True)
    young = tmp_path / (conftest.RUN_PREFIX + 'laeuft')
    young.mkdir()
    other = tmp_path / 'fremder-ordner'
    other.mkdir()
    past = time.time() - (conftest.STALE_HOURS + 1) * 3600
    os.utime(old, (past, past))
    os.utime(other, (past, past))
    removed = conftest.remove_stale_run_folders(str(tmp_path))
    assert removed == [str(old)] and not old.exists()
    assert young.exists() and other.exists()


LEFTOVERS = r'''
import os, sys, json
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, sys.argv[1])
import conftest
from PySide6 import QtCore, QtWidgets
import shiboken6
app = QtWidgets.QApplication([])
widgets = [QtWidgets.QWidget() for _ in range(50)] + [QtWidgets.QDialog() for _ in range(20)]
for w in widgets[::3]:
    w.show()

class Worker(QtCore.QThread):
    def run(self):
        while not self.isInterruptionRequested():
            self.msleep(5)

worker = Worker()
worker.start()
released = conftest.release_qt_leftovers()
print(json.dumps({'released': released, 'alive': sum(shiboken6.isValid(w) for w in widgets),
                  'worker_running': worker.isRunning(), 'left': len(app.topLevelWidgets())}))
'''


def test_windows_left_open_by_tests_are_released_before_python_exits(tmp_path):
    """Exit crash of full runs (1.21.0-rc1): Qt aborted while PySide6 destroyed about 1100 leftover test windows at
    exit. The session end releases them while Python runs: a still running worker is stopped and joined, every
    top-level widget is deleted, the process exits cleanly (exit code 0)."""
    env = dict(os.environ, PYTHONPATH=SRC, QT_QPA_PLATFORM='offscreen')
    out = subprocess.run([sys.executable, '-c', LEFTOVERS, str(Path(__file__).resolve().parent)],
                         capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    import json
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result == {'released': 70, 'alive': 0, 'worker_running': False, 'left': 0}


def test_tests_never_start_the_installed_program():
    """Static guard: no test starts ECU-Studio-AI.exe from an installation folder or the Start menu; process starts
    in tests use this Python, PowerShell scripts of the repository, cmd.exe or git."""
    import re
    here = Path(__file__).resolve().parent
    pattern = re.compile(r'(LOCALAPPDATA|Programs)[^\n]{0,80}ECU-Studio-AI\.exe|startfile\(', re.I)
    offenders = [p.name for p in here.glob('test_*.py') if p.name != Path(__file__).name
                 and pattern.search(p.read_text(encoding='utf-8'))]
    assert offenders == []
