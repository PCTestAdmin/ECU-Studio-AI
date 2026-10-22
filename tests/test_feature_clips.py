import numpy as np


def test_gif_writer_round_trip(tmp_path):
    from PySide6.QtGui import QGuiApplication, QImage, QImageReader
    from ecu_studio.tools.gif_writer import write_gif
    app = QGuiApplication.instance() or QGuiApplication([])
    frames = []
    for i in range(4):
        f = np.full((60, 90, 3), 30, np.uint8)
        f[10:30, 5 + 15 * i:25 + 15 * i] = (240, 80, 20)
        frames.append(f)
    frames.append(frames[-1].copy())          # identical frame extends the delay
    path = tmp_path / 'clip.gif'
    write_gif(path, frames, [100] * 5)
    assert path.read_bytes()[:6] == b'GIF89a'
    reader = QImageReader(str(path))
    assert reader.imageCount() == 4
    images = [reader.read() for _ in range(4)]
    assert not any(im.isNull() for im in images)
    last = images[-1].convertToFormat(QImage.Format.Format_RGB888)
    assert last.pixelColor(5 + 45 + 2, 15).red() > 200 and last.pixelColor(2, 2).red() < 60


def test_showcase_is_synthetic_and_detected(tmp_path):
    from ecu_studio.core.model import BinaryImage
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    from ecu_studio.core.showcase import generate_showcase
    path = generate_showcase(str(tmp_path))
    assert b'SYNTHETIC SHOWCASE - NOT AN ECU' in path.read_bytes()
    maps = scan_calibration_candidates(BinaryImage.from_file(str(path)), use_definitions=True)
    assert sum(1 for m in maps if m.rows > 1 and m.cols > 1) >= 40
