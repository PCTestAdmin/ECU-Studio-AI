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
