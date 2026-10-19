"""Bounded discovery of signed 16-bit tables with negative values.

No ECU function is inferred from the shape or numeric range.
"""
from __future__ import annotations
import numpy as np
from .model import BinaryImage, MapDefinition


def scan_s16(image: BinaryImage, *, max_results: int = 30, scan_mb: int = 2, cancelled=None) -> list[MapDefinition]:
    limit = min(image.size, max(1, scan_mb) * 1024 * 1024)
    if limit < 128:
        return []
    buffer = image.read(0, limit - limit % 2)
    proposals = []
    for endian, dtype in (('big', '>i2'), ('little', '<i2')):
        values = np.frombuffer(buffer, dtype=dtype).astype(np.float32)
        for rows, cols in ((8,8),(12,12),(16,16),(12,16),(16,12)):
            count = rows * cols
            if len(values) < count:
                continue
            starts = np.arange(0, len(values)-count+1, 8, dtype=np.int64)
            for j in range(0,len(starts),768):
                if cancelled and cancelled():
                    return []
                indexes = starts[j:j+768]
                samples = values[indexes[:,None]+np.arange(count)[None,:]].reshape(-1,rows,cols)
                span = samples.max(axis=(1,2))-samples.min(axis=(1,2))
                necessary=(samples.min(axis=(1,2)) < -10)&(span>=40)&(span<28000)
                if not np.any(necessary):
                    continue
                samples,span,indexes=samples[necessary],span[necessary],indexes[necessary]
                dh=np.mean(np.abs(np.diff(samples,axis=2)),axis=(1,2))/np.maximum(span,1)
                dv=np.mean(np.abs(np.diff(samples,axis=1)),axis=(1,2))/np.maximum(span,1)
                good=((samples.min(axis=(1,2)) < -10) & (span >= 40) & (span < 28000) &
                      (dh < .15) & (dv < .17) &
                      (np.std(samples.mean(axis=1),axis=1) > .025*span) &
                      (np.std(samples.mean(axis=2),axis=1) > .025*span))
                for i in np.flatnonzero(good):
                    score = max(0., .35-.24*float(dh[i]+dv[i]))
                    proposals.append((score,int(indexes[i])*2,rows,cols,endian))
                if len(proposals) > max_results*100:
                    proposals.sort(reverse=True)
                    proposals = proposals[:max_results*40]
    proposals.sort(reverse=True)
    accepted = []
    for score,off,rows,cols,endian in proposals:
        size = rows*cols*2
        if any(off < m.offset+m.length and m.offset < off+size for m in accepted):
            continue
        accepted.append(MapDefinition(name=f'Signed-Kandidat @ 0x{off:08X}',offset=off,
                         rows=rows,cols=cols,dtype='s16',endian=endian,
                         kind='Unbekannt',source='heuristic',confidence=round(score,3),
                         label_origin='Signed-16-Struktursuche',
                         label_evidence='Strukturiertes 16-Bit-Kennfeld mit negativen Rohwerten; ECU-Funktion unbekannt.',
                         notes='Vorzeichen, Achsen und Bedeutung unbedingt anhand von Referenzen prüfen.'))
        if len(accepted) >= max_results:
            break
    return sorted(accepted,key=lambda m:m.offset)
