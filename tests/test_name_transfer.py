"""Name transfer between sister software versions: anchored shifts, evidence classes, abstention."""
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.name_transfer import transfer_names, anchors


def _sisters():
    rng = np.random.default_rng(11)
    base = bytearray(rng.integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    y, x = np.mgrid[:8, :8]
    smooth = (40 + 5 * y + 3 * x).astype(np.uint8)
    base[0x1000:0x1040] = smooth.tobytes()                       # unchanged table
    base[0x5000:0x5040] = smooth.tobytes()[::-1]                 # table that will change values
    base[0x6000:0x6040] = bytes(64)                              # flat (zero) table
    target = bytearray(base[:0x3000] + rng.integers(0, 256, 0x200, dtype=np.uint8).tobytes() + base[0x3000:])
    t = 0x5000 + 0x200
    target[t:t + 64] = (np.frombuffer(bytes(target[t:t + 64]), np.uint8).astype(int) + 1).clip(0, 255).astype(np.uint8).tobytes()
    maps = [MapDefinition('A_unchanged', 0x1000, 8, 8, 'u8', 'big'),
            MapDefinition('B_changed', 0x5000, 8, 8, 'u8', 'big'),
            MapDefinition('C_flat', 0x6000, 8, 8, 'u8', 'big')]
    return BinaryImage(bytes(base)), BinaryImage(bytes(target)), maps


def test_anchor_chain_is_monotone():
    source, target, _ = _sisters()
    chain = anchors(source.read(0, source.size), target.read(0, target.size))
    assert chain and all(a[0] < b[0] and a[1] < b[1] for a, b in zip(chain, chain[1:]))


def test_names_follow_the_inserted_block_with_their_evidence():
    source, target, maps = _sisters()
    result = {t.source.name: t for t in transfer_names(source, target, maps)}
    assert result['A_unchanged'].target.offset == 0x1000 and result['A_unchanged'].evidence == 'identisch'
    assert result['B_changed'].target.offset == 0x5200 and result['B_changed'].evidence == 'ähnliche Werte'
    assert result['C_flat'].target.offset == 0x6200 and result['C_flat'].evidence == 'gleiche Umgebung'
    for t in result.values():
        assert t.target.source == 'transfer-proposed' and not t.target.verified
        assert t.target.name == t.source.name


def test_unrelated_image_gets_no_names():
    source, _, maps = _sisters()
    other = BinaryImage(np.random.default_rng(99).integers(0, 256, 0x8000, dtype=np.uint8).tobytes())
    assert transfer_names(source, other, maps) == []
