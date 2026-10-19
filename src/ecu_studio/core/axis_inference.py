"""Conservative adjacency-based *axis suggestions* without invented units/labels.

Absolute location hints are useful for manual inspection but are NOT verified
axis definitions. Only word-aligned 1-D arrays close to a 2-D candidate are
considered. Duplicate, trivial and ambiguous candidates are suppressed.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import struct
from .model import BinaryImage, MapDefinition


@dataclass(frozen=True)
class AxisHint:
    axis: str
    offset: int
    count: int
    dtype: str
    endian: str
    score: float
    reason: str


def _plausibility(v: list[int]) -> float:
    if len(v)<4 or len(set(v))<max(4,len(v)//2):return 0.
    d=[v[i+1]-v[i] for i in range(len(v)-1)]
    if min(d)<0 or max(d)==0 or any(x<0 for x in d):return 0.
    spread=v[-1]-v[0]
    if spread<=0:return 0.
    # Reject simple ordinal counters 0..n or 1..n, common incidental runs.
    if spread==len(v)-1 and all(x==1 for x in d):return 0.
    if max(d)>max(20,4*spread/len(d)):return 0.
    nonzero=sum(dv>0 for dv in d)/len(d)
    if nonzero<.65:return 0.
    return min(.9, .42+.24*nonzero+.24*(1-min(max(d)/spread,1.)))


def suggest_adjacent_axes(image:BinaryImage,m:MapDefinition, *,window:int=96,max_hints:int=4) -> list[AxisHint]:
    """Return plausible small nearby axis arrays, never mutate the map."""
    m.validate(image.size)
    if min(m.rows,m.cols)<4 or m.rows*m.cols>4096 or window<0 or window>512:
        return []
    hits=[]
    left=max(0,m.offset-window)
    right=min(image.size,m.offset+m.length+window)
    for axis,count in [('X',m.cols),('Y',m.rows)]:
        if count>64:continue
        for dtype,width in [('u8',1),('u16',2)]:
            length=count*width
            for endian in (['big'] if width==1 else ['big','little']):
                candidates=[]
                # Just before / after the table, not through its interior.
                for begin,end in [(left,m.offset-length+1),
                                  (m.offset+m.length,right-length+1)]:
                    for offset in range(begin,max(begin,end),width):
                        if offset%width:continue
                        b=image.read(offset,length)
                        if len(b)!=length:continue
                        if width==1:vals=list(b)
                        else:vals=list(struct.unpack(('>' if endian=='big' else '<')+'H'*count,b))
                        score=_plausibility(vals)
                        if score:
                            distance=min(abs(m.offset-(offset+length)),abs(offset-(m.offset+m.length)))
                            proximity=max(0.,1-distance/max(window,1))
                            candidates.append((round(.70*score+.30*proximity,4),offset))
                if candidates:
                    for score,offset in sorted(candidates,reverse=True)[:3]:
                        hits.append(AxisHint(axis,offset,count,dtype,endian,score,
                            'Monotone Werte nahe Kennfeld, ausschließlich Prüfhinweis'))
    # Prefer physically separate X/Y, and don't claim an axis when multiple
    # candidates have very similar strength (usually incidental data).
    selected=[]
    for axis in ('X','Y'):
        pool=sorted([h for h in hits if h.axis==axis],key=lambda x:-x.score)
        if not pool:continue
        best=pool[0]
        alternatives=[h for h in pool[1:] if abs(h.offset-best.offset)>max(h.count,h.count*2)]
        if alternatives and best.score-alternatives[0].score<.04:continue
        selected.append(best)
    if len(selected)==2 and selected[0].offset==selected[1].offset:
        # Square maps may have exactly one nearby axis; it could be X or Y.
        # Avoid implying a specific orientation without an independent layout.
        best=selected[0]
        return [AxisHint('X/Y?',best.offset,best.count,best.dtype,best.endian,
                         best.score,'Monotone Nachbarwerte, Achsenrichtung unbekannt')]
    return selected[:max_hints]
