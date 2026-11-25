"""Graphical recognition check (quality phase 6, synthetic files only): format and fit checks, analysis in a
background thread with cancel and close, results, export only after preview and consent, voluntary feedback,
same export as the command line."""
import json
import threading
import time

import numpy as np
import pytest

pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication  # noqa: E402

from ecu_studio.tools import tester_core as core  # noqa: E402
from ecu_studio.tools import tester_report as T  # noqa: E402
from ecu_studio.ui import tester_assistant as A  # noqa: E402

SECRETS = ('KF_SECRET_NAME', 'VIN_', 'WBA0000000', 'secret_project')


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _pair(tmp_path, n=2):
    data = bytearray(0x4000)
    rows = []
    for i in range(n):
        t = np.array([[20 + 11 * r + 5 * c + (r * c) % 3 + i for c in range(9)] for r in range(7)], np.uint8)
        at = 0x1000 + i * 0x400
        data[at:at + t.size] = t.tobytes()
        rows.append(f'KF_SECRET_NAME_{i},{hex(at)},7,9,u8,big,1,0,,Unbekannt,\n')
    b = tmp_path / 'VIN_WBA0000000_customer.bin'
    b.write_bytes(bytes(data))
    ref = tmp_path / 'secret_project.csv'
    ref.write_text('name,offset,rows,cols,dtype,endian,factor,bias,unit,kind,notes\n' + ''.join(rows),
                   encoding='utf-8')
    return b, ref


def _settle(app, dlg, timeout=60):
    end = time.monotonic() + timeout
    while dlg.running() and time.monotonic() < end:
        app.processEvents()
        time.sleep(.01)
    assert not dlg.running()
    for _ in range(5):
        app.processEvents()


def _ready(app, tmp_path, n=2):
    b, ref = _pair(tmp_path, n)
    dlg = A.TesterAssistant()
    assert dlg.set_firmware(str(b))
    dlg.set_reference(str(ref))
    dlg.line_edit.setText('Synthetisch')
    dlg.check_reference()
    _settle(app, dlg)
    assert dlg.reference_ok, dlg.reference_status.text()
    return dlg, b, ref


def _analysed(app, tmp_path, n=2):
    dlg, b, ref = _ready(app, tmp_path, n)
    dlg.go(3)
    dlg.start_analysis()
    _settle(app, dlg)
    assert dlg.counts is not None, dlg.analysis_status.text()
    return dlg, b, ref


def _visible_text(dlg):
    from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit
    parts = [w.text() for w in dlg.findChildren(QLabel)] + [w.text() for w in dlg.findChildren(QLineEdit)]
    parts += [w.toPlainText() for w in dlg.findChildren(QPlainTextEdit)]
    return '\n'.join(parts)


# ------------------------------------------------------------------------------------------------- input checks

@pytest.mark.parametrize('kind', ['missing', 'empty', 'text', 'filler', 'hex', 'zip', 'definition', 'exe'])
def test_invalid_firmware_is_refused_with_a_reason(app, tmp_path, kind):
    f = tmp_path / ('fw.a2l' if kind == 'definition' else 'fw.exe' if kind == 'exe' else 'fw.bin')
    content = {'empty': b'', 'text': b'hello world, no firmware\n' * 200, 'filler': b'\xff' * 0x4000,
               'hex': b':10000000' + b'00' * 16 + b'F0\r\n' * 100, 'zip': b'PK\x03\x04' + b'\x00' * 4000,
               'definition': b'/begin PROJECT x\n' + b'\x01' * 4000, 'exe': b'MZ' + bytes(range(256)) * 20}
    if kind != 'missing':
        f.write_bytes(content[kind])
    dlg = A.TesterAssistant()
    assert not dlg.set_firmware(str(f))
    assert dlg.image is None and dlg.firmware_status.text()
    assert str(tmp_path) not in dlg.firmware_status.text()
    dlg.go(2)
    assert dlg.stack.currentIndex() == 0          # cannot move on without a checked firmware


