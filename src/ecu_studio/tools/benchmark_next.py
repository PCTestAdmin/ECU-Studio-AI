"""Repeatable synthetic whole-file benchmark, including Qt worker heartbeat."""
from __future__ import annotations
import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
import numpy as np
import psutil
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.scoped_scan import scan_calibration_candidates


class Worker(QThread):
    def __init__(self, image):
        super().__init__()
        self.image = image
        self.error = None
        self.count = 0

    def run(self):
        try:
            self.count = len(scan_calibration_candidates(self.image))
        except Exception as exc:
            self.error = str(exc)


def run(sizes=(1, 4, 8, 16), runs=3):
    app = QApplication.instance() or QApplication([])
    process = psutil.Process()
    results = []
    rng = np.random.default_rng(20261017)
    with tempfile.TemporaryDirectory() as tmp:
        for size in sizes:
            data = bytearray(rng.bytes(size * 1024**2))
            # A disclosed synthetic surface amid random bytes.
            y, x = np.mgrid[:16, :16]
            data[4096:4608] = (1000 + 20*x + 30*y + x*y).astype('>u2').tobytes()
            path = Path(tmp) / 'synthetic.bin'
            path.write_bytes(data)
            loads = []
            for _ in range(runs):
                start = time.perf_counter()
                image = BinaryImage.from_file(str(path))
                loads.append(1000*(time.perf_counter()-start))
            latencies = []
            ram = [process.memory_info().rss]
            previous = time.perf_counter()
            def tick():
                nonlocal previous
                now = time.perf_counter()
                latencies.append(1000*(now-previous))
                previous = now
                ram.append(process.memory_info().rss)
            timer = QTimer()
            timer.timeout.connect(tick)
            timer.start(10)
            worker = Worker(image)
            start = time.perf_counter()
            worker.start()
            while worker.isRunning():
                app.processEvents()
                time.sleep(.001)
            worker.wait()
            tick()
            timer.stop()
            analysis = time.perf_counter()-start
            from ecu_studio.ui.views import MapTableModel
            model = MapTableModel()
            model.set_map(image, MapDefinition('synthetic',4096,16,16))
            start = time.perf_counter()
            render_error = None
            try:
                model.values()
            except Exception as exc:
                render_error = repr(exc)
            decode = 1000*(time.perf_counter()-start)
            results.append(dict(size_mb=size, load_ms=loads, load_median_ms=statistics.median(loads),
                                analysis_seconds=analysis, analysis_runs=1, candidates=worker.count,
                                error=worker.error, rss_sampled_peak_mb=max(ram)/1024**2,
                                heartbeat_max_ms=max(latencies), heartbeat_ticks=len(latencies),
                                surface_decode_ms=decode if render_error is None else None,
                                surface_error=render_error))
    return dict(platform=platform.platform(), python=platform.python_version(), seed=20261017,
                data='synthetic random bytes plus one surface; NOT real firmware',
                limitations='Warm OS cache; sampled process RSS, not allocator peak; Qt event heartbeat, not display FPS. Existing scanners have their own 8 MiB/default limits.',
                results=results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--sizes', type=int, nargs='+', default=[1,4,8,16])
    parser.add_argument('--repeats',type=int,default=1)
    args = parser.parse_args()
    if not 1<=args.repeats<=10 or any(n not in (1,4,8,16) for n in args.sizes):
        raise ValueError('1–10 Wiederholungen und Größen 1/4/8/16 MiB erforderlich')
    reports=[run(args.sizes) for _ in range(args.repeats)]
    result=reports[0]
    if args.repeats>1:
        for i,entry in enumerate(result['results']):
            entries=[r['results'][i] for r in reports]
            times=[e['analysis_seconds'] for e in entries]
            entry['analysis_seconds_runs']=times
            entry['analysis_seconds']=statistics.median(times)
            entry['analysis_runs']=len(times)
            entry['heartbeat_max_ms']=max(e['heartbeat_max_ms'] for e in entries)
            entry['rss_sampled_peak_mb']=max(e['rss_sampled_peak_mb'] for e in entries)
        result['repetitions']=reports[1:]
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
