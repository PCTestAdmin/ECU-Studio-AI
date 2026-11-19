"""Release-candidate check of an INSTALLED ECU Studio AI, run with the installation's own Python runtime.

Only for the isolated installer test (.github/workflows/installer-qa.yml). Synthetic data only, no manufacturer
firmware. Each mode writes <work>/<mode>.json and exits non-zero on any failed check.

  seed     with the OLD installation: private user data (project, settings) that an update must keep
  first    open a test file, automatic map recognition, checksum check, correction preview, corrected copy with
           change log, save project
  restart  a new process: settings kept, project reopened, corrected copy reopened
  compat   the new installation opens the project written by the old one
  window   probe the running main window started from a shortcut (title, icon, taskbar identity)
"""
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

MODE, WORK = sys.argv[1], Path(sys.argv[2])
if MODE != 'window':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
RESULT = {'mode': MODE, 'checks': [], 'python': sys.executable}
if os.environ.get('QA_SANDBOX_HOME'):
    # Local dry run on a developer machine: never touch the real settings (registry) or ~/.ecu_studio_ai.
    _home = Path(os.environ['QA_SANDBOX_HOME'])
    Path.home = classmethod(lambda cls: _home)
    os.environ['LOCALAPPDATA'] = str(_home)
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(_home))
MAP_OFFSET = 0x513C            # 12x16 u16 table behind its axes, found by the scanner (candidate:nx,ny,x,y,z)


def check(name, condition, detail=''):
    RESULT['checks'].append({'name': name, 'ok': bool(condition), 'detail': str(detail)[:400]})
    if not condition:
        raise AssertionError(f'{name}: {detail}')


def firmware() -> bytes:
    """ME7-like multipoint checksum table over five ranges, one range holding a recognisable map."""
    import numpy as np
    from ecu_studio.core import integrity as ig
    table, ranges = 0x10000, [(0x10000, 0x100FF), (0x1000, 0x1FFF), (0x3000, 0x37FF), (0x5000, 0x5FFF),
                              (0x8000, 0x8FFF)]
    data = bytearray(np.random.default_rng(3).integers(0, 256, 0x20000, dtype=np.uint8).tobytes())
    epk = b'40/1/ME7.5/5/5016.01//24f/Dst02o/220503/'
    data[0x200:0x200 + len(epk)] = epk
    nx, ny = 16, 12
    y, x = np.mgrid[:ny, :nx]
    blob = (np.array([nx, ny], '<u2').tobytes() + np.linspace(800, 6800, nx).astype('<u2').tobytes()
            + np.linspace(10, 100, ny).astype('<u2').tobytes() + (1000 + 20 * x + 30 * y + x * y).astype('<u2').tobytes())
    data[0x5100:0x5100 + len(blob)] = blob
    for i, (s, e) in enumerate(ranges):
        rec = table + 16 * i
        data[rec:rec + 8] = (s + 0x800000).to_bytes(4, 'little') + (e + 0x800000).to_bytes(4, 'little')
        data[rec + 8:rec + 16] = ig._pair(0x12345678, 'little')
    data[table + 16 * len(ranges):table + 16 * len(ranges) + 16] = b'\xFF' * 16
    for i, (s, e) in enumerate(ranges):
        rec = table + 16 * i
        data[rec + 8:rec + 16] = ig._pair(ig.reference_word_sum(bytes(data), s, e, 'little'), 'little')
    return bytes(data)


def app_and_window():
    from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QFileDialog
    import ecu_studio
    RESULT['ecu_studio'] = str(Path(ecu_studio.__file__).resolve())
    RESULT['version'] = ecu_studio.__version__
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('ECU Studio AI')
    app.setOrganizationName('ECU Studio')
    messages = RESULT.setdefault('messages', [])
    QMessageBox.information = staticmethod(lambda parent, title, text, *a, **k: messages.append(('info', title, text))
                                           or QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda parent, title, text, *a, **k: messages.append(('warning', title, text))
                                       or QMessageBox.StandardButton.Ok)
    QMessageBox.question = staticmethod(lambda parent, title, text, *a, **k: messages.append(('question', title, text))
                                        or QMessageBox.StandardButton.Yes)
    from ecu_studio.ui.main_window import Window
    return app, Window(), QDialog, QFileDialog