def test_wrong_reference_is_refused(app, tmp_path):
    b, _ = _pair(tmp_path)
    other = tmp_path / 'other.csv'               # tables outside this firmware
    other.write_text('name,offset,rows,cols,dtype,endian,factor,bias,unit,kind,notes\n'
                     'KF_SECRET_NAME,0x9000,7,9,u8,big,1,0,,Unbekannt,\n', encoding='utf-8')
    dlg = A.TesterAssistant()
    dlg.set_firmware(str(b))
    dlg.set_reference(str(other))
    dlg.line_edit.setText('Synthetisch')
    dlg.check_reference()
    _settle(app, dlg)
    assert not dlg.reference_ok and 'KF_SECRET' not in dlg.reference_status.text()
    assert not dlg.next.isEnabled() or dlg.stack.currentIndex() != 2


@pytest.mark.parametrize('damage', ['broken', 'empty', 'missing', 'unsupported'])
def test_broken_or_missing_definition_is_refused(app, tmp_path, damage):
    b, ref = _pair(tmp_path)
    if damage == 'broken':
        ref.write_text('name;offset\nKF_SECRET_NAME;0x1000;;;\n\x00\x01', encoding='utf-8')
    elif damage == 'empty':
        ref.write_text('', encoding='utf-8')
    elif damage == 'missing':
        ref.unlink()
    else:
        ref = ref.with_suffix('.ols')
        ref.write_bytes(b'x' * 100)
    dlg = A.TesterAssistant()
    dlg.set_firmware(str(b))
    dlg.set_reference(str(ref))
    dlg.line_edit.setText('Synthetisch')
    dlg.check_reference()
    _settle(app, dlg)
    assert not dlg.reference_ok
    text = dlg.reference_status.text()
    assert text and str(tmp_path) not in text and 'KF_SECRET' not in text


def test_private_line_name_is_refused_before_reading(app, tmp_path):
    b, ref = _pair(tmp_path)
    dlg = A.TesterAssistant()
    dlg.set_firmware(str(b))
    dlg.set_reference(str(ref))
    dlg.line_edit.setText('MEVD17.2 SW 1037512345')
    dlg.check_reference()
    assert dlg.job is None and not dlg.reference_ok


# -------------------------------------------------------------------------------------------------- analysis

def test_analysis_runs_in_background_and_matches_the_command_line(app, tmp_path):
    dlg, b, ref = _analysed(app, tmp_path)
    assert dlg.stack.currentIndex() == 4
    assert dlg.counts['detection']['exact_2d'] == 2
    dlg.go(5)
    cli = T.measure(str(b), str(ref), 'Synthetisch')
    assert dlg.report == cli                         # GUI and CLI give the same export
    dlg.exact_box.setChecked(True)
    assert dlg.report == T.measure(str(b), str(ref), 'Synthetisch', exact=True)


def test_scanner_never_receives_the_definition(app, tmp_path, monkeypatch):
    import ecu_studio.core.scoped_scan as S
    seen = []
    original = S.scan_calibration_candidates

    def spy(image, **kw):
        seen.append(kw.get('use_definitions'))
        assert not image.maps if hasattr(image, 'maps') else True
        return original(image, **kw)
    monkeypatch.setattr(S, 'scan_calibration_candidates', spy)
    _analysed(app, tmp_path)
    assert seen == [False]


def _slow(started):
    def fn(*a, cancelled=None, progress=None, **k):
        started.set()
        while not cancelled():
            time.sleep(.01)
        raise core.Cancelled()
    return fn


def test_cancel_discards_the_analysis(app, tmp_path, monkeypatch):
    dlg, _, _ = _ready(app, tmp_path)
    started = threading.Event()
    monkeypatch.setattr(core, 'measure_counts', _slow(started))
    dlg.go(3)
    dlg.start_analysis()
    assert started.wait(10)
    assert not dlg.back.isEnabled() and not dlg.start_button.isEnabled()
    dlg.cancel_analysis()
    _settle(app, dlg)
    assert dlg.counts is None and 'Abgebrochen' in dlg.analysis_status.text()
    assert dlg.start_button.isEnabled() and dlg.stack.currentIndex() == 3


