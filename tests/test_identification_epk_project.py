"""EPK project refinement and Siemens data set names (1.21.0, synthetic images only)."""
from ecu_studio.core.identification import identify
from ecu_studio.core.model import BinaryImage


def image(*parts: bytes, size=0x4000) -> BinaryImage:
    data = bytearray(b'\xff' * size)
    pos = 0x100
    for p in parts:
        data[pos:pos + len(p)] = p
        pos += len(p) + 0x200
    return BinaryImage(bytes(data))


EPK = b'40/1/MED17/11/MEVD172X//1234567B/Dst00//'


def test_platform_epk_with_spelled_project_reports_the_variant():
    ident = identify(image(EPK, b'\x00MEVD17.2\x00', b'\x00MED17\x00'))
    assert ident.family == 'MEVD17.2' and ident.level == 'eindeutig'
    assert ident.project == 'MEVD172X'
    assert ident.family_evidence == 'Bosch-EPK @ 0x100 (Plattform MED17, Projekt MEVD172X, Klartext MEVD17.2)'
    assert 'Projekt MEVD172X' in ident.summary()


def test_platform_epk_without_plain_text_keeps_the_platform_and_names_the_project():
    ident = identify(image(EPK))
    assert ident.family == 'MED17' and ident.level == 'eindeutig' and ident.project == 'MEVD172X'


def test_plain_text_that_the_project_does_not_spell_stays_ambiguous():
    for text in (b'\x00MEVD17.2.3\x00', b'\x00ME7.5\x00'):
        ident = identify(image(EPK, text))
        assert ident.family is None and ident.level == 'mehrdeutig'


def test_coarser_plain_text_does_not_refine():
    ident = identify(image(EPK, b'\x00MEVD17\x00'))       # as before 1.21.0: platform vs. other text
    assert ident.family is None and ident.level == 'mehrdeutig'


def test_siemens_data_set_name_is_reported_as_software_not_family():
    ident = identify(image(b'CA4AB123' + b'4AB12300' + b'\x00' * 8 + b'CA4AB123.DAT0044'))
    assert ident.software == ['CA4AB123.DAT'] and ident.family is None and ident.level == 'unbekannt'
    assert any(m.kind == 'Siemens-Datensatz' for m in ident.markers)
    assert identify(image(b'XCA4AB123.DAT')).software == []          # inside a longer token
