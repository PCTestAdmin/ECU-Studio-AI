import os
from pathlib import Path
import numpy as np
import pytest
from ecu_studio.core.model import BinaryImage,MapDefinition
from ecu_studio.core.precision import narrower_storage_alias,rank_candidates
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.axis_records import scan_axis_records


def test_low_diversity_words_cannot_manufacture_u32_complexity():
    y,x=np.mgrid[:12,:24]
    a=(40*((x//3+y//2)%11)).astype('<u2')
    image=BinaryImage(a.tobytes());m=MapDefinition('packed pairs',0,12,12,'u32','little',source='heuristic',confidence=.4)
    assert len(np.unique(a))==11 and narrower_storage_alias(image,m)
    assert not rank_candidates(image,[m])


def test_partial_overlap_and_record_axis_overlap_are_competitors():
    y,x=np.mgrid[:16,:32];image=BinaryImage((20+2*y+x).astype('u1').tobytes())
    one=MapDefinition('one',0,8,8,'u8',source='heuristic',confidence=.4)
    two=MapDefinition('two',50,8,8,'u8',source='heuristic',confidence=.4)
    hits=rank_candidates(image,[one,two])
    assert len(hits)==1
    two=MapDefinition('two',70,8,8,'u8',source='heuristic',confidence=.4,candidate_region_start=40)
    assert len(rank_candidates(image,[one,two]))==1


def test_four_level_plateau_with_two_real_axis_records_is_retained():
    y,x=np.mgrid[:7,:5];values=(50+20*(x>2)+40*(y>3)).astype('u1')
    header=bytes([5,7,10,30,60,100,150,8,20,35,55,80,110,145])
    raw=bytearray(1024);raw[19:19+len(header)+values.size]=header+values.tobytes()
    image=BinaryImage(raw);offset=19+len(header)
    records=scan_axis_records(image)
    assert any((m.offset,m.rows,m.cols,m.dtype)==(offset,7,5,'u8') for m in records)
    result=scan_calibration_candidates(image)
    assert any((m.offset,m.rows,m.cols)==(offset,7,5) for m in result)
    assert all(not m.verified for m in result)


def test_optional_real_gs20_default_has_no_unbound_u32_or_overlaps():
    p=os.environ.get('ECU_STUDIO_GS20_REGRESSION_BIN')
    if not p or not Path(p).exists():pytest.skip('Optional local GS20 fixture')
    image=BinaryImage(Path(p).read_bytes());maps=scan_calibration_candidates(image)
    assert maps and not any(m.dtype=='u32' for m in maps)
    for a,b in zip(maps,maps[1:]):
        assert a.offset+a.length<= (b.candidate_region_start if b.candidate_region_start is not None else b.offset)
    for offset,rows,cols in [(0x3820,8,8),(0x9b50,12,12),(0xb098,9,9)]:
        m=MapDefinition('old width guess',offset,rows,cols,'u32','little')
        assert narrower_storage_alias(image,m)
    assert not image.dirty_bytes
