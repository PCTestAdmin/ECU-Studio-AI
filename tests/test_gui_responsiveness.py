"""The window repaints while a scan thread runs pure Python (GIL hand-over, ecu_studio.main.keep_gui_responsive)."""
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]


def _repaint_while_busy(view) -> float:
    """Shortest of three repaints of the view while another thread computes in Python."""
    stop = threading.Event()

    def spin():
        while not stop.is_set():
            sum(i * i for i in range(200))
    worker = threading.Thread(target=spin)
    worker.start()
    try:
        time.sleep(.05)
        times = []
        for _ in range(3):
            started = time.perf_counter()
            view.grab()
            times.append(time.perf_counter() - started)
        return min(times)
    finally:
        stop.set()
        worker.join()


def test_repaint_during_a_python_scan_thread_is_not_held_up():
    from PySide6.QtCore import QAbstractTableModel, Qt
    from PySide6.QtWidgets import QApplication, QTableView
    from ecu_studio import main

    class Model(QAbstractTableModel):
        def rowCount(self, parent=None): return 60
        def columnCount(self, parent=None): return 16
        def data(self, index, role=Qt.ItemDataRole.DisplayRole):
            return f'{index.row() * index.column():.2f}' if role == Qt.ItemDataRole.DisplayRole else None

    app = QApplication.instance() or QApplication([])  # noqa: F841
    view = QTableView()
    view.setModel(Model())
    view.resize(1400, 900)
    view.grab()
    previous = sys.getswitchinterval()
    try:
        sys.setswitchinterval(.005)                       # Python's default: the scan thread keeps the GIL
        held_up = _repaint_while_busy(view)
        assert main.keep_gui_responsive() == main.GUI_SWITCH_INTERVAL <= .001
        responsive = _repaint_while_busy(view)
    finally:
        sys.setswitchinterval(previous)
    assert responsive * 3 < held_up, (responsive, held_up)


def test_application_and_exe_checks_start_with_the_short_hand_over():
    source = (ROOT / 'src' / 'ecu_studio' / 'main.py').read_text(encoding='utf-8')
    body = source[source.index('def main():'):source.index("if len(sys.argv)==3 and sys.argv[1]=='--smoke-test'")]
    assert 'keep_gui_responsive()' in body
