"""Scope geometry-only discovery to well-understood ECU calibration regions.

This is NOT semantic recognition; XDF/A2L metadata supplies functional labels.
"""
from __future__ import annotations
import bisect
from .model import BinaryImage, MapDefinition
from .detection import discover_maps
from .detection_extended import scan_u8
from .detection_32 import scan_32
from .detection_signed import scan_s16
from .profiles import identify_profile
from .precision import rank_candidates
from .axis_records import scan_axis_records, record_axes
from .structure_scan import scan_structures, lookup_descriptors
from .axis_arrays import scan_count_axes, axis_definitions
from .data_regions import data_mask, data_fraction, data_regions, block_size
from .confidence import apply_confidence, tier_for
from .candidate_model import load_model, score_candidates
from .map_groups import mark_twins
from . import parallel

RECORD_LIMIT=1000   # header records (nx,ny,X,Y,Z): 55 -> 200 -> 1000, each measured on complete OEM A2L (ME9.2.1, EDC17CP09); MS4x unchanged
INDEPENDENT_EVIDENCE=('candidate:code-reference','candidate:code-reference-generic','candidate:count-axis','candidate:nx,ny,x,y,z','candidate:pointer-descriptor','candidate:record-axis')


def _merged(spans):
    """Sorted, merged [start, end) intervals as (starts, ends) lists."""
    merged=[]
    for s,e in sorted(spans):
        if merged and s<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],e)
        else:merged.append([s,e])
    return [m[0] for m in merged],[m[1] for m in merged]


def _overlaps_any(lo,hi,merged):
    starts,ends=merged
    k=bisect.bisect_left(starts,hi)-1
    return k>=0 and ends[k]>lo


PARALLEL_MIN_BYTES=256*1024   # smaller images: worker start-up costs more than it saves
SCANNERS=('discover','u8','u32','s16')


def _scan_task(name,data,max_results,include_u32):
    """Worker-process task (module level, picklable): one record/grid scanner on raw bytes."""
    image=BinaryImage(data)
    if name=='records':
        return scan_axis_records(image,max_results=max_results,include_u32=include_u32)
    fn={'discover':discover_maps,'u8':scan_u8,'u32':scan_32,'s16':scan_s16}[name]
    return fn(image,max_results=max_results)


def _shift_to_window(candidates,start,profile):
    for m in candidates:
        m.offset+=start
        if m.candidate_region_start is not None:m.candidate_region_start+=start
        m.name=f'Unbekannter Datenbereich @ 0x{m.offset:08X}'
        m.kind='Unbekannt'
        m.label_origin=(m.label_origin+' · ' if m.label_origin else 'Heuristik · ')+f'{profile.family} · Datenfenster'
        m.label_evidence=('Strukturkandidat im bekannten Datenfenster, NICHT als Kennfeld identifiziert. '
                          'Für tatsächliche Kennfeldnamen exakt passende XDF/A2L importieren.')


