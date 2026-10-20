import pytest
from ecu_studio.formats.sniff import container_reason, check_raw_image


def test_proprietary_and_container_formats_are_refused_with_route():
    assert 'WinOLS-Projekt' in container_reason(b'\x0b\x00\x00\x00WinOLS File\x00' + b'\x00' * 40, 'x.ols')
    assert 'Mappack' in container_reason(b'\x00' * 64, 'pack.kp')
    assert 'ZIP' in container_reason(b'PK\x03\x04' + b'\x00' * 60, 'a.zip')
    assert 'Intel-HEX' in container_reason(b':020000040080FA\n:10000000', 'fw.hex')
    assert 'S-Record' in container_reason(b'S00F000068656C6C6F202020202000003C\n', 'fw.s19')
    assert 'Definitionsdatei' in container_reason(b'<XDFFORMAT', 'a.xdf')


def test_raw_ecu_images_pass(tmp_path):
    for name, head in (('ms43.bin', b'\x00\x01\xfa\x00' * 64), ('ori', b'\xff' * 256), ('mz.bin', b'MZ' + b'\x00' * 62)):
        assert container_reason(head, name) is None
    path = tmp_path / 'proj.ols'
    path.write_bytes(b'\x0b\x00\x00\x00WinOLS File\x00' + b'\x00' * 100)
    with pytest.raises(ValueError, match='nicht unterstützt'):
        check_raw_image(path)
