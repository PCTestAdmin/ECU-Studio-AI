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
from .curve_records import scan_curve_records
from .structure_scan import scan_structures, lookup_descriptors, c16x_base
from .tricore_refs import call_descriptors
from .type_status import open_axis_signs
from .axis_arrays import scan_count_axes, axis_definitions
from .data_regions import data_mask, data_fraction, data_regions, block_size
from .confidence import apply_confidence
from .candidate_model import load_model, model_status, score_candidates
from .map_groups import mark_twins
from .architecture import detect_architecture, TRICORE, C16X
from .region_classes import text_spans, pointer_spans, address_word_spans, classify, POINTER_COVERAGE
from . import parallel

RECORD_LIMIT=2000   # header records (nx,ny,X,Y,Z): 55 -> 200 -> 1000 -> 2000, each measured on complete OEM A2L (ME9.2.1, EDC17CP09; 1.21.0: MEVD17.2 full images with mixed widths exceed 1000); MS4x unchanged
AXIS_RECORD_LAYOUTS=('candidate:record-axis','candidate:count-axis','candidate:curve-record')


def _axis_ranges(m):
    """Byte ranges of a structural find's axes (its own bytes for a single axis)."""
    if m.record_layout in AXIS_RECORD_LAYOUTS:
        return [(m.offset,m.offset+m.length)]
    if m.record_layout!='candidate:nx,ny,x,y,z':
        return []
    out=[]
    for off,values in ((m.axis_x_offset,m.axes_x),(m.axis_y_offset,m.axes_y)):
        if off is not None and values:
            width=1 if all(0<=v<=255 for v in values) else 2
            out.append((off,off+width*len(values)))
    return out


def _axes_are_pointers(m,addresses):
    """All axes of a header record lie on address words (ARM descriptors, rusEFI Map3D); a single
    axis only if a neighbouring aligned word is an address word as well."""
    ranges=_axis_ranges(m)
    if not ranges or not all(addresses.coverage(a,b)>=POINTER_COVERAGE for a,b in ranges):
        return False
    if m.record_layout!='candidate:nx,ny,x,y,z':
        a,b=ranges[0]
        return addresses.coverage(a-4,a)==1 or addresses.coverage(b,b+4)==1
    return True


INDEPENDENT_EVIDENCE=('candidate:code-reference','candidate:code-reference-generic','candidate:count-axis','candidate:nx,ny,x,y,z','candidate:pointer-descriptor','candidate:record-axis','candidate:curve-record','candidate:code-call')


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


# Smoothness-only (row-pitch) candidates that the bytes themselves contradict (1.21.0 round 3).
# Development data (MEVD17.2/MSD80, 58 images, row-pitch candidates against the A2L):
#  - an accepted header record (count + rising axes) starts strictly inside the run: the run
#    is a list of records, not one table (0 of 661 exact in calibration images, 1 of 96 in
#    full images);
#  - only a signed reading is smooth: a pattern cannot establish a sign, and wraps between
#    unrelated values read smooth signed (2 exact against 2 128 confusions, both makers).
PITCH_NO_RECORDS=True
PITCH_UNSIGNED_ONLY=True
PITCH_LAYOUT='candidate:row-pitch'
# Phase 4: a header only contradicts when nothing stronger contradicts the header. A record whose bytes
# overlap a table the program code addresses (with another start) is an unconfirmed reading; the ranking
# drops it anyway, so it must not remove a pattern reading first (MS43 regression of round 3: the header
# lay inside a code-referenced 8x8 map and displaced the correct neighbouring table).
HEADS_CODE_CHECKED=True
CODE_LAYOUTS=('candidate:code-reference','candidate:code-reference-generic','candidate:code-call',
              'candidate:pointer-descriptor')


def _code_refuted(record,code):
    """True if a code-evidenced table overlaps the record (header to last cell) without being it."""
    starts,items,longest=code
    lo,hi=record.candidate_region_start,record.offset+record.length
    for s,e in items[bisect.bisect_left(starts,lo-longest):bisect.bisect_left(starts,hi)]:
        if e>lo and s<hi and s not in (record.offset,record.candidate_region_start):
            return True
    return False


def _contradicted_patterns(candidates):
    """Row-pitch candidates whose bytes contradict a single table (see above)."""
    records=[m for m in candidates if m.record_layout=='candidate:nx,ny,x,y,z' and m.candidate_region_start is not None]
    if HEADS_CODE_CHECKED and records:
        spans=sorted((m.offset,m.offset+m.length) for m in candidates if m.record_layout in CODE_LAYOUTS)
        if spans:
            code=([s for s,_ in spans],spans,max(e-s for s,e in spans))
            records=[m for m in records if not _code_refuted(m,code)]
    heads=sorted({m.candidate_region_start for m in records})
    out=[]
    for m in candidates:
        if m.record_layout==PITCH_LAYOUT:
            if PITCH_UNSIGNED_ONLY and m.dtype.startswith('s'):
                continue
            if PITCH_NO_RECORDS and heads:
                i=bisect.bisect_right(heads,m.offset)
                if i<len(heads) and heads[i]<m.offset+m.length:
                    continue
        out.append(m)
    return out


