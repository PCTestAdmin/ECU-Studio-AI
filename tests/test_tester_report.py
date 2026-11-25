"""Local tester report: preview first, export only with the consent code of exactly that content, counts only,
checked line name, rounded totals, no private text in output, errors or export (quality phases 3/4, synthetic)."""
import io
import json
import logging

import numpy as np
import pytest

from ecu_studio.tools import tester_report as T

SECRETS = ('KF_SECRET_NAME', 'VIN_', 'WBA0000000', 'secret_project', '0x1000', '4096')


def _pair(tmp_path, n=1):
    data = bytearray(0x4000)
    rows = []
    for i in range(n):
        t = np.array([[20 + 11 * r + 5 * c + (r * c) % 3 + i for c in range(9)] for r in range(7)], np.uint8)
        at = 0x1000 + i * 0x40
        data[at:at + t.size] = t.tobytes()
        rows.append(f'KF_SECRET_NAME_{i},{hex(at)},7,9,u8,big,1,0,,Unbekannt,\n')
    b = tmp_path / 'VIN_WBA0000000_customer.bin'
    b.write_bytes(bytes(data))
    ref = tmp_path / 'secret_project.csv'
    ref.write_text('name,offset,rows,cols,dtype,endian,factor,bias,unit,kind,notes\n' + ''.join(rows),
                   encoding='utf-8')
    return b, ref


def _clean(text, tmp_path):
    for private in SECRETS + (str(tmp_path), tmp_path.name):
        assert private not in text, private


