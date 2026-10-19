"""Extra unsigned 8-bit map-shaped candidates (not semantic identification)."""
from __future__ import annotations
import numpy as np
from .model import BinaryImage,MapDefinition


def scan_u8(image: BinaryImage, max_results: int = 40, scan_mb: int = 2, *, cancelled=None) -> list[MapDefinition]:
    limit=min(image.size, max(scan_mb,1)*1024*1024)
    buf=np.frombuffer(image.read(0,limit),dtype=np.uint8)
    if len(buf)<128:return []
    proposals=[]
    for rows,cols in ((8,8),(8,16),(12,12),(16,16),(16,12),(12,16),(20,16)):
        length=rows*cols
        starts=np.arange(0,len(buf)-length+1,8,dtype=np.int64)
        for left in range(0,len(starts),2048):
            if cancelled and cancelled():
                return []
            pos=starts[left:left+2048]
            a=buf[pos[:,None]+np.arange(length)[None,:]].astype(np.float32).reshape(-1,rows,cols)
            span=a.max(axis=(1,2))-a.min(axis=(1,2))
            h=np.mean(np.abs(np.diff(a,axis=2)),axis=(1,2))/np.maximum(span,1)
            necessary=(span>18)&(h<.12)
            if not np.any(necessary):
                continue
            a,span,h,pos=a[necessary],span[necessary],h[necessary],pos[necessary]
            v=np.mean(np.abs(np.diff(a,axis=1)),axis=(1,2))/np.maximum(span,1)
            active=((span>18)&(h<.12)&(v<.14)&
                    (np.std(a.mean(axis=1),axis=1)>.03*span)&
                    (np.std(a.mean(axis=2),axis=1)>.03*span))
            for n in np.flatnonzero(active):
                score=float(max(0,.36-.25*(h[n]+v[n])))
                proposals.append((score,int(pos[n]),rows,cols))
            if len(proposals)>max_results*300:
                proposals=sorted(proposals,reverse=True)[:max_results*120]
    proposals.sort(reverse=True)
    chosen=[]
    spans=[]
    for score,offset,rows,cols in proposals:
        if any(offset<end and start<offset+rows*cols for start,end in spans):continue
        chosen.append(MapDefinition(name=f'8-Bit-Kandidat @ 0x{offset:08X}', offset=offset,
            rows=rows,cols=cols,dtype='u8',kind='Unbekannt',source='heuristic',
            confidence=round(score,3),notes='Glatter 8-Bit-Datenbereich; Funktion, Skalierung und Dimension sind ungeprüft.'))
        spans.append((offset,offset+rows*cols))
        if len(chosen)>=max_results:break
    return sorted(chosen,key=lambda x:x.offset)
