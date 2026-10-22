"""Minimal animated-GIF writer (GIF89a, LZW) using only NumPy.

Used by ``feature_clips`` to record short UI clips for the documentation
without an imaging dependency. One global palette is built from the most
frequent colours of all frames (15-bit buckets); every following frame only
stores the rectangle that changed since the previous one.
"""
from __future__ import annotations
import struct
from pathlib import Path
import numpy as np


def _palette(frames: list[np.ndarray], size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """Return (palette[size,3] uint8, lut[32768] uint8) for 15-bit colour keys."""
    hist = np.zeros(32768, np.int64)
    sums = np.zeros((32768, 3), np.float64)
    for f in frames:
        px = f.reshape(-1, 3)[::3]
        key = _key(px)
        hist += np.bincount(key, minlength=32768)
        for ch in range(3):
            sums[:, ch] += np.bincount(key, weights=px[:, ch], minlength=32768)
    used = np.flatnonzero(hist)
    top = used[np.argsort(hist[used])[::-1][:size]]
    palette = np.zeros((size, 3), np.uint8)
    palette[:len(top)] = np.round(sums[top] / hist[top, None]).astype(np.uint8)
    # Map every 15-bit key to the nearest palette colour.
    keys = np.arange(32768)
    centres = np.stack([(keys >> 10) & 31, (keys >> 5) & 31, keys & 31], 1).astype(np.float32) * 8.2258 + 4
    lut = np.empty(32768, np.uint8)
    pal = palette[:max(1, len(top))].astype(np.float32)
    for start in range(0, 32768, 4096):
        c = centres[start:start + 4096]
        d = ((c[:, None, :] - pal[None, :, :]) ** 2).sum(2)
        lut[start:start + 4096] = d.argmin(1)
    return palette, lut


def _key(px: np.ndarray) -> np.ndarray:
    px = px.astype(np.int32) >> 3
    return (px[..., 0] << 10) | (px[..., 1] << 5) | px[..., 2]


def _lzw(indices: bytes, min_code: int = 8) -> bytes:
    clear, end = 1 << min_code, (1 << min_code) + 1
    out = bytearray()
    bits = buf = 0
    width = min_code + 1

    def emit(code: int) -> None:
        nonlocal bits, buf
        buf |= code << bits
        bits += width
        while bits >= 8:
            out.append(buf & 255)
            buf >>= 8
            bits -= 8

    table = {}
    nxt = end + 1
    emit(clear)
    prefix = -1
    for b in indices:
        if prefix < 0:
            prefix = b
            continue
        k = (prefix << 8) | b
        code = table.get(k)
        if code is not None:
            prefix = code
            continue
        emit(prefix)
        if nxt < 4096:
            table[k] = nxt
            nxt += 1
            if nxt > (1 << width) and width < 12:
                width += 1
        else:
            emit(clear)
            table.clear()
            nxt, width = end + 1, min_code + 1
        prefix = b
    if prefix >= 0:
        emit(prefix)
    emit(end)
    if bits:
        out.append(buf & 255)
    blocks = bytearray([min_code])
    for i in range(0, len(out), 255):
        chunk = out[i:i + 255]
        blocks.append(len(chunk))
        blocks += chunk
    blocks.append(0)
    return bytes(blocks)


def write_gif(path: str | Path, frames: list[np.ndarray], durations_ms: list[int]) -> int:
    """Write RGB frames (H, W, 3 uint8, equal size) as a looping GIF; return bytes written."""
    h, w = frames[0].shape[:2]
    palette, lut = _palette(frames)
    data = bytearray(b'GIF89a' + struct.pack('<HHBBB', w, h, 0xF7, 0, 0) + palette.tobytes())
    data += b'\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00'
    previous = None
    pending = gce = 0
    for frame, ms in zip(frames, durations_ms):
        idx = lut[_key(frame)]
        if previous is None:
            box = (0, 0, w, h)
        else:
            changed = np.argwhere(idx != previous)
            if not len(changed):
                pending += ms          # identical frame: extend the previous delay
                struct.pack_into('<H', data, gce + 4, max(2, round(pending / 10)))
                continue
            (y0, x0), (y1, x1) = changed.min(0), changed.max(0) + 1
            box = (int(x0), int(y0), int(x1), int(y1))
        pending = ms
        x0, y0, x1, y1 = box
        gce = len(data)
        data += b'\x21\xF9\x04' + struct.pack('<BHBB', 0x04, max(2, round(ms / 10)), 0, 0)
        data += b'\x2C' + struct.pack('<HHHHB', x0, y0, x1 - x0, y1 - y0, 0)
        data += _lzw(np.ascontiguousarray(idx[y0:y1, x0:x1]).tobytes())
        previous = idx
    data += b'\x3B'
    Path(path).write_bytes(data)
    return len(data)