def test_closing_the_window_during_the_analysis_stops_it_first(app, tmp_path, monkeypatch):
    dlg, _, _ = _ready(app, tmp_path)
    started = threading.Event()
    monkeypatch.setattr(core, 'measure_counts', _slow(started))
    dlg.show()
    dlg.go(3)
    dlg.start_analysis()
    assert started.wait(10)
    dlg.close()                                       # does not close while the thread runs
    assert dlg.isVisible() or dlg.running()
    _settle(app, dlg)
    assert not dlg.isVisible() and dlg.counts is None


def test_repeated_starts_run_once_and_late_results_are_ignored(app, tmp_path, monkeypatch):
    dlg, _, _ = _ready(app, tmp_path)
    calls = []
    release = threading.Event()

    def fn(*a, cancelled=None, progress=None, **k):
        calls.append(1)
        release.wait(10)
        return {'detection': {}, 'axis_references': {}, 'function_identification': {}}
    monkeypatch.setattr(core, 'measure_counts', fn)
    dlg.go(3)
    dlg.start_analysis()
    dlg.start_analysis()                             # ignored: one analysis at a time
    dlg.start_button.click()
    release.set()
    _settle(app, dlg)
    assert len(calls) == 1
    # a new input invalidates a result that arrives later
    release.clear()
    dlg.start_analysis()
    dlg.generation += 1                              # e.g. the window started something else meanwhile
    release.set()
    _settle(app, dlg)
    assert len(calls) == 2


def test_failure_shows_only_the_error_kind(app, tmp_path, monkeypatch):
    dlg, _, _ = _ready(app, tmp_path)

    def boom(*a, **k):
        raise RuntimeError(f'{tmp_path} KF_SECRET_NAME 0x1000')
    monkeypatch.setattr(core, 'measure_counts', boom)
    dlg.go(3)
    dlg.start_analysis()
    _settle(app, dlg)
    text = dlg.analysis_status.text()
    assert 'RuntimeError' in text and str(tmp_path) not in text and 'KF_SECRET' not in text


# ---------------------------------------------------------------------------------------------- results/export

def test_results_explain_recall_precision_and_not_evaluable(app, tmp_path):
    dlg, _, _ = _analysed(app, tmp_path)
    text = dlg.result_text.text()
    assert 'Trefferquote' in text and 'Präzision' in text and 'nicht bewertbar' in text
    rows = dict(dlg.bars.rows)
    assert rows['Trefferquote 2D'] == 1.0 and rows['Präzision'] is None
    assert dlg.function_table.rowCount() == len(core.SPLITS)


def test_export_is_not_written_without_consent(app, tmp_path):
    dlg, _, _ = _analysed(app, tmp_path)
    dlg.go(5)
    target = tmp_path / 'r.json'
    assert not dlg.save_button.isEnabled()
    assert not dlg.save_report(str(target)) and not target.exists()
    dlg.consent_box.setChecked(True)
    assert dlg.save_report(str(target))
    saved = json.loads(target.read_text(encoding='utf-8'))
    assert saved == dlg.report and saved['precision'] == 'gerundet'
    core.check_private(saved)
    text = target.read_text(encoding='utf-8')
    for s in SECRETS + (str(tmp_path), tmp_path.name):
        assert s not in text
    assert not dlg.save_report(str(target))           # never overwrites
    assert 'existiert bereits' in dlg.export_status.text()


def test_preview_shows_exactly_the_file_content(app, tmp_path):
    dlg, _, _ = _analysed(app, tmp_path)
    dlg.go(5)
    assert dlg.preview.toPlainText() == core.canonical(dlg.report)
    dlg.consent_box.setChecked(True)
    dlg.exact_box.setChecked(True)                    # a new content needs a new consent
    assert not dlg.consent_box.isChecked()
    assert dlg.preview.toPlainText() == core.canonical(dlg.report) and dlg.report['precision'] == 'exakt'


