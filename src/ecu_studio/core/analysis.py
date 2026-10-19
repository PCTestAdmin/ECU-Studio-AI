"""Tuner productivity helpers: evidence report, surface checks and sibling maps."""
from __future__ import annotations
import math
import numpy as np
from .model import BinaryImage, MapDefinition


def analyze_map(image: BinaryImage, m: MapDefinition) -> dict:
    """Structural plausibility checks only. Not an engine safety or calibration check."""
    m.validate(image.size)
    # Raw read per logical cell: packed numpy reshape would silently shift
    # cells for padded or reversed XDF layouts.
    values = np.array([[image.raw_value(m,r,c) for c in range(m.cols)]
                       for r in range(m.rows)], dtype=np.float64)
    physical=np.array([[m.scale_raw(raw) for raw in row] for row in values],dtype=np.float64)
    vmin,vmax=float(np.min(physical)),float(np.max(physical))
    spread=vmax-vmin
    notes=[]
    if spread==0: notes.append("Alle Tabellenwerte sind identisch (konstant).")
    if np.mean(values==np.max(values)) > .25:notes.append("Mehr als 25 % der Rohwerte entsprechen dem Tabellenmaximum.")
    if m.rows>=2 and m.cols>=2 and spread:
        horiz=np.abs(np.diff(physical,axis=1))
        vert=np.abs(np.diff(physical,axis=0))
        largest=max(float(np.max(horiz)),float(np.max(vert)))
        if largest > .65*spread:notes.append("Starker Sprung zwischen benachbarten Zellen; Datenlayout/Skalierung prüfen.")
    edited=sum((m.cell_offset(r,c)+k) in image._patches
               for r in range(m.rows) for c in range(m.cols)
               for k in range(m.width))
    if m.source=="heuristic":notes.append("Automatisch gefundener Bereich: Offset, Datentyp und Funktion ungeprüft.")
    if not notes:notes.append("Keine einfachen Strukturauffälligkeiten. Das ist KEINE technische Freigabe.")
    return {"min":vmin,"max":vmax,"modified_bytes":edited,"alerts":notes,
            "rows":m.rows,"cols":m.cols,"source":m.source,"type":m.kind}


def find_similar_maps(image: BinaryImage, target: MapDefinition, others: list[MapDefinition], max_count=12) -> list[tuple[float,MapDefinition]]:
    """Pearson similarity on equally-shaped raw value matrices; only a visual shortlist."""
    def extract(m):
        return np.array([[image.raw_value(m,r,c) for c in range(m.cols)] for r in range(m.rows)], dtype=np.float64).ravel()
    t=extract(target)
    if t.std() == 0:return []
    res=[]
    for other in others:
        if other is target or (other.rows,other.cols)!=(target.rows,target.cols):continue
        v=extract(other)
        if v.std() == 0:continue
        score=float(np.corrcoef(t,v)[0,1])
        if math.isfinite(score) and score>=.80:res.append((score,other))
    return sorted(res,key=lambda x:x[0],reverse=True)[:max_count]
