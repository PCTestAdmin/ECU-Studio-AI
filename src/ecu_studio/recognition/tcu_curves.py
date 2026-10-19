"""Low-confidence 1-D interleaved (x,y) curve discovery for transmission files.

Inspired by publicly documented Subaru 5EAT word-pair shift-schedule layouts,
not an implementation of a 5EAT definition, family classifier or tuner.
The actual data format and semantic label MUST be validated per firmware.
"""
from __future__ import annotations
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition


def scan_paired_u16_curves(image: BinaryImage, *, start: int=0, end: int|None=None,
                           min_points: int=7, max_points: int=32,
                           max_results: int=80) -> list[MapDefinition]:
    """Search u16 word pairs (x,y), optional 0xffff terminator.

    Conservative, opt-in tool: 5EAT-style curves only. Value ceilings are
    structural, not proof of km/h, throttle angle, or any TCU function.
    Does not use known names, train weights, or modify the input.
    """
    end = image.size if end is None else end
    if start < 0 or end < start or end > image.size:
        raise ValueError('Ungültiger Speicherbereich')
    if min_points < 5 or max_points < min_points or max_points > 64:
        raise ValueError('Ungültige Punktanzahl')
    if max_results < 1 or max_results > 1000:
        raise ValueError('Ungültiges Ergebnislimit')
    end = min(end, start+16*1024*1024)
    raw = image.read(start,end-start)
    if len(raw) < min_points*4+2: return []
    outputs=[]
    for endian,kind in (('big','>u2'),('little','<u2')):
        # Two possible 16-bit alignments, never copy into an uncontrolled buffer.
        for align in (0,2):
            words=np.frombuffer(raw[align:len(raw)-((len(raw)-align)%2)],dtype=kind)
            if words.size < 2*min_points+1: continue
            x=words[0::2];y=words[1::2]
            if y.size<min_points:continue
            # Look for plausible variable-size curve starts, vectorized.
            n=len(y)
            plausible=(x[:n] <= 300)&(y <= 255)
            dx=np.diff(x[:n].astype(np.int32))
            dy=np.diff(y.astype(np.int32))
            good=(dx>0)&(dx<=85)&(np.abs(dy)<=105)&(plausible[:-1])&(plausible[1:])
            # Runs of valid consecutive pairs. Require a terminator immediately
            # after the last pair or a firm boundary. This limits coincidence.
            borders=np.diff(np.r_[False,good,False].astype(np.int8))
            starts=np.flatnonzero(borders==1)
            ends=np.flatnonzero(borders==-1)
            for lo,stop in zip(starts,ends):
                num=int(stop-lo+1)
                if num<min_points or num>max_points:continue
                if lo+num >= len(x):continue
                xx=x[lo:lo+num]; yy=y[lo:lo+num]
                if xx.size != num or yy.size !=num:continue
                if int(xx[-1])-int(xx[0]) < 25 or len(np.unique(yy)) < 4:continue
                # A single u16 0xffff after the final (x,y) pair is a
                # strong layout clue; do not require preceding x/y interpretation
                # for the following word.
                next_word_ix=2*(lo+num)
                if next_word_ix >= len(words) or int(words[next_word_ix]) != 0xffff: continue
                curve_offset=int(start+align+4*lo)
                if curve_offset+4*num+2>image.size:continue
                score=.22+min(.13,(num-min_points)*.009)
                outputs.append((score,curve_offset,num,endian,[int(z) for z in xx]))
    outputs.sort(key=lambda v:(-v[0],v[1],v[3]))
    selected=[]
    for score,offset,n,endian,xx in outputs:
        if any(max(0,min(offset+4*n,t+4*k)-max(offset,t))>min(4*n,4*k)*.45
               for _,t,k,_,_ in selected):continue
        selected.append((score,offset,n,endian,xx))
        if len(selected)>=max_results:break
    result=[]
    for score,offset,n,endian,xx in sorted(selected,key=lambda a:a[1]):
        m=MapDefinition(name=f'1D-Paarkandidat @ 0x{offset:08X}',offset=offset+2,
                        rows=1,cols=n,dtype='u16',endian=endian,
                        major_stride_bits=32,axes_x=xx,source='tcu-pair-heuristic',
                        confidence=round(score,3),verified=False,
                        label_origin='Ungeprüfte TCU-Paarstruktur',
                        label_evidence=('Streng steigende u16-X-Werte, gebundene Y-Werte und Endmarker; '
                                        'keine bestätigte Kennfeldfunktion, Einheit oder ECU-Familie.'),
                        kind='Unbekannt')
        m.notes=m.label_evidence
        m.validate(image.size)
        result.append(m)
    return result
