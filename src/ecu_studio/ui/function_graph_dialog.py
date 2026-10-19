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
                      'strukturelle Näherung). Doppelklick öffnet das Kennfeld.')
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
        axes = QTreeWidgetItem(self.tree, [f"Gleiche Achsen ({len(graph['shared_axes'])} Gruppen)"])
        for members in graph['shared_axes']:
            m = maps[members[0]]
            node = QTreeWidgetItem(axes, [f'{len(m.axes_y)}×{len(m.axes_x)} Achsen · {len(members)} Kennfelder', '', ''])
            self._add_members(node, members)
        routines.setExpanded(True)
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
