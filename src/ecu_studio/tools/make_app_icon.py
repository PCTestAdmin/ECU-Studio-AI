"""Build the program icon from a square-ish master image (PNG with transparency).

    python -m ecu_studio.tools.make_app_icon MASTER.png

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


def build(master: Path, out: Path = ASSETS) -> dict:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtGui import QGuiApplication, QImage
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (image plugins need an application)
    image = QImage(str(master))
    if image.isNull():
        raise ValueError(f'cannot read {master}')
    square = _crop_square(image)
    pngs = {size: _png(_scaled(square, size)) for size in SIZES}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'app.ico').write_bytes(ico_bytes(pngs))
    (out / 'app_icon.png').write_bytes(pngs[256])
    return {'square': square.width(), 'ico_bytes': (out / 'app.ico').stat().st_size, 'sizes': list(SIZES)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('master', type=Path)
    parser.add_argument('--out', type=Path, default=ASSETS)
    args = parser.parse_args(argv)
    print(build(args.master, args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
