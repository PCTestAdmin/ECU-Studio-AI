"""Windows application entrypoint."""
import sys
from PySide6.QtWidgets import QApplication


GUI_SWITCH_INTERVAL = 0.0005


def keep_gui_responsive() -> float:
    """Shorter GIL hand-over while a scan thread runs pure Python. PySide releases the GIL around Qt calls, and with
    the default 5 ms the scan thread kept it each time: a repaint during a scan (first display of a file, closing the
    checklist) then took as long as the scan itself (MS43: window still for 4.7-5.1 s; with 0.5 ms: 0.11 s)."""
    sys.setswitchinterval(GUI_SWITCH_INTERVAL)
    return sys.getswitchinterval()


def main():
    from ecu_studio.core import parallel
    parallel.enable()   # guarded entry point: scans may use several CPU cores
    keep_gui_responsive()
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
    set_relaunch_properties(int(window.winId()))
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


# System.AppUserModel.* window properties (propkey.h): pid 2 RelaunchCommand, 3 RelaunchIconResource,
# 4 RelaunchDisplayNameResource, 5 ID.
APP_USER_MODEL_FMTID = '{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}'
IID_PROPERTY_STORE = '{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}'


def launcher_path():
    """ECU-Studio-AI.exe of the portable runtime / installation (root/_internal/python/pythonw.exe), else None."""
    from pathlib import Path
    parents = Path(sys.executable).resolve().parents
    launcher = parents[2] / 'ECU-Studio-AI.exe' if len(parents) > 2 else None
    return launcher if launcher and launcher.is_file() else None


def set_relaunch_properties(hwnd: int, launcher=None) -> bool:
    """Taskbar identity of the main window. The launcher runs pythonw.exe as a child process; without these
    properties, pinning the running window would pin pythonw.exe (Python icon, starts nothing). With them the pin
    starts ECU-Studio-AI.exe and shows its icon. Outside the packaged runtime (no launcher) nothing is set."""
    launcher = launcher or launcher_path()
    if sys.platform != 'win32' or not launcher or not hwnd:
        return False
    values = {5: APP_USER_MODEL_ID, 2: f'"{launcher}"', 3: f'{launcher},0', 4: 'ECU Studio AI'}
    try:
        return window_properties(hwnd, values) == values
    except (OSError, ValueError, TypeError, AttributeError):    # cosmetic: never let it stop the start
        return False


def window_properties(hwnd: int, values=None) -> dict:
    """Write (if given) and read back the System.AppUserModel string properties of a window (Windows only)."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [('data1', wintypes.DWORD), ('data2', wintypes.WORD), ('data3', wintypes.WORD),
                    ('data4', ctypes.c_ubyte * 8)]

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [('fmtid', GUID), ('pid', wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [('vt', wintypes.USHORT), ('reserved', wintypes.USHORT * 3), ('value', ctypes.c_void_p),
                    ('pad', ctypes.c_void_p)]

    def guid(text):
        value = GUID()
        if ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(value)):
            raise OSError('bad GUID')
        return value

    store = ctypes.c_void_p()
    ctypes.oledll.shell32.SHGetPropertyStoreForWindow(wintypes.HWND(hwnd), ctypes.byref(guid(IID_PROPERTY_STORE)),
                                                      ctypes.byref(store))
    table = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    method = lambda index, *args: ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *args)(table[index])  # noqa
    get_value = method(5, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    set_value = method(6, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    commit, release = method(7), ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(table[2])
    result = {}
    try:
        for pid, text in (values or {}).items():
            buffer = ctypes.create_unicode_buffer(text)
            value = PROPVARIANT(vt=31, value=ctypes.cast(buffer, ctypes.c_void_p))        # VT_LPWSTR, copied by the store
            set_value(store, ctypes.byref(PROPERTYKEY(guid(APP_USER_MODEL_FMTID), pid)), ctypes.byref(value))
        if values:
            commit(store)
        for pid in (5, 2, 3, 4):
            value = PROPVARIANT()
            get_value(store, ctypes.byref(PROPERTYKEY(guid(APP_USER_MODEL_FMTID), pid)), ctypes.byref(value))
            if value.vt == 31:
                result[pid] = ctypes.wstring_at(value.value)
            ctypes.oledll.ole32.PropVariantClear(ctypes.byref(value))
    finally:
        release(store)
    return result


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
