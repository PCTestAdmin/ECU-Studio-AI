"""Virtual catalogue: Qt requests labels only for rows actually displayed."""
from bisect import bisect_left
from PySide6.QtCore import QAbstractListModel,QModelIndex,Qt,QSize


class CatalogueModel(QAbstractListModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.maps=[]
        self.indices=[]
        self.patches=[]

    def set_context(self,maps,indices,patches):
        self.beginResetModel()
        self.maps,self.indices,self.patches=maps,indices,patches
        self.endResetModel()

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.indices)

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.indices):
            return None
        i=self.indices[index.row()]
        m=self.maps[i]
        if role==Qt.ItemDataRole.UserRole:
            return i
        if role==Qt.ItemDataRole.SizeHintRole:
            return QSize(220,52)
        if role==Qt.ItemDataRole.DisplayRole:
            pos=bisect_left(self.patches,m.offset)
            changed=pos<len(self.patches) and self.patches[pos]<m.offset+m.length
            marker='✓' if m.verified else '•'
            star='★ ' if m.favorite else ''
            folder=f' [{m.folder}]' if m.folder else ''
            status=(' · geprüft' if m.verified else ' · XDF-Zuordnung (ungeprüft)'
                    if m.source=='bundled-definition' else ' · Vorschlag' if m.label_origin else '')
            return (f"{marker} {star}{m.name}{'  [geändert]' if changed else ''}{folder}\n"
                    f'    0x{m.offset:08X}  {m.rows}×{m.cols}  {m.dtype}  | Typ: {m.kind}{status}')
        if role==Qt.ItemDataRole.ToolTipRole:
            return (f'{m.kind}\n{m.label_origin or m.source}\n{m.label_evidence or m.notes}\n'
                    f'Strukturwert: {m.confidence:.2f} (keine Wahrscheinlichkeit)')
