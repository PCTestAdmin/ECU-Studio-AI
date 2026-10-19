"""Professional raw 2D file trace, independent of any known map.

Single window of at most 65,536 raw samples; peak-preserving sampling.
The interpretation (endianness/dtype) is manual, not ECU detection.
"""
from __future__ import annotations

from bisect import bisect_left

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QScrollBar, QMessageBox
)

from ..core.model import FORMATS
from ..core.raw_trace import raw_trace
from ..core.definitions import parse_offset
from .theme import palette


class Raw2DGraph(QWidget):
    """Interactive trace: click cursor, drag byte span, double-click jump to HEX."""
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.setMinimumHeight(300)
        self.setMouseTracking(True)
        self.setToolTip('Ziehen = Bereich markieren · Doppelklick = Hex-Editor · Mausrad = Scrollen · Strg+Rad = Zoom')
        self._drag_start = None
        self._curve_cache_key = None
        self._curve_cache = None
        self._margins = (76, 28, 26, 67)

    def _plot_area(self):
        left, top, right, bottom = self._margins
        return left, top, max(1, self.width()-left-right), max(1, self.height()-top-bottom)

    def _byte_at(self, x):
        trace = self.host.trace()
        if trace.end <= trace.start:
            return None
        left, _, width, _ = self._plot_area()
        x = min(width, max(0, float(x)-left))
        n = (trace.end-trace.start)//trace.width
        index = min(n-1, int(round(x/width*(n-1))))
        return trace.start+index*trace.width

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.host.image is None:
            return
        self._drag_start = self._byte_at(event.position().x())
        if self._drag_start is not None:
            self.host.cursor = self._drag_start
            self.host.selection = None
            self.host.update_inspector()
            self.update()

    def mouseMoveEvent(self, event):
        at = self._byte_at(event.position().x())
        if at is None: return
        self.setToolTip(f'Offset 0x{at:08X} · Doppelklick: zum Hex-Editor')
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            a, b = sorted((self._drag_start, at))
            self.host.cursor = at
            self.host.selection = (a, b+self.host.trace().width) if a != b else None
            self.host.update_inspector()
            self.update()

    def mouseReleaseEvent(self, event):
        self._drag_start = None

    def mouseDoubleClickEvent(self, event):
        at = self._byte_at(event.position().x())
        if at is not None:
            self.host.jump_callback(at)

    def wheelEvent(self, event):
        if not self.host.image:
            return
        steps = event.angleDelta().y() // 120
        if not steps:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.host.zoom_by(-steps)
        else:
            visible = self.host.count
            self.host.go_offset(self.host.start - steps*max(self.host.word_width, (visible//8)*self.host.word_width))
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = palette('dark' if self.host.dark else 'light')
        painter.fillRect(self.rect(), QColor(t['surface']))
        left, top, width, height = self._plot_area()
        painter.setFont(QFont('Consolas', 9))
        painter.setPen(QColor(t['secondary']))
        if self.host.image is None or self.host.image.size == 0:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             'BIN / ORI / MOD öffnen – Rohdaten-2D benötigt kein Kennfeld')
            return
        trace = self.host.trace()
        if not trace.points:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Keine vollständigen Werte verfügbar')
            return
        low, high = trace.low, trace.high
        span = max(1, high-low)
        lo_y, hi_y = low - span*0.06, high + span*0.06
        plot_span = hi_y-lo_y
        painter.fillRect(left, top, width, height, QColor(t['well']))
        for i in range(6):
            y = round(top + height*i/5)
            raw = hi_y - (hi_y-lo_y)*i/5
            painter.setPen(QPen(QColor(t['line2']), 1))
            painter.drawLine(left, y, left+width, y)
            painter.setPen(QColor(t['secondary']))
            painter.drawText(2, y+4, f'{raw:.5g}')
        for i in range(9):
            x = round(left+width*i/8)
            painter.setPen(QPen(QColor(t['line2']), 1))
            painter.drawLine(x, top, x, top+height)
            addr = trace.start + int((trace.end-trace.start)*i/8)
            addr -= addr % trace.width
            painter.setPen(QColor(t['secondary']))
            # Alternate labels to avoid collisions on narrow layouts.
            if i%2 == 0:
                painter.drawText(x-24, top+height+18, f'{addr:08X}')
        sample_end = max(trace.width, trace.end-trace.start-trace.width)
        def xx(offset):
            return left + width * (offset-trace.start) / sample_end
        def yy(value):
            return top + (hi_y-value)/plot_span * height
        # Known map ranges are displayed as file regions, not identified without an A2L.
        first = bisect_left(self.host._map_starts, max(0,trace.start-self.host._max_map_span))
        last = bisect_left(self.host._map_starts, trace.end)
        for m in self.host._map_ranges[first:last]:
            a, b = max(trace.start, m.offset), min(trace.end, m.offset+m.length)
            if b <= a: continue
            x0, x1 = max(left, xx(a)), min(left+width, xx(b))
            painter.fillRect(int(x0), top, max(2,int(x1-x0)),height,QColor(75,135,205,22))
            painter.setPen(QPen(QColor(t['accent']),1,Qt.PenStyle.DashLine))
            painter.drawLine(int(x0),top,int(x0),top+height)
        if self.host.selection:
            a,b=self.host.selection
            x0=max(left, xx(a));x1=min(left+width,xx(b))
            if x1>x0:
                painter.fillRect(int(x0),top,int(x1-x0),height,QColor(66,133,215,50))
        painter.setPen(QPen(QColor(t['accent']),1.5))
        curve_key=(self.host._cache_key,self.width(),self.height(),left,top,width,height)
        if self._curve_cache_key != curve_key:
            path=QPainterPath()
            for i,(offset,raw) in enumerate(trace.points):
                x,y=xx(offset),yy(raw)
                if i == 0:path.moveTo(x,y)
                else:path.lineTo(x,y)
            self._curve_cache = path
            self._curve_cache_key = curve_key
        painter.drawPath(self._curve_cache)
        if self.host.cursor is not None and trace.start <= self.host.cursor < trace.end:
            cursor_x=int(xx(self.host.cursor))
            painter.setPen(QPen(QColor('#C68122' if not self.host.dark else '#E6BA6A'),1.5))
            painter.drawLine(cursor_x,top,cursor_x,top+height)
        painter.setPen(QColor(t['text']))
        painter.setFont(QFont('Segoe UI',10))
        painter.drawText(left,15,f'ROHDATEN  ·  {trace.dtype.upper()}  ·  '
                              f'{self.host.endian.upper()}  ·  {len(trace.points):,} Plotpunkte')
        painter.setPen(QColor(t['secondary']))
        painter.setFont(QFont('Segoe UI',9))
        painter.drawText(left, self.height()-16,
            'Dateioffsets (hex) · Raw-Werte ohne Skalierung · Blau schattiert: bekannte Definitionen · Ziehen: Bereich markieren')


class Raw2DView(QWidget):
    """Independent raw graph with file position, dtype/endian, zoom and selection."""
    def __init__(self, jump_callback, define_callback):
        super().__init__()
        self.image = None
        self.maps = []
        self._map_ranges = []
        self._map_starts = []
        self._max_map_span = 0
        self.dark = False
        self.start = 0
        self.count = 2048
        self.dtype = 'u16'
        self.endian = 'big'
        self.word_width = FORMATS[self.dtype][1]
        self.cursor = None
        self.selection = None
        self.jump_callback=jump_callback
        self.define_callback=define_callback
        self._cache_key = None
        self._cache = None
        # Many scrollbar/wheel events may arrive between paint frames. Update
        # the data position immediately, but coalesce painting to ~60 FPS.
        self._redraw_timer=QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.timeout.connect(self.graph_redraw)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        top=QHBoxLayout()
        top.addWidget(QLabel('Format'))
        self.dtype_box=QComboBox()
        self.dtype_box.addItems([t for t in FORMATS if t != 'f32'])
        self.dtype_box.setCurrentText(self.dtype)
        self.dtype_box.currentTextChanged.connect(self.on_format_change)
        top.addWidget(self.dtype_box)
        top.addWidget(QLabel('Bytefolge'))
        self.endian_box=QComboBox()
        self.endian_box.addItems(['big','little'])
        self.endian_box.currentTextChanged.connect(self.on_format_change)
        top.addWidget(self.endian_box)
        top.addWidget(QLabel('Fenster'))
        self.count_box=QComboBox()
        for c in (256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536):
            self.count_box.addItem(f'{c:,} Werte',c)
        self.count_box.setCurrentIndex(3)
        self.count_box.currentIndexChanged.connect(self.on_count_change)
        top.addWidget(self.count_box)
        top.addWidget(QLabel('Start'))
        self.offset_box=QLineEdit('0x00000000')
        self.offset_box.setFixedWidth(120)
        self.offset_box.setPlaceholderText('0x…')
        self.offset_box.returnPressed.connect(self.on_offset_enter)
        top.addWidget(self.offset_box)
        go=QPushButton('Springen')
        go.clicked.connect(self.on_offset_enter)
        top.addWidget(go)
        layout.addLayout(top)
        self.graph=Raw2DGraph(self)
        layout.addWidget(self.graph,1)
        self.scroll=QScrollBar(Qt.Orientation.Horizontal)
        self.scroll.valueChanged.connect(self.on_scroll)
        layout.addWidget(self.scroll)
        bottom=QHBoxLayout()
        self.info=QLabel('Keine Datei geladen')
        bottom.addWidget(self.info,1)
        jump=QPushButton('Cursor → Hex')
        jump.clicked.connect(self.jump_cursor)
        bottom.addWidget(jump)
        self.define=QPushButton('Markierung → Kennfeld')
        self.define.setEnabled(False)
        self.define.clicked.connect(self.create_map)
        bottom.addWidget(self.define)
        layout.addLayout(bottom)
        self._update_scroll()

    def set_image(self, image):
        self.image=image
        self.maps=[]
        self._map_ranges=[]
        self._map_starts=[]
        self._max_map_span=0
        self.start=0
        self.cursor=None
        self.selection=None
        self.invalidate()
        self._update_scroll()
        self.update_inspector()

    def set_maps(self, maps):
        self.maps=list(maps)
        self._map_ranges=sorted(self.maps,key=lambda m:m.offset)
        self._map_starts=[m.offset for m in self._map_ranges]
        self._max_map_span=max((m.length for m in self._map_ranges),default=0)
        self.graph.update()

    def invalidate(self, deferred=False):
        self._cache_key=None
        self._cache=None
        if deferred:
            if not self._redraw_timer.isActive():
                self._redraw_timer.start(16)
        else:
            self._redraw_timer.stop()
            self.graph.update()

    def graph_redraw(self):
        self.graph.update()

    def trace(self):
        if self.image is None:
            return None
        # 2 extrema per screen pixel are sufficient; drawing 2400 vertices
        # when the plot is 450px wide wastes CPU during rapid scrolling.
        budget=max(300, min(2400, 2*max(150,self.graph.width()-110)))
        key=(id(self.image),self.image.revision,self.start,self.count,self.dtype,self.endian,budget)
        if key != self._cache_key:
            self._cache=raw_trace(self.image,self.start,self.count,self.dtype,self.endian,max_points=budget)
            self._cache_key=key
        return self._cache

    def _update_scroll(self):
        total=(self.image.size//self.word_width) if self.image else 0
        max_idx=max(0,total-1)
        self.scroll.blockSignals(True)
        self.scroll.setRange(0,max_idx)
        self.scroll.setPageStep(max(1,self.count))
        self.scroll.setSingleStep(max(1,self.count//32))
        self.scroll.setValue(min(max_idx,self.start//self.word_width))
        self.scroll.blockSignals(False)
        self.offset_box.setText(f'0x{self.start:08X}')

    def on_format_change(self,unused=None):
        self.dtype=self.dtype_box.currentText()
        self.endian=self.endian_box.currentText()
        self.word_width=FORMATS[self.dtype][1]
        self.start=self.start//self.word_width*self.word_width
        self.selection=None
        self.invalidate()
        self._update_scroll()
        self.update_inspector()

    def on_count_change(self,unused=None):
        self.count=self.count_box.currentData()
        self.invalidate()
        self._update_scroll()
        self.update_inspector()

    def on_scroll(self,word_index):
        self.go_offset(word_index*self.word_width, sync=False)

    def on_offset_enter(self):
        if not self.image: return
        try:
            offset=parse_offset(self.offset_box.text())
            if not 0 <= offset < self.image.size:
                raise ValueError('Außerhalb des geöffneten Datenbereichs')
            self.go_offset(offset)
        except ValueError as exc:
            QMessageBox.warning(self,'Offset ungültig',str(exc))
            self.offset_box.setText(f'0x{self.start:08X}')

    def go_offset(self,offset, sync=True):
        if not self.image or not self.image.size:return
        total=self.image.size//self.word_width
        if total == 0:return
        self.start=max(0,min(int(offset)//self.word_width,total-1))*self.word_width
        self.cursor=self.start
        self.selection=None
        self.invalidate(deferred=True)
        if sync:self._update_scroll()
        else:self.offset_box.setText(f'0x{self.start:08X}')
        self.update_inspector()

    def zoom_by(self,levels):
        index=max(0,min(self.count_box.count()-1, self.count_box.currentIndex()+levels))
        self.count_box.setCurrentIndex(index)

    def update_inspector(self):
        if self.image is None:
            self.info.setText('BIN / ORI / MOD öffnen – keine Kennfeldauswahl notwendig')
        elif self.selection:
            a,b=self.selection
            self.info.setText(f'Markiert: 0x{a:08X}–0x{b-1:08X}  ·  {b-a:,} Byte  ·  '
                              f'{(b-a)//self.word_width:,} Werte  ·  Typ/Dimension selbst prüfen')
        else:
            self.info.setText(f'Cursor: 0x{(self.cursor if self.cursor is not None else self.start):08X}  ·  '
                              f'Fenster: {self.count:,} Rohwerte  ·  Keine Funktionszuordnung')
        self.define.setEnabled(self.selection is not None)

    def jump_cursor(self):
        if self.image and self.image.size:
            self.jump_callback(self.cursor if self.cursor is not None else self.start)

    def create_map(self):
        if self.selection is not None:
            self.define_callback(self.selection[0],self.selection[1],self.dtype,self.endian)
