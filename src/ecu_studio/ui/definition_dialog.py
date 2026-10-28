"""Guided dialog: review and edit one map definition with validation and preview.

"Prüfen" builds a validated proposal (core/definition_edit) and shows the
changes, warnings and the resulting values; "Übernehmen" is only enabled for
the proposal that was checked last and asks for an explicit confirmation. Any
edit after checking disables it again. The firmware bytes are never written.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from ..core.definition_edit import AxisSpec, preview_values, propose
from ..core.model import FORMATS

PREVIEW_LIMIT = 32


def _offset(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    return int(text, 16) if text.lower().startswith('0x') else int(text)


class DefinitionDialog(QDialog):
    def __init__(self, image, definition, parent=None):
        super().__init__(parent)
        self.image, self.definition = image, definition
        self.proposal = None
        self.setWindowTitle(f'Kennfelddefinition bearbeiten / prüfen – {definition.name}')
        self.resize(1080, 720)
        m = definition
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        form = QFormLayout()
        self.name = QLineEdit(m.name)
        self.notes = QPlainTextEdit(m.notes); self.notes.setMaximumHeight(70)
        self.offset = QLineEdit(f'0x{m.offset:X}')
        self.rows = QSpinBox(); self.rows.setRange(1, 512); self.rows.setValue(m.rows)
        self.cols = QSpinBox(); self.cols.setRange(1, 512); self.cols.setValue(m.cols)
        self.dtype = QComboBox(); self.dtype.addItems(list(FORMATS)); self.dtype.setCurrentText(m.dtype)
        self.endian = QComboBox(); self.endian.addItems(['big', 'little']); self.endian.setCurrentText(m.endian)
        self.factor = QDoubleSpinBox(); self.factor.setDecimals(8); self.factor.setRange(-1e9, 1e9); self.factor.setValue(m.factor)
        self.bias = QDoubleSpinBox(); self.bias.setDecimals(6); self.bias.setRange(-1e9, 1e9); self.bias.setValue(m.bias)
        self.unit = QLineEdit(m.unit)
        self.verified = QCheckBox('Fachlich geprüft (nur nach eigener Prüfung setzen)')
        self.verified.setChecked(m.verified)
        for label, widget in (('Name', self.name), ('Beschreibung', self.notes), ('Adresse (Dateioffset)', self.offset),
                              ('Zeilen', self.rows), ('Spalten', self.cols), ('Datentyp', self.dtype),
                              ('Byte-Reihenfolge', self.endian), ('Faktor', self.factor), ('Offset', self.bias),
                              ('Einheit', self.unit), ('Prüfstatus', self.verified)):
            form.addRow(label, widget)
        if m.equation:
            form.addRow('Formel', QLabel(f'{m.equation} (aus der Definition, schreibgeschützt)'))
        left.addLayout(form)
        self.axis_x = self._axis_box('X-Achse (Spalten)', m.axis_x_offset, m.axis_x_unit, m.dtype, m.endian)
        self.axis_y = self._axis_box('Y-Achse (Zeilen)', m.axis_y_offset, m.axis_y_unit, m.dtype, m.endian)
        left.addWidget(self.axis_x['box']); left.addWidget(self.axis_y['box'])
        left.addStretch()
        layout.addLayout(left, 2)
        right = QVBoxLayout()
        self.result = QLabel('Änderungen eintragen und „Prüfen“ wählen. Die BIN-Datei wird nicht verändert.')
        self.result.setWordWrap(True)
        right.addWidget(self.result)
        self.table = QTableWidget()
        right.addWidget(self.table, 1)
        buttons = QDialogButtonBox()
        self.check_button = QPushButton('Prüfen')
        self.apply_button = QPushButton('Übernehmen …')
        self.apply_button.setEnabled(False)
        buttons.addButton(self.check_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.apply_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.check_button.clicked.connect(self.check)
        self.apply_button.clicked.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        layout.addLayout(right, 3)
        for widget in (self.name, self.offset, self.unit, self.axis_x['offset'], self.axis_y['offset'],
                       self.axis_x['unit'], self.axis_y['unit']):
            widget.textChanged.connect(self._invalidate)
        self.notes.textChanged.connect(self._invalidate)
        for widget in (self.rows, self.cols, self.factor, self.bias, self.axis_x['factor'], self.axis_y['factor']):
            widget.valueChanged.connect(self._invalidate)
        for widget in (self.dtype, self.endian, self.axis_x['dtype'], self.axis_y['dtype'],
                       self.axis_x['endian'], self.axis_y['endian']):
            widget.currentIndexChanged.connect(self._invalidate)
        self.verified.toggled.connect(self._invalidate)
        self.check()

    def _axis_box(self, title, offset, unit, dtype, endian):
        box = QGroupBox(title)
        form = QFormLayout(box)
        w = {'box': box, 'offset': QLineEdit('' if offset is None else f'0x{offset:X}'),
             'dtype': QComboBox(), 'endian': QComboBox(), 'factor': QDoubleSpinBox(), 'unit': QLineEdit(unit)}
        w['offset'].setPlaceholderText('leer = Werte unverändert lassen')
        w['dtype'].addItems(list(FORMATS)); w['dtype'].setCurrentText(dtype)
        w['endian'].addItems(['big', 'little']); w['endian'].setCurrentText(endian)
        w['factor'].setDecimals(8); w['factor'].setRange(-1e9, 1e9); w['factor'].setValue(1.0)
        for label, key in (('Adresse', 'offset'), ('Datentyp', 'dtype'), ('Byte-Reihenfolge', 'endian'),
                           ('Faktor', 'factor'), ('Einheit', 'unit')):
            form.addRow(label, w[key])
        # Axis values are only re-read when the user changes how the axis is read:
        # the app does not know the stored type/scaling of an imported axis, and
        # re-reading it with default settings would silently replace correct values.
        w['touched'] = False
        def touch(*_):
            w['touched'] = True
        w['offset'].textChanged.connect(touch)
        for key in ('dtype', 'endian'):
            w[key].currentIndexChanged.connect(touch)
        w['factor'].valueChanged.connect(touch)
        return w

    def _axis_spec(self, w):
        if not w['touched']:
            return None
        offset = _offset(w['offset'].text())
        if offset is None:
            return None
        return AxisSpec(offset, w['dtype'].currentText(), w['endian'].currentText(), w['factor'].value())

    def fields(self) -> dict:
        return {'name': self.name.text(), 'notes': self.notes.toPlainText(), 'offset': _offset(self.offset.text()),
                'rows': self.rows.value(), 'cols': self.cols.value(), 'dtype': self.dtype.currentText(),
                'endian': self.endian.currentText(), 'factor': self.factor.value(), 'bias': self.bias.value(),
                'unit': self.unit.text(), 'axis_x_unit': self.axis_x['unit'].text(),
                'axis_y_unit': self.axis_y['unit'].text(), 'verified': self.verified.isChecked()}

    def _invalidate(self, *_):
        self.proposal = None
        self.apply_button.setEnabled(False)

    def check(self) -> bool:
        self._invalidate()
        try:
            if _offset(self.offset.text()) is None:
                raise ValueError('Adresse fehlt')
            proposal = propose(self.image, self.definition, self.fields(),
                               axis_x=self._axis_spec(self.axis_x), axis_y=self._axis_spec(self.axis_y))
        except ValueError as exc:
            self.result.setText(f'<b>Nicht übernehmbar:</b> {exc}')
            self.table.clear(); self.table.setRowCount(0); self.table.setColumnCount(0)
            return False
        self.proposal = proposal
        self._show_preview(proposal.proposed)
        changes = proposal.changes
        lines = [f'<b>{len(changes)} Änderung(en)</b>' if changes else '<b>Keine Änderung</b>']
        lines += [f'• {key}: {before!r} → {after!r}' for key, (before, after) in list(changes.items())[:12]]
        lines += [f'⚠ {w}' for w in proposal.warnings]
        shown = min(proposal.proposed.rows, PREVIEW_LIMIT), min(proposal.proposed.cols, PREVIEW_LIMIT)
        lines.append(f'Vorschau: {shown[0]} × {shown[1]} Zellen aus den aktuellen Dateibytes.')
        self.result.setText('<br>'.join(lines))
        self.apply_button.setEnabled(bool(changes))
        return True

    def _show_preview(self, m):
        values = preview_values(self.image, m, PREVIEW_LIMIT)
        self.table.clear()
        self.table.setRowCount(len(values)); self.table.setColumnCount(len(values[0]) if values else 0)
        if m.axes_x and len(m.axes_x) == m.cols:
            self.table.setHorizontalHeaderLabels([f'{v:g}' for v in m.axes_x[:PREVIEW_LIMIT]])
        if m.axes_y and len(m.axes_y) == m.rows:
            self.table.setVerticalHeaderLabels([f'{v:g}' for v in m.axes_y[:PREVIEW_LIMIT]])
        for r, row in enumerate(values):
            for c, v in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(f'{v:.6g}'))
        self.table.resizeColumnsToContents()

    def confirm(self):
        if self.proposal is None or not self.check():
            return
        text = '\n'.join(f'{key}: {before!r} → {after!r}' for key, (before, after) in self.proposal.changes.items())
        answer = QMessageBox.question(self, 'Definition übernehmen',
                                      'Diese Änderungen an der Definition übernehmen?\n\n' + text[:1500] +
                                      '\n\nDie BIN-Datei bleibt unverändert; Rückgängig ist möglich.')
        if answer == QMessageBox.StandardButton.Yes:
            self.accept()
