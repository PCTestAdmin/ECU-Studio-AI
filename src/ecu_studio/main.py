"""Windows application entrypoint."""
import sys
from PySide6.QtWidgets import QApplication


def main():
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
    app = QApplication(sys.argv)
    app.setApplicationName("ECU Studio AI")
    app.setOrganizationName("ECU Studio")
    from .ui.main_window import Window
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
