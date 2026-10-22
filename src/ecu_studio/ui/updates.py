"""Update check, dialog and hand-over to the separate updater (Qt side of core.updates)."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
                               QProgressDialog, QMessageBox)
from .. import __version__
from ..core import updates

KEY_AUTO, KEY_LAST, KEY_SKIP = 'updates/auto_check', 'updates/last_check', 'updates/skipped_version'


def data_dir() -> Path:
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'ECUStudioAI'


class CheckWorker(QThread):
    finished_check = Signal(object, str)          # Release | None, error text ('' = ok)

    def run(self):
        try:
            self.finished_check.emit(updates.fetch_latest(), '')
        except updates.UpdateError as exc:
            self.finished_check.emit(None, str(exc))


class DownloadWorker(QThread):
    progress = Signal(int)
    done = Signal(object, str, str)               # path | None, sha256, error

    def __init__(self, release):
        super().__init__()
        self.release, self.stop = release, False

    def run(self):
        try:
            path, digest = updates.download(self.release, data_dir() / 'updates' / self.release.version,
                                            progress=self.progress.emit, cancelled=lambda: self.stop)
            self.done.emit(path, digest, '')
        except updates.UpdateError as exc:
            self.done.emit(None, '', str(exc))


class UpdateDialog(QDialog):
    """'Version X ist verfügbar' with notes and the three choices; result in self.choice."""
    NOW, LATER, SKIP = 'now', 'later', 'skip'

    def __init__(self, release, installable: bool, parent=None):
        super().__init__(parent)
        self.choice = self.LATER
        self.setWindowTitle('ECU Studio AI – Update verfügbar')
        self.resize(620, 460)
        layout = QVBoxLayout(self)
        title = QLabel(f'<b>ECU Studio AI Version {release.version} ist verfügbar. Möchtest du jetzt aktualisieren?</b>')
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(QLabel(f'Installiert: {__version__}  ·  Neu: {release.version}'))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes or '_Keine Änderungshinweise veröffentlicht._')
        layout.addWidget(notes, 1)
        hint = QLabel('Projekte und Einstellungen bleiben erhalten. Das Paket wird per SHA-256 geprüft, die vorherige '
                      'Version bleibt als Sicherung erhalten und wird bei einem Fehler automatisch wiederhergestellt.'
                      if installable else
                      'Diese Installation läuft aus dem Quellcode – „Jetzt aktualisieren“ öffnet die Release-Seite.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        now = QPushButton('Jetzt aktualisieren'); later = QPushButton('Später erinnern')
        skip = QPushButton('Diese Version überspringen')
        for button, value in ((now, self.NOW), (later, self.LATER), (skip, self.SKIP)):
            button.clicked.connect(lambda _=False, v=value: self._pick(v))
            row.addWidget(button)
        layout.addLayout(row)
        now.setDefault(True)

    def _pick(self, value):
        self.choice = value
        self.accept()


class UpdateController:
    """Owns the schedule (start + at most daily), the dialogs and the hand-over to updater.ps1."""

    def __init__(self, window):
        self.window, self.settings = window, window.settings
        self.worker = self.download_worker = None
        self.pending = None                       # (archive, sha256) to install after the window closed
        self.timer = QTimer(window)
        self.timer.setInterval(3600 * 1000)       # re-evaluate hourly; check_due enforces once a day
        self.timer.timeout.connect(lambda: self.check(manual=False))

    # -- settings -------------------------------------------------------------------------
    def auto_enabled(self) -> bool:
        return str(self.settings.value(KEY_AUTO, 'true')).lower() in ('true', '1')

    def set_auto(self, enabled: bool):
        self.settings.setValue(KEY_AUTO, 'true' if enabled else 'false')

    def start(self):
        # No network from tests, CI, smoke and self-checks (headless) or when switched off.
        if os.environ.get('ECU_STUDIO_NO_UPDATE_CHECK') or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        # Every start checks once: a check shortly before a release is published
        # must not hide that release for a whole day (seen with 1.16.0).
        QTimer.singleShot(4000, lambda: self.check(manual=False, startup=True))
        self.timer.start()

    # -- check ----------------------------------------------------------------------------
    def check(self, manual: bool, startup: bool = False):
        if self.worker and self.worker.isRunning():
            return
        if not manual:
            last = self.settings.value(KEY_LAST)
            if not self.auto_enabled() or not (startup or updates.check_due(float(last) if last else None)):
                return
        self.worker = CheckWorker()
        self.worker.finished_check.connect(lambda release, error: self._checked(release, error, manual))
        self.worker.start()

    def _checked(self, release, error, manual):
        if error:
            # Offline or rate-limited: silent for automatic checks, short note when asked.
            if manual:
                QMessageBox.information(self.window, 'Updates', 'Keine Verbindung zu GitHub – bitte später erneut versuchen.\n\n' + error)
            return
        self.settings.setValue(KEY_LAST, time.time())
        skipped = None if manual else self.settings.value(KEY_SKIP)
        if not updates.update_available(__version__, release, skipped):
            if manual:
                QMessageBox.information(self.window, 'Updates', f'ECU Studio AI {__version__} ist aktuell.')
            return
        installable = updates.install_root(sys.executable) is not None
        dialog = UpdateDialog(release, installable, self.window)
        dialog.exec()
        if dialog.choice == UpdateDialog.SKIP:
            self.settings.setValue(KEY_SKIP, release.version)
        elif dialog.choice == UpdateDialog.NOW:
            if installable:
                self._download(release)
            else:
                QDesktopServices.openUrl(QUrl(release.page_url))

    # -- download and hand-over -----------------------------------------------------------
    def _download(self, release):
        progress = QProgressDialog(f'Lade ECU Studio AI {release.version} …', 'Abbrechen', 0, 100, self.window)
        progress.setWindowTitle('Update')
        progress.setMinimumDuration(0)
        self.download_worker = DownloadWorker(release)
        self.download_worker.progress.connect(progress.setValue)
        progress.canceled.connect(lambda: setattr(self.download_worker, 'stop', True))
        self.download_worker.done.connect(lambda path, digest, error: self._downloaded(progress, release, path, digest, error))
        self.download_worker.start()

    def _downloaded(self, progress, release, path, digest, error):
        progress.close()
        if error:
            QMessageBox.warning(self.window, 'Update nicht installiert', error)
            return
        answer = QMessageBox.question(
            self.window, 'Update bereit',
            f'ECU Studio AI {release.version} ist geprüft (SHA-256 {digest[:16]}…).\n\n'
            'Das Programm wird jetzt geschlossen, aktualisiert und neu gestartet. Fortfahren?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.pending = ('update', path, digest)
        self.window.close()          # closeEvent asks about unsaved work and calls launch_pending()

    # -- restore the previous version ---------------------------------------------------------
    def backup_version(self, root: Path | None = None) -> str | None:
        """Version kept by the last update in <install>.backup, or None."""
        root = root or updates.install_root(sys.executable)
        if root is None:
            return None
        backup = root.parent / (root.name + '.backup')
        if not (backup / 'ECU-Studio-AI.exe').is_file():
            return None
        try:
            return (backup / 'VERSION.txt').read_text(encoding='ascii').strip() or '?'
        except OSError:
            return '?'

    def request_restore(self):
        version = self.backup_version()
        if version is None:
            QMessageBox.information(self.window, 'Vorherige Version',
                                    'Es gibt keine gesicherte vorherige Version (erst nach einem Update vorhanden).')
            return
        answer = QMessageBox.question(
            self.window, 'Vorherige Version wiederherstellen',
            f'ECU Studio AI {version} wiederherstellen? Die aktuelle Version {__version__} bleibt als Sicherung '
            'erhalten und kann genauso zurückgeholt werden.\n\nDas Programm wird dafür geschlossen und neu gestartet.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.pending = ('restore',)
            self.window.close()

    def launch_pending(self) -> bool:
        """Start the copied updater detached; called from closeEvent once closing is accepted."""
        if not self.pending:
            return False
        kind, *args = self.pending
        self.pending = None
        root = updates.install_root(sys.executable)
        if root is None:
            return False
        work = data_dir() / 'updates'
        work.mkdir(parents=True, exist_ok=True)
        script = work / 'updater.ps1'
        shutil.copy2(root / '_internal' / 'updater.ps1', script)   # run outside the folder it replaces
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
                   '-File', str(script), '-InstallDir', str(root),
                   '-WaitPid', str(os.getpid()), '-LogFile', str(work / 'update.log'), '-Relaunch']
        if kind == 'restore':
            command.append('-Restore')
        else:
            archive, digest = args
            command += ['-Archive', str(archive), '-Sha256', digest]
        # Windows PowerShell must not inherit a PowerShell 7 module path (see updater.ps1).
        env = {k: v for k, v in os.environ.items() if k.upper() != 'PSMODULEPATH'}
        # Keep PowerShell's current directory outside the installation. On Windows a
        # process whose cwd is the install folder can keep that directory open and make
        # the updater's Rename-Item fail even after the application PID has exited.
        spawn_hidden(command, env, cwd=str(work))
        return True


# CREATE_NO_WINDOW, not DETACHED_PROCESS: without a console Windows PowerShell 5.1
# exits with code 0 WITHOUT running the script. That silently broke every in-app
# update up to 1.16.0. The child still outlives the app (no job object).
SPAWN_FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)


def spawn_hidden(command: list[str], env: dict, cwd: str | os.PathLike | None = None) -> subprocess.Popen:
    """Start a console program (PowerShell) invisibly so that it survives the application."""
    return subprocess.Popen(command, creationflags=SPAWN_FLAGS, close_fds=True, env=env,
                            cwd=cwd,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
