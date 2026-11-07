"""negative_benchmark: classification of finds on a program image, version stability (synthetic files only)."""
import json
import struct
from ecu_studio.tools import negative_benchmark as nb
from test_architecture_false_finds import arm_image, _string_slots


def _image(tmp_path, name, shift=0):
    data = arm_image()
    names = _string_slots([f'TLE8888.INJ{k}' for k in range(1, 29)])
    data[0x18000 + shift:0x18000 + shift + len(names)] = names
    p = struct.pack('<64I', *[0x08010001 + 0x34 * k for k in range(64)])
    data[0x1A000:0x1A000 + len(p)] = p
    path = tmp_path / name
    path.write_bytes(bytes(data))
    return path


def test_negative_benchmark_reports_architecture_levels_and_wrong_classes(tmp_path):
    path = _image(tmp_path, 'a.bin')
    r = nb.evaluate({'name': 'A', 'family': 'synthetic', 'architecture': 'ARM', 'path': str(path)})
    assert r['architecture_detected'] == 'ARM' and r['architecture_expected'] == 'ARM'
    assert r['finds'] == sum(r['tiers'].values()) == r['certainly_wrong'] + r['unclear']
    assert r['finds_per_mib'] >= 0 and r['elapsed_s'] > 0 and r['peak_mb'] > 0
    assert len(r['sha256']) == 64 and r['size'] == path.stat().st_size
    # The scan itself suppresses proven text/pointer finds: none may remain.
    assert r['wrong'].get('text', 0) == 0 and r['wrong'].get('pointer', 0) == 0
    assert r['text_bytes'] > 0 and r['pointer_bytes'] >= 256
    json.dumps(r)


def test_stability_matches_shifted_builds(tmp_path):
    a = nb.evaluate({'name': 'A', 'architecture': 'ARM', 'path': str(_image(tmp_path, 'a.bin'))})
    b = nb.evaluate({'name': 'B', 'architecture': 'ARM', 'path': str(_image(tmp_path, 'b.bin'))})
    data = (tmp_path / 'a.bin').read_bytes()
    s = nb.stability(a, b, data, data)
    assert s['stats'].get('bytes changed', 0) == 0
    assert s['stats'].get('stable', 0) == a['finds']
    assert s['stats']['only in B'] == 0


def _srec(address, payload, chunk=32):
    lines = []
    for i in range(0, len(payload), chunk):
        part = payload[i:i + chunk]
        body = (len(part) + 5).to_bytes(1, 'big') + (address + i).to_bytes(4, 'big') + part
        lines.append('S3' + body.hex().upper() + format(~sum(body) & 0xFF, '02X'))
    end = (5).to_bytes(1, 'big') + address.to_bytes(4, 'big')
    lines.append('S7' + end.hex().upper() + format(~sum(end) & 0xFF, '02X'))
    return '\n'.join(lines) + '\n'


def test_load_address_comes_from_the_srec_of_the_same_build(tmp_path):
    path = _image(tmp_path, 'a.bin')
    data = path.read_bytes()
    app = bytearray(data[0x8000:])
    app[0x1C:0x20] = b'\x12\x34\x56\x78'                        # update header field differs (rusEFI: 12 bytes)
    srec = tmp_path / 'a_update.srec'
    srec.write_text(_srec(0x08008000, bytes(app)))
    r = nb.load_address(data, {'path': str(path), 'srec': str(srec)})
    assert r['load_address'] == '0x8000000' and r['srec_offset_in_bin'] == 0x8000
    assert r['srec_differing_bytes'] == 4
    # Another build's SREC does not fit: no load address is claimed.
    other = tmp_path / 'b_update.srec'
    other.write_text(_srec(0x08008000, bytes(reversed(app))))
    assert 'load_address' not in nb.load_address(data, {'path': str(path), 'srec': str(other)})
