"""Evidence-backed GS20 identification without speculative map naming."""
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.profiles import identify_profile, xdf_match_status
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def gs20_fixture():
    b=bytearray(65536)
    b[0x176:0x17e]=b'GADC9010'
    b[0x3fd8:0x3fdf]=b'7557997'
    b[0xffc8:0xffd8]=b'G2210_0090C0AD10'
    return bytes(b)


def test_gs20_exact_signatures():
    p=identify_profile(BinaryImage(gs20_fixture()))
    assert p.family=='Siemens GS20'
    assert p.controller.startswith('Getriebe')
    assert p.calibration_id=='GADC9010'
    assert p.calibration_number=='7557997' and p.software_version is None
    assert p.project_id=='G2210_0090C0AD10'
    assert (p.cal_start,p.cal_end,p.full_read)==(0,65536,False)


def test_gs20_512k_window():
    full=bytearray(524288)
    full[0x10000:0x20000]=gs20_fixture()
    p=identify_profile(BinaryImage(bytes(full)))
    assert p.family=='Siemens GS20'
    assert (p.cal_start,p.cal_end,p.full_read)==(0x10000,0x20000,True)


def test_gs20_requires_multiple_evidence_markers():
    b=bytearray(gs20_fixture())
    b[0xffc8:0xffd8]=b' '*16
    assert not identify_profile(BinaryImage(bytes(b))).identified
    b=bytearray(gs20_fixture())
    b[0x176:0x17e]=b' '*8
    assert not identify_profile(BinaryImage(bytes(b))).identified
    assert not identify_profile(BinaryImage(bytes(65536))).identified


def test_xdf_mismatched_calibration_is_rejected():
    profile=identify_profile(BinaryImage(gs20_fixture()))
    assert xdf_match_status(profile,'Siemens_GS20_G10C9000_64K.xdf')[0]=='rejected'
    assert xdf_match_status(profile,'MS43_430069_64K.xdf')[0]=='rejected'
    assert xdf_match_status(profile,'Siemens_GS20_GADC9010_512K.xdf')[0]=='rejected'
    assert xdf_match_status(profile,'Siemens_GS20_GADC9010_64K.xdf')[0]=='plausible'
    assert xdf_match_status(profile,'unknown_gs20_64K.xdf')[0]=='unverified'


def test_gs20_scanner_does_not_invent_types():
    b=bytearray(gs20_fixture())
    for r in range(12):
        for c in range(12):
            off=0x9000+2*(r*12+c)
            b[off:off+2]=(100+10*r+2*c).to_bytes(2,'big')
    maps=scan_calibration_candidates(BinaryImage(bytes(b)),limits=(10,5,5,5))
    assert all(m.kind=='Unbekannt' for m in maps)
    assert all('GS20' in m.label_origin for m in maps)
    assert all(m.offset < 65536 for m in maps)


def test_identity_banner_uses_profile_signatures_when_there_is_no_epk():
    """Siemens files carry no EPK: identification must agree with the window title (profile)."""
    from ecu_studio.core.identification import identify
    ident = identify(BinaryImage(gs20_fixture()))
    assert ident.family == 'GS20' and 'GS20' in ident.family_evidence
    assert identify(BinaryImage(bytes(65536))).family is None        # nothing invented for empty data
