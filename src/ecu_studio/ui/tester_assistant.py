"""Graphical assistant for the local recognition check (quality phase 6): Werkzeuge → Kennfelderkennung überprüfen.

Same measurement and export as the command line (tools/tester_core.py): firmware with a real format check,
definition with a fit check, detection on the firmware bytes only in a background thread (cancellable, also
by closing the window), results with recall, agreement and what cannot be evaluated, an export preview of
exactly the file content (rounded unless exact counts are chosen) that is written only after explicit consent,
and voluntary feedback from fixed choices. Nothing is sent anywhere; there is no network code.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QRadioButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..tools import tester_core as core

FAILED = ('Die Messung ist fehlgeschlagen ({0}). Nichts wurde gespeichert. Prüfe, ob die Definition zu genau '
          'dieser Datei gehört.')


class Job(QThread):
    """Runs ``fn(cancelled, progress)`` off the interface thread; never emits after an interruption."""
    progressed = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)
    stopped = Signal()

    def __init__(self, fn, parent):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        stop = self.isInterruptionRequested
        try:
            result = self.fn(stop, lambda i, text: self.progressed.emit(i, text))
        except core.Cancelled:
            self.stopped.emit()
            return
        except Exception as e:   # noqa: BLE001 - reduced to the error kind (texts can carry paths or names)
            message = str(e) if isinstance(e, core.TesterError) else FAILED.format(type(e).__name__)
            if stop():
                self.stopped.emit()
            else:
                self.failed.emit(message)
            return
        if stop():
            self.stopped.emit()
        else:
            self.done.emit(result)


class ShareBars(QWidget):
    """Horizontal bars for shares (0..1); a missing share is drawn as 'nicht bewertbar'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[tuple[str, float | None]] = []
        self.setMinimumHeight(140)

    def set_rows(self, rows):
        self.rows = list(rows)
        self.setMinimumHeight(28 * max(len(self.rows), 1) + 8)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        label_w, h = 260, 22
        width = max(self.width() - label_w - 70, 40)
        pal = self.palette()
        for i, (label, share) in enumerate(self.rows):
            y = 4 + i * 28
            p.setPen(pal.windowText().color())
            p.drawText(0, y, label_w - 8, h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label)
            p.fillRect(label_w, y + 4, width, h - 8, pal.alternateBase())
            if share is None:
                p.drawText(label_w + 6, y, width, h, Qt.AlignmentFlag.AlignVCenter, 'nicht bewertbar')
                continue
            p.fillRect(label_w, y + 4, int(width * max(0.0, min(share, 1.0))), h - 8, QColor(54, 116, 181))
            p.drawText(label_w + width + 6, y, 64, h, Qt.AlignmentFlag.AlignVCenter, f'{share:.0%}')
        p.end()


