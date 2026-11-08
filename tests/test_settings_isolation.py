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