def wait(app, done, what, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if done():
            app.processEvents()
            return
        time.sleep(0.02)
    raise AssertionError(f'{what}: Zeitüberschreitung')


def integrity(app, w):
    w.integrity_timer.stop()
    w.check_integrity_async()
    wait(app, lambda: w.integrity_worker is not None and w.integrity_worker.isFinished() and w._integrity_fresh(),
         'Checksummenprüfung')
    return w.integrity_report


def first():
    from ecu_studio.core import integrity as ig
    from ecu_studio.core.model import BinaryImage
    WORK.mkdir(parents=True, exist_ok=True)
    source = WORK / 'testfirmware.bin'
    source.write_bytes(firmware())
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    app, w, QDialog, QFileDialog = app_and_window()
    check('installed code runs', 'Programs' in RESULT['ecu_studio'] or os.environ.get('QA_ALLOW_DEV'),
          RESULT['ecu_studio'])
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(source), ''))
    w.open_bin()
    check('test file opened', w.image is not None and w.image.digest == original_hash, w.image and w.image.path)
    first_report = integrity(app, w)
    check('checksum check of the original', first_report.status == ig.INCOMPLETE and not first_report.errors,
          first_report.status_text)
    w.scan_maps()
    wait(app, lambda: w.scanner is not None and w.scanner.isFinished(), 'Kennfeldscan', 600)
    found = [m for m in w.maps if m.offset == MAP_OFFSET and (m.rows, m.cols) == (12, 16)]
    check('automatic map recognition', found, [(hex(m.offset), m.rows, m.cols) for m in w.maps][:12])
    w.select_map(found[0])
    check('map selected in the editor', w.offset_edit.text() == f'0x{MAP_OFFSET:X}', w.offset_edit.text())
    before = w.map_model.data(w.map_model.index(2, 3))
    check('map value edited', w.map_model.setData(w.map_model.index(2, 3), str(int(before) + 25)), before)
    w.on_edited()
    bad = integrity(app, w)
    check('edited file: checksum wrong and correctable', bad.status == ig.INVALID and bad.correctable,
          bad.status_text)
    preflight = w._preflight()
    check('preflight never green with wrong checksum',
          not preflight.checks_passed and not preflight.checksum_verified and 'FEHLERHAFT' in preflight.checksum_summary,
          preflight.checksum_summary)
    copy = WORK / 'testfirmware_pruefsumme.bin'
    w.save_destination = lambda *a, **k: (str(copy), '')
    shown = []

    def confirm_and_save(dialog):
        from PySide6.QtWidgets import QCheckBox, QPushButton, QPlainTextEdit
        shown.append(dialog.findChild(QPlainTextEdit).toPlainText())
        dialog.findChild(QCheckBox).setChecked(True)
        next(b for b in dialog.findChildren(QPushButton) if b.text().startswith('Korrigierte Kopie')).click()
        return 1
    QDialog.exec = confirm_and_save
    w.integrity_correction_preview()
    check('correction preview shows every byte', shown and 'Byte' in shown[0] and '0x' in shown[0], shown[:1])
    log_path = Path(str(copy) + '.korrektur.json')
    check('corrected copy and change log written', copy.is_file() and log_path.is_file())
    log = json.loads(log_path.read_text(encoding='utf-8'))
    copy_hash = hashlib.sha256(copy.read_bytes()).hexdigest()
    check('change log names exactly this copy', log['sha256_output'] == copy_hash, log['sha256_output'])
    reopened = ig.check_integrity(BinaryImage.from_file(str(copy)))
    check('corrected copy: no checksum error, still not "valid"', not reopened.errors and reopened.status == ig.INCOMPLETE,
          reopened.status_text)
    check('original file unchanged', hashlib.sha256(source.read_bytes()).hexdigest() == original_hash)
    check('preflight stages', [label for label, _ in preflight.stages()][-1] == 'Flashfreigabe', preflight.stages())
    w.set_theme('light')
    w.notes.setPlainText('QA-Projekt Release-Kandidat')
    project = WORK / 'qa-projekt.ecustudio'
    w.project_path = str(project)
    w.save_project()
    check('project saved', project.is_file() and w.project_state() == w.saved_fingerprint)
    RESULT['project'] = {'maps': len(w.maps), 'dirty_bytes': w.image.dirty_bytes, 'digest': w.image.digest}
    w.close()


def restart():
    from ecu_studio.core import integrity as ig
    expected = json.loads((WORK / 'first.json').read_text(encoding='utf-8'))['project']
    app, w, QDialog, QFileDialog = app_and_window()
    check('setting kept after restart', w.theme == 'light', w.theme)
    w.open_project_file(str(WORK / 'qa-projekt.ecustudio'))
    check('project reopened: maps, notes, edits',
          len(w.maps) == expected['maps'] and w.image.dirty_bytes == expected['dirty_bytes']
          and w.image.digest == expected['digest'] and w.notes.toPlainText() == 'QA-Projekt Release-Kandidat',
          (len(w.maps), w.image.dirty_bytes))
    check('editor empty after reopening', w.selected is None and w.name_edit.text() == '')
    check('reopened project: checksum still wrong', integrity(app, w).status == ig.INVALID)
    w.saved_fingerprint = w.project_state()
    copy = WORK / 'testfirmware_pruefsumme.bin'
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(copy), ''))
    w.open_bin()
    report = integrity(app, w)
    check('corrected copy reopened in the program', w.image.path and Path(w.image.path) == copy
          and not report.errors and report.status == ig.INCOMPLETE, report.status_text)
    w.close()


