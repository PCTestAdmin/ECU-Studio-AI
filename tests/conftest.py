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
RUN_PREFIX = 'ecu-studio-tests-'
STALE_HOURS = 6


def remove_stale_run_folders(temp: str, now: float | None = None) -> list[str]:
    """Run folders of earlier test runs that ended without clean-up (killed process), older than STALE_HOURS.

    Only folders with the prefix of this suite and only below the temporary folder are removed; a run that is
    still going (younger) is left alone.
    """
    import shutil
    import time
    now = time.time() if now is None else now
    removed = []
    try:
        names = os.listdir(temp)
    except OSError:
        return removed
    for name in names:
        path = os.path.join(temp, name)
        if not name.startswith(RUN_PREFIX) or not os.path.isdir(path) or os.path.islink(path):
            continue
        try:
            old = now - os.path.getmtime(path) > STALE_HOURS * 3600
        except OSError:
            continue
        if old:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def pytest_configure(config):
    import tempfile
    remove_stale_run_folders(tempfile.gettempdir())
    run = tempfile.mkdtemp(prefix=f'{RUN_PREFIX}{RUN_ID}-')
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


def release_qt_leftovers(wait_ms: int = 10000) -> int:
    """Delete the windows and dialogs the tests left open, before Python shuts down; returns how many.

    1.21.0-rc1: about 1100 top-level widgets (54 main windows, dialogs, menus) stay alive until the end of a full
    run. PySide6 destroys them together with the QApplication in its own exit handler, and Qt sometimes aborts
    there (0xC0000409 on Windows runners, roughly one run in ten, also with 1.20.1): every test passed, yet the
    process exit code failed the build. Here they go in a defined order while Python still runs: running workers
    are asked to stop and joined, widgets are hidden and deleted (no close(): it would ask about unsaved work and
    save the window layout), deferred deletions are processed.
    """
    try:
        from PySide6.QtCore import QCoreApplication, QEvent, QThread
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return 0
    app = QApplication.instance()
    if app is None:
        return 0
    import gc
    for thread in [o for o in gc.get_objects() if isinstance(o, QThread)]:
        try:
            if thread.isRunning():
                thread.requestInterruption()
            thread.wait(wait_ms)
        except RuntimeError:                     # C++ object already gone
            pass
    widgets = app.topLevelWidgets()
    for widget in widgets:
        try:
            widget.hide()
            widget.deleteLater()
        except RuntimeError:
            pass
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return len(widgets)


def pytest_sessionfinish(session, exitstatus):
    import shutil
    release_qt_leftovers()
    pytest_runtest_logfinish('(Sitzungsende: offene Fenster freigegeben)', None)   # the clean-up is watched too
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
    # The test's settings file goes, also after a failure (teardown runs either way); the rest of the
    # temporary home stays with pytest's own clean-up for diagnosis.
    import shutil
    shutil.rmtree(home / 'settings', ignore_errors=True)
