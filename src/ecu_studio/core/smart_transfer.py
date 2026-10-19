"""Reviewed physical-delta transfer across explicitly compatible firmware projects.

No address-based copying or automatic semantic confirmation. Explicitly requested
physical-grid interpolation has its own domain/unit checks and cell preview.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import math
import struct
import numpy as np
from .model import BinaryImage, MapDefinition, FORMATS


@dataclass(frozen=True)
class FirmwareIdentity:
    sha256: str
    family: str
    hardware: str
    software: str
    evidence: str
    reviewed: bool = False


@dataclass(frozen=True)
class TransferCell:
    row: int
    col: int
    source_original: float
    source_modified: float
    target_before: float
    target_after: float
    offset: int
    before: bytes
    after: bytes
    change_value: float = 0.
    interpolated: bool = False


@dataclass(frozen=True)
class MapTransfer:
    source: str
    target: str
    source_offset: int
    target_offset: int
    status: str
    evidence: str
    cells: tuple[TransferCell, ...] = ()


@dataclass(frozen=True)
class TransferPlan:
    source_identity: FirmwareIdentity
    target_identity: FirmwareIdentity
    source_modified_sha256: str
    target_current_sha256: str
    target_revision: int
    mode: str
    maps: tuple[MapTransfer, ...]
    interpolation_requested: bool = False

    def report(self):
        obj = asdict(self)
        for m in obj['maps']:
            for cell in m['cells']:
                cell['before'] = cell['before'].hex()
                cell['after'] = cell['after'].hex()
        obj['warning'] = 'Manuelle Übernahme erforderlich. Keine Checksummen-/Flashfreigabe.'
        return obj


def _check_identity(image, identity):
    if (identity.sha256 != image.digest or not identity.reviewed or
            not all(s.strip() for s in (identity.family,identity.hardware,identity.software,identity.evidence))):
        raise ValueError('Hashgebundene, fachlich bestätigte Familie/Hardware/Software und Herkunft erforderlich')
    from .profiles import identify_profile
    profile=identify_profile(image)
    if profile.identified and profile.family.casefold()!=identity.family.casefold():
        raise ValueError('Deklarierte Familie widerspricht der vorhandenen Firmwareerkennung')
    known_software=profile.software_version or profile.calibration_id
    if known_software and known_software.casefold()!=identity.software.strip().casefold():
        raise ValueError('Deklarierter Software-/Kalibrierstand widerspricht der Firmwarekennung')


def suggest_links(source: BinaryImage, target: BinaryImage, maps: list[MapDefinition]):
    """Locate unique byte-identical moved surfaces; proposals stay unverified.

    No physical transfer is possible until the target definition is reviewed.
    Nonidentical surfaces use the existing similarity matcher/catalogue.
    """
    from dataclasses import replace
    buf = target.materialize()
    results = []
    for m in maps:
        m.validate(source.size)
        if not m.verified or m.length < 16:
            continue
        template = source.original[m.offset:m.offset+m.length]
        if len(set(template)) < 4:
            continue
        first = buf.find(template)
        if first < 0 or buf.find(template,first+1) >= 0:
            continue
        results.append(replace(m, offset=first, candidate_region_start=None, verified=False, source='transfer-proposed',
                               notes='Eindeutige Byte-Übereinstimmung. Zielachsen/Hardware/Funktion fachlich prüfen.'))
    return results


def plan_transfer(source: BinaryImage, target: BinaryImage,
                  source_maps: list[MapDefinition], target_maps: list[MapDefinition], *,
                  source_identity: FirmwareIdentity, target_identity: FirmwareIdentity,
                  mode='delta', interpolate=False, links=None) -> TransferPlan:
    for image, identity in ((source,source_identity),(target,target_identity)):
        _check_identity(image,identity)
    if source_identity.family.casefold() != target_identity.family.casefold():
        raise ValueError('Unterschiedliche ECU-Familien')
    if source_identity.hardware.casefold() != target_identity.hardware.casefold():
        raise ValueError('Hardware-Kompatibilität nicht bestätigt: Kennungen weichen ab')
    if mode not in ('delta','percent'):
        raise ValueError('Nur physikalisches Delta oder Prozentänderung unterstützt')
    base = BinaryImage(source.original)
    plans = []
    if links is not None and (not isinstance(links,dict) or any(type(k)is not int or type(v)is not int or
           not 0<=k<len(source_maps) or not 0<=v<len(target_maps) for k,v in links.items())):
        raise ValueError('Ungültige explizite Kennfeldpaarung')
    for map_index,m in enumerate(source_maps):
        m.validate(source.size)
        changed = any(source.read(m.cell_offset(r,c),m.width) != base.read(m.cell_offset(r,c),m.width)
                      for r in range(m.rows) for c in range(m.cols))
        if not changed:
            continue
        # Semantic key independent of addresses and map ordering.
        matches = ([target_maps[links[map_index]]] if links is not None and map_index in links else
                   [t for t in target_maps if t.name.casefold()==m.name.casefold() and t.kind==m.kind])
        conflict = ''
        t = matches[0] if len(matches)==1 else None
        cells = []
        resampled=False
        try:
            if not m.verified:
                raise ValueError('Quelldefinition nicht fachlich bestätigt')
            if t is None:
                raise ValueError('Keine eindeutige Zieldefinition (Name/Funktion)')
            t.validate(target.size)
            if not t.verified:
                raise ValueError('Zieldefinition nicht fachlich bestätigt')
            if m.kind!=t.kind:
                raise ValueError('Gepaarte Kennfelder haben unterschiedliche bestätigte Funktionen')
            if (m.rows,m.cols) != (t.rows,t.cols) and not interpolate:
                raise ValueError('Dimensionskonflikt – keine automatische Interpolation')
            if m.equation or t.equation:
                raise ValueError('Nichtlineare Umrechnungsformel ohne geprüfte Inverse')
            if m.unit != t.unit:
                raise ValueError('Unterschiedliche Werteinheiten')
            for n, nt, a, b in ((m.cols,t.cols,m.axes_x,t.axes_x),(m.rows,t.rows,m.axes_y,t.axes_y)):
                if n > 1 and (len(a)!=n or len(b)!=n or not np.isfinite(a).all() or
                              not np.isfinite(b).all() or not np.allclose(a,b,rtol=0,atol=1e-9)):
                    if not interpolate:raise ValueError('Achsen fehlen oder unterscheiden sich')
                    resampled=True
                if n!=nt:resampled=True
            if (m.axis_x_unit,m.axis_y_unit)!=(t.axis_x_unit,t.axis_y_unit):
                raise ValueError('Unterschiedliche Achseneinheiten')
            code, width, low, high = FORMATS[t.dtype]
            fmt = ('>' if t.endian=='big' else '<')+code
            originals=base.matrix(m,physical=True)
            modified=source.matrix(m,physical=True)
            delta=modified-originals
            if mode=='percent':
                if np.any((originals==0)&(delta!=0)):
                    raise ValueError('Prozentänderung bei Quellwert null nicht definiert')
                delta=np.divide(delta,originals,out=np.zeros_like(delta),where=originals!=0)*100.
            if resampled:
                from .interpolation import resample_surface
                originals=resample_surface(originals,m,t)
                modified=resample_surface(modified,m,t)
                delta=resample_surface(delta,m,t)
            for r in range(t.rows):
                for c in range(t.cols):
                    old = float(originals[r,c])
                    mod = float(modified[r,c])
                    change=float(delta[r,c])
                    if change == 0:
                        continue
                    before = target.physical_value(t,r,c)
                    after = before+change if mode=='delta' else before*(1+change/100.)
                    if not math.isfinite(after):
                        raise ValueError('Nichtendlicher Übertragungswert')
                    raw = t.raw_from_physical(after)
                    if not low <= raw <= high:
                        raise ValueError(f'Rohwertüberlauf in Zelle {r}/{c}')
                    pos = t.cell_offset(r,c)
                    payload = struct.pack(fmt,raw)
                    if payload != target.read(pos,width):
                        cells.append(TransferCell(r,c,old,mod,before,struct.unpack(fmt,payload)[0]*t.factor+t.bias,
                                                  pos,target.read(pos,width),payload,change,resampled))
        except (ValueError,OverflowError,TypeError) as exc:
            conflict = str(exc)
            cells = []
        plans.append(MapTransfer(m.name,t.name if t else '',m.offset,t.offset if t else -1,
                     'conflict' if conflict else 'ready', conflict or
                     ('Bestätigte Paarung; physikalisch linear/bilinear interpolierte Änderung, keine Extrapolation.' if resampled else
                      'Bestätigte Definitionen, identische Achsen; physikalische Änderung mit Zielskalierung.'),tuple(cells)))
    # Overlaps block all affected maps, including identical writes.
    from dataclasses import replace
    owners = {}
    overlap = set()
    for i, item in enumerate(plans):
        for cell in item.cells:
            for p in range(cell.offset,cell.offset+len(cell.after)):
                if p in owners:
                    overlap.update((i,owners[p]))
                owners[p] = i
    for i in overlap:
        plans[i] = replace(plans[i],status='conflict',evidence='Überlappende Zielkennfelder',cells=())
    return TransferPlan(source_identity,target_identity,hashlib.sha256(source.materialize()).hexdigest(),
                        hashlib.sha256(target.materialize()).hexdigest(),target.revision,mode,tuple(plans),bool(interpolate))


def apply_transfer(target: BinaryImage, plan: TransferPlan, selected: list[int], *, confirmed=False):
    if not confirmed:
        raise ValueError('Ausdrückliche Bestätigung der ausgewählten Änderungen erforderlich')
    if (target.digest != plan.target_identity.sha256 or target.revision != plan.target_revision or
            hashlib.sha256(target.materialize()).hexdigest()!=plan.target_current_sha256):
        raise ValueError('Ziel oder Vorschau hat sich geändert – erneut vergleichen')
    if not selected or len(set(selected))!=len(selected):
        raise ValueError('Eindeutige Auswahl erforderlich')
    changes = []
    for i in selected:
        if type(i) is not int or not 0 <= i < len(plan.maps) or plan.maps[i].status!='ready':
            raise ValueError('Konflikt oder ungültige Auswahl')
        for cell in plan.maps[i].cells:
            changes.extend((cell.offset+j,b,a) for j,(b,a) in enumerate(zip(cell.before,cell.after)))
    return target.commit(changes,label='Smart Map Transfer · '+plan.source_modified_sha256,
                         expected_revision=plan.target_revision)
