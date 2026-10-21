from pathlib import Path
import random
import struct
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.detection import discover_maps, _guess_kind
import numpy as np


def test_raw_type_guesses_are_explicitly_weak():
    assert _guess_kind(np.full((16,16),1400))[0]=="Boost-Verdacht"
    assert _guess_kind(np.full((16,16),50))[0]=="AGR-Verdacht"
    assert _guess_kind(np.full((16,16),6500))[0]=="Unbekannt"


def test_structural_scan_has_candidates_without_claiming_verification():
    rng=random.Random(11)
    data=bytearray(rng.randbytes(10000))
    for r in range(16):
        for c in range(16):
            struct.pack_into(">H",data,0x800+(r*16+c)*2, 950+62*r+17*c)
    result=discover_maps(BinaryImage(bytes(data)),max_results=40,scan_limit_mb=1)
    assert result
    assert all(not m.verified and m.source=="heuristic" for m in result)
    assert all(m.confidence < 0.5 for m in result)


def test_synthetic_demo_identifies_both_structures():
    # The demo is constructed to have simple 16x16 surfaces and is not ECU firmware.
    from ecu_studio.core.definitions import import_definitions
    base=Path(__file__).resolve().parents[1]/"examples"/"demo"
    demo=BinaryImage((base/"demo_synthetic.bin").read_bytes())
    result=discover_maps(demo)
    inferred={(m.offset,m.kind,m.endian) for m in result}
    assert (0x1000,"Boost-Verdacht","big") in inferred
    assert (0x2000,"AGR-Verdacht","big") in inferred
    imported=import_definitions(str(base/"demo_definitions.csv"),demo.size)
    assert imported[0].kind=="Boost" and imported[1].kind=="AGR"
    assert all(not x.verified for x in imported)
