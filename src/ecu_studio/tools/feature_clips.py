"""Record short feature clips (animated GIFs) of the real app for the roadmap.

Usage: python -m ecu_studio.tools.feature_clips OUT_DIR [--only NAME ...]

Runs the actual main window offscreen on a synthetic showcase image
(core/showcase.py, no manufacturer data), drives it like a user would and
draws a mouse pointer with click marks into the frames. Settings go to a
temporary scope; the user's layout and preferences stay untouched.
"""
from __future__ import annotations
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
import numpy as np

WIDTH = 1360
HEIGHT = 820
OUT_WIDTH = 960
CLIPS = ('scan', 'filter', 'view3d', 'compare', 'support', 'english')


class Recorder:
    """Collects frames of a base widget, optional overlay dialog and pointer."""

    def __init__(self, app, base):
        self.app, self.base = app, base
        self.frames: list[np.ndarray] = []
        self.durations: list[int] = []
        self.pointer = None
        self.overlay = None
        self.scale = OUT_WIDTH / WIDTH

    # -- geometry ---------------------------------------------------------
    def at(self, widget, rx: float = .5, ry: float = .5):
        from PySide6.QtCore import QPoint
        local = QPoint(int(widget.width() * rx), int(widget.height() * ry))
        top = widget.window()
        point = widget.mapTo(top, local)
        if top is not self.base and self.overlay is not None:
            off = self._overlay_origin()
            return (point.x() + off[0], point.y() + off[1])
        return (point.x(), point.y())

    def _overlay_origin(self):
        d = self.overlay
        return ((self.base.width() - d.width()) // 2, max(30, (self.base.height() - d.height()) // 2))

    # -- frames -----------------------------------------------------------
    def _compose(self, click: float = 0.0):
        from PySide6.QtCore import Qt, QPointF, QRectF
        from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF, QPen
        self.app.processEvents()
        image = self.base.grab().toImage()
        if self.overlay is not None:
            painter = QPainter(image)
            painter.fillRect(image.rect(), QColor(0, 0, 0, 110))
            x, y = self._overlay_origin()
            painter.fillRect(QRectF(x + 6, y + 8, self.overlay.width(), self.overlay.height()), QColor(0, 0, 0, 90))
            painter.drawImage(x, y, self.overlay.grab().toImage())
            painter.setPen(QPen(QColor(90, 140, 220), 1))
            painter.drawRect(QRectF(x, y, self.overlay.width() - 1, self.overlay.height() - 1))
            painter.end()
        image = image.scaled(int(image.width() * self.scale), int(image.height() * self.scale),
                             Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if self.pointer is not None:
            px, py = self.pointer[0] * self.scale, self.pointer[1] * self.scale
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if click:
                r = 6 + 16 * click
                painter.setPen(QPen(QColor(255, 196, 0, int(230 * (1 - click))), 3))
                painter.setBrush(QColor(255, 196, 0, int(70 * (1 - click))))
                painter.drawEllipse(QPointF(px, py), r, r)
            arrow = QPolygonF([QPointF(px + dx, py + dy) for dx, dy in
                               ((0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12.5), (12.5, 12.5))])
            painter.setPen(QPen(QColor(0, 0, 0), 1.3))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawPolygon(arrow)
            painter.end()
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        h, w, bpl = image.height(), image.width(), image.bytesPerLine()
        raw = np.frombuffer(image.constBits(), np.uint8, count=h * bpl).reshape(h, bpl)
        return raw[:, :w * 3].reshape(h, w, 3).copy()

    def hold(self, ms: int) -> None:
        self.frames.append(self._compose())
        self.durations.append(ms)

    def move(self, target, ms: int = 600) -> None:
        start = self.pointer or (self.base.width() * .55, self.base.height() * .6)
        steps = max(4, ms // 45)
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            self.pointer = (start[0] + (target[0] - start[0]) * e, start[1] + (target[1] - start[1]) * e)
            self.frames.append(self._compose())
            self.durations.append(ms // steps)

    def click(self, action=None) -> None:
        for c in (.15, .45):
            self.frames.append(self._compose(click=c))
            self.durations.append(60)
        if action:
            action()
        for c in (.7, .95):
            self.frames.append(self._compose(click=c))
            self.durations.append(60)

    def save(self, path: Path) -> int:
        from .gif_writer import write_gif
        return write_gif(path, self.frames, self.durations)


def _window(app, image, maps, theme='dark'):
    from ecu_studio.ui.main_window import Window
    win = Window()
    win.resize(WIDTH, HEIGHT)
    win.set_theme(theme)
    win.load_state(image, maps, [], '', None)
    win.show()
    app.processEvents()
    return win


def _close(win) -> None:
    # Recorded edits are throw-away: skip the "unsaved changes" question.
    win.saved_fingerprint = win.project_state()
    win.close()


def _select(win, predicate):
    for row in range(win.catalog_model.rowCount()):
        index = win.catalog_model.index(row, 0)
        m = win.maps[index.data(0x0100)]
        if predicate(m):
            win.map_list.setCurrentIndex(index)
            win.on_map_selection()
            return index
    return None


def _toolbar_button(win, title):
    from PySide6.QtWidgets import QToolBar
    bar = win.findChild(QToolBar, 'toolbar_main')
    return bar.widgetForAction(win.actions[title])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--only', nargs='*', choices=CLIPS)
    args = parser.parse_args(argv)
    wanted = args.only or list(CLIPS)
    if len(wanted) > 1:
        # One process per clip: the translation patches and worker threads of
        # one scene must not leak into the next.
        import subprocess
        return max(subprocess.call([sys.executable, '-m', 'ecu_studio.tools.feature_clips', str(args.out),
                                    '--only', name]) for name in wanted)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if sys.platform == 'win32':
        # The offscreen platform finds no system fonts on its own.
        os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
    work = Path(tempfile.mkdtemp(prefix='ecu-clips-'))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(work / 'settings'))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    QCoreApplication.setOrganizationName('ECU Studio Clips')
    from ecu_studio.core.model import BinaryImage
    from ecu_studio.core.showcase import generate_showcase
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    args.out.mkdir(parents=True, exist_ok=True)
    source = generate_showcase(str(work))
    image = BinaryImage.from_file(str(source))
    maps = scan_calibration_candidates(image, use_definitions=True)
    rec_holder: dict = {}

    # Message boxes become short overlay frames instead of blocking the run.
    def info(parent, title, text, *a, **k):
        rec = rec_holder.get('rec')
        if rec is None:
            return QMessageBox.StandardButton.Ok
        box = QMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.show()
        rec.overlay = box
        rec.hold(300)
        ok = box.button(QMessageBox.StandardButton.Ok)
        rec.move(rec.at(ok), 450)
        rec.click()
        rec.overlay = None
        box.close()
        return QMessageBox.StandardButton.Ok
    QMessageBox.information = staticmethod(info)
    results = {}

    def finish(name, rec):
        path = args.out / f'{name}.gif'
        size = rec.save(path)
        results[name] = (len(rec.frames), size)
        print(f'{name}: {len(rec.frames)} Bilder, {size / 1024:.0f} KiB', flush=True)

    big = lambda m: m.rows == 16 and m.cols == 16

    if 'scan' in wanted:
        win = _window(app, BinaryImage.from_file(str(source)), [])
        rec = rec_holder['rec'] = Recorder(app, win)
        rec.hold(900)
        button = _toolbar_button(win, 'Intelligente Kennfeldsuche (Struktur + Referenz)')
        rec.move(rec.at(button), 700)
        rec.click(win.scan_maps)
        while win.scanner and win.scanner.isRunning():
            rec.hold(120)
            time.sleep(.08)
        app.processEvents()
        rec.hold(300)
        index = None
        for row in range(win.catalog_model.rowCount()):
            m = win.maps[win.catalog_model.index(row, 0).data(0x0100)]
            if big(m) and row > 2:
                index = win.catalog_model.index(row, 0)
                break
        rect = win.map_list.visualRect(index)
        rec.move(rec.at(win.map_list.viewport(), (rect.center().x()) / win.map_list.viewport().width(),
                        rect.center().y() / win.map_list.viewport().height()), 700)
        rec.click(lambda: (win.map_list.setCurrentIndex(index), win.on_map_selection(),
                           win.tabs.setCurrentWidget(win.view2d)))
        rec.hold(2600)
        finish('scan', rec)
        _close(win)

    if 'filter' in wanted:
        win = _window(app, image, list(maps))
        rec = rec_holder['rec'] = Recorder(app, win)
        rec.hold(700)
        rec.move(rec.at(win.tier_filter), 700)
        for i in (1, 2, 4, 0):
            rec.click(lambda i=i: win.tier_filter.setCurrentIndex(i))
            rec.hold(1300)
        finish('filter', rec)
        _close(win)

    if 'view3d' in wanted:
        win = _window(app, image, list(maps))
        _select(win, big)
        win.tabs.setCurrentWidget(win.view2d)
        rec = rec_holder['rec'] = Recorder(app, win)
        rec.hold(600)
        bar = win.tabs.tabBar()
        tab = bar.tabRect(win.tabs.indexOf(win.view3d)).center()
        rec.move(rec.at(bar, tab.x() / bar.width(), tab.y() / bar.height()), 600)
        rec.click(lambda: win.tabs.setCurrentWidget(win.view3d))
        rec.hold(400)
        grip = rec.at(win.view3d, .55, .55)
        rec.move(grip, 400)
        yaw0, pitch0 = win.view3d.yaw, win.view3d.pitch
        steps = 40
        for i in range(1, steps + 1):
            win.view3d.yaw = yaw0 + 360 * i / steps
            win.view3d.pitch = pitch0 + 14 * np.sin(np.pi * i / steps)
            rec.pointer = (grip[0] + 180 * np.sin(2 * np.pi * i / steps), grip[1] - 40 * np.sin(np.pi * i / steps))
            win.view3d.update()
            rec.hold(70)
        rec.hold(900)
        finish('view3d', rec)
        _close(win)

    if 'compare' in wanted:
        mod = BinaryImage.from_file(str(source))
        changed = [m for m in maps if m.rows >= 8 and m.cols >= 8][1:4]
        for k, m in enumerate(changed):
            for r in range(m.rows // 3, m.rows):
                for c in range(m.cols // 2, m.cols):
                    value = mod.physical_value(m, r, c)
                    mod.write_physical(m, r, c, round(value * (1.04 + .02 * k + .004 * (r + c))))
        mod_path = work / 'showcase_mod.bin'
        mod_path.write_bytes(mod.materialize())
        win = _window(app, image, list(maps))
        rec = rec_holder['rec'] = Recorder(app, win)
        original_get = QFileDialog.getOpenFileName
        original_exec = QDialog.exec
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(mod_path), ''))

        def play(dialog):
            from PySide6.QtWidgets import QTabWidget, QTableWidget
            dialog.resize(1080, 620)
            dialog.show()
            rec.overlay = dialog
            rec.hold(900)
            tabs = dialog.findChild(QTabWidget)
            table = tabs.widget(0)
            row = table.visualItemRect(table.item(0, 1)).center()
            rec.move(rec.at(table.viewport(), row.x() / table.viewport().width(),
                            row.y() / table.viewport().height()), 600)
            rec.click(lambda: table.setCurrentCell(0, 1))
            rec.hold(600)
            bar = tabs.tabBar()
            index = next(i for i in range(tabs.count()) if 'Heatmap' in tabs.tabText(i))
            tab = bar.tabRect(index).center()
            rec.move(rec.at(bar, tab.x() / bar.width(), tab.y() / bar.height()), 600)
            rec.click(lambda: tabs.setCurrentIndex(index))
            rec.hold(2800)
            rec.overlay = None
            dialog.close()
            return 0
        QDialog.exec = lambda self: play(self)
        try:
            rec.hold(600)
            rec.click(win.compare_file)
            rec.hold(500)
        finally:
            QFileDialog.getOpenFileName = original_get
            QDialog.exec = original_exec
        finish('compare', rec)
        _close(win)

    if 'support' in wanted:
        win = _window(app, image, list(maps))
        rec = rec_holder['rec'] = Recorder(app, win)
        original_exec = QDialog.exec

        def play(dialog):
            from PySide6.QtWidgets import QTableWidget
            dialog.resize(1120, 640)
            dialog.show()
            rec.overlay = dialog
            rec.hold(1200)
            table = dialog.findChild(QTableWidget)
            if table is not None:
                bar = table.verticalScrollBar()
                rec.move(rec.at(table.viewport(), .5, .6), 500)
                for i in range(1, 13):
                    bar.setValue(int(bar.maximum() * i / 12))
                    rec.hold(160)
            rec.hold(1500)
            rec.overlay = None
            dialog.close()
            return 0
        QDialog.exec = lambda self: play(self)
        try:
            rec.hold(400)
            win.show_support_matrix()
        finally:
            QDialog.exec = original_exec
        finish('support', rec)
        _close(win)

    if 'english' in wanted:
        # Last: installing the translation patches Qt for the rest of the process.
        german = _window(app, image, list(maps))
        _select(german, big)
        german.tabs.setCurrentWidget(german.view2d)
        rec = Recorder(app, german)
        rec.pointer = rec.at(german.menuBar(), .2, .5)
        rec.hold(1800)
        first = rec._compose()
        from ecu_studio.ui import i18n_qt
        i18n_qt.install(app, 'en')
        english = _window(app, image, list(maps))
        _select(english, big)
        english.tabs.setCurrentWidget(english.view2d)
        rec.base = english
        second = rec._compose()
        def wipe(a, b):
            width = a.shape[1]
            for i in range(1, 11):
                edge = int(width * i / 10)
                frame = a.copy()
                frame[:, :edge] = b[:, :edge]
                frame[:, max(0, edge - 3):edge] = (255, 196, 0)
                rec.frames.append(frame)
                rec.durations.append(55)
            rec.frames.append(b)
            rec.durations.append(2400)
        wipe(first, second)
        wipe(second, first)
        finish('english', rec)
        _close(german)
        _close(english)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