def test_preview_writes_nothing_and_shows_the_complete_export(tmp_path, capsys):
    b, ref = _pair(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert T.main([str(b), str(ref), '--line', 'Synthetisch']) == 0
    cap = capsys.readouterr()
    assert 'Vorschau' in cap.out and '--consent' in cap.out and 'Wiedererkennbarkeit' in cap.out
    assert 'keine unabhängige Validierung' in cap.out
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    _clean(cap.out + cap.err, tmp_path)


def test_export_needs_the_code_of_this_content(tmp_path, capsys):
    b, ref = _pair(tmp_path)
    target = tmp_path / 'report.json'
    assert T.main([str(b), str(ref), '--line', 'Synthetisch', '--export', str(target), '--consent', 'falsch']) == 2
    assert not target.exists()
    code = T.consent_code(T.measure(str(b), str(ref), 'Synthetisch'))
    assert T.main([str(b), str(ref), '--line', 'Synthetisch', '--export', str(target), '--consent', code]) == 0
    report = json.loads(target.read_text(encoding='utf-8'))
    assert report['format'] == T.FORMAT and report['detection']['exact_2d'] == 1
    assert report['line'] == 'Synthetisch' and report['precision'] == 'gerundet'
    _clean(target.read_text(encoding='utf-8'), tmp_path)
    T.check_private(report)
    assert T.main([str(b), str(ref), '--line', 'Synthetisch', '--export', str(target), '--consent', code]) == 2
    other = T.consent_code(T.measure(str(b), str(ref), 'Andere Linie'))
    assert other != code                       # a changed content needs a new preview
    _clean(capsys.readouterr().err, tmp_path)


def test_private_fields_are_refused():
    base = {'format': T.FORMAT, 'version': '1', 'line': 'Bosch MEVD17.2', 'precision': 'exakt'}
    for bad in ({'detection': {'sha256': 'ab'}}, {'detection': {'offset': 4096}},
                {'axis_references': {'objects': [1, 2]}}, {'function_identification': {'table@0.5': 'FN_SECRET'}},
                {'detection': {'exact_2d': b'\x01'}}, {'detection': {'KF_SECRET': 1}},
                {'extra_text': 'x'}, {'line': 'MEVD 1037512345'}, {'line': 'C:/Users/x/y.bin'}):
        with pytest.raises(ValueError):
            T.check_private(base | bad)
    T.check_private(base | {'detection': {'exact_2d': 3}})
    with pytest.raises(ValueError):            # claims rounded, carries an exact total
        T.check_private(base | {'precision': 'gerundet', 'detection': {'reference_2d': 1158}})
    T.check_private(base | {'precision': 'gerundet', 'detection': {'reference_2d': 1200, 'exact_2d': 37}})


@pytest.mark.parametrize('n, rounded', [(0, 0), (99, 99), (100, 100), (812, 810), (1158, 1200), (12345, 12000),
                                        (True, True), (0.5, 0.5)])
def test_totals_from_100_are_rounded_to_two_digits(n, rounded):
    assert T.round_count(n) == rounded


@pytest.mark.parametrize('line', ['Bosch MEVD17.2', 'Siemens MSD80', 'Delco D98', 'EDC16 (C31)'])
def test_plain_line_names_pass(line):
    assert T.check_line(line) == line


@pytest.mark.parametrize('line', ['', 'x', 'MEVD17.2 1037512345', 'DME 7123456', 'WBA0000000ABC1234',
                                  'MSD80 0x80000000', 'MSD80\nnote', 'C:\\Users\\a', 'a' * 41,
                                  'MSD80 "x"', 'deadbeefcafe'])
def test_line_with_numbers_paths_or_odd_characters_is_refused(line):
    with pytest.raises(T.TesterError):
        T.check_line(line)


def test_line_must_not_repeat_a_file_name():
    with pytest.raises(T.TesterError):
        T.check_line('customer', 'C:/x/VIN_customer.bin')


@pytest.mark.parametrize('damage', ['empty', 'truncated', 'random', 'bad_csv', 'missing'])
def test_manipulated_inputs_fail_without_private_text(tmp_path, capsys, damage):
    b, ref = _pair(tmp_path)
    if damage == 'empty':
        b.write_bytes(b'')
    elif damage == 'truncated':
        b.write_bytes(b.read_bytes()[:0x1010])
    elif damage == 'random':
        b.write_bytes(np.random.default_rng(1).integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    elif damage == 'bad_csv':
        ref.write_text('name;offset\nKF_SECRET_NAME;0x1000;;;\n\x00\x01', encoding='utf-8')
    else:
        b.unlink()
    target = tmp_path / 'r.json'
    code = T.main([str(b), str(ref), '--line', 'Synthetisch'])
    cap = capsys.readouterr()
    assert code in (0, 1, 2) and not target.exists()
    _clean(cap.out + cap.err, tmp_path)
    if code == 0:   # still measurable: the export stays counts only
        assert 'Vorschau' in cap.out


def test_logging_and_warnings_are_silenced_during_the_measurement(tmp_path, caplog):
    b, ref = _pair(tmp_path)
    with caplog.at_level(logging.DEBUG):
        T.measure(str(b), str(ref), 'Synthetisch')
    _clean(caplog.text, tmp_path)
    assert logging.root.manager.disable == 0


def test_assistant_saves_only_after_explicit_yes(tmp_path, monkeypatch):
    b, ref = _pair(tmp_path)
    monkeypatch.chdir(tmp_path)
    answers = iter([f'"{b}"', str(ref), 'Synthetisch', 'nein'])
    out = io.StringIO()
    assert T.assistant(lambda _: next(answers), out) == 0
    assert not list(tmp_path.glob('*.json')) and 'Nicht gespeichert' in out.getvalue()
    _clean(out.getvalue(), tmp_path)
    answers = iter([str(b), str(ref), 'Synthetisch', 'ja', ''])
    assert T.assistant(lambda _: next(answers), io.StringIO()) == 0
    saved = tmp_path / 'ecu-studio-testbericht.json'
    report = json.loads(saved.read_text(encoding='utf-8'))
    T.check_private(report)
    _clean(saved.read_text(encoding='utf-8'), tmp_path)
    answers = iter([str(b), str(ref), 'Synthetisch', 'ja', ''])
    with pytest.raises(T.TesterError):          # never overwrites
        T.assistant(lambda _: next(answers), io.StringIO())


def test_assistant_refuses_a_private_line_before_measuring(tmp_path, monkeypatch):
    b, ref = _pair(tmp_path)
    called = []
    monkeypatch.setattr(T, 'measure', lambda *a, **k: called.append(1))
    answers = iter([str(b), str(ref), 'MEVD17.2 SW 1037512345'])
    with pytest.raises(T.TesterError):
        T.assistant(lambda _: next(answers), io.StringIO())
    assert not called


def test_rounded_export_hides_exact_totals(tmp_path):
    b, ref = _pair(tmp_path, n=3)
    exact = T.measure(str(b), str(ref), 'Synthetisch', exact=True)
    rounded = T.measure(str(b), str(ref), 'Synthetisch')
    assert exact['precision'] == 'exakt' and rounded['precision'] == 'gerundet'
    assert {k: v for k, v in T.coarsen(exact['axis_references']).items()} == rounded['axis_references']


def test_no_network_code():
    import inspect
    src = inspect.getsource(T)
    for word in ('urllib', 'socket', 'requests', 'http.client', 'smtplib'):
        assert word not in src
