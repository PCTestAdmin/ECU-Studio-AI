"""Run by tests/test_app_icon.py in its own process with Qt's native Windows platform: a real top-level window
and dialog get the program icon and taskbar identity, read back through the Windows API. Prints JSON."""
import ctypes
import json
import sys
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from ecu_studio import main
from ecu_studio.tools.make_app_icon import ico_entries

ASSETS = Path(main.__file__).resolve().parent / 'ui' / 'assets'
WM_GETICON, ICON_SMALL, ICON_BIG = 0x7F, 0, 1


def window_icon(hwnd: int, kind: int) -> QImage:
    send = ctypes.windll.user32.SendMessageW
    send.restype = ctypes.c_void_p
    send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    handle = send(hwnd, WM_GETICON, kind, 0)
    return QImage.fromHICON(handle) if handle else QImage()


def difference(image: QImage, reference: QImage) -> float:
    """Mean absolute ARGB difference per channel (0-255); the reference is scaled only if the sizes differ."""
    if reference.size() != image.size():
        reference = reference.scaled(image.width(), image.height())
    reference = reference.convertToFormat(QImage.Format.Format_ARGB32)
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    total = 0
    for y in range(image.height()):
        for x in range(image.width()):
            a, b = image.pixel(x, y), reference.pixel(x, y)
            total += sum(abs((a >> s & 255) - (b >> s & 255)) for s in (0, 8, 16, 24))
    return total / (image.width() * image.height() * 4)


def probe(launcher: str) -> dict:
    process_id = main.set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setWindowIcon(main.app_icon())
    window, dialog = QWidget(), QDialog()
    window.setWindowTitle('ECU Studio AI icon probe')
    window.show()
    dialog.show()
    app.processEvents()
    hwnd = int(window.winId())
    relaunch = main.set_relaunch_properties(hwnd, launcher)
    entries = {size: QImage.fromData(png) for size, png in ico_entries((ASSETS / 'app.ico').read_bytes()).items()}
    result = {'process_id': process_id, 'relaunch_set': relaunch,
              'properties': {str(k): v for k, v in main.window_properties(hwnd).items()}}
    for name, handle in (('window', hwnd), ('dialog', int(dialog.winId()))):
        for kind, label in ((ICON_SMALL, 'small'), (ICON_BIG, 'big')):
            image = window_icon(handle, kind)
            result[f'{name}_{label}'] = None if image.isNull() else {
                'size': image.width(), 'difference': round(difference(image, entries[image.width()]), 1)}
    extract = ctypes.windll.shell32.ExtractIconW
    extract.restype = ctypes.c_void_p
    extract.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    handle = extract(None, sys.executable, 0)                         # the Python interpreter's own icon, 32 px
    if handle:
        result['python_icon_difference'] = round(difference(QImage.fromHICON(handle), entries[32]), 1)
    dialog.close()
    window.close()
    return result


if __name__ == '__main__':
    print(json.dumps(probe(sys.argv[1])))
