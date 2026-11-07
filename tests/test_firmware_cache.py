"""1.19.1 final review: no module-level cache keeps whole firmware images alive.

59f355d cached ``detect_architecture`` (lru_cache, 8 images as keys); 1.19.0
already did so for the C16x load address (8 images) and the A2L reference
(4 images). An open program therefore held up to 20 firmware files after their
projects were closed. These tests measure retained memory with tracemalloc on
synthetic images (no firmware bytes) and fail with any of those caches.
"""
import gc
import tracemalloc
from ecu_studio.core import architecture, structure_scan
from ecu_studio.core.architecture import detect_architecture, C16X
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from test_architecture_false_finds import c16x_image, arm_image, _with_c16x_references

MIB = 1024 * 1024


def _retained(run):
    """Bytes still allocated after ``run()`` returned and its local data was dropped."""
    # Warm-up: the first decision imports modules (about 0.7 MB), once per process.
    small = bytes(c16x_image(seed=98))
    detect_architecture(small)
    structure_scan.c16x_base(small)
    del small
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        run()
        gc.collect()
        return tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()


def _images(count, size, build=c16x_image):
    # Distinct images: the seed changes the bytes, the decision stays the same.
    for seed in range(count):
        yield bytes(build(size=size, seed=10 + seed))


def test_architecture_detection_of_ten_images_keeps_none_of_them():
    decisions = []

    def run():
        for data in _images(10, MIB):
            decisions.append(detect_architecture(data).name)
    retained = _retained(run)
    assert decisions == [C16X] * 10
    # One cached image would be 1 MiB; 59f355d kept eight.
    assert retained < MIB // 4, retained


def test_c16x_load_address_keeps_no_image():
    def run():
        for data in _images(10, MIB):
            structure_scan.c16x_base(data)
    assert _retained(run) < MIB // 4


def test_ten_scans_in_sequence_keep_no_firmware_and_decide_as_before():
    # Warm-up with the same image size: models, translations and, where workers are
    # available, the process pool start once. The pool's feeder thread then keeps one
    # pickled job until the next one replaces it (multiprocessing); that does not grow.
    scan_calibration_candidates(BinaryImage(bytes(c16x_image(size=0x40000, seed=99))), use_definitions=False)
    results = []

    def run():
        for data in _images(10, 0x40000):
            diag = {}
            found = scan_calibration_candidates(BinaryImage(data), use_definitions=False, diagnostics=diag)
            results.append((diag['architecture'].split(':')[0], len(found)))
    retained = _retained(run)
    assert [r[0] for r in results] == [C16X] * 10
    # 59f355d: 8 + 8 cached copies of 256 KiB images = 4 MiB.
    assert retained < MIB // 2, retained


def test_repeated_scan_and_reopened_project_give_identical_results_without_growth(tmp_path):
    path = tmp_path / 'c16x.bin'
    path.write_bytes(bytes(_with_c16x_references(c16x_image())))

    def scan():
        # "Open the project": a fresh image from the file, as the application loads it.
        diag = {}
        found = scan_calibration_candidates(BinaryImage(path.read_bytes()), use_definitions=False,
                                            diagnostics=diag)
        return diag['architecture'], [(m.offset, m.rows, m.cols, m.dtype, m.record_layout, m.evidence_tier)
                                      for m in found]
    first = scan()
    assert first[0].startswith('C16x:')
    assert any(o == 0x15000 and tier == 'Code-Beleg' for o, *_, tier in first[1])
    runs = []
    retained = _retained(lambda: runs.extend(scan() for _ in range(3)))
    assert all(r == first for r in runs)
    assert retained < 0x20000, retained


def test_architecture_decision_is_computed_once_per_scan(monkeypatch):
    calls = {'signs': 0, 'base': 0}
    signs, base = architecture.signs, structure_scan.c16x_base

    def counted_signs(data):
        calls['signs'] += 1
        return signs(data)

    def counted_base(data):
        calls['base'] += 1
        return base(data)
    monkeypatch.setattr(architecture, 'signs', counted_signs)
    monkeypatch.setattr(structure_scan, 'c16x_base', counted_base)
    import ecu_studio.core.scoped_scan as scoped
    monkeypatch.setattr(scoped, 'c16x_base', counted_base)
    data = bytes(_with_c16x_references(c16x_image()))
    scan_calibration_candidates(BinaryImage(data), use_definitions=False)
    assert calls == {'signs': 1, 'base': 1}
    # Equal input, equal decision: same result for bytes, bytearray and memoryview.
    assert detect_architecture(data) == detect_architecture(bytearray(data)) == detect_architecture(memoryview(data))
    assert detect_architecture(bytes(arm_image())).name == 'ARM'


def test_a2l_reference_cache_keeps_records_not_firmware(tmp_path):
    from ecu_studio.tools import structure_benchmark as sb
    from test_axis_groups import A2L, _a2l_bin
    a2l = tmp_path / 'ref.a2l'
    a2l.write_text(A2L)
    linked = []

    def run():
        for seed in range(6):
            data = bytearray(MIB)
            data[:0x1000] = _a2l_bin()
            data[0x800] = seed                                    # distinct images, same records
            linked.append(sb.a2l_reference(str(a2l), BinaryImage(bytes(data)), anchor=0x800000))
    retained = _retained(run)
    assert all(any(m.name == 'GKF_A' for m in maps) for maps in linked)
    # 1.19.0 kept four 1 MiB images as cache keys.
    assert retained < MIB // 2, retained
    # Linked records stay cached by SHA-256 (bounded), the images do not.
    assert len(sb._A2L_CACHE) == sb.A2L_CACHE_SIZE
    sb._A2L_CACHE.clear()
