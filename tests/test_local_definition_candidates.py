from ecu_studio.core.model import BinaryImage
from ecu_studio.core.profiles import local_xdf_candidates

def test_local_xdf_selects_only_plausible_version_size_and_never_imports(tmp_path):
    data=bytearray(0x80000); data[0x70008:0x7000e]=b'430069'
    im=BinaryImage(bytes(data))
    ok=tmp_path/'Siemens_MS43_430069_stock_512K.xdf'; ok.write_text('<not-parsed/>')
    (tmp_path/'Siemens_MS43_430066_512K.xdf').write_text('<bad/>')
    (tmp_path/'Siemens_MS43_430069_64K.xdf').write_text('<bad/>')
    assert local_xdf_candidates(im,tmp_path)==[ok]
    assert im.dirty_bytes==0
