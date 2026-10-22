"""Help dialog: ECU support matrix with status, measured software versions and limits."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)
from ..core.support import STATUSES, load

STATUS_MARK = {'validiert': '✅ validiert', 'teilweise': '🟡 teilweise', 'experimentell': '🧪 experimentell',
               'nicht validiert': '⚪ nicht validiert'}
COLUMNS = ('Steuergerät', 'Prozessor', 'Status', 'Gemessene Softwarestände', 'Erkennung (gemessen)', 'Grenzen / benötigt')


def _quality(entry) -> str:
    parts = []
    for s in entry.software:
        if s.get('no_reference'):
            parts.append(f"{s['name']}: {s['found_2d']} Kandidaten, ohne Referenz nicht bewertbar")
            continue
        text = f"{s['name']}: {s['exact_2d']}/{s['reference_2d']} exakt"
        if s.get('precision_2d') is not None:
            text += f", Präzision {s['precision_2d']:.0%}"
        if s['role'] == 'test':
            text += ' (Test)'
        parts.append(text)
    return '\n'.join(parts) or 'nicht gemessen'


def build_table(entries) -> QTableWidget:
    table = QTableWidget(len(entries), len(COLUMNS))
    table.setHorizontalHeaderLabels(COLUMNS)
    for row, e in enumerate(entries):
        limits = e.limits + (('\nBenötigt: ' + e.needed) if e.needed else '')
        values = (e.family, e.processor, STATUS_MARK.get(e.status, e.status),
                  '\n'.join(s['name'] for s in e.software) or '–', _quality(e), limits.strip() or '–')
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, col, item)
    table.setWordWrap(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Stretch)
    table.resizeRowsToContents()
    return table


class SupportDialog(QDialog):
    def __init__(self, parent=None, current: str | None = None):
        super().__init__(parent)
        self.setWindowTitle('Unterstützte Steuergeräte')
        self.resize(1200, 640)
        layout = QVBoxLayout(self)
        legend = ' · '.join(f'<b>{STATUS_MARK[k]}</b>: {v}' for k, v in STATUSES.items())
        info = QLabel(('<p>' + (f'Geladene Datei: <b>{current}</b></p><p>' if current else '') + legend +
                       '</p><p>Messwerte: exakt erkannte 2D-Kennfelder (Start, Größe, Zellbreite) gegen die '
                       'Referenz. Präzision nur bei vollständiger Referenz. „Test“ = nie zum Einstellen '
                       'verwendet. Kein Ergebnis ist eine Flashfreigabe.</p>'))
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = build_table(load())
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
