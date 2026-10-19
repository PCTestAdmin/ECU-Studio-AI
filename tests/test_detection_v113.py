"""Cross-version identity gates, source provenance and learned-ranking boundaries."""
import hashlib
import json
import os
from pathlib import Path
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage,MapDefinition
from ecu_studio.core.profiles import identify_profile,xdf_match_status
from ecu_studio.core.xdf import read_xdf
from ecu_studio.core.precision import rank_candidates
from ecu_studio.recognition.bundled_definitions import DATA,sources,matching_source,definition_candidates
from ecu_studio.recognition.calibration_ranker import installed_ranker,training_status
from ecu_studio.tools.train_calibration_ranker import load_corpus,fingerprint


@pytest.mark.parametrize('size',[65536,524288])
@pytest.mark.parametrize('software',['430037','430055','430056','430064','430066','430069'])
def test_six_ms43_versions_require_more_than_header_for_named_maps(size,software):
    raw=bytearray(size);start=0 if size==65536 else 0x70000
    raw[start+8:start+14]=software.encode()
    image=BinaryImage(raw);profile=identify_profile(image)
    assert profile.family=='Siemens MS43' and profile.software_version==software
    assert matching_source(image)['software']==software
    if software=='430069' and size==65536:
        assert definition_candidates(image)==[]  # zero axes: no fabricated named maps
    other='430037' if software!='430037' else '430069'
    assert xdf_match_status(profile,f'MS{other}_64K.xdf')[0]=='rejected'

def test_all_offline_sources_immutable_and_distinct():
    rows=sources()
    assert len(rows)==16 and len({r['file'] for r in rows})==16
    assert {r['family'] for r in rows}=={'Siemens MS41','Siemens MS42','Siemens MS43'}
    for r in rows:
        payload=(DATA/r['file']).read_bytes()
        assert hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()==r['git_blob']
        assert r['variant']=='Standard' and r['license']=='GPL-3.0'

def test_ms43_header_incidental_numeric_substrings_and_conflicting_project():
    raw=bytearray(65536);raw[8:14]=b'430069';raw[19:25]=b'430006'
    raw[64:76]=b'ca430069.DAT'
    assert identify_profile(BinaryImage(raw)).software_version=='430069'
    raw[64:76]=b'ca430066.DAT'
    assert identify_profile(BinaryImage(raw)).family=='Unbekannt'

def test_adjacent_xdf_categories_are_one_based(tmp_path):
    path=tmp_path/'categories.xdf'
    path.write_text('''<XDFFORMAT><XDFHEADER><CATEGORY index="0" name="Axis"/>
    <CATEGORY index="1" name="Unsorted"/></XDFHEADER><XDFTABLE><title>axis</title>
    <CATEGORYMEM category="1"/><XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0" mmedelementsizebits="8"
    mmedrowcount="1" mmedcolcount="4"/></XDFAXIS></XDFTABLE></XDFFORMAT>''')
    assert read_xdf(path,BinaryImage(bytes(32))).maps[0].folder=='Axis'

def test_training_provenance_splits_and_no_semantic_authority():
    model=installed_ranker();report=training_status()
    assert model and report['ranking_release_gate']
    assert not report['private_bin_training'] and report['real_heldout_oem_firmwares']==0
    assert report['verified_function_labels']==0
    doc,rows=load_corpus(DATA.parent/'training'/'calibration_corpus.json')
    by_id={r['id']:r for r in rows}
    split=report['split_ids']
    for k in split:
        for other in split:
            if k==other:continue
            assert not set(split[k])&set(split[other])
            assert not set(report['split_source_groups'][k])&set(report['split_source_groups'][other])
            for a in split[k]:
                for b in split[other]:
                    assert np.mean(np.abs(fingerprint(by_id[a]['values'])-fingerprint(by_id[b]['values'])))>.015
    yy,xx=np.mgrid[:12,:12]
    raw=(1000+100*yy+30*xx).astype('>u2').tobytes()
    maps=rank_candidates(BinaryImage(raw),[MapDefinition('unknown',0,12,12,'u16',source='heuristic',confidence=.4)])
    assert maps and all(m.kind=='Unbekannt' and not m.verified for m in maps)
    assert 'Open-ECU-Preset-Rangwert' in maps[0].notes

def test_optional_public_ms42_full_and_partial_compatibility():
    sample=os.environ.get('ECU_STUDIO_MS42_REGRESSION_BIN')
    if not sample or not Path(sample).is_file():pytest.skip('Optional public MS42 compatibility fixture not configured')
    payload=Path(sample).read_bytes()
    assert hashlib.sha256(payload).hexdigest()=='010d6bf17bcfe46a9f436ba8e11dff375466ee948aaaf10d43a1d8325757b2cc'
    all_maps=[]
    for raw in (payload,payload[0x48000:0x50000]):
        image=BinaryImage(raw);assert identify_profile(image).family=='Siemens MS42'
        maps=definition_candidates(image)
        assert len(maps)>400 and all(m.folder!='Axis' and not m.verified for m in maps)
        assert not image.dirty_bytes
        all_maps.append(maps)
    assert {(m.name,m.offset-0x48000,m.rows,m.cols,m.dtype) for m in all_maps[0]}=={
        (m.name,m.offset,m.rows,m.cols,m.dtype) for m in all_maps[1]}