# After 1.21.0-rc1: values the program code loads directly (tricore_refs.direct_loads) start objects of
# their own; a smoothness-only run with one strictly inside spans several objects. Applied as a pure removal
# after ranking: dropping such runs inside the pitch search freed its result budget for weaker readings
# (development data, MEVD17.2 full images: +41 confusions elsewhere), so here nothing can take their place.
LOADED_REFUTES_PITCH=True


def _crosses(m,points):
    """True if a point of the sorted list lies strictly inside the table (not at its start)."""
    i=bisect.bisect_right(points,m.offset)
    return i<len(points) and points[i]<m.offset+m.length


def refuted_by_loads(candidates,loaded):
    """The candidates without the smoothness-only runs that a directly loaded value lies inside."""
    points=sorted(loaded)
    if not LOADED_REFUTES_PITCH or not points:
        return list(candidates)
    return [m for m in candidates if not (m.record_layout==PITCH_LAYOUT and _crosses(m,points))]


# Quality phase 4: the head of a chained curve record (n, X[n], W[n]; structure evidence) that lies strictly
# inside a smoothness-only run refutes the run, as a 2-D header record does (PITCH_NO_RECORDS). Applied after
# ranking as a pure removal (see LOADED_REFUTES_PITCH). Development data (58 images, A2L for evaluation only):
# confusions 5 138 -> 4 478, exact 2-D tables unchanged (0 lost); exact 1-D objects +1 381 (MEVD17.2) and
# +3 239 (MSD80), 0 lost. Found while classifying the 1-D hits lost to code-backed axes: the extra tables moved
# smoothness-only runs over chained curve records, which only fill gaps.
CURVE_HEADS_REFUTE_PITCH=True
# Quality phase 5: the axis of a code-named curve (tricore_refs.CODE_CURVES) becomes an axis candidate only when
# the curve itself is accepted (ablation switch).
CURVE_AXES_WITH_CURVE=True
# Quality phase 6: the axis of a code-named curve that was NOT accepted only fills a gap when it has at least
# three points, the general rule of axis_arrays ("two-point arrays are common by chance"): a lone two-point
# count axis has nothing that confirms its width or sign. HOLDOUT-DERIVED: the three new unmarked width errors
# of quality phase 5 (one holdout line) were exactly such two-point gap fillers (an 8-bit axis read as 16-bit
# under a 16-bit count); development data has no two-point gap filler at all, so the rule is not confirmed there
# (0 changes). All 106 gap fillers with three or more points (development 51, holdout 55) matched the reference.
ORPHAN_MIN_POINTS=3
# Quality phase 5 (P3): a smoothness-only run that STARTS inside a chained curve record (behind its head, before
# the end of its values) is refuted as well; before, only a head strictly inside the run counted, so runs starting
# within the record covered its curve (development data: 13 + 4 exact 1-D objects lost that way). Ablation switch.
CURVE_RECORD_REFUTES_PITCH_START=True