def scan_calibration_candidates(image: BinaryImage, *,
                                limits: tuple[int,int,int,int] = (70,40,30,25),
                                cancelled=None, progress=None,
                                use_definitions: bool = True,
                                include_u32: bool = False, diagnostics=None,
                                structure_limit: int = 400) -> list[MapDefinition]:
    # Raw 32-bit geometry is severely width-ambiguous. Keep it an explicit
    # exploratory option; definition-backed 32-bit maps always remain supported.
    if diagnostics is not None:
        diagnostics.update({'format':1,'sha256':image.digest,'size':image.size,
            'include_unbound_u32':bool(include_u32),'independent_verification':False})
    if use_definitions:
        from ecu_studio.recognition.bundled_definitions import definition_candidates
        if progress: progress(2)
        defined = definition_candidates(image, cancelled=cancelled)
        if defined:
            if diagnostics is not None:diagnostics.update({'method':'bundled-definition','accepted_count':len(defined)})
            if progress: progress(100)
            return defined
    profile=identify_profile(image)
    start=profile.cal_start
    end=profile.cal_end
    target=BinaryImage(image.read(start,end-start)) if start is not None and end is not None else image
    # Record and grid scanners are independent of the structure scan below: on
    # large images they run in worker processes meanwhile (same results, same order).
    background=target.size>=PARALLEL_MIN_BYTES and parallel.worker_count()>1
    jobs=None
    if background:
        data=target.read(0,target.size)
        jobs=[parallel.defer(_scan_task,'records',data,RECORD_LIMIT,include_u32,parallel=True)]
        jobs+=[parallel.defer(_scan_task,name,data,limits[i],include_u32,parallel=True)
               for i,name in enumerate(SCANNERS) if name!='u32' or include_u32]
        candidates=[]
    else:
        candidates=scan_axis_records(target,max_results=RECORD_LIMIT,cancelled=cancelled,include_u32=include_u32)
        for i,scanner in enumerate((discover_maps,scan_u8,scan_32,scan_s16)):
            if scanner is scan_32 and not include_u32:continue
            if cancelled and cancelled():
                return []
            if progress:
                progress(i*23)
            candidates.extend(scanner(target,max_results=limits[i],cancelled=cancelled))
    if cancelled and cancelled():
        return []
    if start is not None and jobs is None:
        _shift_to_window(candidates,start,profile)
    # Grid-free geometry runs on the full image: code references live outside
    # the calibration window. Offsets are already absolute.
    if progress:
        progress(75)
    lo,hi=start or 0,end if end is not None else image.size
    raw=image.read(0,image.size)
    mask=data_mask(raw) if start is None else None
    # Unknown image: the row-pitch search only visits data-like blocks (faster,
    # and code bytes cannot produce smoothness-only candidates).
    regions=data_regions(mask,gap=block_size(len(raw))) if mask is not None else None
    axes=scan_count_axes(raw,lo,hi) if structure_limit>0 else []
    if structure_limit>0:
        # Axes named by lookup calls are code-confirmed even without a chain.
        known={ax.header for ax in axes}
        spans=[(ax.header,ax.end) for ax in axes]
        for pair in lookup_descriptors(raw,lo,hi).values():
            for ax in pair:
                if ax and ax.header not in known and not any(ax.header<e and s<ax.end for s,e in spans):
                    axes.append(ax);known.add(ax.header);spans.append((ax.header,ax.end))
        axes.sort(key=lambda ax:ax.header)
    structures=scan_structures(image,lo,hi,max_results=structure_limit,cancelled=cancelled,
                               axes=axes,regions=regions) if structure_limit>0 else []
    if cancelled and cancelled():
        return []
    if jobs is not None:
        for job in jobs:
            part=job.result(cancelled)
            if part is None:
                return []
            candidates.extend(part)
        if start is not None:
            _shift_to_window(candidates,start,profile)
    # Curves and breakpoint arrays carry their own (code/count) evidence; the
    # surface ranking below only judges 2-D areas.
    lines=[m for m in structures if min(m.rows,m.cols)<3]+axis_definitions(axes)
    candidates=[m for m in structures if min(m.rows,m.cols)>=3]+candidates
    if start is None:
        # Unknown image: code is scanned too. Smoothness-only candidates must lie
        # in data-like blocks; code references, axis chains and record headers
        # are independent evidence and stay.
        def in_data(m):
            return m.record_layout in INDEPENDENT_EVIDENCE or data_fraction(mask,m.offset,m.offset+m.length)>=.5
        dropped=sum(not in_data(m) for m in candidates+lines)
        candidates=[m for m in candidates if in_data(m)]
        lines=[m for m in lines if in_data(m)]
        if diagnostics is not None:diagnostics['outside_data_blocks']=dropped
    if diagnostics is not None:diagnostics.update({'method':'heuristic','scope':[start or 0,end or image.size],
        'input_candidates':len(candidates),'structure_candidates':len(structures),'axis_candidates':len(axes)})
    ranked=rank_candidates(image,candidates,max_results=sum(limits)+structure_limit,diagnostics=diagnostics)
    spans=[(m.candidate_region_start if m.candidate_region_start is not None else m.offset,m.offset+m.length) for m in lines]
    # Legacy grid windows must not swallow a detected axis or referenced curve.
    merged=_merged(spans)
    kept=[m for m in ranked if not _overlaps_any(m.offset,m.offset+m.length,merged)]
    # Axes of accepted header records are axes too (EDC17 SWORD records, ME9, MED17 ...).
    taken=_merged([(m.offset,m.offset+m.length) for m in lines])
    extra=[a for m in kept for a in record_axes(image,m)
           if not _overlaps_any(a.offset,a.offset+a.length,taken)]
    result=sorted(kept+lines+extra,key=lambda m:m.offset)
    apply_confidence(result,family=profile.family if start is not None else 'Unbekannt')
    # Data-only candidates: learned scorer (family-out validated) replaces the
    # coarse class rate with the held-out hit rate of the candidate's score.
    model=load_model()
    if model is not None:
        full_mask=mask if mask is not None else data_mask(raw)
        scores=score_candidates(image,result,full_mask)
        drop_below=model.get('drop_below')
        keep=[]
        for i,m in enumerate(result):
            if i in scores:
                p,rate=scores[i]
                if drop_below is not None and p<drop_below:
                    continue
                m.calibrated_rate=round(rate,3)
                m.evidence_tier=tier_for(rate)
                m.notes=(m.notes+f' Lernmodell (familienübergreifend geprüft): Score {p:.2f}, '
                         f'gemessene Trefferquote dieses Score-Bereichs {rate:.0%}.').strip()
            keep.append(m)
        if diagnostics is not None:diagnostics['model_dropped']=len(result)-len(keep)
        result=keep
    twins=mark_twins(raw,result)
    if diagnostics is not None:
        diagnostics['accepted_count']=len(result)
        diagnostics['content_twin_groups']=twins
    if progress:
        progress(100)
    return result
