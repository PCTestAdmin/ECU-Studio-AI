"""Windows application entrypoint."""
import sys
from PySide6.QtWidgets import QApplication


def main():
    from ecu_studio.core import parallel
    parallel.enable()   # guarded entry point: scans may use several CPU cores
    if len(sys.argv)==3 and sys.argv[1]=='--smoke-test':
        try:
            from .tools.gui_smoke import run
            return run(sys.argv[2])
        except Exception:
            import traceback
            from pathlib import Path
            destination=Path(sys.argv[2])
            destination.mkdir(parents=True,exist_ok=True)
            (destination/'smoke-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            return 1
    if sys.argv[1:]==['--self-check']:
        return self_check()
    set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("ECU Studio AI")
    app.setOrganizationName("ECU Studio")
    app.setWindowIcon(app_icon())
    apply_language(app)
    from .ui.main_window import Window
    window = Window()
    window.show()
    return app.exec()


APP_USER_MODEL_ID = 'PCTestAdmin.ECUStudioAI'


def app_icon():
    """Program icon for all windows and dialogs: the ICO with all sizes, the PNG if Qt's ICO plugin is missing."""
    from pathlib import Path
    from PySide6.QtGui import QIcon
    assets = Path(__file__).resolve().parent / 'ui' / 'assets'
    icon = QIcon(str(assets / 'app.ico'))
    return icon if icon.availableSizes() else QIcon(str(assets / 'app_icon.png'))


def set_app_user_model_id() -> bool:
    """Own taskbar identity on Windows, so the taskbar shows the program icon instead of pythonw.exe's."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID) == 0
    except (AttributeError, OSError):
        return False


def apply_language(app) -> str:
    """Interface language from the settings (default: system language); must run before windows exist."""
    from PySide6.QtCore import QSettings
    from .core import i18n
    from .ui import i18n_qt
    code = QSettings("ECU Studio", "ECU Studio AI").value('language', 'system')
    if code not in i18n.LANGUAGES:
        code = i18n.system_language()
    i18n_qt.install(app, code)
    return code


def self_check():
    """Used by the updater after installing: load the whole UI offscreen, then exit 0."""
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    try:
        app=QApplication([sys.argv[0]])
        from .ui.main_window import Window
        window=Window()
        window.close()
        app.processEvents()
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
