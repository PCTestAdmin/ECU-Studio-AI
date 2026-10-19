"""Auditable range interpolation/smoothing and declarative reusable recipes."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import struct
import numpy as np
from pathlib import Path
from .model import BinaryImage, MapDefinition, FORMATS
from .workflows import BatchPreview, apply_batch
from .storage import atomic_write


def plan_surface_edit(image: BinaryImage, m: MapDefinition, mode: str, *,
                      cells: list[tuple[int,int]] | None=None, amount=0.) -> BatchPreview:
    m.validate(image.size)
    if m.equation:
        raise ValueError('Keine geprüfte Inverse für nichtlineare Formel')
    selected = sorted(set(cells if cells is not None else
                           ((r,c) for r in range(m.rows) for c in range(m.cols))))
    if not selected or any(not (0<=r<m.rows and 0<=c<m.cols) for r,c in selected):
        raise ValueError('Ungültige Zellenauswahl')
    if not math.isfinite(amount):
        raise ValueError('Nichtendlicher Betrag')
    a = image.matrix(m,physical=True)
    out = a.copy()
    r0,r1 = min(r for r,c in selected),max(r for r,c in selected)
    c0,c1 = min(c for r,c in selected),max(c for r,c in selected)
    def coordinates(axis,n):
        if not axis:
            return np.arange(n,dtype=float)
        result=np.asarray(axis,dtype=float)
        if len(result)!=n or not np.isfinite(result).all() or (n>1 and not (
                np.all(np.diff(result)>0) or np.all(np.diff(result)<0))):
            raise ValueError('Interpolation benötigt vollständige, streng monotone Achsen oder reine Zellindizes')
        return result
    if mode.startswith('interpolate'):
        xs,ys=coordinates(m.axes_x,m.cols),coordinates(m.axes_y,m.rows)
    for r,c in selected:
        if mode=='add':
            out[r,c] += amount
        elif mode=='percent':
            out[r,c] *= 1+amount/100
        elif mode=='set':
            out[r,c] = amount
        elif mode=='smooth':
            # Snapshot-based 3x3 mean, no sequential feedback; only selected cells change.
            out[r,c] = np.mean(a[max(0,r-1):r+2,max(0,c-1):c+2])
        elif mode in ('interpolate_x','interpolate_y','interpolate_xy'):
            if mode=='interpolate_x':
                if c0==c1:
                    raise ValueError('Mindestens zwei Spalten für Interpolation')
                t=(xs[c]-xs[c0])/(xs[c1]-xs[c0])
                out[r,c]=a[r,c0]*(1-t)+a[r,c1]*t
            elif mode=='interpolate_y':
                if r0==r1:
                    raise ValueError('Mindestens zwei Zeilen für Interpolation')
                t=(ys[r]-ys[r0])/(ys[r1]-ys[r0])
                out[r,c]=a[r0,c]*(1-t)+a[r1,c]*t
            else:
                if r0==r1 or c0==c1:
                    raise ValueError('Mindestens zwei Zeilen/Spalten für bilineare Interpolation')
                x,y=(xs[c]-xs[c0])/(xs[c1]-xs[c0]),(ys[r]-ys[r0])/(ys[r1]-ys[r0])
                out[r,c]=(1-y)*((1-x)*a[r0,c0]+x*a[r0,c1])+y*((1-x)*a[r1,c0]+x*a[r1,c1])
        else:
            raise ValueError('Unbekannte Bearbeitungsoperation')
    code,width,low,high=FORMATS[m.dtype]
    fmt=('>' if m.endian=='big' else '<')+code
    updates=[]
    prior=[]
    before=[]
    after=[]
    changed=0
    for r,c in selected:
        if not math.isfinite(out[r,c]):
            raise ValueError('Nichtendliches Ergebnis')
        value=m.raw_from_physical(out[r,c])
        if not low<=value<=high:
            raise ValueError(f'Rohwertüberlauf in {r}/{c}')
        p=m.cell_offset(r,c)
        payload=struct.pack(fmt,value)
        old=image.read(p,width)
        if old!=payload:
            updates.append((p,payload))
            prior.append((p,old))
            changed+=sum(x!=y for x,y in zip(old,payload))
        before.append(a[r,c])
        after.append(struct.unpack(fmt,payload)[0]*m.factor+m.bias)
    return BatchPreview(float(min(before)),float(max(before)),float(min(after)),float(max(after)),
                        len(updates),changed,updates,image.digest,image.revision,tuple(prior))


def plan_recipe(image: BinaryImage, maps: list[MapDefinition], recipe: dict) -> BatchPreview:
    """JSON operations; no eval, Python execution, filesystem commands or plugins.

    Bind to exact firmware hash. Different projects require a reviewed transfer.
    Every operation is simulated before a single combined transaction is offered.
    """
    if recipe.get('schema')!=1 or recipe.get('source_sha256')!=image.digest:
        raise ValueError('Rezept benötigt Schema 1 und den passenden Firmware-Hash')
    operations=recipe.get('operations')
    if not isinstance(operations,list) or not 1<=len(operations)<=500:
        raise ValueError('1–500 Rezeptschritte erforderlich')
    scratch=BinaryImage(image.materialize())
    for op in operations:
        found=[m for m in maps if m.name==op.get('map')]
        if len(found)!=1 or not found[0].verified:
            raise ValueError('Rezept benötigt eine eindeutige, bestätigte Kennfelddefinition')
        preview=plan_surface_edit(scratch,found[0],op['mode'],cells=op.get('cells'),amount=float(op.get('amount',0)))
        apply_batch(scratch,preview)
    updates=[(pos,new) for pos,old,new in scratch.changed_ranges()]
    return BatchPreview(0,0,0,0,len(scratch._undo),scratch.dirty_bytes,updates,image.digest,
                        image.revision,tuple((p,image.read(p,len(b))) for p,b in updates))