def refuted_by_curve_heads(candidates,curves):
    """The candidates without the smoothness-only runs that a chained curve record head lies strictly inside
    (and, with CURVE_RECORD_REFUTES_PITCH_START, that start strictly inside a chained curve record)."""
    heads=sorted({c.candidate_region_start for c in curves if c.candidate_region_start is not None})
    if not CURVE_HEADS_REFUTE_PITCH or not heads:
        return list(candidates)
    records=_merged([(c.candidate_region_start,c.offset+c.length) for c in curves
                     if c.candidate_region_start is not None and c.offset>c.candidate_region_start])
    def starts_inside(m):
        starts,ends=records
        k=bisect.bisect_right(starts,m.offset)-1
        return k>=0 and starts[k]<m.offset<ends[k]
    return [m for m in candidates if not (m.record_layout==PITCH_LAYOUT and
            (_crosses(m,heads) or (CURVE_RECORD_REFUTES_PITCH_START and starts_inside(m))))]


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
                                structure_limit: int = 400, step=None) -> list[MapDefinition]:
    # Raw 32-bit geometry is severely width-ambiguous. Keep it an explicit
    # exploratory option; definition-backed 32-bit maps always remain supported.
    if diagnostics is not None:
        diagnostics.update({'format':1,'sha256':image.digest,'size':image.size,
            'include_unbound_u32':bool(include_u32),'independent_verification':False})
    def stage(text, percent=None):
        # ``step`` names the running stage for the user; ``progress`` stays a plain percentage.
        if step: step(text)
        if progress and percent is not None: progress(percent)
    if use_definitions:
        from ecu_studio.recognition.bundled_definitions import definition_candidates
        stage('Mitgelieferte Definitionen prüfen', 2)
        defined = definition_candidates(image, cancelled=cancelled)
        if defined:
            if diagnostics is not None:diagnostics.update({'method':'bundled-definition','accepted_count':len(defined)})
            if progress: progress(100)
            return defined
    stage('Kalibrierbereich bestimmen')
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
        stage('Datensatzköpfe und Raster', 5)
        candidates=scan_axis_records(target,max_results=RECORD_LIMIT,cancelled=cancelled,include_u32=include_u32)
        for i,scanner in enumerate((discover_maps,scan_u8,scan_32,scan_s16)):
            if scanner is scan_32 and not include_u32:continue
            if cancelled and cancelled():
                return []
            if progress:
                progress(5+i*23)
            candidates.extend(scanner(target,max_results=limits[i],cancelled=cancelled))
    if cancelled and cancelled():
        return []
    if start is not None and jobs is None:
        _shift_to_window(candidates,start,profile)
    # Grid-free geometry runs on the full image: code references live outside
    # the calibration window. Offsets are already absolute.
    stage('Achsen-Arrays', 75)
    lo,hi=start or 0,end if end is not None else image.size
    raw=image.read(0,image.size)
    # Code decoders run only for an established architecture (core/architecture):
    # chance opcodes of other code are no evidence.
    arch=detect_architecture(raw)
    if diagnostics is not None:diagnostics['architecture']=arch.describe()
    # Computed once per scan and passed on; nothing keeps the image after the scan.
    base=c16x_base(raw) if arch.name==C16X and structure_limit>0 else None
    mask=data_mask(raw) if start is None else None
    # Unknown image: the row-pitch search only visits data-like blocks (faster,
    # and code bytes cannot produce smoothness-only candidates).
    regions=data_regions(mask,gap=block_size(len(raw))) if mask is not None else None
    axes=scan_count_axes(raw,lo,hi) if structure_limit>0 else []
    if cancelled and cancelled():
        return []
    stage('Programmcode: Interpolationsaufrufe', 78)
    calls=call_descriptors(raw,lo,hi) if structure_limit>0 and arch.name==TRICORE else {}
    if structure_limit>0:
        # Axes named by lookup calls are code-confirmed even without a chain.
        known={ax.header for ax in axes}
        spans=[(ax.header,ax.end) for ax in axes]
        lookups=lookup_descriptors(raw,lo,hi,base) if arch.name==C16X else {}
        # Axes from routine-level prelookups (tricore_refs.PRE_FUNCTION) are weaker: they only count as part of
        # an accepted table, never as axis candidates of their own (MEVD17.2 development: 16-18 curve records
        # per image were displaced by such axes).
        # Axes of code-named curves (tricore_refs.CODE_CURVES) only count together with their curve (added
        # below once it is accepted): an axis alone would displace the curve record that holds both (quality
        # phase 5, development data: 67 exact curves lost before).
        pairs=list(lookups.values())+[(c.x_axis,c.y_axis) for c in calls.values()
                                      if getattr(c,'pre_scope','')!='function'
                                      and not (CURVE_AXES_WITH_CURVE and getattr(c,'curve',''))]
        def add_axis(ax):
            # Values decide: a record's second count lies inside the span of its first axis.
            if ax and ax.header not in known and not any(ax.offset<e and s<ax.end for s,e in spans):
                axes.append(ax);known.add(ax.header);spans.append((ax.header,ax.end))
        for pair in pairs:
            for ax in pair:
                add_axis(ax)
        axes.sort(key=lambda ax:ax.header)
    stage('Strukturen und Zeilenabstände', 82)
    structures=scan_structures(image,lo,hi,max_results=structure_limit,cancelled=cancelled,
                               axes=axes,regions=regions,calls=calls,architecture=arch,
                               base=base) if structure_limit>0 else []
    if cancelled and cancelled():
        return []
    orphans=[]   # axes of code-named curves the structure scan did not accept: gap fillers only (below)
    if structure_limit>0 and CURVE_AXES_WITH_CURVE:
        accepted={m.offset for m in structures if min(m.rows,m.cols)==1}
        for c in calls.values():
            if getattr(c,'curve','') and c.data in accepted:
                add_axis(c.x_axis)
            elif getattr(c,'curve','') and c.x_axis.header not in known and c.x_axis.count>=ORPHAN_MIN_POINTS:
                orphans.append(c.x_axis)
        axes.sort(key=lambda ax:ax.header)
    if jobs is not None:
        stage('Datensatzköpfe und Raster (parallel)', 88)
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
    before=len(candidates)
    candidates=_contradicted_patterns(candidates)
    if diagnostics is not None:diagnostics['contradicted_patterns']=before-len(candidates)
    stage(f'{len(candidates)} Kandidaten bewerten', 92)
    ranked=rank_candidates(image,candidates,max_results=sum(limits)+structure_limit,diagnostics=diagnostics)
    spans=[(m.candidate_region_start if m.candidate_region_start is not None else m.offset,m.offset+m.length) for m in lines]
    # Legacy grid windows must not swallow a detected axis or referenced curve.
    merged=_merged(spans)
    kept=[m for m in ranked if not _overlaps_any(m.offset,m.offset+m.length,merged)]
    records=[m for m in candidates if m.record_layout=='candidate:nx,ny,x,y,z']
    all_curves=scan_curve_records(image,records,cancelled=cancelled)
    before=len(kept)
    kept=refuted_by_curve_heads(kept,all_curves)
    if diagnostics is not None:diagnostics['curve_refuted_patterns']=before-len(kept)
    # Axes of accepted header records are axes too (EDC17 SWORD records, ME9, MED17 ...).
    taken=_merged([(m.offset,m.offset+m.length) for m in lines])
    extra=[a for m in kept for a in record_axes(image,m)
           if not _overlaps_any(a.offset,a.offset+a.length,taken)]
    # Curve records (n, X, W) only fill gaps: they never displace a 2-D table, a
    # line or a record axis (the record list gives byte order and chain neighbours).
    occupied=_merged([((m.candidate_region_start if m.candidate_region_start is not None else m.offset),m.offset+m.length)
                      for m in kept+lines+extra])
    curves=[c for c in all_curves
            if not _overlaps_any(c.candidate_region_start,c.offset+c.length,occupied)]
    seen=set()
    for c in curves:   # axis and values of one record, each once
        key=(c.offset,c.cols,c.record_layout)
        if key not in seen:
            seen.add(key);extra.append(c)
    if orphans:
        # The call target may still be a standalone axis (development data: mini set, 4 exact axes): it fills a
        # gap that no table, line, record axis or curve record covers.
        filled=[((m.candidate_region_start if m.candidate_region_start is not None else m.offset),m.offset+m.length)
                for m in kept+lines+extra]
        added=[]
        for a in axis_definitions(sorted({ax.header:ax for ax in orphans}.values(),key=lambda ax:ax.header)):
            s=a.candidate_region_start if a.candidate_region_start is not None else a.offset
            if not _overlaps_any(s,a.offset+a.length,_merged(filled)):
                extra.append(a);filled.append((s,a.offset+a.length));added.append(a.offset)
        if diagnostics is not None:diagnostics['curve_orphan_axes']=added
    before=len(kept)
    kept=refuted_by_loads(kept,getattr(calls,'loaded',()))
    if diagnostics is not None:diagnostics['loaded_refuted_patterns']=before-len(kept)
    result=sorted(kept+lines+extra,key=lambda m:m.offset)
    # Proven non-tables: runs of text strings, and pointer tables of an
    # architecture with a known pointer format (core/region_classes). Only
    # near-complete coverage counts; everything else stays a candidate.
    # Header records whose axes are address words are pointer structures
    # (little-endian 0x080Axxxx reads as a falling u8 axis 0x11 0x10 0x0A 0x08).
    text,pointers=text_spans(raw),pointer_spans(raw,arch)
    addresses=address_word_spans(raw,arch)
    suppressed={'text':0,'pointer':0}
    kept_result=[]
    for m in result:
        reason=classify(m.offset,m.offset+m.length,text,pointers)
        if not reason and len(addresses) and _axes_are_pointers(m,addresses):
            reason='pointer'
        if reason:
            suppressed[reason]+=1
        else:
            kept_result.append(m)
    result=kept_result
    if diagnostics is not None:diagnostics['suppressed']=suppressed
    opened=open_axis_signs(image,result)
    if diagnostics is not None:diagnostics['axis_signs_open']=opened
    apply_confidence(result,family=profile.family if start is not None else 'Unbekannt')
    # Data-only candidates: a learned scorer may drop weak ones; it is applied only
    # with cleared training data (core/candidate_model.py). None ships with 1.19.
    # Its score is noted, not shown as a probability.
    model=load_model()
    if diagnostics is not None:diagnostics['candidate_model']=model_status()
    if model is not None:
        stage('Lernmodell für Datenmuster-Funde', 97)
        full_mask=mask if mask is not None else data_mask(raw)
        scores=score_candidates(image,result,full_mask)
        drop_below=model.get('drop_below')
        keep=[]
        for i,m in enumerate(result):
            if i in scores:
                p,_=scores[i]
                if drop_below is not None and p<drop_below:
                    continue
                m.notes=(m.notes+f' Lernmodell (freigegebene Trainingsdaten): Score {p:.2f}, keine Wahrscheinlichkeit.').strip()
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
