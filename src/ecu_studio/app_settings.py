"""Where the program keeps its settings (window layout, theme, language, update check).

The installed program uses the Windows registry (HKEY_CURRENT_USER\\Software\\ECU Studio\\ECU Studio AI), as
every version before. Two environment variables change that, and child processes inherit them:

  ECU_STUDIO_SETTINGS_DIR   settings go to an INI file in this folder instead of the registry
  ECU_STUDIO_TEST_PROFILE   set by the test suite: without ECU_STUDIO_SETTINGS_DIR no settings are opened at all
                            (RuntimeError), so a test, a smoke run or a program started by a test can never fall
                            back to the user's real registry key

1.21.0: until then the redirect existed only inside the test process (QSettings.setDefaultFormat). A program a
test started in a new process would have used the registry.
"""
from __future__ import annotations
import os
from pathlib import Path

ORGANIZATION, APPLICATION = 'ECU Studio', 'ECU Studio AI'
SETTINGS_DIR = 'ECU_STUDIO_SETTINGS_DIR'
TEST_PROFILE = 'ECU_STUDIO_TEST_PROFILE'


class SettingsIsolationError(RuntimeError):
    """A test profile without its own settings folder: refusing to open the real settings."""


def settings_file() -> Path | None:
    """The INI file used instead of the registry, or None for the registry (installed program)."""
    folder = os.environ.get(SETTINGS_DIR)
    if folder:
        return Path(folder) / ORGANIZATION / (APPLICATION + '.ini')
    if os.environ.get(TEST_PROFILE):
        raise SettingsIsolationError(f'{TEST_PROFILE} gesetzt, aber kein {SETTINGS_DIR}: '
                                     'echte Einstellungen werden im Testprofil nicht geöffnet.')
    return None


def app_settings():
    """QSettings for the program. Honours the redirect above, then QSettings.setDefaultFormat/setPath
    (screenshot and smoke tools), else the registry."""
    from PySide6.QtCore import QSettings
    path = settings_file()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        return QSettings(str(path), QSettings.Format.IniFormat)
    return QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, ORGANIZATION, APPLICATION)


def is_registry(settings) -> bool:
    return settings.fileName().upper().startswith('\\HKEY_')
