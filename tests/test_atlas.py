from types import SimpleNamespace
import pytest
from ecu_studio.core.atlas import merge_intervals, atlas_stats, overview_slices


def map_(start,length,verified=False):
    return SimpleNamespace(offset=start,length=length,verified=verified)


def test_union_coverage_patch_inside_outside_and_immutability():
    maps=[map_(10,25),map_(20,20,True),map_(60,10)]
    stats=atlas_stats(100,maps,[10,30,39,40,50,62,99])
    assert stats.mapped_bytes==40
    assert stats.verified_bytes==20
    assert stats.changed_unmapped==3  # 40,50,99
    assert stats.changed_bytes==7


def test_merge_rejects_outside_and_merges_touching():
    assert merge_intervals([(20,30),(5,10),(10,15),(12,25)],60)==[(5,30)]
    with pytest.raises(ValueError,match='außerhalb'):
        merge_intervals([(1,101)],100)


def test_overview_slice_crosses_rows_and_stops_before_boundary():
    out=list(overview_slices(8,23,size=100,rows=10))
    assert out==[(0,.8,1.0),(1,0.0,1.0),(2,0.0,.3)]
    assert list(overview_slices(8,8,size=100,rows=10))==[]
