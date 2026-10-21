from pathlib import Path
import hashlib
import os
import pytest
from ecu_studio.core.model import BinaryImage
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.public_sources import (
    source_rows,map_hints,candidates,attach_ms43_preview,fetch_and_index,
    fetch_pinned_source)

MS43=Path(os.environ.get('ECU_STUDIO_MS43_REGRESSION_BIN','/mnt/data/MS43_430069_512KB.bin'))
GS20=Path(os.environ.get('ECU_STUDIO_GS20_REGRESSION_BIN','/mnt/data/GS20_90C0_64KB.bin'))

def test_real_public_index_is_seeded_idempotently(tmp_path):
    path=tmp_path/'catalog.sqlite'
    db=DefinitionCatalog(path)
    stats=db.stats()
    assert stats['public_sources']>=14
    assert stats['public_map_hints']==118
    assert stats['public_families']==4
    assert stats['verified_maps']==0
    assert stats['definitions']==0
    again=DefinitionCatalog(path)
    assert again.stats()==stats
    hints=map_hints(db)
    assert any(r['name']=='ip_tqi_maf__n__maf' for r in hints)
    assert any(r['name']=='ip_iga_tco_1_pl_ivvt__n__maf' for r in hints)


def test_cross_ecu_candidates_never_mismatch_gs20(tmp_path):
    db=DefinitionCatalog(tmp_path/'db.sqlite')
    if not GS20.exists() or not MS43.exists():pytest.skip('User samples not mounted')
    gs=BinaryImage.from_file(str(GS20))
    ms=BinaryImage.from_file(str(MS43))
    assert candidates(db,gs)==[]
    chosen=candidates(db,ms)
    assert len(chosen)==1
    assert chosen[0]['id']=='ms43-430069-512'
    assert 'Extended Load' in chosen[0]['variant']
    with pytest.raises(ValueError,match='nicht zur Quelle'):
        fetch_and_index(db,gs,'gs20-g10c9000-64',acknowledged_variant=True)


def test_sample_hints_only_with_consent_stay_unverified(tmp_path):
    db=DefinitionCatalog(tmp_path/'db.sqlite')
    if not MS43.exists():pytest.skip('User MS43 not mounted')
    image=BinaryImage.from_file(str(MS43))
    with pytest.raises(ValueError,match='explizit'):
        attach_ms43_preview(db,image)
    result=attach_ms43_preview(db,image,acknowledged_variant=True)
    assert result['indexed']>=70
    assert db.stats()['verified_maps']==0
    assert all(not x.verified for x in db.firmware_maps(image))
    assert db.firmware_maps(BinaryImage(image.original[:-1]+b'Z'))==[]


def test_only_pinned_github_source_urls_allowed(tmp_path):
    item=source_rows(DefinitionCatalog(tmp_path/'db.sqlite'))[0]
    bogus=dict(item,repository='attacker.org/path',path='../stolen.xdf')
    with pytest.raises(ValueError,match='Nicht autorisierte'):
        fetch_pinned_source(bogus,tmp_path)


def test_bad_patch_variant_requires_explicit_review(tmp_path):
    db=DefinitionCatalog(tmp_path/'db.sqlite')
    if not MS43.exists():pytest.skip('User MS43 not mounted')
    with pytest.raises(ValueError,match='explizit'):
        fetch_and_index(db,BinaryImage.from_file(str(MS43)),'ms43-430069-512')


def test_download_requires_exact_github_blob_hash(tmp_path,monkeypatch):
    from ecu_studio.recognition import public_sources
    class Response:
        def __init__(self, payload):self.payload=payload
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n):return self.payload[:n]
    payload=b'<XDFFORMAT version="1.80">'+b' '*151+b'</XDFFORMAT>'
    blob=hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()
    src={'repository':'ms4x-net/ms43','path':'definitions/sample.xdf','git_blob':blob}
    captured=[]
    def fake_urlopen(req,timeout=30):
        captured.append((req.full_url,timeout))
        return Response(payload)
    monkeypatch.setattr(public_sources.urllib.request,'urlopen',fake_urlopen)
    result=fetch_pinned_source(src,tmp_path)
    assert result.read_bytes()==payload
    assert captured==[('https://raw.githubusercontent.com/ms4x-net/ms43/main/definitions/sample.xdf',30)]
    src['git_blob']='0'*40
    with pytest.raises(ValueError,match='weicht'):
        fetch_pinned_source(src,tmp_path)


def test_public_seed_never_creates_training_examples(tmp_path):
    from ecu_studio.recognition.ml import train
    db=DefinitionCatalog(tmp_path/'db.sqlite')
    assert db.stats()['public_map_hints']>=118
    assert not db.verified_references()
    with pytest.raises(ValueError):train(db)
