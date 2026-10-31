"""Program icon: ICO content, use in the .exe build, installer, windows and taskbar identity."""
import os
import struct
import sys
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'src' / 'ecu_studio' / 'ui' / 'assets'


def _entries(data: bytes):
    reserved, kind, count = struct.unpack('<HHH', data[:6])
    assert (reserved, kind) == (0, 1)
    for i in range(count):
        w, h, colors, _, planes, bits, size, offset = struct.unpack('<BBBBHHII', data[6 + 16 * i:22 + 16 * i])
        yield (w or 256), (h or 256), bits, data[offset:offset + size]


def test_ico_holds_every_windows_size_as_transparent_png():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from ecu_studio.tools.make_app_icon import SIZES
    app = QApplication.instance() or QApplication([])  # noqa: F841 (widget tests share it)
    entries = list(_entries((ASSETS / 'app.ico').read_bytes()))
    assert [w for w, *_ in entries] == list(SIZES)
    for w, h, bits, png in entries:
        image = QImage.fromData(png)
        assert png.startswith(b'\x89PNG') and bits == 32 and (image.width(), image.height()) == (w, h) == (w, w)
        assert image.hasAlphaChannel() and image.pixel(0, 0) >> 24 == 0          # transparent corner
    big = QImage(str(ASSETS / 'app_icon.png'))
    assert (big.width(), big.height()) == (256, 256)


def test_ico_container_round_trips():
    from ecu_studio.tools.make_app_icon import ico_bytes
    pngs = {16: b'\x89PNG-a', 256: b'\x89PNG-bb'}
    assert [(w, png) for w, _, _, png in _entries(ico_bytes(pngs))] == [(16, b'\x89PNG-a'), (256, b'\x89PNG-bb')]


def test_application_sets_the_window_icon_and_taskbar_identity(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ecu_studio import main
    app = QApplication.instance() or QApplication([])  # noqa: F841
    icon = main.app_icon()
    assert not icon.isNull() and max(s.width() for s in icon.availableSizes()) == 256
    source = (ROOT / 'src' / 'ecu_studio' / 'main.py').read_text(encoding='utf-8')
    assert 'app.setWindowIcon(app_icon())' in source and 'set_app_user_model_id()' in source
    if sys.platform == 'win32':
        assert main.set_app_user_model_id()
    else:
        assert not main.set_app_user_model_id()


def test_exe_build_and_installer_use_the_icon():
    build = (ROOT / 'src' / 'ecu_studio' / 'tools' / 'build_portable_runtime.py').read_text(encoding='utf-8')
    assert "'/win32icon:'+str(icon)" in build and "'ui'/'assets'/'app.ico'" in build
    installer = (ROOT / 'packaging' / 'installer.iss').read_text(encoding='utf-8-sig')
    assert 'SetupIconFile=..\\src\\ecu_studio\\ui\\assets\\app.ico' in installer
    pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert '"ecu_studio.ui" = ["assets/*"]' in pyproject


@pytest.mark.skipif(sys.platform != 'win32' or not Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe').exists(),
                    reason='Windows .NET compiler not available')
def test_compiled_launcher_carries_the_icon(tmp_path):
    import subprocess
    exe = tmp_path / 'ECU-Studio-AI.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo', '/target:winexe',
                    '/platform:x64', '/win32icon:' + str(ASSETS / 'app.ico'), '/reference:System.Windows.Forms.dll',
                    '/out:' + str(exe), str(ROOT / 'packaging' / 'windows_launcher.cs')], check=True,
                   capture_output=True)
    data = exe.read_bytes()
    first = next(png for *_, png in _entries((ASSETS / 'app.ico').read_bytes()))
    assert first in data                                       # icon image embedded as a resource
