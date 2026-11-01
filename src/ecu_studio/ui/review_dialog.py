"""Review checklist dialog: detected maps in check order, with reasons; confirm or reject explicitly."""
from __future__ import annotations
import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)
from ..core.review_checklist import checklist, decision, latest, entry_key, table_key

COLUMNS = ('Priorität', 'Kennfeld', 'Adresse', 'Größe / Typ', 'Gründe', 'Verknüpfungen')


class ReviewDialog(QDialog):
    """Works on the main window's maps; decisions go to ``window.reviews`` (saved with the project)."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('Prüfliste der erkannten Kennfelder')
        self.resize(1250, 640)
        layout = QVBoxLayout(self)
        info = QLabel('Reihenfolge nach Prüfbedarf: Widersprüche zu Definitionen, unbelegter Datentyp, fehlende '
                      'Achsen und ungemessene Beweisarten zuerst. <b>Bestätigen</b> markiert das Kennfeld als von '
                      'dir geprüft (danach als lokale Referenz nutzbar), <b>Ablehnen</b> entfernt es und ein neuer '
                      'Scan bietet dieselbe Tabelle nicht erneut an (außer mit stärkerem Beleg). Entscheidungen '
                      'gelten nur für diese Datei, lassen sich unter <b>Entscheidungen …</b> zurücknehmen und werden '
                      'mit dem Projekt gespeichert, nicht hochgeladen und nicht automatisch zum Training verwendet.')
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setWordWrap(True)
        self.table.doubleClicked.connect(self.jump)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for text, slot in (('Anzeigen', self.jump), ('Bestätigen …', self.confirm), ('Ablehnen …', self.reject_map),
                           ('Entscheidungen …', self.show_decisions)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.count = QLabel()
        buttons.addWidget(self.count)
        layout.addLayout(buttons)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.close)
        layout.addWidget(close)
        self.reload()

    def reload(self):
        fusion = getattr(self.window, 'last_fusion', None) or {}
        self.items = checklist(self.window.maps, conflicts=fusion.get('conflicts'),
                               definition_warnings=fusion.get('definition_warnings'))
        # Columns are measured once after filling. A header left in ResizeToContents mode re-measures the
        # whole column on every setItem: quadratic, minutes for a few thousand detected maps.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            m = item.map
            values = (f'{item.priority} ({item.score:g})', m.name, f'0x{m.offset:X}',
                      f'{m.rows}×{m.cols} {m.dtype} {m.endian}', '\n'.join(item.reasons), '\n'.join(item.links) or '–')
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, cell)
        self.table.resizeColumnsToContents()
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.resizeRowsToContents()
        self.table.setUpdatesEnabled(True)
        decided = len(self.open_decisions())
        self.count.setText(f'{len(self.items)} offen · {decided} Entscheidungen im Projekt')

    def current(self):
        row = self.table.currentRow()
        return self.items[row].map if 0 <= row < len(self.items) else None

    def jump(self, *args):
        m = self.current()
        if m is not None:
            self.window.select_map(m)

    def confirm(self):
        m = self.current()
        if m is None:
            return
        if self.window.image.dirty_bytes:
            QMessageBox.warning(self, 'Original erforderlich', 'Bestätigen nur anhand der unveränderten Originaldatei.')
            return
        answer = QMessageBox.question(
            self, 'Kennfeld bestätigen',
            f'{m.name} @ 0x{m.offset:X} ({m.rows}×{m.cols} {m.dtype})\n\nLage, Größe, Datentyp und Achsen selbst '
            'geprüft (z. B. gegen Definition, Programmcode oder Messung)? Funktion, Einheit und Skalierung werden '
            'dadurch nicht bestätigt.')
        if answer != QMessageBox.StandardButton.Yes:
            return
        m.verified = True
        if self.NOTE not in m.notes:
            m.notes = (m.notes + ' ' + self.NOTE).strip()
        self.window.reviews.append(decision(m, 'bestätigt', image_sha256=self.window.image.digest))
        self.window.refresh_map_list()
        self.reload()

    def reject_map(self):
        m = self.current()
        if m is None:
            return
        reason, ok = QInputDialog.getText(self, 'Kennfeld ablehnen',
                                          f'{m.name} @ 0x{m.offset:X}\nGrund (optional, wird im Projekt gespeichert):')
        if not ok:
            return
        self.window.reviews.append(decision(m, 'abgelehnt', reason, image_sha256=self.window.image.digest))
        self.window.drop_map(m)
        self.reload()

    NOTE = 'Manuell geprüft (Prüfliste): Lage, Größe, Datentyp, Achsen.'

    def open_decisions(self) -> list[dict]:
        """Latest confirmation or rejection per table of this file (withdrawn ones left out)."""
        return [e for e in latest(getattr(self.window, 'reviews', []), self.window.image.digest).values()
                if e['decision'] != 'zurückgenommen']

    def show_decisions(self):
        entries = self.open_decisions()
        if not entries:
            QMessageBox.information(self, 'Entscheidungen', 'Für diese Datei liegen keine Entscheidungen vor.')
            return
        labels = [f"{e['decision']}: {e['name']} @ 0x{e['offset']:X} ({e['rows']}×{e['cols']} {e['dtype']})"
                  + (f" – {e['reason']}" if e.get('reason') else '') for e in entries]
        choice, ok = QInputDialog.getItem(self, 'Entscheidung zurücknehmen', 'Entscheidung auswählen:', labels, 0, False)
        if ok and choice in labels:
            self.withdraw(entries[labels.index(choice)])

    def withdraw(self, entry: dict):
        """Undo one decision: a confirmed map is unverified again; a rejected table is offered by the next scan."""
        key = entry_key(entry)
        if entry['decision'] == 'bestätigt':
            for m in self.window.maps:
                if m.verified and table_key(m) == key and m.name == entry['name'] and self.NOTE in m.notes:
                    m.verified = False
                    m.notes = m.notes.replace(self.NOTE, '').strip()
        withdrawn = dict(entry, decision='zurückgenommen', reason=f"{entry['decision']} zurückgenommen")
        withdrawn['at'] = datetime.datetime.now().isoformat(timespec='seconds')
        self.window.reviews.append(withdrawn)
        self.window.refresh_map_list()
        self.reload()
        if entry['decision'] == 'abgelehnt':
            QMessageBox.information(self, 'Ablehnung zurückgenommen',
                                    f"{entry['name']} @ 0x{entry['offset']:X}: der nächste Kennfeldscan bietet "
                                    'diese Tabelle wieder an.')