def seed():
    """Old installation (1.19.1): user data an update must keep. Uses only APIs present in 1.19.1."""
    import numpy as np
    from PySide6.QtCore import QSettings
    from ecu_studio.core.model import BinaryImage, MapDefinition, save_project
    import ecu_studio
    RESULT['version'] = ecu_studio.__version__
    WORK.mkdir(parents=True, exist_ok=True)
    data = bytearray(65536)
    y, x = np.mgrid[:8, :8]
    data[0x1000:0x1000 + 128] = (500 + 10 * x + 7 * y).astype('>u2').tobytes()
    source = WORK / 'alt.bin'
    source.write_bytes(bytes(data))
    image = BinaryImage.from_file(str(source))
    image.write(0x1002, b'\x02\x10')
    m = MapDefinition('Alte Tabelle', 0x1000, 8, 8, 'u16', unit='mbar', source='manual', verified=True)
    save_project(str(WORK / 'alt.ecustudio'), image, [m], [{'offset': 0x1000, 'label': 'Marke'}], 'Projekt aus 1.19.1')
    settings = QSettings('ECU Studio', 'ECU Studio AI')
    settings.setValue('ui/theme', 'light')
    settings.setValue('qa/marker', 'vor-dem-update')
    settings.sync()
    check('old version seeded', (WORK / 'alt.ecustudio').is_file(), ecu_studio.__version__)


def compat():
    from PySide6.QtCore import QSettings
    app, w, QDialog, QFileDialog = app_and_window()
    settings = QSettings('ECU Studio', 'ECU Studio AI')
    check('settings of the old version kept', settings.value('qa/marker') == 'vor-dem-update' and w.theme == 'light',
          settings.value('qa/marker'))
    w.open_project_file(str(WORK / 'alt.ecustudio'))
    check('project of the old version opens', [m.name for m in w.maps] == ['Alte Tabelle'] and w.image.dirty_bytes == 2
          and w.notes.toPlainText() == 'Projekt aus 1.19.1' and len(w.bookmarks) == 1, [m.name for m in w.maps])
    w.saved_fingerprint = w.project_state()
    w.close()


def window():
    """The main window of a process started from a shortcut: title with version, program icon, taskbar identity."""
    import ctypes
    from ctypes import wintypes
    from PySide6.QtGui import QImage, QGuiApplication
    from ecu_studio import main, __version__
    from ecu_studio.tools.make_app_icon import ico_entries
    app = QGuiApplication.instance() or QGuiApplication([])
    pid = int(sys.argv[3])
    found = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32 = ctypes.windll.user32

    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buffer, 512)
            if buffer.value.startswith('ECU Studio AI'):
                found.append((hwnd, buffer.value))
        return True
    user32.EnumWindows(enum_proc(visit), 0)
    check('main window visible', found, pid)
    hwnd, title = found[0]
    check('window title shows the version', f'v{__version__}' in title, title)
    send = user32.SendMessageW
    send.restype = ctypes.c_void_p
    send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    entries = {size: QImage.fromData(png) for size, png in
               ico_entries((Path(main.__file__).parent / 'ui' / 'assets' / 'app.ico').read_bytes()).items()}
    for kind, label in ((0, 'small'), (1, 'big')):
        handle = send(hwnd, 0x7F, kind, 0)
        image = QImage.fromHICON(handle) if handle else QImage()
        check(f'window icon ({label}) is the program icon', not image.isNull() and image.width() in entries
              and _difference(image, entries[image.width()]) < 8, image.width())
    properties = main.window_properties(hwnd)
    check('taskbar identity of the window', properties.get(5) == main.APP_USER_MODEL_ID
          and properties.get(2, '').strip('"').lower().endswith('ecu-studio-ai.exe'), properties)
    RESULT['title'] = title


def _difference(image, reference):
    from PySide6.QtGui import QImage
    reference = reference.convertToFormat(QImage.Format.Format_ARGB32)
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    total = 0
    for y in range(image.height()):
        for x in range(image.width()):
            a, b = image.pixel(x, y), reference.pixel(x, y)
            total += sum(abs((a >> s & 255) - (b >> s & 255)) for s in (0, 8, 16, 24))
    return total / (image.width() * image.height() * 4)


if __name__ == '__main__':
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        {'first': first, 'restart': restart, 'seed': seed, 'compat': compat, 'window': window}[MODE]()
        RESULT['passed'] = True
    except Exception:
        RESULT['passed'] = False
        RESULT['error'] = traceback.format_exc()
    (WORK / f'{MODE}.json').write_text(json.dumps(RESULT, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps({k: RESULT.get(k) for k in ('mode', 'passed', 'version', 'error')}, ensure_ascii=False))
    sys.exit(0 if RESULT['passed'] else 1)
