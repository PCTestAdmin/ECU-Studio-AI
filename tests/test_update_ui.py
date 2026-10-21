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
    monkeypatch.setattr(c, 'check', lambda manual: called.append(manual))
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
