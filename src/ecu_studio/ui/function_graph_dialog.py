"""Dialog: map groups by consuming code routine and by shared axes."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QDialogButtonBox


class FunctionGraphDialog(QDialog):
    def __init__(self, parent, maps, graph, on_select):
        super().__init__(parent)
        self.setWindowTitle('Funktionsgraph – zusammengehörige Kennfelder')
        self.resize(760, 620)
        self.maps, self.on_select = maps, on_select
        layout = QVBoxLayout(self)
        info = QLabel(f"{graph['referenced']} Kennfelder werden im Programmcode referenziert. "
                      'Gruppen = von derselben Routine gelesen (Routinen-Grenzen aus Rücksprungbefehlen, '
                      'strukturelle Näherung) oder dieselbe gespeicherte Achse (gleiche Adresse). '
                      'Doppelklick öffnet das Kennfeld.')
        info.setWordWrap(True)
        info.setObjectName('hint')
        layout.addWidget(info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Gruppe / Kennfeld', 'Adresse', 'Größe'])
        self.tree.setColumnWidth(0, 470)
        layout.addWidget(self.tree, 1)
        routines = QTreeWidgetItem(self.tree, [f"Gleiche Routine ({len(graph['groups'])} Gruppen)"])
        for g in graph['groups']:
            node = QTreeWidgetItem(routines, [f'Routine 0x{g.routine_start:06X} · {g.size} Kennfelder', '', ''])
            self._add_members(node, g.members)
        axes = QTreeWidgetItem(self.tree, [f"Gemeinsame gespeicherte Achse ({len(graph['shared_axes'])} Gruppen)"])
        for g in graph['shared_axes']:
            status = ('unsicher' if g.uncertain else
                      'aus Definition' if g.evidence == 'definition' else 'strukturell, ungeprüft')
            name = f'{g.reference} · ' if g.reference else ''
            node = QTreeWidgetItem(axes, [f'{name}{g.points} Punkte · {len(g.indices)} Kennfelder · {status}',
                                          f'0x{g.axis_offset:08X}', ''])
            node.setToolTip(0, g.describe())
            self._add_members(node, g.indices)
        hints = QTreeWidgetItem(self.tree, [f"Gleiche Achswerte, andere Adresse – Hypothese ({len(graph['axis_hints'])})"])
        hints.setToolTip(0, 'Gleiche Stützstellenwerte belegen keine Zusammengehörigkeit; nur ein Hinweis zur Prüfung.')
        for members in graph['axis_hints']:
            self._add_members(QTreeWidgetItem(hints, [f'{len(members)} Kennfelder', '', '']), members)
        self._add_functions(graph)
        routines.setExpanded(True)
        axes.setExpanded(not graph['groups'])
        self.tree.itemDoubleClicked.connect(self._open)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_functions(self, graph):
        """Function membership per table (core/function_id): only from definitions and relations to tables
        with a known function; a hypothesis never names a function nobody declared."""
        from ..core.function_id import STATUSES, UNKNOWN, counts, identify
        hyps = identify(self.maps, graph=graph)
        n = counts(hyps)
        top = QTreeWidgetItem(self.tree, ['Funktionszuordnung (' + ' · '.join(f'{s} {n[s]}' for s in STATUSES) + ')'])
        top.setToolTip(0, 'Funktionen nur aus Definitionen (A2L FUNCTION) oder über Beziehungen zu Kennfeldern mit '
                          'bekannter Funktion (gemeinsame Achse, gleiche Routine, direkter Nachbar). Keine Namen aus Werten.')
        for status in STATUSES:
            chosen = [h for h in hyps if h.status == status and (status != UNKNOWN or h.contradictions)]
            if not chosen:
                continue
            label = (f'{status}: {len(chosen)} Kennfelder' if status != UNKNOWN else
                     f'Widersprüchlich (Unbekannt): {len(chosen)} Kennfelder')
            node = QTreeWidgetItem(top, [label, '', ''])
            for h in chosen[:500]:
                m = self.maps[h.index]
                item = QTreeWidgetItem(node, [f'{m.name} → {h.function or "?"}', f'0x{m.offset:08X}',
                                              f'{m.rows}×{m.cols} {m.dtype}'])
                item.setToolTip(0, h.describe())
                item.setData(0, Qt.ItemDataRole.UserRole, h.index)
            if len(chosen) > 500:
                QTreeWidgetItem(node, [f'… {len(chosen) - 500} weitere', '', ''])

    def _add_members(self, parent, members):
        for i in members:
            m = self.maps[i]
            item = QTreeWidgetItem(parent, [m.name, f'0x{m.offset:08X}', f'{m.rows}×{m.cols} {m.dtype}'])
            item.setData(0, Qt.ItemDataRole.UserRole, i)

    def _open(self, item, _column):
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.on_select(self.maps[index])
