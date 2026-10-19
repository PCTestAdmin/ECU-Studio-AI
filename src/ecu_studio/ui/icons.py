"""Consistent line icons drawn from inline SVG, tinted to the active theme.

Own simple outlines (24 px grid, 2 px stroke); no third-party icon assets.
"""
from __future__ import annotations
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    'open': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'save': '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
            '<path d="M7 3v5h8V3"/><rect x="7" y="13" width="10" height="6" rx="1"/>',
    'export': '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    'a2l': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'
           '<path d="M9 14l-2 2 2 2"/><path d="M15 14l2 2-2 2"/>',
    'xdf': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'
           '<path d="M8 13h8"/><path d="M8 17h5"/>',
    'scan': '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/><path d="M11 8v6"/><path d="M8 11h6"/>',
    'raw2d': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/>'
             '<path d="M9 3v18"/><path d="M15 3v18"/>',
    'undo': '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    'redo': '<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>',
    'commands': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3"/><path d="M13 15h4"/>',
}


def line_icon(name: str, color: str, size: int = 20) -> QIcon:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
           f'{PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        icon.addPixmap(pixmap)
    return icon