def test_manipulated_export_after_the_preview_is_refused(app, tmp_path):
    dlg, _, _ = _analysed(app, tmp_path)
    dlg.go(5)
    dlg.consent_box.setChecked(True)
    dlg.report['detection']['found_2d'] = 7           # changed after it was shown
    target = tmp_path / 'r.json'
    assert not dlg.save_report(str(target)) and not target.exists()
    assert 'Zustimmungscode' in dlg.export_status.text()


@pytest.mark.parametrize('extra', [{'path': 'C:/x.bin'}, {'detection': {'offset': 4096}},
                                   {'line': 'MEVD17.2 1037512345'}, {'note': 'anderer Text'},
                                   {'function_identification': {'names': ['KF_SECRET_NAME']}}])
def test_disallowed_metadata_is_refused(app, tmp_path, extra):
    dlg, _, _ = _analysed(app, tmp_path)
    dlg.go(5)
    dlg.consent_box.setChecked(True)
    dlg.report = {**dlg.report, **extra}
    dlg.shown_code = core.consent_code(dlg.report)    # even with a matching code
    target = tmp_path / 'r.json'
    assert not dlg.save_report(str(target)) and not target.exists()
    assert 'abgelehnt' in dlg.export_status.text()


def test_rounding_from_100(app, tmp_path):
    counts = {'detection': {'reference_2d': 1158, 'exact_2d': 37}, 'axis_references': {'objects': 812},
              'function_identification': {}}
    rounded = core.build_report(counts, 'Synthetisch', 'x.a2l')
    assert rounded['detection'] == {'reference_2d': 1200, 'exact_2d': 37}
    assert rounded['axis_references'] == {'objects': 810}
    exact = core.build_report(counts, 'Synthetisch', 'x.a2l', exact=True)
    assert exact['detection']['reference_2d'] == 1158
    core.check_private(rounded)
    core.check_private(exact)


def test_feedback_has_fixed_choices_and_needs_consent(app, tmp_path):
    dlg = A.TesterAssistant()
    dlg.go(6)
    target = tmp_path / 'f.json'
    assert not dlg.save_feedback(str(target)) and not target.exists()
    dlg.rating_group.button(2).setChecked(True)
    dlg.topic_boxes[0].setChecked(True)
    assert not dlg.feedback_consent.isChecked()       # a changed feedback needs a new consent
    dlg.feedback_consent.setChecked(True)
    assert dlg.save_feedback(str(target))
    saved = json.loads(target.read_text(encoding='utf-8'))
    core.check_feedback(saved)
    assert saved['rating'] == core.FEEDBACK_RATINGS[1] and saved['topic_1'] is True
    assert dlg.feedback_preview.toPlainText() == core.canonical(saved)
    with pytest.raises(ValueError):
        core.check_feedback({**saved, 'comment': 'frei'})
    with pytest.raises(ValueError):
        core.feedback_report('super', ())


def test_no_network_code_in_core_and_assistant():
    import inspect
    for mod in (core, A):
        src = inspect.getsource(mod)
        for word in ('urllib', 'socket', 'requests', 'http.client', 'smtplib', 'QNetwork', 'webbrowser'):
            assert word not in src, (mod.__name__, word)


def test_menu_entry_opens_the_assistant(app, monkeypatch):
    from ecu_studio.ui.main_window import Window
    opened = []
    monkeypatch.setattr('ecu_studio.ui.tester_assistant.TesterAssistant.exec', lambda self: opened.append(self))
    win = Window()
    try:
        win.actions['Kennfelderkennung überprüfen (lokaler Test) …'].trigger()
        assert opened and isinstance(opened[0], A.TesterAssistant)
    finally:
        win.hide()
        win.deleteLater()
