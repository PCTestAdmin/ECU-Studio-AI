"""The TriCore walk visits only the instructions that change its state (1.21.0, synthetic code).

Skipping the other instructions must not change any result: branch targets and jump
targets on skipped instructions, empty state lists after ``ret`` and targets inside a
32-bit instruction are replayed in address order. Checked against a walk that visits
every instruction of the sweep.
"""
import random
import numpy as np
from ecu_studio.core import tricore_refs as tr
from test_tricore_refs import RET, call, j16, load

NOP16 = (0x0000).to_bytes(2, 'little')          # no state change (16-bit)
ADD32 = (0x0B | 0x00 << 8).to_bytes(4, 'little')  # 32-bit RR form without address effect (bit 0 set)


def cond16(at, target):
    """jeq d15,#0,disp4 style forward branch (opcode 0x1E, disp4 zero-extended)."""
    return (0x1E | (((target - at) // 2) & 0xF) << 8).to_bytes(2, 'little')


def full_stream(data):
    h = tr._halfwords(data)
    ats, lens, ws = [], [], []
    for at, length, w in tr._sweep(h):
        ats.append(at); lens.append(length); ws.append(w)
    return ats, lens, ws, np.asarray(ats, dtype=np.int64)


def random_code(seed, size=0x4000):
    rnd = random.Random(seed)
    code = bytearray()
    while len(code) < size - 64:
        at = len(code)
        k = rnd.random()
        if k < .25:
            code += NOP16
        elif k < .40:
            code += ADD32
        elif k < .50:
            code += RET
        elif k < .60:   # forward branch onto a following no-op (skipped instruction)
            code += cond16(at, at + 2 + 2 * rnd.randint(0, 6))
        elif k < .68:
            code += j16(at, at + 2 + 2 * rnd.randint(0, 8))
        elif k < .85:
            code += load(rnd.choice((4, 5, 6)), 0x8000 + 2 * rnd.randint(0, 0x1000))
        else:
            code += call(at, 0x7000 + 2 * rnd.randint(0, 0x100))
    img = bytearray(0x10000)
    img[0x100:0x100 + len(code)] = code
    img[0x7000:0x7400] = RET * 0x200
    return bytes(img)


def same(a, b):
    return (list(a[0]) == list(b[0]) and sorted(a[0].generic) == sorted(b[0].generic)
            and a[0].unmapped == b[0].unmapped and a[1:] == b[1:])


def test_filtered_stream_gives_the_full_sweep_result():
    for seed in range(12):
        data = random_code(seed)
        h = tr._halfwords(data)
        bases = tr.global_bases(h)
        full = tr._walk(h, bases, len(data), stream=full_stream(data))
        fast = tr._walk(h, bases, len(data), stream=tr._stream(data))
        assert same(full, fast), seed
        assert len(tr._stream(data)[0]) < len(full_stream(data)[0])


def test_stream_skips_only_instructions_without_effect():
    data = random_code(99)
    ats, lens, words, starts = tr._stream(data)
    assert list(starts) == full_stream(data)[0]
    for at, length, w in zip(ats, lens, words):
        op = w & 0xFF
        assert (length == 2 and (w == 0x9000 or op in tr._ACT16 or op in tr._COND16_DISP4 | tr._COND16_DISP8)
                or length == 4 and (op in tr._ACT32 or op in tr._COND32))


def test_stream_is_compact_and_searchable():
    """Typed arrays (4 bytes per instruction, not ~36 for a list of ints): a 10-MB image has
    ~4 million instructions. The sorted start offsets stay int64 because searchsorted with
    Python ints copies an int32 array on every call."""
    from array import array
    ats, lens, words, starts = tr._stream(random_code(7))
    assert isinstance(ats, array) and ats.itemsize <= 4
    assert isinstance(lens, array) and lens.itemsize == 1
    assert isinstance(words, array) and words.itemsize == 4
    assert starts.dtype == np.int64
    assert tr._stream(b'')[3].size == 0
