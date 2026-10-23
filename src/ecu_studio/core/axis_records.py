"""Conservative count/axis/table record discovery, independent of fixed grids.

Supported *hypothesis*: nx,ny,X[nx],Y[ny],Z[ny,nx], packed, with byte or
word counts and byte/word axes. This is not a universal ECU record decoder.
No physical units or functional names can be inferred from this layout alone.
"""
from __future__ import annotations
import numpy as np
from .model import BinaryImage, MapDefinition
from .axis_inference import _plausibility
from .precision import surface_evidence, narrower_storage_alias


def _steps(values) -> list:
    return [b-a for a,b in zip(values,values[1:])]


def _monotone(d) -> bool:
    return all(x>0 for x in d) or all(x<0 for x in d)


def _record_axis(values):
    # Plain Python: axes have at most 32 points, where NumPy call overhead
    # dominated the record scan (300 000 calls on a 2 MB image).
    d=_steps(values)
    if not _monotone(d):return False
    # A single jump swallowing almost the whole axis is weak record evidence.
    # Explicit source definitions remain exempt from this discovery heuristic.
    if max(abs(x) for x in d)>.75*abs(values[-1]-values[0]):return False
    return bool(_plausibility(values if d[0]>0 else [-v for v in values]))


def _sign_rank(image: BinaryImage, m: MapDefinition) -> int:
    """0 for the preferred reading of equally scored u16/s16 hypotheses."""
    if m.width!=2:
        return 0
    raw=np.frombuffer(image.read(m.offset,m.length),np.uint8)
    top=bool(np.any((raw[0::2] if m.endian=='big' else raw[1::2])>=0x80))
    return int(m.dtype.startswith('s')!=top)


def _strict(values) -> bool:
    return _monotone(_steps(values))


def _axis_pair(x, y, wide: bool = True) -> bool:
    """Both axes plausible; with 16-bit counts and axes one may be relaxed.

    The count header already fixes both lengths, so one axis may carry an
    index (0..n) or a single wide step (e.g. 6000 -> 12000 rpm) as long as the
    other one looks like a breakpoint axis. Only for 16-bit counts and axes
    (``wide``): a byte count of 4..32 occurs by chance every ninth byte, and the
    relaxed rule produced a header in random data (negative control, 2 MB).
    """
    if not wide:
        return _record_axis(x) and _record_axis(y)
    return _strict(x) and _strict(y) and (_record_axis(x) or _record_axis(y))


CHAIN_GAP=4   # alignment padding between consecutive records


def _chained(rough: list[MapDefinition], accepted: list[MapDefinition]) -> list[MapDefinition]:
    """Noisy-valued records that touch another accepted record (packed record lists).

    Measured on complete A2L (development): noisy records without a neighbour
    added about as many false as true tables; inside a chain they are records.
    """
    heads=np.array(sorted({m.candidate_region_start for m in accepted}),dtype=np.int64)
    ends=np.array(sorted({m.offset+m.length for m in accepted}),dtype=np.int64)
    def near(sorted_a,lo,hi):
        k=np.searchsorted(sorted_a,lo)
        return k<len(sorted_a) and sorted_a[k]<=hi
    return [m for m in rough if near(heads,m.offset+m.length,m.offset+m.length+CHAIN_GAP)
            or near(ends,m.candidate_region_start-CHAIN_GAP,m.candidate_region_start)]


FLAT_REASON='Konstant/zu wenig Dynamik'
ROUGH_REASON='Zu verrauscht oder eindimensional'
FLAT_SCORE=.05   # ranked after every table with a coherent surface
# Own evidence class (confidence.py): shape from header and axes only, values unverified.
SHAPE_ONLY_ORIGIN='Dimensionsheader + zwei monotone Rohachsen, Werte ohne Oberflächenbeleg (ungeprüft)'


