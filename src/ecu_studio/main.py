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
    app = QApplication(sys.argv)
    app.setApplicationName("ECU Studio AI")
    app.setOrganizationName("ECU Studio")
    apply_language(app)
    from .ui.main_window import Window
    window = Window()
    window.show()
    return app.exec()


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
