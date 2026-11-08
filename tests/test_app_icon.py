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


def test_small_sizes_are_painted_for_the_pixel_grid(tmp_path):
    """16-24 px use the simplified motif (chip, display, curve; no ring); larger sizes stay the master image."""
    import shutil
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from ecu_studio.tools.make_app_icon import SMALL, ico_entries, refresh_small, small_icon
    app = QApplication.instance() or QApplication([])  # noqa: F841
    for size in SMALL:
        image = small_icon(size)
        assert (image.width(), image.height()) == (size, size)
        assert image.pixel(0, 0) >> 24 == 0 and image.pixel(size // 2, size // 2) >> 24 == 255
        stored = QImage.fromData(ico_entries((ASSETS / 'app.ico').read_bytes())[size])
        assert stored.pixel(size // 2, size // 2) >> 24 == 255            # opaque chip centre, not a blurred ring
    shutil.copy(ASSETS / 'app.ico', tmp_path / 'app.ico')
    refresh_small(tmp_path)
    before, after = ico_entries((ASSETS / 'app.ico').read_bytes()), ico_entries((tmp_path / 'app.ico').read_bytes())
    assert all(before[size] == after[size] for size in before if size not in SMALL)


def test_exe_build_and_installer_use_the_icon():
    from ecu_studio import main
    build = (ROOT / 'src' / 'ecu_studio' / 'tools' / 'build_portable_runtime.py').read_text(encoding='utf-8')
    assert "'/win32icon:'+str(icon)" in build and "'ui'/'assets'/'app.ico'" in build
    installer = (ROOT / 'packaging' / 'installer.iss').read_text(encoding='utf-8-sig')
    assert 'SetupIconFile=..\\src\\ecu_studio\\ui\\assets\\app.ico' in installer
    # Start menu and desktop shortcuts carry the window's AppUserModelID, so Windows links the running pythonw.exe
    # window to them (taskbar icon, pinning) instead of to python.
    shortcuts = [line for line in installer.splitlines() if line.startswith('Name:') and 'ECU-Studio-AI.exe' in line]
    assert len(shortcuts) == 2
    assert all(f'AppUserModelID: "{main.APP_USER_MODEL_ID}"' in line for line in shortcuts)
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


@pytest.mark.skipif(sys.platform != 'win32' or not Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe').exists(),
                    reason='Windows .NET compiler not available')
def test_compiled_launcher_carries_the_program_version(tmp_path):
    """Explorer > Properties > Details showed file version 0.0.0.0 up to 1.19.0."""
    import subprocess
    from ecu_studio.tools.build_portable_runtime import compile_launcher
    exe = tmp_path / 'ECU-Studio-AI.exe'
    compile_launcher(ROOT, exe, '7.8.9')
    script = ("$v=(Get-Item -LiteralPath $env:EXE).VersionInfo;"
              "$v.FileVersion;$v.ProductVersion;$v.ProductName;$v.CompanyName")
    out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True,
                         env={**os.environ, 'EXE': str(exe)}, check=True).stdout.split('\n')
    assert [line.strip() for line in out[:4]] == ['7.8.9.0', '7.8.9', 'ECU Studio AI', 'PCTestAdmin']
    first = next(png for *_, png in _entries((ASSETS / 'app.ico').read_bytes()))
    assert first in exe.read_bytes()                           # icon still embedded


def test_installer_carries_the_program_version():
    installer = (ROOT / 'packaging' / 'installer.iss').read_text(encoding='utf-8-sig')
    assert 'VersionInfoVersion={#AppVersion}' in installer


def test_relaunch_properties_need_the_packaged_launcher():
    from ecu_studio import main
    assert main.launcher_path() is None                        # development run: python.exe, no launcher next to it
    assert not main.set_relaunch_properties(1)
    source = (ROOT / 'src' / 'ecu_studio' / 'main.py').read_text(encoding='utf-8')
    assert 'set_relaunch_properties(int(window.winId()))' in source


def _probe(script, *args, env=None):
    import json
    import subprocess
    run_env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), **(env or {}))
    result = subprocess.run([sys.executable, str(ROOT / 'tests' / script), *map(str, args)], capture_output=True,
                            text=True, env=run_env, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows only')
def test_real_windows_get_the_program_icon_and_taskbar_identity():
    """A real (not offscreen) window and dialog, read back through the Windows API: WM_GETICON returns the ICO's own
    16/32 px images (not Python's), and the window carries AppUserModelID plus relaunch command, icon and name."""
    launcher = r'C:\Program Files\ECU Studio AI\ECU-Studio-AI.exe'
    result = _probe('windows_icon_probe.py', launcher, env={'QT_QPA_PLATFORM': 'windows'})
    assert result['process_id'] and result['relaunch_set']
    assert result['properties'] == {'5': 'PCTestAdmin.ECUStudioAI', '2': f'"{launcher}"', '3': f'{launcher},0',
                                    '4': 'ECU Studio AI'}
    for key in ('window_small', 'window_big', 'dialog_small', 'dialog_big'):
        assert result[key] and result[key]['difference'] < 5, (key, result[key])
    if 'python_icon_difference' in result:
        assert result['python_icon_difference'] > 20         # the comparison does tell the two icons apart


BUILT_EXE = ROOT / 'dist' / 'ECU-Studio-AI' / 'ECU-Studio-AI.exe'


@pytest.mark.skipif(sys.platform != 'win32' or os.environ.get('ECU_STUDIO_GUI_TESTS') != '1' or not BUILT_EXE.exists(),
                    reason='needs a built dist/ECU-Studio-AI and ECU_STUDIO_GUI_TESTS=1 (starts the real app)')
def test_built_program_shows_its_icon_in_explorer_window_and_taskbar():
    """End to end on the built package: Explorer's icons from the exe and the running app window (launcher ->
    pythonw.exe -> app), inspected from outside."""
    result = _probe('windows_app_probe.py', BUILT_EXE)
    assert 'error' not in result, result
    assert all(diff < 5 for diff in result['exe_icon'].values()), result['exe_icon']
    assert result['title'].startswith('ECU Studio AI')
    assert result['properties']['5'] == 'PCTestAdmin.ECUStudioAI'
    assert result['properties']['2'] == f'"{BUILT_EXE}"'
    assert result['window_small']['difference'] < 5 and result['window_big']['difference'] < 5
    assert result['exit_code'] == 0
