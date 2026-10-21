"""Qt virtual table models + dependency-light native 2D/3D visualizations."""
from __future__ import annotations
from math import cos, sin, radians
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import QWidget
from ..core.i18n import translated_roles
from ..core.model import BinaryImage, MapDefinition, FORMATS
from .theme import palette, heat_rgb, heat_tint


def display_decimals(m: MapDefinition) -> int:
    """Decimals needed to show one raw step of the scaling (0..4)."""
    from math import ceil, log10
    step = abs(m.factor) if m.factor else 1.
    return 0 if step >= 1 else min(4, ceil(-log10(step) - 1e-9))


class HexTableModel(QAbstractTableModel):
    edited = Signal()
    def __init__(self):
        super().__init__()
        self.image: BinaryImage | None = None
        self.dark=False
        self.radix=16

    def set_image(self, image: BinaryImage | None):
        self.beginResetModel()
        self.image = image
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() or self.image is None:
            return 0
        return (self.image.size + 15) // 16

    def columnCount(self, parent=QModelIndex()):
        return 16

    @translated_roles
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return f"{section*16:08X}"
        return f"{section:02X}"

    def flags(self, idx):
        base = super().flags(idx)
        if self.image and idx.isValid() and idx.row()*16 + idx.column() < self.image.size:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, idx, role=Qt.ItemDataRole.DisplayRole):
        if not self.image or not idx.isValid():
            return None
        pos = idx.row()*16 + idx.column()
        if pos >= self.image.size:
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return f"{self.image.byte(pos):02X}" if self.radix==16 else str(self.image.byte(pos))
        if role == Qt.ItemDataRole.BackgroundRole:
            theme=palette("dark" if self.dark else "light")
            return QColor(theme["changed"]) if pos in self.image._patches else QColor(theme["surface2"] if idx.row()%2 else theme["surface"])
        if role == Qt.ItemDataRole.ForegroundRole:
            theme=palette("dark" if self.dark else "light")
            return QColor(theme["changed_text"] if pos in self.image._patches else theme["text"])
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Offset 0x{pos:08X} · Original {self.image.original[pos]:02X}"
        return None

    def setData(self, idx, value, role=Qt.ItemDataRole.EditRole):
        if not self.image or role != Qt.ItemDataRole.EditRole or not idx.isValid():
            return False
        value = str(value).strip().upper().removeprefix("0X")
        if self.radix==16 and not (len(value) == 2 and all(c in "0123456789ABCDEF" for c in value)):
            return False
        if self.radix==10 and (not value.isdecimal() or not 0<=int(value)<=255):
            return False
        try:
            self.image.write(idx.row()*16+idx.column(), bytes([int(value,self.radix)]))
        except ValueError:
            return False
        self.dataChanged.emit(idx,idx)
        self.edited.emit()
        return True

    def refresh(self):
        if self.rowCount():
            self.dataChanged.emit(self.index(0,0),self.index(self.rowCount()-1, 15))


