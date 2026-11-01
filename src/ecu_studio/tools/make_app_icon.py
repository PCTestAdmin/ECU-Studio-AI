"""Build the program icon from a square-ish master image (PNG with transparency).

    python -m ecu_studio.tools.make_app_icon MASTER.png
    python -m ecu_studio.tools.make_app_icon --small-only      :: repaint 16-24 px, keep the larger entries

Writes ``src/ecu_studio/ui/assets/app.ico`` (16-256 px, PNG-compressed entries, read by Windows since Vista;
used for the .exe, the installer and the window) and ``app_icon.png`` (256 px, window icon without the Qt ICO
plugin). The transparent border is cropped to a square around the motif so small sizes stay as large as
possible; scaling halves step by step for clean downsampling. Only Qt (already a dependency) is used.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
SMALL = (16, 20, 24)     # painted by small_icon(): the scaled master is not recognizable this small
ASSETS = Path(__file__).resolve().parents[1] / 'ui' / 'assets'
MARGIN = 0.02            # share of the side kept free around the motif


def _crop_square(image):
    from PySide6.QtGui import QImage
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = image.width(), image.height()
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if image.pixel(x, y) >> 24 > 8:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise ValueError('image is fully transparent')
    left, top, right, bottom = min(xs), min(ys), max(xs) + 1, max(ys) + 1
    side = int(max(right - left, bottom - top) * (1 + 2 * MARGIN))
    cx, cy = (left + right) // 2, (top + bottom) // 2
    square = QImage(side, side, QImage.Format.Format_ARGB32)
    square.fill(0)
    from PySide6.QtGui import QPainter
    painter = QPainter(square)
    painter.drawImage(side // 2 - cx, side // 2 - cy, image)
    painter.end()
    return square


def _scaled(image, size: int):
    from PySide6.QtCore import Qt
    while image.width() >= 2 * size:
        image = image.scaled(image.width() // 2, image.height() // 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    return image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _png(image) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise RuntimeError('PNG encoding failed')
    buffer.close()
    return bytes(data)


def ico_bytes(pngs: dict[int, bytes]) -> bytes:
    """ICO container with one PNG-compressed 32-bit entry per size."""
    header = struct.pack('<HHH', 0, 1, len(pngs))
    offset = len(header) + 16 * len(pngs)
    entries, blobs = b'', b''
    for size, png in sorted(pngs.items()):
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    return header + entries + blobs


def small_icon(size: int):
    """The motif reduced for 16-24 px: chip body with pins, blue display and the rising cyan map curve.

    Scaled down, the master's swoosh ring and fine pins blur into a blob (and the dark ring disappears on dark
    taskbars), so these sizes are painted on the pixel grid instead: same colors and layout, no ring."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pin = max(2, round(size * 0.125))                        # pin length; the body sits inside the pins
    body = QRectF(pin, pin, size - 2 * pin, size - 2 * pin)
    count = 3 if size < 24 else 4
    step = body.width() / (count + 1)
    p.setPen(QPen(QColor('#9fb0c2'), 1))
    for i in range(1, count + 1):
        c = int(body.left() + step * i) + 0.5                  # centred on a pixel column/row: crisp lines
        p.drawLine(QPointF(c, 0.5), QPointF(c, pin))
        p.drawLine(QPointF(c, size - pin), QPointF(c, size - 0.5))
        p.drawLine(QPointF(0.5, c), QPointF(pin, c))
        p.drawLine(QPointF(size - pin, c), QPointF(size - 0.5, c))
    shade = QLinearGradient(body.topLeft(), body.bottomRight())
    shade.setColorAt(0, QColor('#55636f'))
    shade.setColorAt(1, QColor('#161c24'))
    p.setPen(QPen(QColor('#c3cfdb'), 1))
    p.setBrush(shade)
    radius = size / 10
    p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    inset = 2 if size < 24 else 3
    screen = body.adjusted(inset, inset, -inset, -inset)
    glow = QLinearGradient(screen.topLeft(), screen.bottomLeft())
    glow.setColorAt(0, QColor('#0b2f78'))
    glow.setColorAt(1, QColor('#1260d0'))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawRect(screen)
    x0, x1, y0, y1 = screen.left(), screen.right(), screen.top(), screen.bottom()
    curve = QPainterPath(QPointF(x0, y0 + screen.height() * 0.78))
    curve.cubicTo(QPointF(x0 + screen.width() * 0.45, y0 + screen.height() * 0.85),
                  QPointF(x0 + screen.width() * 0.5, y0 + screen.height() * 0.2), QPointF(x1, y0 + screen.height() * 0.22))
    area = QPainterPath(curve)
    area.lineTo(x1, y1)
    area.lineTo(x0, y1)
    area.closeSubpath()
    p.setBrush(QColor('#1d8bff'))
    p.drawPath(area)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor('#7ff3ff'), max(1.2, size / 13), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPath(curve)
    p.end()
    return image


def build(master: Path, out: Path = ASSETS) -> dict:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtGui import QGuiApplication, QImage
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (image plugins need an application)
    image = QImage(str(master))
    if image.isNull():
        raise ValueError(f'cannot read {master}')
    square = _crop_square(image)
    pngs = {size: _png(small_icon(size) if size in SMALL else _scaled(square, size)) for size in SIZES}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'app.ico').write_bytes(ico_bytes(pngs))
    (out / 'app_icon.png').write_bytes(pngs[256])
    return {'square': square.width(), 'ico_bytes': (out / 'app.ico').stat().st_size, 'sizes': list(SIZES)}


def ico_entries(data: bytes) -> dict[int, bytes]:
    """PNG entry per size of an ICO written by ico_bytes()."""
    count = struct.unpack('<H', data[4:6])[0]
    entries = {}
    for i in range(count):
        width, _, _, _, _, _, size, offset = struct.unpack('<BBBBHHII', data[6 + 16 * i:22 + 16 * i])
        entries[width or 256] = data[offset:offset + size]
    return entries


def refresh_small(out: Path = ASSETS) -> dict:
    """Repaint only the small sizes of the existing ICO; the larger entries stay byte for byte."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    pngs = ico_entries((out / 'app.ico').read_bytes())
    pngs.update({size: _png(small_icon(size)) for size in SMALL})
    (out / 'app.ico').write_bytes(ico_bytes(pngs))
    return {'ico_bytes': (out / 'app.ico').stat().st_size, 'repainted': list(SMALL)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('master', type=Path, nargs='?')
    parser.add_argument('--out', type=Path, default=ASSETS)
    parser.add_argument('--small-only', action='store_true', help='repaint only the 16-24 px entries of app.ico')
    args = parser.parse_args(argv)
    if not args.small_only and args.master is None:
        parser.error('MASTER is required unless --small-only is given')
    print(refresh_small(args.out) if args.small_only else build(args.master, args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
