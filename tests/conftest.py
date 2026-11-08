"""Every test runs with temporary home and app-data folders and its own settings file.

The main window opens the project database and the fingerprint library in the
user's folders; without this, a test run would read and change the real ones.
Its settings (window layout, theme, language, update check) would otherwise go
into the registry key of the installed ECU Studio AI.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_user_folders(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp('home')
    for name in ('USERPROFILE', 'HOME', 'LOCALAPPDATA', 'APPDATA'):
        monkeypatch.setenv(name, str(home))
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        yield
        return
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(home / 'settings'))
    yield
    QSettings.setDefaultFormat(QSettings.Format.NativeFormat)
