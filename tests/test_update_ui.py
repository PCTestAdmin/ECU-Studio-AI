"""Update dialog and controller behaviour (offscreen, no network)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from ecu_studio.core import updates
from ecu_studio.ui import updates as ui

RELEASE = updates.Release('9.9.0', '## Neu\n- Schneller', 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/tag/v9.9.0',
                          'ECU-Studio-AI-9.9.0-windows-x64.zip',
                          'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v9.9.0/a.zip', 5,
                          'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v9.9.0/a.zip.sha256', None)


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    class W:                                   # the controller only needs settings + a parent widget
        pass
    from PySide6.QtWidgets import QWidget
    w = QWidget(); w.settings = QSettings(str(tmp_path / 's.ini'), QSettings.Format.IniFormat)
    w.close = lambda: None
    yield w


def test_dialog_text_buttons_and_choice(window):
    dialog = ui.UpdateDialog(RELEASE, installable=True, parent=window)
    texts = [b.text() for b in dialog.findChildren(QPushButton)]
    assert texts == ['Jetzt aktualisieren', 'Später erinnern', 'Diese Version überspringen']
    from PySide6.QtWidgets import QLabel, QTextBrowser
    labels = ' '.join(l.text() for l in dialog.findChildren(QLabel))
    assert 'ECU Studio AI Version 9.9.0 ist verfügbar. Möchtest du jetzt aktualisieren?' in labels
    assert 'Schneller' in dialog.findChildren(QTextBrowser)[0].toPlainText()   # release notes shown
    dialog.findChildren(QPushButton)[2].click()
    assert dialog.choice == ui.UpdateDialog.SKIP


def test_skip_is_remembered_and_auto_check_can_be_disabled(window, monkeypatch):
    c = ui.UpdateController(window)
    assert c.auto_enabled()
    c.set_auto(False); assert not c.auto_enabled()
    c.set_auto(True)
    monkeypatch.setattr(ui.UpdateDialog, 'exec', lambda self: setattr(self, 'choice', self.SKIP))
    c._checked(RELEASE, '', manual=False)
    assert window.settings.value(ui.KEY_SKIP) == '9.9.0' and window.settings.value(ui.KEY_LAST) is not None
    shown = []
    monkeypatch.setattr(ui.UpdateDialog, 'exec', lambda self: shown.append(1))
    c._checked(RELEASE, '', manual=False)            # skipped version: no dialog on automatic checks
    assert not shown
    c._checked(RELEASE, '', manual=True)             # but "Jetzt nach Updates suchen" still shows it
    assert shown


def test_offline_is_silent_automatically_and_explained_when_asked(window, monkeypatch):
    infos = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: infos.append(a[2] if len(a) > 2 else ''))
    c = ui.UpdateController(window)
    c._checked(None, 'Update-Prüfung nicht möglich: offline', manual=False)
    assert not infos and window.settings.value(ui.KEY_LAST) is None   # retried next time
    c._checked(None, 'Update-Prüfung nicht möglich: offline', manual=True)
    assert infos and 'Keine Verbindung' in infos[0]


def test_no_automatic_network_check_when_headless(window, monkeypatch):
    called = []
    c = ui.UpdateController(window)
    monkeypatch.setattr(c, 'check', lambda manual, startup=False: called.append(manual))
    c.start()
    assert not c.timer.isActive() and not called


def test_source_checkout_opens_release_page_instead_of_installing(window, monkeypatch):
    opened = []
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    monkeypatch.setattr(ui.UpdateDialog, 'exec', lambda self: setattr(self, 'choice', self.NOW))
    c = ui.UpdateController(window)
    c._checked(RELEASE, '', manual=True)
    assert opened == [RELEASE.page_url] and c.pending is None
    assert c.launch_pending() is False                # nothing to hand over


def _installed(tmp_path, with_backup=True):
    root = tmp_path / 'ECU-Studio-AI'
    for folder, version in ((root, '1.15.0'), (tmp_path / 'ECU-Studio-AI.backup', '1.14.0'))[:2 if with_backup else 1]:
        (folder / '_internal').mkdir(parents=True)
        (folder / 'ECU-Studio-AI.exe').write_bytes(b'')
        (folder / '_internal' / 'updater.ps1').write_text('# updater')
        (folder / 'VERSION.txt').write_text(version + '\n')
    return root


def test_restore_names_backup_version_and_hands_over_to_updater(window, tmp_path, monkeypatch):
    root = _installed(tmp_path)
    c = ui.UpdateController(window)
    assert c.backup_version(root) == '1.14.0'
    monkeypatch.setattr(ui.updates, 'install_root', lambda exe: root)
    monkeypatch.setattr(ui, 'data_dir', lambda: tmp_path / 'data')
    asked = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.Yes)[1])
    started = []
    monkeypatch.setattr(ui.subprocess, 'Popen', lambda cmd, **k: started.append((cmd, k.get('env', {}))))
    c.request_restore()
    assert '1.14.0 wiederherstellen' in asked[0] and c.pending == ('restore',)
    assert c.launch_pending() is True
    cmd, env = started[0]
    assert '-Restore' in cmd and '-Archive' not in cmd and str(root) in cmd
    assert not any(k.upper() == 'PSMODULEPATH' for k in env)          # no inherited PowerShell 7 module path


def test_restore_without_backup_only_informs(window, tmp_path, monkeypatch):
    root = _installed(tmp_path, with_backup=False)
    monkeypatch.setattr(ui.updates, 'install_root', lambda exe: root)
    infos = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: infos.append(a[2]))
    c = ui.UpdateController(window)
    c.request_restore()
    assert c.pending is None and 'keine gesicherte' in infos[0]


def test_start_checks_even_if_checked_recently(window, monkeypatch):
    """A check minutes before a release is published must not hide it for a day."""
    import time
    started = []

    class FakeWorker:                                           # records the start, no network
        def __init__(self):
            started.append(1)
            self.finished_check = type('S', (), {'connect': lambda self, fn: None})()

        def start(self):
            pass

        def isRunning(self):
            return False

    c = ui.UpdateController(window)
    window.settings.setValue(ui.KEY_LAST, time.time())          # checked just now
    monkeypatch.setattr(ui, 'CheckWorker', FakeWorker)
    c.check(manual=False)                                       # hourly timer: not due yet
    assert not started
    c.check(manual=False, startup=True)                         # app start: always checks
    assert started == [1]


def test_updater_start_flags_never_detach_powershell():
    """DETACHED_PROCESS makes Windows PowerShell exit 0 without running the script (1.15/1.16.0 bug)."""
    import subprocess
    assert not ui.SPAWN_FLAGS & getattr(subprocess, 'DETACHED_PROCESS', 0x8)


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell')
def test_spawned_powershell_really_runs_its_script_from_a_windowless_parent(tmp_path):
    """The real hand-over path: started like the app starts the updater, the script must run."""
    import subprocess, sys, time
    from pathlib import Path
    out = tmp_path / 'ran.txt'
    probe = tmp_path / 'probe.ps1'
    probe.write_text("param([string]$Out)\nAdd-Content -LiteralPath $Out -Value 'ran'\n", encoding='utf-8')
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
               '-File', str(probe), '-Out', str(out)]
    # Parent without console (pythonw, like the packaged app) that exits right after spawning.
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    parent = pythonw if pythonw.exists() else Path(sys.executable)
    code = ('import os,sys;sys.path.insert(0,sys.argv[1]);from ecu_studio.ui import updates as u;'
            'u.spawn_hidden(sys.argv[2:],{k:v for k,v in os.environ.items() if k.upper()!="PSMODULEPATH"})')
    src = str(Path(ui.__file__).resolve().parents[2])
    subprocess.run([str(parent), '-c', code, src, *command], timeout=60, check=True)
    for _ in range(120):
        if out.exists():
            break
        time.sleep(.5)
    assert out.exists(), 'PowerShell started but did not run the updater script'
