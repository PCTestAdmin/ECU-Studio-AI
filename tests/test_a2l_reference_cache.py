"""1.19.1: the A2L reference cache never returns stale or shared map assignments.

Until 1.19.1 the cache key was the A2L *path* (plus image hash and anchor): a
definition edited under the same path, even at the same size, kept returning the
old records, and every caller received the same MapDefinition objects, so a
rename in one workflow (name transfer, version compare) leaked into the next.
All files here are synthetic; no firmware bytes.
"""
import gc
import threading
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.name_transfer import definition_maps, transfer_names
from ecu_studio.tools import structure_benchmark as sb

ANCHOR = 0x800000
MAPS = 24
MIB = 1024 * 1024


def _a2l(prefix='KF', factor=1):
    """24 maps with their own rising axes (KfUb: nX, nY, X[4], Y[3], 4 x 3 values) at 0x800000 + 0x40 k."""
    blocks = [f'/begin CHARACTERISTIC {prefix}_{k:02d} "map {k}" MAP 0x{ANCHOR + 0x40 * k:X} KfUb 0 NO_COMPU_METHOD 0 255\n'
              f'  /begin AXIS_DESCR STD_AXIS nmot NO_COMPU_METHOD 4 0 255 /end AXIS_DESCR\n'
              f'  /begin AXIS_DESCR STD_AXIS rl NO_COMPU_METHOD 3 0 255 /end AXIS_DESCR /end CHARACTERISTIC'
              for k in range(0, MAPS * factor, factor)]
    return ('/begin PROJECT P "" /begin MODULE M ""\n'
            '/begin MOD_COMMON "" BYTE_ORDER MSB_LAST ALIGNMENT_BYTE 1 /end MOD_COMMON\n'
            '/begin RECORD_LAYOUT KfUb NO_AXIS_PTS_X 1 UBYTE NO_AXIS_PTS_Y 2 UBYTE AXIS_PTS_X 3 UBYTE INDEX_INCR DIRECT\n'
            '  AXIS_PTS_Y 4 UBYTE INDEX_INCR DIRECT FNC_VALUES 5 UBYTE ROW_DIR DIRECT /end RECORD_LAYOUT\n'
            + '\n'.join(blocks) + '\n/end MODULE /end PROJECT\n')


def _bin(size=0x4000, tag=0):
    data = bytearray(size)
    for k in range(MAPS * 2):
        at = 0x40 * k
        record = [4, 3, 10, 20, 30, 40, 5, 15, 25] + [(k * 7 + i * 3) % 200 for i in range(12)]
        data[at:at + len(record)] = bytes(record)
    data[-1] = tag                                   # distinct images, same records
    return bytes(data)


HEADER = 9                                           # nX, nY, X[4], Y[3] in front of the values


def _names(maps):
    return {m.name for m in maps if m.rows * m.cols >= 2 and '.' not in m.name}


def _write(path, text):
    path.write_bytes(text.encode('utf-8'))
    return str(path)


def test_same_firmware_with_two_definitions_gets_each_definitions_maps(tmp_path):
    image = BinaryImage(_bin())
    a = _write(tmp_path / 'a.a2l', _a2l('KF'))
    b = _write(tmp_path / 'b.a2l', _a2l('KX', factor=2))         # other names and other places
    first, second = sb.a2l_reference(a, image), sb.a2l_reference(b, image)
    assert _names(first) == {f'KF_{k:02d}' for k in range(MAPS)}
    assert _names(second) == {f'KX_{k:02d}' for k in range(0, 2 * MAPS, 2)}
    assert {m.offset for m in second if m.name == 'KX_02'} == {0x80 + HEADER}
    assert _names(sb.a2l_reference(a, image)) == _names(first)


def test_definition_changed_under_the_same_path_and_size_is_linked_anew(tmp_path):
    image = BinaryImage(_bin())
    path = tmp_path / 'def.a2l'
    old, new = _a2l('KF'), _a2l('KG')
    assert len(old) == len(new)                                    # same size, other content
    _write(path, old)
    assert 'KF_00' in _names(sb.a2l_reference(str(path), image))
    _write(path, new)
    names = _names(sb.a2l_reference(str(path), image))
    assert 'KG_00' in names and not any(n.startswith('KF_') for n in names)
    # A changed record parameter (address) at the same size moves the map.
    moved = new.replace(f'0x{ANCHOR:X} KfUb', f'0x{ANCHOR + 0x40 * 30:X} KfUb')
    assert len(moved) == len(new)
    _write(path, moved)
    assert {m.offset for m in sb.a2l_reference(str(path), image) if m.name == 'KG_00'} == {0x40 * 30 + HEADER}


