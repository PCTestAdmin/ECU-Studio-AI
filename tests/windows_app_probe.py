"""Starts a built ECU-Studio-AI.exe (launcher -> pythonw.exe -> app) and inspects it from outside through the Windows
API: icons Explorer extracts from the exe, and the running main window's icons and taskbar identity. Prints JSON.

    python tests/windows_app_probe.py dist/ECU-Studio-AI/ECU-Studio-AI.exe

Run by tests/test_app_icon.py only when ECU_STUDIO_GUI_TESTS=1, because the real application starts (it reads and
writes its normal settings)."""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402

from ecu_studio import main  # noqa: E402
from ecu_studio.tools.make_app_icon import ico_entries  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_icon_probe import ICON_BIG, ICON_SMALL, difference, window_icon  # noqa: E402

user32 = ctypes.windll.user32
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def exe_icon(exe: Path, size: int) -> QImage:
    """The icon image Windows (Explorer) takes from the exe at a given size."""
    handle, ident = wintypes.HICON(), wintypes.UINT()
    count = user32.PrivateExtractIconsW(str(exe), 0, size, size, ctypes.byref(handle), ctypes.byref(ident), 1, 0)
    image = QImage.fromHICON(handle.value) if count == 1 and handle.value else QImage()
    if handle.value:
        user32.DestroyIcon(handle)
    return image


def app_windows(pids: set[int]) -> list[int]:
    found = []

    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):   # GW_OWNER
            found.append(hwnd)
        return True
    user32.EnumWindows(ENUM(visit), 0)
    return found


def child_pids(parent: int) -> set[int]:
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
                          f'(Get-CimInstance Win32_Process -Filter "ParentProcessId={parent}").ProcessId'],
                         capture_output=True, text=True).stdout
    return {int(x) for x in out.split()}


def probe(exe: Path, timeout: float = 60) -> dict:
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (QImage.fromHICON needs it)
    entries = {size: QImage.fromData(png) for size, png in ico_entries(
        (Path(main.__file__).resolve().parent / 'ui' / 'assets' / 'app.ico').read_bytes()).items()}
    result = {'exe_icon': {s: round(difference(exe_icon(exe, s), entries[s]), 1) for s in (16, 24, 32, 48, 256)}}
    env = {k: v for k, v in os.environ.items() if k not in ('QT_QPA_PLATFORM', 'PYTHONPATH')}   # a real desktop app
    launcher = subprocess.Popen([str(exe)], cwd=exe.parent, env=env)
    try:
        deadline, hwnd = time.time() + timeout, 0
        while time.time() < deadline and not hwnd:
            time.sleep(1)
            pids = child_pids(launcher.pid)
            windows = app_windows(pids)
            hwnd = windows[0] if windows else 0
        if not hwnd:
            return {**result, 'error': 'no application window appeared'}
        time.sleep(2)                                        # properties are set right after the window is shown
        buffer = ctypes.create_unicode_buffer(260)
        user32.GetWindowTextW(hwnd, buffer, 260)
        result['title'] = buffer.value
        result['properties'] = {str(k): v for k, v in main.window_properties(hwnd).items()}
        for kind, label in ((ICON_SMALL, 'small'), (ICON_BIG, 'big')):
            image = window_icon(hwnd, kind)
            result[f'window_{label}'] = None if image.isNull() else {
                'size': image.width(), 'difference': round(difference(image, entries[image.width()]), 1)}
        user32.PostMessageW(hwnd, 0x0010, 0, 0)               # WM_CLOSE: the normal way out
        launcher.wait(timeout=30)
        result['exit_code'] = launcher.returncode
    finally:
        if launcher.poll() is None:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(launcher.pid)], capture_output=True)
    return result


if __name__ == '__main__':
    print(json.dumps(probe(Path(sys.argv[1]).resolve())))
