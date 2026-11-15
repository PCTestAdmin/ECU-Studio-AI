"""Every test runs with temporary home and app-data folders and its own settings file.

The main window opens the project database and the fingerprint library in the
user's folders; without this, a test run would read and change the real ones.
Its settings (window layout, theme, language, update check) would otherwise go
into the registry key of the installed ECU Studio AI.

1.21.0 (registry isolation):
- The whole run is a test profile (ECU_STUDIO_TEST_PROFILE): the program refuses to open settings
  without a redirect, also in processes a test starts (they inherit the environment).
- Each test gets its own settings folder (ECU_STUDIO_SETTINGS_DIR and QSettings' INI path); between
  tests a folder of this run is used. No update check, no visible windows by default.
- Before each test the isolation is checked; a test whose settings would not be isolated is skipped.
- The registry keys of the installed program are only READ: before the run and after every test. A
  change fails the run and names the test (or another program that wrote at the same time).
"""
import os
import uuid
import pytest

RUN_ID = f'{os.getpid()}-{uuid.uuid4().hex[:8]}'
WATCHED_KEYS = (r'Software\ECU Studio',
                r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F8CD5330-FC90-4891-BFDA-58E6668C93A5}_is1')


def _registry_snapshot() -> dict:
    """Read-only copy of the watched keys (value names and values); {} where not Windows."""
    try:
        import winreg
    except ImportError:
        return {}
    out = {}

    def walk(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
        except OSError:
            return
        with key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                out[path + '|' + name] = repr(value)
                i += 1
            subkeys, i = [], 0
            while True:
                try:
                    subkeys.append(winreg.EnumKey(key, i))
                except OSError:
                    break
                i += 1
        for sub in subkeys:
            walk(path + '\\' + sub)
    for path in WATCHED_KEYS:
        walk(path)
    return out


_registry = {'last': None, 'changes': []}
_run = {'settings': None}


def pytest_configure(config):
    import tempfile
    run = tempfile.mkdtemp(prefix=f'ecu-studio-tests-{RUN_ID}-')
    os.environ['ECU_STUDIO_TEST_PROFILE'] = RUN_ID
    _run['settings'] = os.environ['ECU_STUDIO_SETTINGS_DIR'] = os.path.join(run, 'settings')
    os.environ['ECU_STUDIO_NO_UPDATE_CHECK'] = '1'
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    config._ecu_run_folder = run
    _registry['last'] = _registry_snapshot()


def pytest_runtest_logfinish(nodeid, location):
    now = _registry_snapshot()
    if now != _registry['last']:
        names = sorted(k.split('|')[-1] for k in set(now) | set(_registry['last'])
                       if now.get(k) != _registry['last'].get(k))
        _registry['changes'].append((nodeid, names))
    _registry['last'] = now


def pytest_sessionfinish(session, exitstatus):
    import shutil
    shutil.rmtree(getattr(session.config, '_ecu_run_folder', ''), ignore_errors=True)
    if _registry['changes']:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter):
    for nodeid, names in _registry['changes']:
        terminalreporter.write_line(
            f'REGISTRY GEÄNDERT während/nach {nodeid}: {", ".join(names)} '
            '(Test nicht isoliert oder ein anderes ECU-Studio-Programm schrieb gleichzeitig)', red=True)


@pytest.fixture(autouse=True)
def _isolated_user_folders(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp('home')
    for name in ('USERPROFILE', 'HOME', 'LOCALAPPDATA', 'APPDATA'):
        monkeypatch.setenv(name, str(home))
    monkeypatch.setenv('ECU_STUDIO_SETTINGS_DIR', str(home / 'settings'))
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        yield
        return
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(home / 'settings'))
    # Proof before the test: the program's settings are an INI file in this test's folder.
    from ecu_studio.app_settings import app_settings, is_registry
    settings = app_settings()
    location = os.path.normcase(os.path.abspath(settings.fileName()))
    if is_registry(settings) or not location.startswith(os.path.normcase(str(home))):
        pytest.skip('Einstellungen nicht nachweisbar isoliert: Test nicht ausgeführt')
    yield
    # Stay on INI files between tests (this run's folder), never back to the registry.
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _run['settings'])
