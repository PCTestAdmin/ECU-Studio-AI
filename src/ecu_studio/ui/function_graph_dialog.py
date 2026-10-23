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
        routines.setExpanded(True)
        axes.setExpanded(not graph['groups'])
        self.tree.itemDoubleClicked.connect(self._open)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_members(self, parent, members):
        for i in members:
            m = self.maps[i]
            item = QTreeWidgetItem(parent, [m.name, f'0x{m.offset:08X}', f'{m.rows}×{m.cols} {m.dtype}'])
            item.setData(0, Qt.ItemDataRole.UserRole, i)

    def _open(self, item, _column):
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.on_select(self.maps[index])
