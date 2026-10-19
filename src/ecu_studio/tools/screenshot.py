"""Render the main window offscreen to PNG files (docs and visual review).

Usage: python -m ecu_studio.tools.screenshot BIN OUT_DIR [--tab NAME]
Uses a temporary settings scope so the user's window layout is untouched.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin')
    parser.add_argument('out', type=Path)
    parser.add_argument('--size', default='1510x930')
    args = parser.parse_args(argv)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    QCoreApplication.setOrganizationName('ECU Studio Screenshot')
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
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


if __name__ == '__main__':
    raise SystemExit(main())