def test_callers_get_their_own_copies(tmp_path):
    image = BinaryImage(_bin())
    path = _write(tmp_path / 'def.a2l', _a2l())
    first = sb.a2l_reference(path, image)
    for m in first:
        m.name, m.notes, m.factor = 'RENAMED', 'adopted', 9.0
    again = sb.a2l_reference(path, image)
    assert 'RENAMED' not in _names(again) and all(m.factor == 1.0 for m in again)


def test_name_transfer_and_version_compare_follow_a_definition_change(tmp_path):
    from ecu_studio.ui.version_compare_dialog import load_source
    source_path = tmp_path / 'source.bin'
    source_path.write_bytes(_bin())
    target = BinaryImage(_bin(tag=1))
    definition = tmp_path / 'def.a2l'
    _write(definition, _a2l('KF'))
    before = transfer_names(BinaryImage(_bin()), target, definition_maps(str(definition), BinaryImage(_bin())))
    assert {t.target.name for t in before} >= {'KF_00', 'KF_23'}
    _, maps, _ = load_source(str(source_path), str(definition))
    assert 'KF_05' in _names(maps)
    _write(definition, _a2l('KG'))                                   # definition replaced in place
    after = transfer_names(BinaryImage(_bin()), target, definition_maps(str(definition), BinaryImage(_bin())))
    names = {t.target.name for t in after}
    assert names >= {'KG_00', 'KG_23'} and not any(n.startswith('KF_') for n in names)
    _, maps, _ = load_source(str(source_path), str(definition))
    assert 'KG_05' in _names(maps) and not any(n.startswith('KF_') for n in _names(maps))


def test_reopening_the_same_firmware_links_once_and_gives_equal_results(tmp_path, monkeypatch):
    path = _write(tmp_path / 'def.a2l', _a2l())
    calls = []
    link = sb._a2l_link
    monkeypatch.setattr(sb, '_a2l_link', lambda *a: calls.append(1) or link(*a))
    sb._A2L_CACHE.clear()
    results = [sb.a2l_reference(path, BinaryImage(_bin())) for _ in range(5)]   # "open project" five times
    assert len(calls) == 1
    assert all([(m.name, m.offset, m.rows, m.cols) for m in r] == [(m.name, m.offset, m.rows, m.cols) for m in results[0]]
               for r in results)


def test_parallel_access_returns_the_right_definition_to_every_thread(tmp_path):
    a = _write(tmp_path / 'a.a2l', _a2l('KF'))
    b = _write(tmp_path / 'b.a2l', _a2l('KX', factor=2))
    images = [BinaryImage(_bin(tag=t)) for t in range(3)]
    sb._A2L_CACHE.clear()
    jobs = [(a if k % 2 else b, images[k % 3]) for k in range(48)]
    barrier = threading.Barrier(8)

    def run(job):
        path, image = job
        try:
            barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            pass
        return path, _names(sb.a2l_reference(path, image))
    with ThreadPoolExecutor(8) as pool:
        for path, names in pool.map(run, jobs):
            prefix = 'KF_' if path == a else 'KX_'
            assert len(names) == MAPS and all(n.startswith(prefix) for n in names)
    assert len(sb._A2L_CACHE) <= sb.A2L_CACHE_SIZE


def test_project_switches_keep_no_firmware_and_no_definition_text(tmp_path):
    a = _write(tmp_path / 'a.a2l', _a2l('KF'))
    b = _write(tmp_path / 'b.a2l', _a2l('KX', factor=2))
    sb.a2l_reference(a, BinaryImage(_bin(MIB, 200)))                 # warm-up: imports
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.take_snapshot()
        for k in range(8):                                           # 8 projects, 1 MiB each, alternating definitions
            sb.a2l_reference(a if k % 2 else b, BinaryImage(_bin(MIB, k)))
        gc.collect()
        after = tracemalloc.take_snapshot()
        retained = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    def big(snapshot):
        return sorted(t.size for t in snapshot.traces if t.size >= MIB // 4)
    # No image-sized block survives (a kept firmware would be one 1 MiB block each);
    # the four cached entries hold linked records only (~1.6 KB per map object).
    assert big(after) == big(before)
    assert retained - sum(t.size for t in before.traces) < MIB, retained
    assert len(sb._A2L_CACHE) == sb.A2L_CACHE_SIZE
    sb._A2L_CACHE.clear()
