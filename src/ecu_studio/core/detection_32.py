"""Bounded 32-bit rectangular *structural* scanner; unknown semantics and scale.

Expands the raw scanner beyond 8-/16-bit data; no names are guessed from values.
"""
from __future__ import annotations
import numpy as np
from .model import BinaryImage, MapDefinition


def scan_32(image: BinaryImage, *, max_results: int = 35, scan_mb: int = 2, cancelled=None) -> list[MapDefinition]:
    limit = min(image.size, max(1, scan_mb) * 1024 * 1024)
    if limit < 128:
        return []
    buf = image.read(0, limit - limit % 4)
    found = []
    for endian, storage in (('big', '>u4'), ('little', '<u4')):
        values = np.frombuffer(buf, dtype=storage)
        for rows, cols in ((8,8),(12,12),(16,16),(16,12),(12,16)):
            n = rows*cols
            if len(values)<n:continue
            starts = np.arange(0,len(values)-n+1,4,dtype=np.int64)
            for j in range(0,len(starts),512):
                if cancelled and cancelled():
                    return []
                part = starts[j:j+512]
                a = values[part[:,None] + np.arange(n)[None,:]].astype(np.float64).reshape(-1,rows,cols)
                span = a.max(axis=(1,2)) - a.min(axis=(1,2))
                necessary=(span>1000)&(span<3e9)
                if not np.any(necessary):
                    continue
                a,span,part=a[necessary],span[necessary],part[necessary]
                r = np.mean(np.abs(np.diff(a,axis=1)),axis=(1,2))/np.maximum(span,1)
                c = np.mean(np.abs(np.diff(a,axis=2)),axis=(1,2))/np.maximum(span,1)
                live = ((span > 1000) & (span < 3e9) & (r < .09) & (c < .09)
                        & (np.std(a.mean(axis=1),axis=1)>.02*span)
                        & (np.std(a.mean(axis=2),axis=1)>.02*span))
                for ix in np.flatnonzero(live):
                    score = float(max(0, .35 - .23*(r[ix]+c[ix])))
                    found.append((score, int(part[ix]*4), rows, cols, endian))
                if len(found)>max_results*150:
                    found=sorted(found,reverse=True)[:max_results*60]
    found.sort(reverse=True)
    chosen=[]
    spans=[]
    for score,offset,rows,cols,endian in found:
        stop = offset+rows*cols*4
        if any(offset<b and a<stop for a,b in spans):continue
        from .precision import narrower_storage_alias
        probe=MapDefinition('32-Bit-Prüfung',offset,rows,cols,'u32',endian)
        if narrower_storage_alias(image,probe):continue
        spans.append((offset,stop))
        chosen.append(MapDefinition(name=f'32-Bit-Kandidat @ 0x{offset:08X}',offset=offset,
                                    rows=rows,cols=cols,dtype='u32',endian=endian,
                                    source='heuristic',kind='Unbekannt',confidence=round(score,3),
                                    notes='Glatter 32-Bit-Datenbereich; signed/unsigned, Skalierung und Zweck ungeprüft.'))
        if len(chosen)>=max_results:break
    return sorted(chosen,key=lambda m:m.offset)
