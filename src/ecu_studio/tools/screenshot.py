"""Render the main window offscreen to PNG files (docs and visual review).

Usage: python -m ecu_studio.tools.screenshot BIN OUT_DIR [--size WxH]
       python -m ecu_studio.tools.screenshot --version-compare OUT_DIR
The second form renders the version comparison dialog with two synthetic sister
versions (fixed seed, no manufacturer data).
Uses a temporary settings scope so the user's window layout is untouched.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path


def synthetic_versions():
    """Two related synthetic images: B = A with 32 bytes inserted, one map changed, one gone."""
    import numpy as np
    from ecu_studio.core.model import BinaryImage, MapDefinition
    rng = np.random.default_rng(23)
    a = bytearray(rng.integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    maps = []
    for k in range(12):
        rows, cols, off = 8, 12, 0x2000 + k * 0x200
        z = np.add.outer(np.arange(rows) * (7 + k), np.arange(cols) * (3 + k % 4)) + 10 * k
        a[off:off + rows * cols * 2] = z.astype('<u2').tobytes()
        maps.append(MapDefinition(f'Synthetisch_KF_{k:02d}', off, rows, cols, 'u16', 'little', factor=.1,
                                  unit='%', source='xdf'))
    b = bytearray(a[:0x1000] + rng.integers(0, 256, 32, dtype=np.uint8).tobytes() + a[0x1000:-32])
    for k in (2, 5, 9):
        off = 0x2000 + k * 0x200 + 32
        z = np.frombuffer(bytes(b[off:off + 192]), '<u2').astype(int)
        z[::5] += 3
        b[off:off + 192] = z.astype('<u2').tobytes()
    gone = 0x2000 + 11 * 0x200 + 32
    b[gone - 16:gone + 208] = rng.integers(0, 256, 224, dtype=np.uint8).tobytes()
    return BinaryImage(bytes(a)), maps, BinaryImage(bytes(b))


def version_compare(out: Path, app) -> None:
    from ecu_studio.core.version_compare import compare_versions
    from ecu_studio.ui.main_window import Window
    from ecu_studio.ui.version_compare_dialog import VersionCompareDialog
    source, maps, target = synthetic_versions()
    out.mkdir(parents=True, exist_ok=True)
    for theme in ('dark', 'light'):
        win = Window()
        win.set_theme(theme)
        win.load_state(target, [], [], '', None)
        dialog = VersionCompareDialog(win)
        dialog.resize(1280, 820)
        dialog.source, dialog.source_maps, dialog.source_label = source, maps, 'Synthetischer Stand A'
        dialog.source_info.setText(f'Stand A: Synthetischer Stand A · {len(maps)} Definitionen')
        dialog.compared(compare_versions(source, maps, target, win.maps))
        dialog.mark_unique()
        dialog.table.selectRow(2)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(out / f'{theme}-version-compare.png'))
        dialog.hide()
        win.deleteLater()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin', nargs='?')
    parser.add_argument('out', type=Path)
    parser.add_argument('--size', default='1510x930')
    parser.add_argument('--version-compare', action='store_true')
    parser.add_argument('--map-pack', action='store_true')
    args = parser.parse_args(argv)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if sys.platform == 'win32':
        # The offscreen platform finds no system fonts on its own.
        os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    QCoreApplication.setOrganizationName('ECU Studio Screenshot')
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    if args.map_pack:
        map_pack(args.out, app)
        return 0
    if args.version_compare:
        version_compare(args.out, app)
        print(f'Vergleichsdialog in {args.out}')
        return 0
    if not args.bin:
        parser.error('BIN fehlt')
    from ecu_studio.core.model import BinaryImage
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    from ecu_studio.ui.main_window import Window
    image = BinaryImage.from_file(args.bin)
    maps = scan_calibration_candidates(image, use_definitions=True)
    w, h = (int(v) for v in args.size.split('x'))
    args.out.mkdir(parents=True, exist_ok=True)
    for theme in ('dark', 'light'):
        win = Window()
        win.resize(w, h)
        win.set_theme(theme)
        win.load_state(image, maps, [], '', None)
        two_d = [i for i, m in enumerate(win.maps) if min(m.rows, m.cols) >= 6]
        if two_d:
            win.map_list.setCurrentIndex(win.catalog_model.index(two_d[0], 0))
            win.on_map_selection()
        win.show()
        for tab in (win.view2d, win.map_table, win.view3d):
            win.tabs.setCurrentWidget(tab)
            app.processEvents()
            name = {win.view2d: 'heatmap', win.map_table: 'table', win.view3d: '3d'}[tab]
            win.grab().save(str(args.out / f'{theme}-{name}.png'))
        win.hide()
        win.deleteLater()
    print(f'{len(maps)} Kandidaten; Screenshots in {args.out}')
    return 0


def map_pack(out, app):
    """Package preview screenshots, synthetic data and isolated local settings."""
    import tempfile
    from PySide6.QtCore import QSettings
    from PySide6.QtTest import QTest
    from ecu_studio.core.map_pack import make_pack, write_pack
    from ecu_studio.ui.main_window import Window
    from ecu_studio.ui.map_pack_dialog import MapPackDialog
    from ecu_studio.core.project_store import ProjectStore
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, folder)
        source, maps, _ = synthetic_versions()
        for m in maps[:4]:
            m.axis_x_offset = 0x1800; m.axis_x_ref = 'SYNTHETIC_SHARED_X'
        path = Path(folder) / 'synthetic.ecupack.json'
        write_pack(path, make_pack(source, maps[:4]))
        for theme in ('dark', 'light'):
            window = Window(); window.project_store = ProjectStore(Path(folder) / 'index.sqlite3')
            window.set_theme(theme); window.load_state(source, [], [], '', None)
            dialog = MapPackDialog(window, path)
            dialog.resize(1180, 760)
            assert dialog.worker.wait(10000)
            app.processEvents()
            dialog.show(); app.processEvents(); QTest.qWait(50)
            assert dialog.pack is not None
            dialog.grab().save(str(out / f'{theme}-map-pack.png'))
            dialog.close(); window.saved_fingerprint = window.project_state(); window.close()
            app.processEvents()


if __name__ == '__main__':
    raise SystemExit(main())
