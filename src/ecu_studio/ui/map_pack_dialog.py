"""Preview and review for the existing map-pack import/export commands."""
from pathlib import Path
import json

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QDialog)
from ..core.map_pack import make_pack, write_pack, read_pack, preview_pack, apply_pack, source_for_comparison
from ..core.model import BinaryImage
from .next_dialogs import AsyncDialog, table


class MapPackDialog(AsyncDialog):
    def __init__(self, window, path):
        super().__init__(window, 'Kennfeldpaket · Inhalt und Übernahme')
        self.window, self.pack, self.preview = window, None, None
        self.path = path
        self.info = QLabel('Paket wird geprüft …'); self.info.setWordWrap(True)
        self.layout_.addWidget(self.info)
        self.view, self.model = table(['Kennfeld', 'Offset', 'Format', 'Quelle', 'Achsen', 'Status'])
        self.layout_.addWidget(self.view, 1)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMaximumHeight(150)
        self.layout_.addWidget(self.details)
        buttons = QHBoxLayout()
        self.adopt = QPushButton('Definitionen ausdrücklich übernehmen'); self.adopt.setEnabled(False)
        self.adopt.clicked.connect(self.apply)
        self.compare = QPushButton('Mit lokalem Quellstand vergleichen …'); self.compare.setEnabled(False)
        self.compare.clicked.connect(self.compare_source)
        self.remember = QPushButton('Paket lokal merken'); self.remember.setEnabled(False)
        self.remember.clicked.connect(self.index_pack)
        for b in (self.adopt, self.compare, self.remember): buttons.addWidget(b)
        close = QPushButton('Schließen'); close.clicked.connect(self.reject); buttons.addWidget(close)
        self.layout_.addLayout(buttons)
        self.run_task(lambda: read_pack(path), self.loaded)

    def loaded(self, pack):
        self.pack = pack
        self.remember.setEnabled(True)
        axes = lambda m: ' / '.join(f'{axis} 0x{at:X}' for axis, at in (('X', m.axis_x_offset), ('Y', m.axis_y_offset)) if at is not None)
        self.model.set_rows([(m.name, f'0x{m.offset:X}', f'{m.rows}×{m.cols} {m.dtype} {m.endian}',
                              m.source, axes(m), 'Bestätigt laut Autor' if m.verified else 'Ungeprüfte Paketangabe') for m in pack.maps()])
        meta = {k: v for k, v in pack.document.items() if k not in ('maps', 'axis_groups')}
        self.details.setPlainText(json.dumps(meta, indent=2, ensure_ascii=False))
        try:
            self.preview = preview_pack(pack, self.window.image, self.window.maps)
            self.adopt.setEnabled(not self.preview.conflicts)
            self.info.setText(f'{len(pack.document["maps"])} Definitionen · Original-Hash passt. '
                              'Die Übernahme bleibt ungeprüft und ändert keine BIN-Bytes.')
            if self.preview.conflicts:
                self.details.appendPlainText('\n' + '\n'.join(self.preview.conflicts[:50]))
        except ValueError as exc:
            self.info.setText('Keine direkte Übernahme möglich. Für verwandte Softwarestände den lokalen Quellstand wählen.')
            self.details.appendPlainText(str(exc))
            self.compare.setEnabled(pack.sha256 != self.window.image.digest and not pack.unknown_fields)

    def index_pack(self):
        try:
            self.window.project_store.index_pack(self.path)
            self.window.update_local_suggestions()
            self.remember.setEnabled(False)
        except Exception as exc:
            self.error(exc)

    def apply(self):
        if not self.preview:
            return
        answer = QMessageBox.question(self, 'Paketübernahme bestätigen',
                    'Definitionen ungeprüft übernehmen und einen Projektversionsstand anlegen? Mit Strg+Z rückgängig.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            apply_pack(self.window.image, self.window.maps, self.preview, confirmed=True, snapshots=self.window.snapshots)
            self.window.on_edited()
            self.accept()
        except Exception as exc:
            self.adopt.setEnabled(False)
            self.error(exc)

    def compare_source(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Original-BIN des Pakets wählen', '', 'BIN (*.bin *.ori)')
        if not path:
            return
        def load():
            source = BinaryImage.from_file(path)
            maps = source_for_comparison(self.pack, source)
            return source, maps, 'Kennfeldpaket ' + self.pack.sha256
        self.run_task(load, self.source_loaded)

    def source_loaded(self, loaded):
        from .version_compare_dialog import VersionCompareDialog
        dialog = VersionCompareDialog(self.window)
        dialog.source_loaded(loaded)
        dialog.exec()
        self.loaded(self.pack)


def export_dialog(window):
    dialog = QDialog(window); dialog.setWindowTitle('Kennfeldpaket exportieren')
    layout = QVBoxLayout(dialog)
    hint = QLabel('Nur Definitionen und erkannte ECU-Kennungen. Keine BIN-Bytes, Notizen oder lokalen Dateipfade. '
                  'Kennfeldnamen und Einheiten vor der Weitergabe prüfen.'); hint.setWordWrap(True)
    layout.addWidget(hint)
    mode = QComboBox(); mode.addItems(['Alle Definitionen', 'Nur bestätigte Definitionen', 'Ausgewählte Kennfelder'])
    layout.addWidget(mode)
    axes = QCheckBox('Gespeicherte Achsadressen und Gruppen einschließen'); axes.setChecked(True)
    layout.addWidget(axes)
    annotations = QCheckBox('Beschreibungen und Belege ausdrücklich einschließen (auf private Angaben prüfen)')
    layout.addWidget(annotations)
    view, model = table(['Kennfeld', 'Offset', 'Format', 'Geprüft']); layout.addWidget(view)
    def chosen():
        if mode.currentIndex() == 1:
            return [m for m in window.maps if m.verified]
        if mode.currentIndex() == 2:
            indices = window.map_list.selectionModel().selectedRows()
            from PySide6.QtCore import Qt
            return [window.maps[i.data(Qt.ItemDataRole.UserRole)] for i in indices]
        return list(window.maps)
    def refresh():
        model.set_rows([(m.name, f'0x{m.offset:X}', f'{m.rows}×{m.cols} {m.dtype}', m.verified) for m in chosen()])
    mode.currentIndexChanged.connect(refresh); refresh()
    def save():
        try:
            pack = make_pack(window.image, chosen(), include_axes=axes.isChecked(), include_annotations=annotations.isChecked())
            path, _ = window.save_destination(dialog, 'Kennfeldpaket speichern', 'maps.ecupack.json', 'JSON (*.json)')
            if path:
                protected = [window.image.path, window.project_path]
                write_pack(path, pack, protected=protected)
                window.project_store.index_pack(path)
                window.update_local_suggestions()
                dialog.accept()
        except Exception as exc:
            QMessageBox.warning(dialog, 'Paketexport fehlgeschlagen', str(exc))
    buttons = QHBoxLayout(); save_button = QPushButton('Paket speichern …'); save_button.clicked.connect(save)
    close = QPushButton('Abbrechen'); close.clicked.connect(dialog.reject)
    buttons.addWidget(save_button); buttons.addWidget(close); layout.addLayout(buttons)
    dialog.resize(850, 560)
    return dialog.exec()
