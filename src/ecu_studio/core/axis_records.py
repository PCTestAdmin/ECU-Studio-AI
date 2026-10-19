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


def _record_axis(values):
    d=np.diff(np.asarray(values,dtype=float))
    if not (np.all(d>0) or np.all(d<0)):return False
    # A single jump swallowing almost the whole axis is weak record evidence.
    # Explicit source definitions remain exempt from this discovery heuristic.
    if max(abs(d))>.75*abs(values[-1]-values[0]):return False
    return bool(_plausibility(values if d[0]>0 else [-v for v in values]))


def scan_axis_records(image: BinaryImage, *, max_results=40, cancelled=None, include_u32=False):
    if max_results <= 0 or image.size < 32:return []
    buf=image.read(0,min(image.size,2*1024*1024))
    found=[]
    for count_width in (1,2):
        for endian in (['big'] if count_width==1 else ['big','little']):
            for phase in range(count_width):
                usable=(len(buf)-phase)//count_width*count_width
                counts=np.frombuffer(buf[phase:phase+usable],dtype=('>' if endian=='big' else '<')+'u'+str(count_width))
                if len(counts)<2:continue
                starts=np.flatnonzero((counts[:-1]>=4)&(counts[:-1]<=32)&
                                     (counts[1:]>=4)&(counts[1:]<=32))
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
                            axes=np.frombuffer(buf[axis_start:end],dtype=('>' if order=='big' else '<')+'u'+str(axis_width))
                            x,y=axes[:cols].tolist(),axes[cols:].tolist()
                            if not _record_axis(x) or not _record_axis(y):continue
                            for dtype in ('u8','u16','s16','u32'):
                                if dtype=='u32' and not include_u32:continue
                                for storage in (['big'] if dtype=='u8' else ['big','little']):
                                    if dtype!='u8' and ((axis_width==2 and storage!=order) or
                                                       (count_width==2 and storage!=endian)):continue
                                    m=MapDefinition(f'Achsen-/Header-Kandidat @ 0x{end:08X}',end,rows,cols,
                                        dtype,storage,source='heuristic',confidence=.44,
                                        axes_x=x,axes_y=y,
                                        record_layout='candidate:nx,ny,x,y,z',
                                        candidate_region_start=header,
                                        axes_info='Rohachsen aus Count/Axis-Hypothese; Einheiten und Orientierung ungeprüft',
                                        label_origin='Dimensionsheader + zwei monotone Rohachsen (ungeprüft)',
                                        notes=f'Layout-Hypothese: {count_width*8}-Bit nx/ny, {axis_width*8}-Bit Achsen ({order}); keine physikalische Skalierung.')
                                    if end+m.length>len(buf):continue
                                    ev=surface_evidence(image.matrix(m),min_unique=4)
                                    if ev['valid'] and not narrower_storage_alias(image,m,ev):
                                        found.append((ev['score'],m))
                    if len(found)>max_results*30:
                        found=sorted(found,key=lambda item:-item[0])[:max_results*10]
    found.sort(key=lambda item:-item[0])
    unique={}
    for _,m in found:
        unique.setdefault((m.offset,m.rows,m.cols,m.dtype,m.endian),m)
    return list(unique.values())[:max_results]
