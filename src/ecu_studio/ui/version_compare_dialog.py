"""Two software versions: matched maps, side-by-side values, controlled adoption as a project version."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)
from ..core.model import BinaryImage, MapDefinition, load_project
from ..core.name_transfer import MEASURED, definition_maps
from ..core.version_compare import CLASSES, FILTERS, adopt_definitions, compare_versions, filter_pairs
from ..core.versioning import make_snapshot
from .next_dialogs import AsyncDialog

COLUMNS = ('Übernehmen', 'Kennfeld', 'Stand A', 'Stand B', 'Verschiebung', 'Zuordnung', 'Beleg',
           'Geänderte Zellen', 'Max. Δ physisch', 'Max. Δ %', 'Achsen', 'Hinweis')
CLASS_COLORS = {'exakt': '#2EA043', 'strukturell': '#2EA043', 'wahrscheinlich': '#D29922',
                'mehrdeutig': '#CF222E', 'nicht zuordenbar': '#6E7681'}


def load_source(path: str, definition: str | None = None) -> tuple[BinaryImage, list[MapDefinition], str]:
    """A project (definitions inside) or a BIN with its XDF/A2L/CSV definition."""
    if Path(path).suffix.lower() == '.ecustudio':
        image, maps, _, _ = load_project(path, ignored_fields=set())   # read only: nothing is saved back
        return image, [m for m in maps if m.rows * m.cols >= 2], Path(path).stem
    if not definition:
        raise ValueError('Für eine BIN wird die Definition des Stands benötigt')
    image = BinaryImage.from_file(path)
    return image, definition_maps(definition, image), Path(path).stem


class VersionCompareDialog(AsyncDialog):
    """Stand A (with definitions) against the open file (Stand B)."""

    def __init__(self, window):
        super().__init__(window, 'Softwarestände vergleichen · Kennfelder zuordnen und übernehmen')
        self.window = window
        self.source = self.source_maps = None
        self.source_label = ''
        self.result = None
        self.shown = []
        intro = QLabel('Stand A bringt Definitionen mit (Projekt oder BIN + XDF/A2L), Stand B ist die geöffnete Datei. '
                       'Zugeordnet wird über Anker, die in beiden Dateien genau einmal vorkommen; eine gleiche Adresse '
                       'allein ist kein Beleg. Übernommen werden nur Definitionen – die BIN bleibt unverändert.')
        intro.setWordWrap(True)
        intro.setObjectName('hint')
        self.layout_.addWidget(intro)
        line = QHBoxLayout()
        load = QPushButton('Stand A laden …')
        load.clicked.connect(self.choose_source)
        line.addWidget(load)
        self.source_info = QLabel('Stand A: nicht gewählt')
        line.addWidget(self.source_info, 1)
        line.addWidget(QLabel('Filter'))
        self.filter = QComboBox()
        self.filter.addItems(FILTERS)
        self.filter.currentIndexChanged.connect(self.show_pairs)
        line.addWidget(self.filter)
        self.layout_.addLayout(line)
        self.summary = QLabel('')
        self.summary.setWordWrap(True)
        self.layout_.addWidget(self.summary)
        self.tabs = QTabWidget()
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_values)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_target())
        pairs_page = QSplitter(Qt.Orientation.Vertical)
        pairs_page.addWidget(self.table)
        values = QWidget()
        values_layout = QVBoxLayout(values)
        self.value_caption = QLabel('Kennfeld wählen: Werte von Stand A und Stand B nebeneinander (physikalisch). '
                                    'Rot = in B höher, Blau = in B niedriger.')
        self.value_caption.setWordWrap(True)
        values_layout.addWidget(self.value_caption)
        sides = QHBoxLayout()
        self.view_a, self.view_b = QTableWidget(), QTableWidget()
        for view in (self.view_a, self.view_b):
            view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            sides.addWidget(view)
        # Synchronized: scrolling or selecting a cell on one side follows on the other.
        for a, b in ((self.view_a, self.view_b), (self.view_b, self.view_a)):
            a.verticalScrollBar().valueChanged.connect(b.verticalScrollBar().setValue)
            a.horizontalScrollBar().valueChanged.connect(b.horizontalScrollBar().setValue)
            a.currentCellChanged.connect(lambda r, c, *_, other=b: other.setCurrentCell(r, c)
                                         if (other.currentRow(), other.currentColumn()) != (r, c) else None)
        values_layout.addLayout(sides)
        pairs_page.addWidget(values)
        self.tabs.addTab(pairs_page, 'Zuordnung')
        self.only_b = QTableWidget(0, 4)
        self.only_b.setHorizontalHeaderLabels(('Kennfeld', 'Offset', 'Größe', 'Herkunft'))
        self.only_b.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.only_b.cellDoubleClicked.connect(self.open_only_b)
        self.tabs.addTab(self.only_b, 'Nur in Stand B')
        self.layout_.addWidget(self.tabs, 1)
        buttons = QHBoxLayout()
        self.confirm_probable = QCheckBox('Auch „wahrscheinlich“ zugeordnete übernehmen (ausdrücklich bestätigt)')
        buttons.addWidget(self.confirm_probable)
        buttons.addStretch()
        for title, method in (('Alle eindeutigen markieren', self.mark_unique), ('In Stand B öffnen', self.open_target),
                              ('Markierte übernehmen …', self.adopt), ('Schließen', self.reject)):
            button = QPushButton(title)
            button.clicked.connect(method)
            buttons.addWidget(button)
        self.layout_.addLayout(buttons)

    # -- loading and comparing -------------------------------------------------
    def choose_source(self):
        if self.worker and self.worker.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Stand A: Projekt oder BIN mit Definition', str(Path.home()),
                                              'Projekt oder Firmware (*.ecustudio *.bin *.ori);;Alle Dateien (*)')
        if not path:
            return
        definition = None
        if Path(path).suffix.lower() != '.ecustudio':
            definition, _ = QFileDialog.getOpenFileName(self, 'Definition von Stand A', str(Path(path).parent),
                                                        'Definitionen (*.xdf *.a2l *.xml *.csv);;Alle Dateien (*)')
            if not definition:
                return
        self.run_task(lambda: load_source(path, definition), self.source_loaded)

    def source_loaded(self, loaded):
        self.source, self.source_maps, self.source_label = loaded
        self.source_info.setText(f'Stand A: {self.source_label} · {len(self.source_maps)} Definitionen · '
                                 f'SHA-256 {self.source.digest[:12]}')
        self.compare()

    def compare(self):
        if self.source is None:
            return
        source, maps, target = self.source, list(self.source_maps), self.window.image
        existing = list(self.window.maps)
        self.task_generation += 1
        self.run_task(lambda: compare_versions(source, maps, target, existing,
                                               cancelled=lambda: QThread.currentThread().isInterruptionRequested()),
                      self.compared)

    def compared(self, result):
        self.result = result
        counts = result['counts']
        rates = ', '.join(f'{e} {r}' for e, r in MEASURED.items())
        self.summary.setText(' · '.join(f'{c}: {counts[c]}' for c in CLASSES) +
                             f" · nur in Stand B: {len(result['target_only'])}\n"
                             f'Gemessene Trefferquoten der Belegarten (Schwesterstände): {rates}.')
        self.show_pairs()
        self.only_b.setRowCount(len(result['target_only']))
        for row, j in enumerate(result['target_only']):
            m = self.window.maps[j]
            for col, value in enumerate((m.name, f'0x{m.offset:08X}', f'{m.rows}×{m.cols} {m.dtype}', m.source)):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, j)
                self.only_b.setItem(row, col, item)
        self.tabs.setTabText(1, f"Nur in Stand B ({len(result['target_only'])})")

    def show_pairs(self, *_):
        if not self.result:
            return
        self.shown = filter_pairs(self.result['pairs'], self.filter.currentText())
        self.table.setRowCount(len(self.shown))
        for row, p in enumerate(self.shown):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled if p.adoptable
                           else Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            values = (p.source.name, f'0x{p.source.offset:08X}',
                      f'0x{p.target.offset:08X}' if p.target else '–',
                      f'{p.shift:+d}' if p.shift is not None else '–', p.match, p.evidence,
                      f'{p.changed_cells}/{p.total_cells}' if p.target else '–',
                      f'{p.max_abs_physical:g}' if p.target else '–',
                      f'{p.max_relative_percent:g}' if p.max_relative_percent is not None else '–',
                      p.axes, p.conflict)
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                if col == 5:
                    item.setForeground(QColor(CLASS_COLORS[p.match]))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def current_pair(self):
        row = self.table.currentRow()
        return self.shown[row] if 0 <= row < len(self.shown) else None

    def show_values(self):
        p = self.current_pair()
        for view in (self.view_a, self.view_b):
            view.clear()
            view.setRowCount(0)
        if p is None or p.target is None:
            return
        try:
            a = BinaryImage(self.source.original).matrix(p.source, physical=True)
            b = BinaryImage(self.window.image.original).matrix(p.target, physical=True)
        except (ValueError, IndexError) as exc:
            self.value_caption.setText(f'Werte nicht lesbar: {exc}')
            return
        delta = b - a
        peak = float(np.max(np.abs(delta))) or 1.
        for view, values, label in ((self.view_a, a, 'A'), (self.view_b, b, 'B')):
            view.setRowCount(values.shape[0])
            view.setColumnCount(values.shape[1])
            for r in range(values.shape[0]):
                for c in range(values.shape[1]):
                    item = QTableWidgetItem(f'{float(values[r, c]):g}')
                    d = float(delta[r, c])
                    if d and label == 'B':
                        k = int(200 * abs(d) / peak)
                        item.setBackground(QColor(255, 255 - k, 255 - k) if d > 0 else QColor(255 - k, 255 - k, 255))
                    item.setToolTip(f'A {float(a[r, c]):g} · B {float(b[r, c]):g} · Δ {d:+g}')
                    view.setItem(r, c, item)
            view.resizeColumnsToContents()
        self.value_caption.setText(f'{p.source.name}: Stand A @ 0x{p.source.offset:X} · Stand B @ 0x{p.target.offset:X} · '
                                   f'{p.changed_cells} von {p.total_cells} Zellen verschieden ({p.match}). '
                                   'Rot = in B höher, Blau = in B niedriger.')

    # -- adoption ---------------------------------------------------------------
    def marked(self):
        return [self.shown[r] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]

    def mark_unique(self):
        for row, p in enumerate(self.shown):
            if p.adoptable and not p.needs_confirmation:
                self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def adopt(self):
        pairs = self.marked()
        if not pairs:
            self.error('Zuerst Kennfelder in der Spalte „Übernehmen“ markieren')
            return
        try:
            added, protocol = adopt_definitions(pairs, self.window.maps, source_label=self.source_label,
                                                confirm_probable=self.confirm_probable.isChecked())
        except ValueError as exc:
            self.error(exc)
            return
        if not added:
            QMessageBox.information(self, 'Nichts zu übernehmen', 'Alle markierten Definitionen sind in Stand B schon vorhanden.')
            return
        lines = '\n'.join(f'  {e["name"]}: 0x{e["source_offset"]:X} → 0x{e["target_offset"]:X} ({e["match"]})'
                          for e in protocol[:25])
        more = f'\n  … {len(protocol) - 25} weitere' if len(protocol) > 25 else ''
        answer = QMessageBox.question(
            self, 'Definitionen übernehmen',
            f'{len(added)} Definitionen werden als UNGEPRÜFTE Vorschläge zu Stand B hinzugefügt:\n{lines}{more}\n\n'
            'Die BIN wird nicht verändert. Danach wird ein Versionsstand mit diesen Definitionen angelegt.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.window.apply_adopted_definitions(added, protocol, self.source_label)
        self.compare()

    def open_target(self):
        p = self.current_pair()
        if p is None or p.target is None:
            return
        match = next((m for m in self.window.maps if (m.offset, m.rows, m.cols, m.dtype) ==
                      (p.target.offset, p.target.rows, p.target.cols, p.target.dtype)), None)
        if match is None:
            self.window.jump(p.target.offset)
        else:
            self.window.select_map(match)

    def open_only_b(self, row, _col):
        item = self.only_b.item(row, 0)
        if item is not None:
            self.window.select_map(self.window.maps[item.data(Qt.ItemDataRole.UserRole)])
