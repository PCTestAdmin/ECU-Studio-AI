"""Memory-coverage statistics for dense ECU image visualization.

Coverage is byte-based and cannot establish functional ECU correctness.
"""
from __future__ import annotations
from dataclasses import dataclass
from bisect import bisect_right
from typing import Iterable


def merge_intervals(intervals: Iterable[tuple[int,int]], size: int) -> list[tuple[int,int]]:
    """Return sorted disjoint half-open ranges, rejecting invalid boundaries."""
    if size < 0:raise ValueError('Ungültige Dateigröße')
    valid=[]
    for a,b in intervals:
        if not (0<=a<=b<=size):raise ValueError('Intervall außerhalb der BIN')
        if a!=b:valid.append((a,b))
    valid.sort()
    merged=[]
    for a,b in valid:
        if merged and merged[-1][1]>=a:
            merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged


@dataclass(frozen=True)
class AtlasStats:
    mapped_bytes: int
    verified_bytes: int
    changed_bytes: int
    changed_unmapped: int


def atlas_stats(size: int, maps: Iterable, patched_positions: Iterable[int]) -> AtlasStats:
    mapped=[]; verified=[]
    for m in maps:
        interval=(m.offset,m.offset+m.length)
        mapped.append(interval)
        if m.verified:verified.append(interval)
    cov=merge_intervals(mapped,size)
    ver=merge_intervals(verified,size)
    starts=[a for a,_ in cov]
    changed=set(patched_positions)
    if any(p<0 or p>=size for p in changed):raise ValueError('Patch außerhalb der BIN')
    not_in_any_map=0
    for pos in changed:
        idx=bisect_right(starts,pos)-1
        if idx<0 or pos>=cov[idx][1]:not_in_any_map+=1
    return AtlasStats(
        mapped_bytes=sum(b-a for a,b in cov),
        verified_bytes=sum(b-a for a,b in ver),
        changed_bytes=len(changed),
        changed_unmapped=not_in_any_map,
    )


def overview_slices(start: int, end: int, *, size: int, rows: int):
    """Yield (row, start_fraction, end_fraction) without materializing every byte."""
    if rows<1 or size<0 or not 0<=start<=end<=size:raise ValueError('Ungültiges Speicherintervall')
    if start==end or size==0:return
    stride=max(1,(size+rows-1)//rows)
    first=start//stride
    last=(end-1)//stride
    for row in range(first,last+1):
        base=row*stride
        a=max(start,base)
        b=min(end,base+stride)
        yield row,(a-base)/stride,(b-base)/stride
