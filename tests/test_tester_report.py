"""Local tester report: preview first, export only with the consent code of exactly that content, counts only
(quality phase 3, synthetic)."""
import json

import numpy as np
import pytest

from ecu_studio.tools import tester_report as T


def _pair(tmp_path):
    data = bytearray(0x4000)
    t = np.array([[20 + 11 * r + 5 * c + (r * c) % 3 for c in range(9)] for r in range(7)], np.uint8)
    data[0x1000:0x1000 + t.size] = t.tobytes()
    b = tmp_path / 'VIN_WBA0000000_customer.bin'
    b.write_bytes(bytes(data))
    ref = tmp_path / 'secret_project.csv'
    ref.write_text('name,offset,rows,cols,dtype,endian,factor,bias,unit,kind,notes\n'
                   'KF_SECRET_NAME,0x1000,7,9,u8,big,1,0,,Unbekannt,\n', encoding='utf-8')
    return b, ref


def test_preview_writes_nothing_and_shows_the_complete_export(tmp_path, capsys):
    b, ref = _pair(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert T.main([str(b), str(ref), '--line', 'Synthetisch']) == 0
    out = capsys.readouterr().out
    assert 'Vorschau' in out and '--consent' in out
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    for private in ('KF_SECRET_NAME', 'VIN_', 'secret_project', '0x1000', '4096', str(tmp_path)):
        assert private not in out


def test_export_needs_the_code_of_this_content(tmp_path, capsys):
    b, ref = _pair(tmp_path)
    target = tmp_path / 'report.json'
    assert T.main([str(b), str(ref), '--line', 'Synthetisch', '--export', str(target), '--consent', 'falsch']) == 2
    assert not target.exists()
    code = T.consent_code(T.measure(str(b), str(ref), 'Synthetisch'))
    assert T.main([str(b), str(ref), '--line', 'Synthetisch', '--export', str(target), '--consent', code]) == 0
    report = json.loads(target.read_text(encoding='utf-8'))
    assert report['format'] == T.FORMAT and report['detection']['exact_2d'] == 1
    assert report['line'] == 'Synthetisch' and 'KF_SECRET_NAME' not in target.read_text(encoding='utf-8')
    assert T.main([str(b), str(ref), '--line', 'Synthetisch', '--export', str(target), '--consent', code]) == 2
    other = T.consent_code(T.measure(str(b), str(ref), 'Andere Linie'))
    assert other != code                       # a changed content needs a new preview


def test_private_fields_are_refused():
    with pytest.raises(ValueError):
        T.check_private({'detection': {'sha256': 'ab'}})
    with pytest.raises(ValueError):
        T.check_private({'detection': {'offset': 4096}})
    with pytest.raises(ValueError):
        T.check_private({'axis_references': {'objects': [1, 2]}})
    with pytest.raises(ValueError):
        T.check_private({'function_identification': {'table@0.5': 'FN_SECRET'}})
    T.check_private({'line': 'Bosch MEVD17.2', 'detection': {'exact_2d': 3}})