def _flat_record(m: MapDefinition, axis_width: int, kind: str, image: BinaryImage) -> bool:
    """Accept a constant or coarse value block when the header alone fixes the shape.

    Calibrations keep many flat tables (unused functions, one value everywhere).
    Their surface carries no evidence, but count header plus two monotone,
    plausible axes do. The value width cannot be read from flat data, so only the
    axis width is accepted (one candidate, no width guessing); the sign is signed
    only if the axes are signed or the values look negative. Measured on the
    complete EDC17CP09 A2L (development): 257 of 443 headed records with valid
    axes were flat and had been dropped.
    """
    if m.width!=axis_width or m.dtype=='u32':
        return False
    if axis_width==2:
        raw=np.frombuffer(image.read(m.offset,m.length),('<' if m.endian=='little' else '>')+'u2')
        negative=kind=='i' or bool(np.any(raw>=0x8000))
        if m.dtype!=('s16' if negative else 'u16'):
            return False
    m.label_origin=SHAPE_ONLY_ORIGIN
    m.notes+=' Werte ohne glatte Oberfläche: Größe nur durch Kopf und Achsen belegt, Wertebreite = Achsenbreite (ungeprüft).'
    return True


def _x_axis_possible(buf: bytes, counts: np.ndarray, starts: np.ndarray, phase: int,
                     count_width: int, endian: str) -> np.ndarray:
    """Vectorised pre-filter: headers whose X axis is strictly monotone in some tried reading.

    Every accepted record needs that (both axis rules require strict X), so the
    filter only skips headers the loop below would reject anyway; results are
    unchanged, the record scan gets several times faster.
    """
    b=np.frombuffer(buf,np.uint8).astype(np.int64)
    keep=np.zeros(len(starts),bool)
    cols=counts[starts].astype(np.int64)
    axis_start=phase+starts.astype(np.int64)*count_width+2*count_width
    for axis_width in (1,2):
        for order in (['big'] if axis_width==1 else ['big','little']):
            if count_width==2 and axis_width==2 and order!=endian:continue
            for c in np.unique(cols).tolist():
                sel=np.flatnonzero((cols==c)&~keep)
                if not len(sel):continue
                pos=axis_start[sel][:,None]+axis_width*np.arange(c)[None,:]
                ok=pos[:,-1]+axis_width<=len(b)
                sel,pos=sel[ok],pos[ok]
                if axis_width==1:
                    v=b[pos]
                    variants=(v,)
                else:
                    hi,lo=(b[pos],b[pos+1]) if order=='big' else (b[pos+1],b[pos])
                    v=hi*256+lo
                    variants=(v,np.where(v>=0x8000,v-0x10000,v))
                for w in variants:
                    d=np.diff(w,axis=1)
                    keep[sel[np.all(d>0,axis=1)|np.all(d<0,axis=1)]]=True
    return keep


