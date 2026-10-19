"""Explainable classification and map proximity sets; NOT an ECU-function oracle."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
from .model import MapDefinition

# Only a supplied label/definition contributes to semantic grouping; morphology alone
# cannot safely tell whether a table is torque, boost or ignition.
KINDS={
 'Drehmoment': ('drehmoment','torque','nm limit','nm_limit','momenten'),
 'Ladedruck / Boost': ('ladedruck','boost','wastegate','charge pressure','charging pressure'),
 'Zündung': ('zündung','ignition','spark','zwinkel'),
 'Einspritzung': ('einspritz','injection','injekt','fuel quantity'),
 'Lambda / Luftmasse': ('lambda','luftmasse','air mass','afr','maf'),
 'Kraftstoffdruck': ('rail pressure','fuel pressure','kraftstoffdruck','kraftstoff / druck','rail_druck'),
 'Turbo / VTG': ('vtg','vnt','turbo'),
 'Drehzahl / Leerlauf': ('drehzahl','idle','rpm limit','leerlauf'),
 'Temperatur / Schutz': ('temperatur','temperature','thermal','overtemp','protection'),
 'AGR / EGR': ('agr','egr','exhaust gas recirc'),
 'Abgasnachbehandlung': ('nachbehandlung','aftertreatment','dpf','scr'),
}
UNKNOWN=('unbekannt','andere','other','boost-verdacht','agr-verdacht','diagnose')

@dataclass(frozen=True)
class MapGroup:
    key: str
    title: str
    indices: tuple[int,...]
    basis: str
    verified_members: int
    note: str


def _label(m: MapDefinition) -> str | None:
    kind=m.kind.strip().lower()
    # No guessing from arbitrary names for structurally detected candidates.
    if kind in UNKNOWN or m.source in ('heuristic','ml-proposed','reference-shape') and not m.verified:
        return None
    text=(m.kind+' '+m.name).lower() if m.verified else kind
    for label,words in KINDS.items():
        if any(w in text for w in words): return label
    return None


def group_maps(maps: list[MapDefinition], *, gap_limit: int=4096) -> list[MapGroup]:
    """Group named types, then structural proximity. Unverified stays unverified."""
    if gap_limit < 0: raise ValueError('Negativer Gruppenabstand')
    keyed:dict[str,list[int]]={}
    remaining=[]
    for i,m in enumerate(maps):
        group=_label(m)
        if group: keyed.setdefault(group,[]).append(i)
        else: remaining.append(i)
    groups=[]
    for label,ids in sorted(keyed.items()):
        groups.append(MapGroup('semantic:'+label,label,tuple(sorted(ids,key=lambda i:maps[i].offset)),
            'Definitionstyp / beschriftete Referenz',sum(maps[i].verified for i in ids),
            'Gleiches Themengebiet ist KEIN Nachweis physikalischer Abhängigkeiten.'))
    # Cluster by address only if shape matches and no labeled function. Every member
    # explicitly unknown. Sorting makes behavior deterministic and scalable.
    remaining.sort(key=lambda i:(maps[i].offset,i))
    clusters=[]
    for i in remaining:
        m=maps[i]
        if clusters:
            last=maps[clusters[-1][-1]]
            nearby=0 <= m.offset - (last.offset+last.length) <= gap_limit
            same_shape=(m.rows,m.cols,m.dtype)==(last.rows,last.cols,last.dtype)
            if nearby and same_shape:
                clusters[-1].append(i);continue
        clusters.append([i])
    count=0
    for ids in clusters:
        if len(ids)>1:
            count+=1
            groups.append(MapGroup(f'proximity:{count}',f'Nachbarschaft {count} (unbestätigt)',
                tuple(ids),'Speichernähe + identische Matrixform',sum(maps[i].verified for i in ids),
                'Nur ein struktureller Hinweis – keine ECU-Funktionszuordnung.'))
        else:
            groups.append(MapGroup(f'single:{ids[0]}','Nicht zugeordnet',tuple(ids),
                'Keine belastbare Gruppierung',int(maps[ids[0]].verified),
                'Die Funktion dieses Kennfelds ist nicht bestätigt.'))
    return sorted(groups,key=lambda g:(0 if g.key.startswith('semantic:') else 1, g.title,
                                         maps[g.indices[0]].offset))


def export_groups_csv(path: str | Path, groups: list[MapGroup], maps: list[MapDefinition]) -> None:
    with Path(path).open('w',newline='',encoding='utf-8-sig') as fd:
        writer=csv.writer(fd,delimiter=';')
        writer.writerow(['group','basis','offset','name','type','source','map_verified','group_note'])
        for group in groups:
            for i in group.indices:
                m=maps[i]
                writer.writerow([group.title,group.basis,f'0x{m.offset:08X}',m.name,m.kind,
                                 m.source,'geprüft' if m.verified else 'ungeprüft',group.note])
