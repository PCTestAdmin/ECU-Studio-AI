"""Virtual catalogue: Qt requests labels only for rows actually displayed."""
from bisect import bisect_left
from ..core.i18n import translated_roles, t
from ..core.confidence import describe, dtype_doubt, evidence_level, is_experimental
from PySide6.QtCore import QAbstractListModel,QModelIndex,Qt,QSize


class CatalogueModel(QAbstractListModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.maps=[]
        self.indices=[]
        self.patches=[]
        self.axis_groups={}

    def set_context(self,maps,indices,patches,axis_groups=None):
        self.beginResetModel()
        self.maps,self.indices,self.patches=maps,indices,patches
        self.axis_groups=axis_groups or {}
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
            level=evidence_level(m)
            status=(' · geprüft' if m.verified else ' · XDF-Zuordnung (ungeprüft)'
                    if m.source=='bundled-definition' else
                    f" · {t(level)}{' · ' + t('experimentell') if is_experimental(m) else ''}" if level else
                    ' · Name übertragen (ungeprüft)' if m.label_origin.startswith('Namensübertragung') else
                    ' · Vorschlag' if m.label_origin else '')
            doubt=dtype_doubt(m)
            groups=self.axis_groups.get(i,())
            shared=(' · Achse geteilt'+(' (unsicher)' if any(g.uncertain for g in groups) else '')) if groups else ''
            return (f"{marker} {star}{t(m.name)}{'  [geändert]' if changed else ''}{folder}\n"
                    f'    0x{m.offset:08X}  {m.rows}×{m.cols}  {m.dtype}{"?" if doubt else ""}  | Typ: {t(m.kind)}{status}{shared}')
        if role==Qt.ItemDataRole.DecorationRole and evidence_level(m):
            return _tier_dot(evidence_level(m))
        if role==Qt.ItemDataRole.ToolTipRole:
            rate=(describe(m) or ('Von dir geprüft' if m.verified else
                  'Aus einer Definition (Lage laut Definition)' if m.source!='heuristic' and not m.label_origin else
                  f'Strukturwert: {m.confidence:.2f} (keine Wahrscheinlichkeit)'))
            shared=''.join('\n'+g.describe() for g in self.axis_groups.get(i,()))
            doubt=dtype_doubt(m)
            doubt=f'\nDatentyp {m.dtype} nicht belegt: {doubt}' if doubt else ''
            return f'{m.kind}\n{m.label_origin or m.source}\n{m.label_evidence or m.notes}\n{rate}{doubt}{shared}'


TIER_COLORS={'Code-Beleg':'#2EA043','Strukturbeleg':'#D29922','Datenmuster-Vermutung':'#8B949E'}


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