class MapTableModel(QAbstractTableModel):
    edited = Signal()
    def __init__(self):
        super().__init__()
        self.image: BinaryImage | None = None
        self.map: MapDefinition | None = None
        self.dark=False
        self._values_cache = {}

    def set_map(self, image, selected):
        self.beginResetModel()
        self.image, self.map = image, selected
        self._values_cache.clear()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return self.map.rows if self.map is not None and not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return self.map.cols if self.map is not None and not parent.isValid() else 0

    @translated_roles
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if self.map is None:
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            unit=self.map.axis_x_unit if orientation == Qt.Orientation.Horizontal else self.map.axis_y_unit
            return unit or self.map.axes_info or 'Indexachse'
        if role != Qt.ItemDataRole.DisplayRole:return None
        axis = self.map.axes_x if orientation == Qt.Orientation.Horizontal else self.map.axes_y
        if section < len(axis):
            return f"{axis[section]:g}"
        return str(section)

    def flags(self, idx):
        flags = super().flags(idx)
        if self.map and idx.isValid():
            if not self.map.equation:
                flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, idx, role=Qt.ItemDataRole.DisplayRole):
        if not self.map or not self.image or not idx.isValid():
            return None
        try:
            v = self.image.physical_value(self.map,idx.row(),idx.column())
        except (ValueError, IndexError):
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                return 'N/A: Formel für Rohwert ungültig'
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            # Editing must round-trip without losing significant digits. Raw
            # integer maps must not turn 2745410467 into 2.7454105e+09.
            if not self.map.equation and self.map.factor == 1 and self.map.bias == 0:
                return str(self.image.raw_value(self.map,idx.row(),idx.column()))
            if role == Qt.ItemDataRole.EditRole:
                return f"{v:.17g}"
            # Display: as many decimals as one raw step resolves, not float noise.
            return f"{v:.{display_decimals(self.map)}f}" if not self.map.equation else f"{v:.5g}"
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.BackgroundRole:
            pos = self.map.cell_offset(idx.row(),idx.column())
            if any((pos+j) in self.image._patches for j in range(self.map.width)):
                return QColor(palette("dark" if self.dark else "light")["changed"])
            lo,hi=self.value_range()
            return QColor(*heat_tint((v-lo)/(hi-lo) if hi>lo else .5,"dark" if self.dark else "light"))
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(palette("dark" if self.dark else "light")["text"])
        if role == Qt.ItemDataRole.ToolTipRole:
            raw = self.image.raw_value(self.map,idx.row(),idx.column())
            return f"Rohwert {raw} | Physikalisch {v:g} {self.map.unit}"
        return None

    def setData(self, idx, value, role=Qt.ItemDataRole.EditRole):
        if not self.map or not self.image or role != Qt.ItemDataRole.EditRole:
            return False
        try:
            v = float(str(value).replace(",","."))
            self.image.write_physical(self.map,idx.row(),idx.column(),v)
        except (ValueError,OverflowError,IndexError):
            return False
        self.dataChanged.emit(idx,idx)
        self.edited.emit()
        return True

    def values(self, max_samples=96):
        """Return sampled display values, not a full 512x512 repaint on each frame."""
        if not self.map or not self.image:
            return []
        m = self.map
        key=(id(self.image),id(m),self.image.revision,max_samples,
             m.offset,m.rows,m.cols,m.dtype,m.endian,m.factor,m.bias,
             m.storage_order,m.major_stride_bits,m.minor_stride_bits,m.equation)
        if key in self._values_cache:
            return self._values_cache[key]
        m.validate(self.image.size)  # Once per surface, not once per cell.
        from struct import unpack
        fmt=('>' if m.endian=='big' else '<') + FORMATS[m.dtype][0]
        step_r = max(1, (m.rows + max_samples - 1) // max_samples)
        step_c = max(1, (m.cols + max_samples - 1) // max_samples)
        try:
            if not m.equation:
                values=self.image.matrix(m,physical=True)[::step_r,::step_c].tolist()
            else:
                values=[[m.scale_raw(unpack(fmt,self.image.read(m.cell_offset(r,c),m.width))[0])
                         for c in range(0,m.cols,step_c)] for r in range(0,m.rows,step_r)]
        except (ValueError,OverflowError):
            return []  # do not paint a plausible but incorrectly scaled surface
        self._values_cache={key: values}
        return values

    def value_range(self) -> tuple[float, float]:
        """Physical min/max of the whole map, cached per image revision."""
        values=self.values(max_samples=512)
        key=('range',id(values))
        if key not in self._values_cache:
            flat=[x for row in values for x in row]
            self._values_cache[key]=(min(flat),max(flat)) if flat else (0.,0.)
        return self._values_cache[key]

    def refresh(self):
        self._values_cache.clear()
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(self.index(0,0),self.index(self.rowCount()-1,self.columnCount()-1))


class Map2DView(QWidget):
    """Clickable heatmap with value legend; opens exact editor cells."""
    cellSelected = Signal(int, int)
    def __init__(self, model: MapTableModel):
        super().__init__()
        self.model = model
        self.setMinimumHeight(280)

    MARGINS = (70, 56, 104, 44)   # left, top, right (legend), bottom

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme=palette("dark" if self.model.dark else "light")
        p.fillRect(self.rect(), QColor(theme["surface"]))
        matrix = self.model.values(max_samples=96)
        if not matrix:
            p.setPen(QColor(theme["secondary"]))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"Kennfeld auswählen oder Umrechnungsformel prüfen")
            return
        m = self.model.map
        rows, cols = len(matrix), len(matrix[0])
        left, top, right, bottom = self.MARGINS
        width = max(2, self.width()-left-right)
        height = max(2, self.height()-top-bottom)
        flat = [x for row in matrix for x in row]
        lo, hi = min(flat), max(flat)
        span = hi-lo or 1.0
        cw, ch = width/cols,height/rows
        show_values = cw >= 38 and ch >= 17 and rows == m.rows and cols == m.cols
        decimals = display_decimals(m) if not m.equation else 2
        value_font = QFont("Segoe UI", 8 if cw < 52 else 9)
        for r in range(rows):
            for c in range(cols):
                t = (matrix[r][c]-lo)/span
                rect = QRectF(left+c*cw,top+r*ch,cw+.3,ch+.3)
                p.fillRect(rect,QColor(*heat_rgb(t)))
                if show_values:
                    p.setFont(value_font)
                    p.setPen(QColor(18,22,28) if .3 < t < .85 else QColor(250,250,252))
                    text = (str(round(matrix[r][c])) if not m.equation and m.factor == 1 and m.bias == 0
                            else f"{matrix[r][c]:.{decimals}f}")
                    p.drawText(rect,Qt.AlignmentFlag.AlignCenter,text)
        # Title and status line
        p.setPen(QColor(theme["text"]))
        p.setFont(QFont("Segoe UI",11,QFont.Weight.DemiBold))
        p.drawText(20,24,f"{m.name}")
        p.setPen(QColor(theme['secondary']))
        p.setFont(QFont('Segoe UI',9))
        certainty = 'manuell geprüft' if m.verified else 'Typ-Vorschlag · nicht bestätigt'
        p.drawText(20,42,f"{m.rows} × {m.cols}  ·  {m.dtype}  ·  {m.kind}  ·  {certainty}"
                   + ("  ·  Vorschau gerastert" if rows!=m.rows or cols!=m.cols else ""))
        # Axis labels: every breakpoint when there is room, else first/last.
        p.setFont(QFont("Cascadia Mono",8))
        p.setPen(QColor(theme['secondary']))
        def axis_label(axis, i, n):
            return f"{axis[i]:.4g}" if len(axis) == n else str(i)
        step_x = max(1, int(46 // max(cw, 1)) + 1)
        for c in range(0, cols, step_x):
            p.drawText(QRectF(left+c*cw, top+height+4, max(cw*step_x, 40), 16),
                       Qt.AlignmentFlag.AlignLeft if cw*step_x < 40 else Qt.AlignmentFlag.AlignHCenter,
                       axis_label(m.axes_x, min(m.cols-1, c*max(1,(m.cols+95)//96)), m.cols))
        step_y = max(1, int(16 // max(ch, 1)) + 1)
        for r in range(0, rows, step_y):
            p.drawText(QRectF(4, top+r*ch, left-10, max(ch, 14)), Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,
                       axis_label(m.axes_y, min(m.rows-1, r*max(1,(m.rows+95)//96)), m.rows))
        p.drawText(left, top+height+34, ("X: Achse" if len(m.axes_x)==m.cols else "X: Index")
                   + ("   ·   Y: Achse" if len(m.axes_y)==m.rows else "   ·   Y: Index")
                   + (f"   ·   {m.unit}" if m.unit else ""))
        # Colour legend
        lx, lw = left+width+22, 14
        for i in range(int(height)):
            p.fillRect(QRectF(lx, top+height-i-1, lw, 1.5), QColor(*heat_rgb(i/max(1,height-1))))
        p.setPen(QColor(theme['line']))
        p.drawRect(QRectF(lx, top, lw, height))
        p.setPen(QColor(theme['secondary']))
        p.drawText(QRectF(lx+lw+4, top-6, 72, 14), Qt.AlignmentFlag.AlignLeft, f"{hi:.6g}")
        p.drawText(QRectF(lx+lw+4, top+height-8, 72, 14), Qt.AlignmentFlag.AlignLeft, f"{lo:.6g}")


    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.model.map is None:return
        matrix=self.model.values(max_samples=96)
        if not matrix:return
        left,top,right,bottom=self.MARGINS
        w=max(2,self.width()-left-right)
        h=max(2,self.height()-top-bottom)
        x,y=event.position().x(),event.position().y()
        if not (left<=x<left+w and top<=y<top+h):return
        sampled_r=min(len(matrix)-1,int((y-top)*len(matrix)/h))
        sampled_c=min(len(matrix[0])-1,int((x-left)*len(matrix[0])/w))
        m=self.model.map
        step_r=max(1,(m.rows+96-1)//96)
        step_c=max(1,(m.cols+96-1)//96)
        self.cellSelected.emit(min(m.rows-1,sampled_r*step_r),
                               min(m.cols-1,sampled_c*step_c))


class Map3DView(QWidget):
    """Isometric wireframe; 3D projection without GPU/driver dependencies."""
    def __init__(self, model: MapTableModel):
        super().__init__()
        self.model=model
        self.setMinimumHeight(280)
        self.yaw = 38.0
        self.pitch = 34.0
        self.last_x: float | None = None
        self.last_y: float | None = None
        self.zoom=0.66

    def mousePressEvent(self, event):
        self.last_x = float(event.position().x())
        self.last_y = float(event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.last_x is not None:
            self.yaw += (event.position().x()-self.last_x)*.4
            self.pitch = max(8.0,min(80.0,self.pitch +(event.position().y()-self.last_y)*.25))
            self.last_x = event.position().x()
            self.last_y = event.position().y()
            self.update()

    def wheelEvent(self,event):
        self.zoom=max(.3,min(1.4,self.zoom*(1.1 if event.angleDelta().y()>0 else .91)))
        self.update()

    def mouseReleaseEvent(self,event):
        self.last_x = None
        self.last_y = None

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme=palette("dark" if self.model.dark else "light")
        p.fillRect(self.rect(),QColor(theme["surface"]))
        a = self.model.values(max_samples=56)
        if not a:
            p.setPen(QColor(theme["secondary"]))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"Kennfeld auswählen oder Umrechnungsformel prüfen")
            return
        rows,cols=len(a),len(a[0])
        flat=[v for row in a for v in row]
        # Baseline is rendered only when the selected map includes changed cells.
        # This is a visualization, not an ECU-specific safety assessment.
        original=None
        m=self.model.map
        if self.model.image and any(m.offset<=p<m.offset+m.length for p in self.model.image._patches):
            from struct import unpack
            from ..core.model import FORMATS
            image=self.model.image
            pat=('>' if m.endian=='big' else '<')+FORMATS[m.dtype][0]
            sr=max(1,(m.rows+56-1)//56)
            sc=max(1,(m.cols+56-1)//56)
            try:
                original=[[m.scale_raw(unpack(pat,image.original[m.cell_offset(r,c):m.cell_offset(r,c)+m.width])[0])
                          for c in range(0,m.cols,sc)] for r in range(0,m.rows,sr)]
                flat.extend(v for row in original for v in row)
            except (ValueError,OverflowError,IndexError):original=None
        lo,hi=min(flat),max(flat)
        span=hi-lo or 1
        from ..core.plot_axes import sampled_axis_positions
        step_r=max(1,(m.rows+56-1)//56)
        step_c=max(1,(m.cols+56-1)//56)
        xs,has_x=sampled_axis_positions(m.axes_x,m.cols,step_c)
        ys,has_y=sampled_axis_positions(m.axes_y,m.rows,step_r)
        cy,sy=cos(radians(self.yaw)),sin(radians(self.yaw))
        cp,sp=cos(radians(self.pitch)),sin(radians(self.pitch))
        dim=min(self.width(),self.height())*self.zoom
        def project(r,c,table):
            x=(xs[c]-.5)*1.65
            z=(ys[r]-.5)*1.65
            y=((table[r][c]-lo)/span-.5)*.95
            xx=x*cy-z*sy
            zz=x*sy+z*cy
            yy=y*cp-zz*sp
            return self.width()/2+xx*dim*.65, self.height()/2-yy*dim*.72
        # Filled, value-coloured surface drawn back to front (painter's algorithm).
        def depth(r,c):
            x=(xs[c]-.5)*1.65
            z=(ys[r]-.5)*1.65
            return x*sy+z*cy
        edge=QColor(theme['surface'])
        edge.setAlpha(150)
        quads=[]
        for r in range(rows-1):
            for c in range(cols-1):
                corners=((r,c),(r,c+1),(r+1,c+1),(r+1,c))
                mean=sum(a[i][j] for i,j in corners)/4
                quads.append((sum(depth(i,j) for i,j in corners)/4,corners,mean))
        quads.sort(key=lambda q:-q[0])
        p.setPen(QPen(edge,.8))
        for _,corners,mean in quads:
            p.setBrush(QBrush(QColor(*heat_rgb((mean-lo)/span))))
            p.drawPolygon(QPolygonF([QPointF(*project(i,j,a)) for i,j in corners]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if rows==1 or cols==1:   # curves: no area to fill
            p.setPen(QPen(QColor(theme['accent']),2))
            pts=[QPointF(*project(r,c,a)) for r in range(rows) for c in range(cols)]
            for p1,p2 in zip(pts,pts[1:]):
                p.drawLine(p1,p2)
        if original is not None:   # ORI wireframe on top of the modified surface
            p.setPen(QPen(QColor('#9299A5'),1.2,Qt.PenStyle.DashLine))
            for r in range(rows):
                for c in range(cols-1):
                    x1,y1=project(r,c,original);x2,y2=project(r,c+1,original)
                    p.drawLine(int(x1),int(y1),int(x2),int(y2))
            for c in range(cols):
                for r in range(rows-1):
                    x1,y1=project(r,c,original);x2,y2=project(r+1,c,original)
                    p.drawLine(int(x1),int(y1),int(x2),int(y2))
        p.setPen(QColor(theme["text"]))
        p.setFont(QFont("Segoe UI",11))
        p.drawText(18,26,f"3D · {self.model.map.name}")
        p.setPen(QColor(theme['secondary']))
        p.setFont(QFont('Segoe UI',9))
        p.drawText(18,44,f"Typ: {self.model.map.kind}" +
                   (" · geprüft" if self.model.map.verified else " · ungeprüfter Vorschlag"))
        p.setPen(QColor(theme["secondary"]))
        p.setFont(QFont("Segoe UI",9))
        axis_info=('echte X/Y-Achsen' if has_x and has_y else 'fehlende Achsen: Indexabstand')
        p.drawText(18,self.height()-18,
            f'Maus: drehen / Neigung · Rad: Zoom · Farbe = Wert, Grau gestrichelt = ORI · {axis_info}')


class MemoryAtlasView(QWidget):
    """Click-to-jump BIN overview: verified maps, unverified maps, changed bytes.

    This is a structural occupancy view; it does not identify ECU features.
    """
    def __init__(self, jump_callback):
        super().__init__()
        self.jump_callback=jump_callback
        self.image=None
        self.maps=[]
        self.setMouseTracking(True)
        self.setMinimumHeight(360)
        self._left=98
        self._top=88
        self._right=22
        self._row_h=9
        self._rows=48

    def set_context(self,image,maps):
        self.image=image
        self.maps=list(maps)
        self.update()

    def _geometry(self):
        rows=min(68,max(12,(self.height()-125)//self._row_h))
        left=self._left
        width=max(1,self.width()-self._left-self._right)
        return rows,left,width

    def paintEvent(self,event):
        from ..core.atlas import overview_slices,atlas_stats
        dark=getattr(self,'dark',False)
        colors=palette('dark' if dark else 'light')
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing,False)
        painter.fillRect(self.rect(),QColor(colors['surface']))
        painter.setPen(QColor(colors['text']))
        painter.setFont(QFont('Segoe UI',12,QFont.Weight.DemiBold))
        painter.drawText(17,26,'Speicheratlas  /  Kennfeldabdeckung')
        if not self.image or not self.image.size:
            painter.setPen(QColor(colors['secondary']))
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'BIN öffnen, um Speicherbelegung zu sehen')
            return
        s=atlas_stats(self.image.size,self.maps,self.image._patches)
        ratio=s.mapped_bytes/self.image.size*100 if self.image.size else 0
        painter.setFont(QFont('Segoe UI',9))
        painter.setPen(QColor(colors['secondary']))
        painter.drawText(18,46,f'{self.image.size:,} Byte   ·   {ratio:.1f}% definiert   ·   '
                                 f'{s.changed_bytes:,} geändert   ·   {s.changed_unmapped:,} außerhalb bekannter Maps')
        rows,left,width=self._geometry()
        self._rows=rows
        chunk=max(1,(self.image.size+rows-1)//rows)
        colors_key={'unknown': '#C2CDD9' if not dark else '#5A6777',
                    'verified':'#2861AB' if not dark else '#78A9EC',
                    'changed':'#D28A28' if not dark else '#EAB564'}
        legend=[('Definition',colors_key['unknown']),('Verifiziert',colors_key['verified']),('Geändert',colors_key['changed'])]
        lx=20
        for label,color in legend:
            painter.fillRect(lx,60,9,9,QColor(color))
            painter.setPen(QColor(colors['secondary']))
            painter.drawText(lx+14,68,label)
            lx+=115
        painter.setPen(QColor(colors['secondary']))
        painter.setFont(QFont('Consolas',8))
        for row in range(rows):
            y=self._top+row*self._row_h
            painter.fillRect(left,y,width,self._row_h-2,QColor(colors['well']))
            painter.drawText(9,y+7,f'{min(row*chunk,self.image.size):08X}')
            for x_frac in (.25,.5,.75):
                x=int(left+x_frac*width)
                painter.setPen(QColor(colors['line2']))
                painter.drawLine(x,y,x,y+self._row_h-3)
        def put(start,end,color):
            for row,f0,f1 in overview_slices(start,end,size=self.image.size,rows=rows):
                if row>=rows:continue
                x0=left+round(f0*width)
                x1=left+round(f1*width)
                painter.fillRect(x0,self._top+row*self._row_h,max(2,x1-x0),
                                 self._row_h-2,QColor(color))
        for m in self.maps:
            if m.verified:continue
            put(m.offset,m.offset+m.length,colors_key['unknown'])
        for m in self.maps:
            if not m.verified:continue
            put(m.offset,m.offset+m.length,colors_key['verified'])
        for start,orig,changed in self.image.changed_ranges():
            put(start,start+len(orig),colors_key['changed'])
        painter.setPen(QColor(colors['secondary']))
        painter.drawText(18,self.height()-14,
            'Anklicken: Zur Offsetposition im Hex-Editor springen. Farben zeigen Definitionen, nicht ECU-Funktionssicherheit.')

    def _position_offset(self,x,y):
        if not self.image or not self.image.size:return None
        rows,left,width=self._geometry()
        row=int((y-self._top)//self._row_h)
        if row<0 or row>=rows or x<left or x>left+width:return None
        stride=max(1,(self.image.size+rows-1)//rows)
        pos=row*stride+int(((x-left)/width)*stride)
        return min(self.image.size-1,pos)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            offset=self._position_offset(event.position().x(),event.position().y())
            if offset is not None:self.jump_callback(offset)

    def mouseMoveEvent(self,event):
        offset=self._position_offset(event.position().x(),event.position().y())
        self.setToolTip(f'Offset 0x{offset:08X} · Klicken zum Hex-Editor' if offset is not None else '')

class MapCurveView(QWidget):
    """Editable-map companion: 2D cut with original/current overlays.

    Clicking a sampled point selects the exact table cell. No claim about
    physical axis calibration where axes are absent or non-monotonic.
    """
    cellSelected = Signal(int, int)

    def __init__(self, model: MapTableModel):
        from PySide6.QtWidgets import QComboBox, QSpinBox, QLabel, QHBoxLayout, QVBoxLayout
        super().__init__()
        self.model=model
        self.setMinimumHeight(280)
        outer=QVBoxLayout(self)
        line=QHBoxLayout()
        line.addWidget(QLabel('Schnitt:'))
        self.mode=QComboBox()
        self.mode.addItems(['Zeile (X-Achse)','Spalte (Y-Achse)'])
        line.addWidget(self.mode)
        line.addWidget(QLabel('Index:'))
        self.slice=QSpinBox()
        self.slice.setRange(0,0)
        line.addWidget(self.slice)
        line.addStretch(1)
        outer.addLayout(line)
        self.canvas=_CurveCanvas(self)
        outer.addWidget(self.canvas,1)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.slice.valueChanged.connect(self.canvas.update)
        self.model.modelReset.connect(self._mode_changed)
        self.model.dataChanged.connect(lambda *_:self.canvas.update())

    def _mode_changed(self,*args):
        m=self.model.map
        self.slice.setMaximum(max(0,((m.rows if self.mode.currentIndex()==0 else m.cols)-1)) if m else 0)
        self.canvas.update()

    def curve_data(self):
        import math
        import struct
        m=self.model.map
        image=self.model.image
        if m is None or image is None:return [], False
        try:m.validate(image.size)
        except ValueError:return [],False
        mode=self.mode.currentIndex()
        n=m.cols if mode==0 else m.rows
        k=self.slice.value()
        axis=m.axes_x if mode==0 else m.axes_y
        try:
            numeric_axis=[float(v) for v in axis]
            use_axis=(len(numeric_axis)==n and all(math.isfinite(x) for x in numeric_axis)
                      and (all(numeric_axis[i+1]>numeric_axis[i] for i in range(n-1)) or
                           all(numeric_axis[i+1]<numeric_axis[i] for i in range(n-1))))
        except (TypeError,ValueError,OverflowError):
            use_axis=False
            numeric_axis=[]
        fmt=('>' if m.endian=='big' else '<')+FORMATS[m.dtype][0]
        step=max(1,(n+159)//160)
        ids=list(range(0,n,step))
        if ids and ids[-1]!=n-1:ids.append(n-1)
        data=[]
        for i in ids:
            r,c=(k,i) if mode==0 else (i,k)
            pos=m.cell_offset(r,c)
            try:
                a=struct.unpack(fmt,image.original[pos:pos+m.width])[0]
                b=struct.unpack(fmt,image.read(pos,m.width))[0]
                before=m.scale_raw(a); after=m.scale_raw(b)
                if not math.isfinite(before) or not math.isfinite(after):return [],False
                data.append((numeric_axis[i] if use_axis else float(i),before,after,r,c))
            except (ValueError,OverflowError,IndexError,struct.error):return [],False
        return data,use_axis


class _CurveCanvas(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.owner=parent
        self.setMinimumHeight(250)
        self._points=[]

    def paintEvent(self,event):
        import math
        from PySide6.QtCore import QRectF
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors=palette('dark' if self.owner.model.dark else 'light')
        p.fillRect(self.rect(),QColor(colors['surface']))
        data,use_axis=self.owner.curve_data()
        self._points=[]
        if not data:
            p.setPen(QColor(colors['secondary']))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Kennfeld auswählen / Skalierung prüfen')
            return
        left,top=67,33
        width=max(20,self.width()-left-28)
        height=max(20,self.height()-top-62)
        xmin,xmax=data[0][0],data[-1][0]
        values=[v for row in data for v in row[1:3]]
        vmin,vmax=min(values),max(values)
        yr=vmax-vmin or 1.0
        xr=xmax-xmin or 1.0
        def xy(row,value):
            return (left+(row[0]-xmin)/xr*width,top+height-(value-vmin)/yr*height)
        grid=QColor(colors['line2'])
        p.setPen(QPen(grid,1))
        for i in range(5):
            y=top+i*height/4
            p.drawLine(int(left),int(y),int(left+width),int(y))
            p.setPen(QColor(colors['secondary']))
            p.drawText(5,int(y)+4,f'{(vmax-(vmax-vmin)*i/4):.4g}')
            p.setPen(QPen(grid,1))
        p.drawLine(int(left),int(top),int(left),int(top+height))
        from PySide6.QtCore import Qt as _Qt
        orig=QPen(QColor('#8A8F9C'),1.6,_Qt.PenStyle.DashLine)
        edited=QPen(QColor('#2563EB' if not self.owner.model.dark else '#68C2FF'),2.1)
        for column,pen in ((1,orig),(2,edited)):
            p.setPen(pen)
            for j in range(len(data)-1):
                x1,y1=xy(data[j],data[j][column]);x2,y2=xy(data[j+1],data[j+1][column])
                p.drawLine(int(x1),int(y1),int(x2),int(y2))
        for row in data:
            self._points.append((*xy(row,row[2]),row[3],row[4]))
        p.setPen(QColor(colors['text']))
        p.drawText(left,19,'— MOD     - - ORI  |  Werte: '+(self.owner.model.map.unit or 'keine Einheit'))
        p.setPen(QColor(colors['secondary']))
        p.drawText(left,self.height()-28,f'{xmin:.5g}')
        p.drawText(left+width-70,self.height()-28,f'{xmax:.5g}')
        p.drawText(left,self.height()-9,
                   ('Definition-Achse' if use_axis else 'INDEX (Achse nicht geprüft)') +
                   ' · Klick auf Kurve: Kennfeldzelle markieren')

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self._points:return
        x,y=event.position().x(),event.position().y()
        nearest=min(self._points,key=lambda q:(q[0]-x)**2 + (q[1]-y)**2)
        if (nearest[0]-x)**2+(nearest[1]-y)**2<900:
            self.owner.cellSelected.emit(nearest[2],nearest[3])
