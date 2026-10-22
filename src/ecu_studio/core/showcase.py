"""Synthetic showcase image for documentation clips; NOT a real ECU firmware.

Packed count/axis records (nx, ny, X[nx], Y[ny], Z[ny][nx], 16-bit big endian)
with smooth, made-up surfaces between filler bytes. The scanner finds them
through the same record evidence it uses on real files, so the clips show the
real detection path without shipping any manufacturer data.
"""
from __future__ import annotations
import math
import random
import struct
from pathlib import Path

RPM = [800, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500]
LOAD = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160]


def _surface(kind: int, nx: int, ny: int) -> list[list[int]]:
    rows = []
    for r in range(ny):
        u = r / max(1, ny - 1)
        row = []
        for c in range(nx):
            v = c / max(1, nx - 1)
            if kind == 0:      # boost-like plateau
                z = 1000 + 1400 * (1 - math.exp(-3 * u)) * (0.4 + 0.6 * math.sin(math.pi * min(1, v * 1.2)))
            elif kind == 1:    # ignition-like ridge
                z = 2200 + 1800 * v - 1500 * u + 300 * math.sin(4 * v + 2 * u)
            elif kind == 2:    # torque-like bowl
                z = 3000 - 2000 * (u - 0.6) ** 2 - 1200 * (v - 0.45) ** 2 + 800 * u
            else:              # lambda-like saddle
                z = 1000 + 180 * math.tanh(3 * (u - 0.7)) * math.tanh(3 * (v - 0.6)) - 90 * u
            row.append(max(0, min(65535, int(z))))
        rows.append(row)
    return rows


def _record(nx: int, ny: int, kind: int) -> bytes:
    x = [int(a) for a in (RPM[:nx] if nx <= 16 else range(800, 800 + 400 * nx, 400))]
    y = [int(a) for a in LOAD[:ny]]
    z = _surface(kind, nx, ny)
    out = struct.pack('>HH', nx, ny) + struct.pack(f'>{nx}H', *x) + struct.pack(f'>{ny}H', *y)
    for row in z:
        out += struct.pack(f'>{nx}H', *row)
    return out


def generate_showcase(folder: str) -> Path:
    rnd = random.Random(2026)
    data = bytearray(rnd.randbytes(0x8000))
    data[0x40:0x40 + 32] = b'SYNTHETIC SHOWCASE - NOT AN ECU '
    sizes = [(16, 16), (16, 12), (12, 12), (16, 10), (10, 8), (8, 8), (16, 16), (12, 10),
             (14, 12), (16, 8), (11, 9), (16, 16), (12, 16), (10, 10), (16, 14), (9, 7)]
    for block in range(3):
        chain = bytearray()
        for i, (nx, ny) in enumerate(sizes):
            chain += _record(nx, ny, (i + block) % 4)
            chain += b'\x00' * (len(chain) % 2)
        data += chain
        data += rnd.randbytes(0x1800)
    path = Path(folder) / 'showcase_synthetisch.bin'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))
    return path