class TesterAssistant(QDialog):
    PAGES = ('Einführung', 'Firmware', 'Definition', 'Analyse', 'Ergebnis', 'Export', 'Feedback')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Kennfelderkennung überprüfen – lokaler Test')
        self.resize(900, 680)
        self.image = None
        self.firmware = ''
        self.reference = ''
        self.reference_ok = False
        self.counts = None
        self.report = None
        self.shown_code = None
        self.job = None
        self.generation = 0
        self._pending_close = False
        self.saved: list[Path] = []
        root = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setStyleSheet('font-weight: 600; font-size: 15px')
        root.addWidget(self.title)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        for build in (self._intro, self._firmware_page, self._reference_page, self._analysis_page,
                      self._result_page, self._export_page, self._feedback_page):
            self.stack.addWidget(build())
        nav = QHBoxLayout()
        self.back = QPushButton('Zurück')
        self.next = QPushButton('Weiter')
        self.close_button = QPushButton('Schließen')
        self.back.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next.clicked.connect(lambda: self.go(self.stack.currentIndex() + 1))
        self.close_button.clicked.connect(self.reject)
        nav.addStretch(1)
        for b in (self.back, self.next, self.close_button):
            nav.addWidget(b)
        root.addLayout(nav)
        self.go(0)

    # ------------------------------------------------------------------------------------------- pages
    def _page(self, text):
        w = QWidget()
        lay = QVBoxLayout(w)
        if text:
            lab = QLabel(text)
            lab.setWordWrap(True)
            lay.addWidget(lab)
        return w, lay

    def _intro(self):
        w, lay = self._page(
            'Dieser Assistent misst lokal, wie gut ECU Studio die Kennfelder einer eigenen Firmware findet. '
            'Dazu brauchst du die Firmware (BIN/ORI) und eine passende Definition (A2L, XDF oder CSV), die genau '
            'zu dieser Datei gehört.\n\n'
            'So läuft es ab: Die Kennfeldsuche bekommt nur die Firmware-Bytes – die Definition wird erst danach '
            'zum Vergleich gelesen. Das Ergebnis zeigt, wie viele Kennfelder der Definition gefunden wurden '
            '(Trefferquote), wie oft Datentyp und Achsen stimmen und was sich nicht bewerten lässt.\n\n'
            'Es wird nichts gesendet. Ein Bericht wird nur gespeichert, wenn du ihn ansiehst und zustimmst; er '
            'enthält nur Zählwerte. Verwende nur Dateien, die du rechtmäßig nutzen darfst. Die Messung ist deine '
            'eigene Messung und keine unabhängige Validierung von ECU Studio.')
        lay.addStretch(1)
        return w

    def _firmware_page(self):
        w, lay = self._page('Wähle die Firmware (Rohabbild, z. B. .bin oder .ori). Die Datei wird nur gelesen.')
        row = QHBoxLayout()
        self.firmware_edit = QLineEdit()
        self.firmware_edit.setReadOnly(True)
        pick = QPushButton('Firmware wählen …')
        pick.clicked.connect(self.pick_firmware)
        row.addWidget(self.firmware_edit, 1)
        row.addWidget(pick)
        lay.addLayout(row)
        self.firmware_status = QLabel()
        self.firmware_status.setWordWrap(True)
        lay.addWidget(self.firmware_status)
        lay.addStretch(1)
        return w

    def _reference_page(self):
        w, lay = self._page('Wähle die Definition, die zu genau dieser Firmware gehört, und gib die '
                            'Steuergerätelinie an (z. B. „Bosch MEVD17.2“, ohne Software- oder Teilenummer).')
        form = QFormLayout()
        row = QHBoxLayout()
        self.reference_edit = QLineEdit()
        self.reference_edit.setReadOnly(True)
        pick = QPushButton('Definition wählen …')
        pick.clicked.connect(self.pick_reference)
        row.addWidget(self.reference_edit, 1)
        row.addWidget(pick)
        form.addRow('Definition', row)
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText('z. B. Bosch MEVD17.2')
        self.line_edit.textChanged.connect(lambda _: self._reference_changed())
        form.addRow('Steuergerätelinie', self.line_edit)
        self.anchor_edit = QLineEdit()
        self.anchor_edit.setPlaceholderText('nur A2L, leer = automatisch')
        self.anchor_edit.textChanged.connect(lambda _: self._reference_changed())
        form.addRow('A2L-Basisadresse', self.anchor_edit)
        lay.addLayout(form)
        self.check_button = QPushButton('Passung prüfen')
        self.check_button.clicked.connect(self.check_reference)
        lay.addWidget(self.check_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.reference_status = QLabel()
        self.reference_status.setWordWrap(True)
        lay.addWidget(self.reference_status)
        lay.addStretch(1)
        return w

    def _analysis_page(self):
        w, lay = self._page('Die Kennfeldsuche läuft lokal und kann je nach Datei einige Minuten dauern. Sie '
                            'bekommt nur die Firmware-Bytes, nicht die Definition.')
        row = QHBoxLayout()
        self.start_button = QPushButton('Analyse starten')
        self.cancel_button = QPushButton('Analyse abbrechen')
        self.cancel_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_analysis)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        row.addWidget(self.start_button)
        row.addWidget(self.cancel_button)
        row.addStretch(1)
        lay.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(core.STEPS))
        self.progress.setValue(0)
        lay.addWidget(self.progress)
        self.analysis_status = QLabel()
        self.analysis_status.setWordWrap(True)
        lay.addWidget(self.analysis_status)
        lay.addStretch(1)
        return w

    def _result_page(self):
        w, lay = self._page('')
        self.result_text = QLabel()
        self.result_text.setWordWrap(True)
        lay.addWidget(self.result_text)
        self.bars = ShareBars()
        lay.addWidget(self.bars)
        self.function_table = QTableWidget(0, 4)
        self.function_table.setHorizontalHeaderLabels(['Bekannte Funktionen', 'richtig', 'falsch', 'offen'])
        self.function_table.verticalHeader().setVisible(False)
        lay.addWidget(QLabel('Funktionszuordnung: ein Teil der Kennfelder gilt als bekannt (Anker), der Rest wird '
                             'zugeordnet; offen = nicht zugeordnet statt geraten.'))
        lay.addWidget(self.function_table, 1)
        return w

    def _export_page(self):
        w, lay = self._page('Vorschau – genau dieser Inhalt würde als Datei gespeichert (sonst nichts):')
        self.exact_box = QCheckBox('Exakte Zählwerte (höheres Wiedererkennungsrisiko)')
        self.exact_box.toggled.connect(lambda _: self.refresh_preview())
        lay.addWidget(self.exact_box)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        lay.addWidget(self.preview, 1)
        warn = QLabel(core.PRIVACY_WARNING)
        warn.setWordWrap(True)
        lay.addWidget(warn)
        self.consent_box = QCheckBox('Ich habe den Inhalt geprüft und bin mit dem Speichern einverstanden.')
        self.consent_box.toggled.connect(lambda on: self.save_button.setEnabled(on and self.report is not None))
        lay.addWidget(self.consent_box)
        self.save_button = QPushButton('Bericht speichern …')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        lay.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.export_status = QLabel('Ohne Speichern wird nichts aufbewahrt.')
        self.export_status.setWordWrap(True)
        lay.addWidget(self.export_status)
        return w

    def _feedback_page(self):
        w, lay = self._page('Freiwillig: Wie hilfreich war die Erkennung? Es gibt nur feste Antworten, keine '
                            'freie Texteingabe. Auch das Feedback wird nur nach Vorschau und Zustimmung als Datei '
                            'gespeichert und nirgendwohin gesendet.')
        self.rating_group = QButtonGroup(self)
        grid = QGridLayout()
        for i, label in enumerate(('keine Angabe', *core.FEEDBACK_RATINGS)):
            rb = QRadioButton(label)
            rb.setChecked(i == 0)
            rb.setProperty('rating', None if i == 0 else label)
            self.rating_group.addButton(rb, i)
            grid.addWidget(rb, 0, i)
        lay.addLayout(grid)
        self.topic_boxes = []
        for topic in core.FEEDBACK_TOPICS:
            box = QCheckBox(topic)
            box.setProperty('topic', topic)       # the original value: the shown text may be translated
            box.toggled.connect(lambda _: self.refresh_feedback())
            self.topic_boxes.append(box)
            lay.addWidget(box)
        self.rating_group.buttonToggled.connect(lambda *_: self.refresh_feedback())
        self.feedback_preview = QPlainTextEdit()
        self.feedback_preview.setReadOnly(True)
        self.feedback_preview.setMaximumHeight(160)
        lay.addWidget(self.feedback_preview)
        self.feedback_consent = QCheckBox('Ich bin mit dem Speichern dieses Feedbacks einverstanden.')
        self.feedback_save = QPushButton('Feedback speichern …')
        self.feedback_save.setEnabled(False)
        self.feedback_consent.toggled.connect(self.feedback_save.setEnabled)
        self.feedback_save.clicked.connect(self.save_feedback)
        lay.addWidget(self.feedback_consent)
        lay.addWidget(self.feedback_save, 0, Qt.AlignmentFlag.AlignLeft)
        info = QLabel('Ob und an wen du gespeicherte Dateien weitergibst (z. B. als Anhang in einem selbst '
                      'erstellten GitHub-Issue), entscheidest du selbst. ECU Studio sendet nichts.')
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addStretch(1)
        self.refresh_feedback()
        return w

    # -------------------------------------------------------------------------------------- navigation
    def can_leave(self, index) -> bool:
        if index == 1:
            return self.image is not None
        if index == 2:
            return self.reference_ok
        if index == 3:
            return self.counts is not None and not self.running()
        return True

    def go(self, index):
        index = max(0, min(index, self.stack.count() - 1))
        if index > self.stack.currentIndex() and not all(self.can_leave(i) for i in range(index)):
            return
        if self.running() and index != 3:
            return
        self.stack.setCurrentIndex(index)
        self.title.setText(f'Schritt {index + 1} von {self.stack.count()}: {self.PAGES[index]}')
        if index == 4:
            self.show_results()
        if index == 5:
            self.refresh_preview()
        self.update_nav()

    def update_nav(self):
        i = self.stack.currentIndex()
        self.back.setEnabled(i > 0 and not self.running())
        self.next.setEnabled(i < self.stack.count() - 1 and self.can_leave(i))

    def running(self) -> bool:
        return self.job is not None and self.job.isRunning()

    # -------------------------------------------------------------------------------------------- inputs
    def pick_firmware(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Firmware wählen', '', 'Firmware (*.bin *.ori *.mod);;Alle Dateien (*)')
        if path:
            self.set_firmware(path)

    def set_firmware(self, path: str) -> bool:
        self.image, self.firmware = None, path
        self._reset_results()
        self.reference_ok = False
        self.firmware_edit.setText(Path(path).name)
        try:
            self.image = core.check_firmware(path)
        except core.TesterError as e:
            self.firmware_status.setText(str(e))
        else:
            self.firmware_status.setText(f'Firmware geprüft: Rohabbild mit {self.image.size // 1024} KiB.')
        self.update_nav()
        return self.image is not None

    def pick_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Definition wählen', '',
                                              'Definition (*.a2l *.xdf *.csv);;Alle Dateien (*)')
        if path:
            self.set_reference(path)

    def set_reference(self, path: str):
        self.reference = path
        self.reference_edit.setText(Path(path).name)
        self._reference_changed()

    def _reference_changed(self):
        self.reference_ok = False
        self._reset_results()
        self.reference_status.setText('')
        self.update_nav()

    def _anchor(self) -> str | None:
        text = self.anchor_edit.text().strip()
        return text or None

    def check_reference(self) -> None:
        if self.running() or self.image is None:
            return
        try:
            line = core.check_line(self.line_edit.text(), self.firmware, self.reference)
            anchor = self._anchor()
            base = int(anchor, 0) if anchor else None
        except core.TesterError as e:
            self.reference_status.setText(str(e))
            return
        except ValueError:
            self.reference_status.setText('A2L-Basisadresse: bitte als Zahl angeben, z. B. 0x80000000.')
            return
        self.reference_status.setText('Definition wird gelesen und geprüft …')
        image, reference = self.image, self.reference
        self._run(lambda stop, progress: core.check_reference(reference, image, base),
                  lambda result: self._reference_checked(line, result), self.reference_status)

    def _reference_checked(self, line, result):
        self.line = line
        self.reference_ok = True
        axes = (f", {result['axes_rising']} von {result['axes']} Achsen geordnet" if result['axes'] else '')
        self.reference_status.setText(f"Definition passt: {result['tables_2d']} Kennfelder (2D) in dieser "
                                      f"Firmware{axes}.")
        self.update_nav()

    # ------------------------------------------------------------------------------------------ analysis
    def start_analysis(self) -> None:
        if self.running() or not self.reference_ok:
            return
        self._reset_results()
        firmware, reference, anchor = self.firmware, self.reference, self._anchor()
        self.progress.setValue(0)
        self.analysis_status.setText('Analyse läuft …')
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._run(lambda stop, progress: core.measure_counts(firmware, reference, anchor=anchor, cancelled=stop,
                                                             progress=progress),
                  self._analysed, self.analysis_status)

    def _analysed(self, counts):
        self.counts = counts
        self.progress.setValue(len(core.STEPS))
        self.analysis_status.setText('Analyse abgeschlossen.')
        self.go(4)

    def cancel_analysis(self):
        if self.running():
            self.job.requestInterruption()
            self.analysis_status.setText('Wird abgebrochen …')
            self.cancel_button.setEnabled(False)

    def _run(self, fn, on_done, status: QLabel):
        self.generation += 1
        generation = self.generation
        self.job = Job(fn, self)
        current = lambda: generation == self.generation   # noqa: E731
        self.job.progressed.connect(lambda i, text: current() and self._progress(i, text))
        self.job.done.connect(lambda value: current() and on_done(value))
        self.job.failed.connect(lambda text: current() and status.setText(text))
        self.job.stopped.connect(lambda: current() and status.setText('Abgebrochen. Nichts wurde gespeichert.'))
        self.job.finished.connect(self._finished)
        self.job.start()
        self.update_nav()

    def _progress(self, i, text):
        self.progress.setValue(i)
        self.analysis_status.setText(f'Schritt {i + 1} von {len(core.STEPS)}: {text} …')

    def _finished(self):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.update_nav()
        if self._pending_close:
            self._pending_close = False
            super().reject()

    def _reset_results(self):
        self.counts = self.report = self.shown_code = None
        if hasattr(self, 'preview'):
            self.preview.document().setPlainText('')
            self.consent_box.setChecked(False)

    # ------------------------------------------------------------------------------------------- results
    def show_results(self):
        if self.counts is None:
            return
        report = core.build_report(self.counts, self.line, self.reference, exact=True)
        s = core.summary(report)
        self.result_text.setText(
            f"Die Definition enthält {s['reference_2d']} Kennfelder (2D). Gefunden wurden {s['found_2d']} "
            f"Kandidaten, davon {s['exact_2d']} mit genau passender Lage und Größe.\n\n"
            'Trefferquote = Anteil der Kennfelder der Definition, die genau gefunden wurden. Eine Präzision '
            '(Anteil richtiger Kandidaten) lässt sich hier nicht berechnen: eine eigene Definition ist selten '
            f"vollständig. {s['not_evaluable_2d']} Kandidaten stehen nicht in der Definition und sind deshalb "
            'nicht bewertbar – sie sind nicht automatisch falsch.')
        self.bars.set_rows([('Trefferquote 2D', s['recall_2d']), ('Datentyp richtig (der Treffer)', s['type_2d']),
                            ('Achsen richtig', s['axes_2d']), ('Trefferquote 1D', s['recall_1d']),
                            ('Präzision', s['precision_2d'])])
        fn = report['function_identification']
        rows = [(k, v) for k, v in fn.items() if isinstance(v, dict)]
        self.function_table.setRowCount(len(rows))
        for r, (key, v) in enumerate(rows):
            mode, fraction = key.split('@')
            label = {'table': 'Kennfelder', 'block': 'Speicherblöcke', 'function': 'Funktionen'}[mode]
            values = (f'{float(fraction):.0%} {label}', v['correct'], v['wrong'], v['unknown'] + v['withheld'])
            for c, value in enumerate(values):
                self.function_table.setItem(r, c, QTableWidgetItem(str(value)))

    # -------------------------------------------------------------------------------------------- export
    def refresh_preview(self):
        if self.counts is None:
            return
        self.report = core.build_report(self.counts, self.line, self.reference, exact=self.exact_box.isChecked())
        core.check_private(self.report)
        self.shown_code = core.consent_code(self.report)
        # document(): the preview shows the file content byte for byte, never a translation of it
        self.preview.document().setPlainText(core.canonical(self.report))
        self.consent_box.setChecked(False)
        self.save_button.setEnabled(False)

    def save_report(self, target: str | None = None) -> bool:
        if self.report is None or not self.consent_box.isChecked():
            return False
        if not target:
            target, _ = QFileDialog.getSaveFileName(self, 'Bericht speichern', 'ecu-studio-testbericht.json',
                                                    'JSON (*.json)')
            if not target:
                return False
        try:
            # The code of what was shown: a report changed after the preview is refused.
            core.write_export(Path(target), self.report, self.shown_code)
        except core.TesterError as e:
            self.export_status.setText(str(e))
            return False
        self.saved.append(Path(target))
        self.export_status.setText('Gespeichert (nur Zählwerte). Ob und an wen du die Datei weitergibst, '
                                   'entscheidest du selbst.')
        return True

    def feedback(self) -> dict:
        rating = self.rating_group.checkedButton().property('rating') if self.rating_group.checkedButton() else None
        return core.feedback_report(rating, [b.property('topic') for b in self.topic_boxes if b.isChecked()])

    def refresh_feedback(self):
        if not hasattr(self, 'feedback_preview'):
            return
        self.feedback_preview.document().setPlainText(core.canonical(self.feedback()))
        self.feedback_consent.setChecked(False)

    def save_feedback(self, target: str | None = None) -> bool:
        if not self.feedback_consent.isChecked():
            return False
        if not target:
            target, _ = QFileDialog.getSaveFileName(self, 'Feedback speichern', 'ecu-studio-feedback.json',
                                                    'JSON (*.json)')
            if not target:
                return False
        content = self.feedback()
        try:
            core.write_export(Path(target), content, core.consent_code(content))
        except core.TesterError as e:
            QMessageBox.warning(self, 'Feedback nicht gespeichert', str(e))
            return False
        self.saved.append(Path(target))
        return True

    # ----------------------------------------------------------------------------------------- closing
    def reject(self):
        if self.running():
            # Close during the analysis: stop it, discard the result, close when the thread has ended.
            self._pending_close = True
            self.generation += 1
            self.job.requestInterruption()
            self.analysis_status.setText('Wird abgebrochen; das Fenster schließt danach …')
            return
        super().reject()

    def closeEvent(self, event):
        if self.running():
            event.ignore()
            self.reject()
            return
        super().closeEvent(event)


__all__ = ['TesterAssistant', 'ShareBars', 'Job']