def scan_axis_records(image: BinaryImage, *, max_results=40, cancelled=None, include_u32=False):
    if max_results <= 0 or image.size < 32:return []
    buf=image.read(0,min(image.size,2*1024*1024))
    found=[]
    rough=[]   # header + axes fine, values noisy: kept only inside a chain of records
    for count_width in (1,2):
        for endian in (['big'] if count_width==1 else ['big','little']):
            for phase in range(count_width):
                usable=(len(buf)-phase)//count_width*count_width
                counts=np.frombuffer(buf[phase:phase+usable],dtype=('>' if endian=='big' else '<')+'u'+str(count_width))
                if len(counts)<2:continue
                starts=np.flatnonzero((counts[:-1]>=4)&(counts[:-1]<=32)&
                                     (counts[1:]>=4)&(counts[1:]<=32))
                starts=starts[_x_axis_possible(buf,counts,starts,phase,count_width,endian)]
                for ix,index in enumerate(starts):
                    if ix%128==0 and cancelled and cancelled():return []
                    cols,rows=int(counts[index]),int(counts[index+1])
                    header=phase+int(index)*count_width
                    axis_start=header+2*count_width
                    for axis_width in (1,2):
                        end=axis_start+(cols+rows)*axis_width
                        if end+rows*cols>len(buf):continue
                        for order in (['big'] if axis_width==1 else ['big','little']):
                            if count_width==2 and axis_width==2 and order!=endian:continue
                            # Signed 16-bit axes (temperatures, Bosch EDC17 SWORD layouts) only
                            # rise when read signed; unsigned reading is tried first.
                            for kind in (('u','i') if axis_width==2 else ('u',)):
                                axes=np.frombuffer(buf[axis_start:end],dtype=('>' if order=='big' else '<')+kind+str(axis_width))
                                x,y=axes[:cols].tolist(),axes[cols:].tolist()
                                if kind=='i' and min(x+y)>=0:continue      # same reading as unsigned
                                if _axis_pair(x,y,count_width==2 and axis_width==2):break
                            else:
                                continue
                            for dtype in ('u8','u16','s16','u32'):
                                if dtype=='u32' and not include_u32:continue
                                for storage in (['big'] if dtype=='u8' else ['big','little']):
                                    if dtype!='u8' and ((axis_width==2 and storage!=order) or
                                                       (count_width==2 and storage!=endian)):continue
                                    m=MapDefinition(f'Achsen-/Header-Kandidat @ 0x{end:08X}',end,rows,cols,
                                        dtype,storage,source='heuristic',confidence=.44,
                                        axes_x=x,axes_y=y,
                                        axis_x_offset=axis_start,axis_y_offset=axis_start+cols*axis_width,
                                        record_layout='candidate:nx,ny,x,y,z',
                                        candidate_region_start=header,
                                        axes_info='Rohachsen aus Count/Axis-Hypothese; Einheiten und Orientierung ungeprüft',
                                        label_origin='Dimensionsheader + zwei monotone Rohachsen (ungeprüft)',
                                        notes=f'Layout-Hypothese: {count_width*8}-Bit nx/ny, {axis_width*8}-Bit Achsen ({order}); keine physikalische Skalierung.')
                                    if end+m.length>len(buf):continue
                                    ev=surface_evidence(image.matrix(m),min_unique=4)
                                    if ev['valid'] and not narrower_storage_alias(image,m,ev):
                                        found.append((ev['score'],m))
                                    elif ev['reason']==FLAT_REASON and _flat_record(m,axis_width,kind,image):
                                        found.append((FLAT_SCORE,m))
                                    elif (ev['reason']==ROUGH_REASON and _record_axis(x) and _record_axis(y)
                                          and _flat_record(m,axis_width,kind,image)):
                                        rough.append(m)
                    if len(found)>max_results*30:
                        found=sorted(found,key=lambda item:-item[0])[:max_results*10]
    found.extend((FLAT_SCORE,m) for m in _chained(rough,[m for _,m in found]))
    # One hypothesis per span: u16/s16 readings of the same bytes must not use
    # up the result limit. The better surface wins; on a tie (e.g. all values
    # negative, both readings equally smooth) the signed reading is kept, and
    # the unsigned one where no top bit is set (identical values).
    found.sort(key=lambda item:(-item[0],_sign_rank(image,item[1])))
    unique={}
    for _,m in found:
        unique.setdefault((m.offset,m.rows,m.cols,m.width,m.endian),m)
    return list(unique.values())[:max_results]


RECORD_AXIS_LAYOUT = 'candidate:record-axis'


def record_axes(image: BinaryImage, m: MapDefinition) -> list[MapDefinition]:
    """The X/Y breakpoint arrays of an accepted nx,ny,X,Y,Z header candidate, as 1 x n objects.

    Count and axis widths follow from header position, data start and the point
    counts (unique for 2 + 2 or more points); the byte order and sign are the
    ones that reproduce the axis values the candidate was accepted with.
    """
    if m.record_layout != 'candidate:nx,ny,x,y,z' or m.candidate_region_start is None or not m.axes_x:
        return []
    header, n = m.candidate_region_start, m.cols + m.rows
    for cw in (1, 2):
        for aw in (1, 2):
            if header + 2 * cw + n * aw != m.offset:
                continue
            start = header + 2 * cw
            for order in ('little', 'big'):
                for kind in ('u', 'i'):
                    dt = np.dtype(kind + '1') if aw == 1 else np.dtype(('<' if order == 'little' else '>') + kind + '2')
                    v = np.frombuffer(image.read(start, n * aw), dt).tolist()
                    if v[:m.cols] == list(m.axes_x) and v[m.cols:] == list(m.axes_y):
                        dtype = ('s' if kind == 'i' else 'u') + str(8 * aw)
                        return [MapDefinition(f'Achse {label} von 0x{m.offset:08X}', off, 1, count, dtype, order,
                                              source='heuristic', confidence=.44, record_layout=RECORD_AXIS_LAYOUT,
                                              candidate_region_start=header,
                                              label_origin='Stützstellen eines Kopf-Datensatzes (ungeprüft)',
                                              label_evidence=f'{label}-Achse des Datensatzes @ 0x{header:X} mit Anzahl-Kopf.',
                                              notes='Achsen-Hypothese aus nx,ny,X,Y,Z-Kopf; Einheit unbekannt.')
                                for label, off, count in (('X', start, m.cols), ('Y', start + m.cols * aw, m.rows))]
    return []

