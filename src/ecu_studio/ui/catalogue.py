"""Virtual catalogue: Qt requests labels only for rows actually displayed."""
from bisect import bisect_left
from ..core.i18n import translated_roles, t
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

    @translated_roles
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
                    if m.source=='bundled-definition' else
                    f' · {t(m.evidence_tier)} {m.calibrated_rate:.0%}' if m.calibrated_rate is not None else
                    f' · {t(m.evidence_tier)}' if m.evidence_tier else ' · Vorschlag' if m.label_origin else '')
            return (f"{marker} {star}{t(m.name)}{'  [geändert]' if changed else ''}{folder}\n"
                    f'    0x{m.offset:08X}  {m.rows}×{m.cols}  {m.dtype}  | Typ: {t(m.kind)}{status}')
        if role==Qt.ItemDataRole.DecorationRole and m.evidence_tier:
            return _tier_dot(m.evidence_tier)
        if role==Qt.ItemDataRole.ToolTipRole:
            rate=(f'Gemessene Trefferquote dieser Evidenzklasse: {m.calibrated_rate:.0%} ({m.evidence_tier})'
                  if m.calibrated_rate is not None else
                  f'Evidenzklasse ohne ausreichende Messung ({m.evidence_tier})' if m.evidence_tier else
                  f'Strukturwert: {m.confidence:.2f} (keine Wahrscheinlichkeit)')
            return f'{m.kind}\n{m.label_origin or m.source}\n{m.label_evidence or m.notes}\n{rate}'


TIER_COLORS={'gesichert':'#2EA043','wahrscheinlich':'#D29922','Vermutung':'#8B949E','nicht kalibriert':'#6E7681'}


def _tier_dot(tier):
    from PySide6.QtGui import QColor,QPainter,QPixmap
    pixmap=QPixmap(10,10)
    pixmap.fill(QColor(0,0,0,0))
    painter=QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(TIER_COLORS.get(tier,'#6E7681')))
    painter.setPen(QColor(0,0,0,0))
    painter.drawEllipse(1,1,8,8)
    painter.end()
    return pixmap
