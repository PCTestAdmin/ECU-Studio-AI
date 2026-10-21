import pytest
from ecu_studio.recognition.intake import register_explicit_firmware
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.core.model import BinaryImage

def test_md1_claim_is_not_auto_verified(tmp_path):
    im=BinaryImage(b'\x11'*16384)
    db=DefinitionCatalog(tmp_path/'ecus.sqlite')
    with pytest.raises(ValueError):register_explicit_firmware(db,im,family='Bosch MD1',software='MD1CSXXX',variant='manual',expected_sha256=im.digest)
    with pytest.raises(ValueError,match='SHA'):
        register_explicit_firmware(db,im,family='Bosch MD1',software='MD1CSXXX',variant='manual',expected_sha256='0'*64,acknowledge=True)
    out=register_explicit_firmware(db,im,family='Bosch MD1',software='MD1CSXXX',variant='manual',expected_sha256=im.digest,acknowledge=True)
    assert out['status']=='user-declared-unverified'
    assert db.stats()['verified_maps']==0
    with pytest.raises(ValueError,match='Widerspr'):
        register_explicit_firmware(db,im,family='Bosch MG1',software='MG1XXX',variant='different',expected_sha256=im.digest,acknowledge=True)
