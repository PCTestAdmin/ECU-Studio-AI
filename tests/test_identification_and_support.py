"""ECU identification from stored markers and the measured support matrix."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.identification import identify
from ecu_studio.core import support


def _image(*chunks):
    buf = bytearray(0x4000)
    pos = 0x100
    for c in chunks:
        buf[pos:pos + len(c)] = c
        pos += len(c) + 0x200
    return BinaryImage(bytes(buf))


def test_bosch_epk_names_the_family_with_its_offset():
    ident = identify(_image(b'33/1/EDC17_CP09/11/P_574//V8KB///'))
    assert ident.family == 'EDC17CP09'
    assert ident.family_evidence == 'Bosch-EPK @ 0x100'
    assert ident.epk.startswith('33/1/EDC17_CP09')


def test_bosch_notation_is_normalised():
    assert identify(_image(b'55/1/MED91/5/4420.01//D915A/')).family == 'MED9.1'
    assert identify(_image(b'40/1/ME7.5/3/4019.20//24B/')).family == 'ME7.5'


def test_placeholder_epk_and_two_family_names_stay_ambiguous():
    # BMW EDC16 dumps: placeholder EPK and both C31 and C35 in plain text.
    ident = identify(_image(b'99/1/EDC16C31/999/X000/X/0X0000_000/______', b'EDC16C35', b'EDC16C31'))
    assert ident.family is None and ident.ambiguous == ['EDC16C31', 'EDC16C35']
    assert 'mehrdeutig' in ident.summary()


def test_hardware_software_and_part_numbers():
    ident = identify(_image(b'1037370888' + b'0281011964', b'8V0907404A', b'5WK90027'))
    assert ident.hardware == ['0281011964', '5WK90027'] and ident.software == ['1037370888']
    assert ident.part_numbers == ['8V0907404A']
    assert all(m.offset >= 0x100 for m in ident.markers)


def test_no_markers_means_no_identity():
    ident = identify(BinaryImage(bytes(range(256)) * 64))
    assert ident.family is None and not ident.ambiguous and not ident.hardware
    assert 'keine Kennung' in ident.summary()


def test_support_matrix_is_measured_not_claimed():
    entries = support.load()
    assert entries and all(e.status in support.STATUSES for e in entries)
    for e in entries:
        complete = [s for s in e.software if s['complete_reference']]
        if e.status == 'validiert':
            assert any(s['precision_2d'] >= .5 and s['exact_2d'] >= .2 * s['reference_2d'] for s in complete), e.family
        elif e.status == 'teilweise':
            # partial reference only, or complete reference with insufficient precision (said in limits)
            assert e.software and (not complete or 'unzureichend' in e.limits), e.family
        else:
            assert not e.software, e.family          # no numbers without a measurement
            assert e.needed or e.limits, e.family    # and it says what is missing


def test_support_matrix_lists_the_target_families_and_finds_identities():
    names = ' '.join(e.family for e in support.load())
    for family in ('EDC17CP09', 'MED17.5', 'MD1', 'MG1', 'Simos', 'SID807', 'MSD80', 'EDC16C34'):
        assert family in names
    assert support.lookup('EDC17CP09').status == 'validiert'
    assert support.lookup('MD1CS001').status == 'nicht validiert'
    assert support.lookup('unbekannt') is None and support.lookup(None) is None


def test_support_matrix_file_holds_counts_only():
    raw = json.loads(support.DATA.read_text(encoding='utf-8'))
    text = json.dumps(raw)
    assert ':\\\\' not in text and '/Users/' not in text and 'Temp' not in text


def test_support_dialog_shows_every_family():
    from PySide6.QtWidgets import QApplication
    from ecu_studio.ui.support_dialog import SupportDialog
    app = QApplication.instance() or QApplication([])
    dialog = SupportDialog(None, 'Familie EDC17CP09')
    assert dialog.table.rowCount() == len(support.load())
    cells = [dialog.table.item(r, 2).text() for r in range(dialog.table.rowCount())]
    assert any('validiert' in c for c in cells)


def test_continental_plain_text_names_and_parent_lookup():
    assert identify(_image(b'SIMOS 18.1')).family == 'SIMOS18.1'
    assert identify(_image(b'SID807EVO')).family == 'SID807EVO'
    assert identify(_image(b'MG1CS002')).family == 'MG1CS002'
    assert identify(_image(b'xxSIDE')).family is None                 # no digits, no family
    assert support.lookup('SIMOS18.1').family.startswith('Continental Simos')
    assert support.lookup('MED17.1.62.9').family == 'Bosch MED17.1.62'


def test_matrix_takes_new_family_measurements_by_family_name():
    from ecu_studio.tools.support_matrix import build
    row = {'name': 'Bosch MG1CS002 probe', 'family': 'Bosch MG1CS002', 'role': 'test', 'complete_reference': True,
           'group': 'x', 'reference_2d': 100, 'found_2d': 80, 'exact_2d': 60, 'type_exact_2d': 55, 'axes_correct': 50,
           'with_axes': 50, 'reference_1d': 10, 'exact_1d': 5, 'seconds': 1.0, 'peak_mb': None, 'recall_2d': .7,
           'precision_2d': .8, 'false_positives_2d': 16}
    entries = {e['family']: e for e in build([{'rows': [row]}])['entries']}
    mg1 = next(e for name, e in entries.items() if name.startswith('Bosch MG1'))
    assert mg1['status'] == 'validiert' and mg1['software'][0]['exact_2d'] == 60
    md1 = next(e for name, e in entries.items() if name.startswith('Bosch MD1'))
    assert md1['status'] == 'nicht validiert' and not md1['software']
