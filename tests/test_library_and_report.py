import random
import struct
from pathlib import Path
import pytest

from ecu_studio.core.demo import generate_demo
from ecu_studio.core.definitions import import_definitions
from ecu_studio.core.library import MapLibrary
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.report import export_html, report_html


def test_synthetic_demo_is_labeled_only_via_csv(tmp_path):
    binary, csv_path = generate_demo(str(tmp_path))
    image = BinaryImage.from_file(str(binary))
    definitions = import_definitions(str(csv_path), image.size)
    assert len(definitions) == 2
    assert [m.offset for m in definitions] == [0x2000, 0x5000]
    assert all(not m.verified for m in definitions)
    assert 800 < image.raw_value(definitions[0], 0, 0) < 1000
    assert 0 <= image.raw_value(definitions[1], 10, 10) <= 100


def test_user_confirmed_library_recognizes_unambiguous_exact_bytes(tmp_path):
    binary, csv_path = generate_demo(str(tmp_path))
    image = BinaryImage.from_file(str(binary))
    defs = import_definitions(str(csv_path), image.size)
    lib = MapLibrary(tmp_path / 'library.json')
    with pytest.raises(ValueError, match='manuell geprüft'):
        lib.add(image, defs[0])
    defs[0].verified = True
    lib.add(image, defs[0])
    assert len(lib.signatures) == 1
    cloned = MapLibrary(tmp_path / 'library.json')
    found = cloned.find(image)
    assert len(found) == 1
    assert found[0].offset == defs[0].offset
    assert found[0].kind == 'Boost' and not found[0].verified
    assert 'Referenztreffer' in found[0].label_origin and found[0].type_score > 0
    assert found[0].source == 'exact-reference'


def test_ambiguous_pattern_is_not_auto_tagged(tmp_path):
    binary, csv_path = generate_demo(str(tmp_path))
    image = BinaryImage.from_file(str(binary))
    m = import_definitions(str(csv_path), image.size)[0]
    m.verified = True
    lib = MapLibrary(tmp_path / 'library.json')
    lib.add(image, m)
    payload = image.read(m.offset, m.length)
    ambiguous = BinaryImage(payload + b'\xff' * 128 + payload)
    assert lib.find(ambiguous) == []


def test_change_report_includes_map_ranges_but_escapes_html(tmp_path):
    binary, csv_path = generate_demo(str(tmp_path))
    image = BinaryImage.from_file(str(binary))
    m = import_definitions(str(csv_path), image.size)[0]
    m.name = '<unsafe> Boost'
    image.write(m.offset, b'\x00\x01')
    page = report_html(image, [m], '<script>')
    assert '&lt;unsafe&gt;' in page and '&lt;script&gt;' in page
    assert '0x00002000' in page
    out = tmp_path / 'report.html'
    export_html(str(out), image, [m], 'ok')
    assert out.exists() and 'Geänderte Bytes' in out.read_text(encoding='utf-8')
