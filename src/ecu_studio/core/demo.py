"""Synthetic demonstration file; NOT a real ECU firmware/calibration."""
from pathlib import Path
import random
import struct
from .definitions import export_definitions
from .model import MapDefinition


def generate_demo(folder: str) -> tuple[Path, Path]:
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    bin_path = target / 'demo_synthetisch.bin'
    defs_path = target / 'demo_synthetisch.maps.csv'
    data = bytearray(random.Random(461).randbytes(64 * 1024))
    boost = MapDefinition(name='DEMO · Ladedruck Soll (fiktiv)', offset=0x2000, rows=16, cols=16,
                          dtype='u16', endian='big', factor=1, unit='mbar',
                          kind='Boost', source='synthetic',
                          notes='Nur DEMO. Werte keinem Fahrzeug zuordnen.')
    egr = MapDefinition(name='DEMO · AGR-Soll (fiktiv)', offset=0x5000, rows=16, cols=16,
                        dtype='u16', endian='big', factor=1, unit='%',
                        kind='AGR', source='synthetic',
                        notes='Nur DEMO. Keine fahrzeugspezifische Kalibrierung.')
    for r in range(16):
        for c in range(16):
            pressure = min(2800, 850 + r*72 + c*36 + r*c//2)
            rate = max(0, min(100, 82 - r*4 - c*2 + (c//4)*2))
            struct.pack_into('>H', data, boost.offset + 2*(r*16+c), pressure)
            struct.pack_into('>H', data, egr.offset + 2*(r*16+c), rate)
    bin_path.write_bytes(data)
    export_definitions(str(defs_path), [boost, egr])
    return bin_path, defs_path
