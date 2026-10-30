"""Evidence-based post-ranking of unlabeled map-shaped regions.

This is geometry detection, NOT map-function identification. A random byte window,
wrong endian interpretation, or overlapping array must not turn into an ECU label.
No training data or binary content is stored.
"""
from __future__ import annotations
import bisect
import itertools
import numpy as np
from functools import lru_cache
from .model import BinaryImage, MapDefinition

STRUCTURAL_LAYOUTS = ('candidate:nx,ny,x,y,z', 'candidate:code-reference', 'candidate:row-pitch',
                      'candidate:code-reference-generic', 'candidate:pointer-descriptor', 'candidate:code-call')


@lru_cache(maxsize=1)
def _structure_advisor():
    try:
        from ecu_studio.recognition.structure_rejector import installed_rejector
        return installed_rejector()
    except (ValueError,TypeError,OSError,ImportError):
        return None


def surface_evidence(values, *, min_unique=12) -> dict:
    """Bounded, scale-independent diagnostics for an array-like region."""
    a=np.asarray(values,dtype=np.float64)
    if a.ndim!=2 or min(a.shape)<3 or a.size>4096 or not np.isfinite(a).all():
        return {'valid':False,'score':0.,'reason':'Unzureichende Matrix'}
    p05,p25,p75,p95=np.percentile(a,[5,25,75,95])
    spread=float(p95-p05)
    if spread<6 or len(np.unique(a))<min(8,min_unique):
        return {'valid':False,'score':0.,'reason':'Konstant/zu wenig Dynamik'}
    dx=np.diff(a,axis=1);dy=np.diff(a,axis=0)
    h=float(np.median(np.abs(dx))/spread)
    v=float(np.median(np.abs(dy))/spread)
    # Derivative outliers indicate code/noise, not continuously sampled surface.
    tails=float((np.percentile(np.abs(dx),90)+np.percentile(np.abs(dy),90))/(2*spread))
    rows=float(np.std(a.mean(axis=1))/spread)
    cols=float(np.std(a.mean(axis=0))/spread)
    # A 2D candidate must vary along two independent axes, not be a repeated
    # 1D axis or unstructured noise. Values are structural rankings only.
    coherent=(h<.24 and v<.28 and tails<.70 and
              rows>.008 and cols>.008 and rows<1.25 and cols<1.25 and
              len(np.unique(a))>=min_unique)
    penalty=min(1., .75*h+.75*v+.45*tails)
    quality=max(0.,min(1.,1.-penalty))
    return {'valid':bool(coherent),'score':round(quality,4),
            'horizontal_jump':round(h,4),'vertical_jump':round(v,4),
            'tail_jump':round(tails,4),'row_variation':round(rows,4),
            'column_variation':round(cols,4),
            'reason':'2D-Oberflächenstruktur' if coherent else 'Zu verrauscht oder eindimensional'}


EVIDENCED_LAYOUTS=('candidate:nx,ny,x,y,z','candidate:code-reference','candidate:code-reference-generic',
                   'candidate:pointer-descriptor','candidate:code-call')


def _header_inside(plain):
    """Predicate: does an offset lie strictly inside one of the given candidates?"""
    spans=sorted(((m.candidate_region_start if m.candidate_region_start is not None else m.offset),m.offset+m.length)
                 for m in plain)
    starts=[s for s,_ in spans]
    reach=list(itertools.accumulate((e for _,e in spans),max))
    def inside(a):
        k=bisect.bisect_left(starts,a)-1
        return k>=0 and reach[k]>a
    return inside


def _priority(m, inside) -> bool:
    if m.record_layout not in EVIDENCED_LAYOUTS:
        return False
    head=m.candidate_region_start if m.candidate_region_start is not None else m.offset
    return not inside(head)


def rank_candidates(image:BinaryImage, candidates:list[MapDefinition], *,
                    max_results:int=140, diagnostics=None) -> list[MapDefinition]:
    """Reject obvious noise, flag endianness ambiguity, deduplicate overlaps.

    Existing exact BIN-bound definitions remain outside this heuristic and take
    precedence. Scores are NOT probabilities and never make a map verified.
    """
    evaluated=[]
    def reject(m,reason):
        if diagnostics is None:return
        counts=diagnostics.setdefault('rejection_counts',{})
        counts[reason]=counts.get(reason,0)+1
        samples=diagnostics.setdefault('rejection_examples',[])
        if len(samples)<200:samples.append({'offset':m.offset,'rows':m.rows,'cols':m.cols,
            'dtype':m.dtype,'endian':m.endian,'reason':reason})
    advisor=_structure_advisor()
    from ecu_studio.recognition.calibration_ranker import installed_ranker
    preset_advisor=installed_ranker()
    for m in candidates:
        try:
            if m.rows<3 or m.cols<3 or m.rows*m.cols>4096:
                reject(m,'unsupported-geometry');continue
            m.validate(image.size)
            a=image.matrix(m)
            # Layouts with independent structural evidence (header axes, code
            # reference, inferred row pitch) may be small tables with few values.
            ev=surface_evidence(a,min_unique=4 if m.record_layout in STRUCTURAL_LAYOUTS else 12)
            # Shape given by two axes the code loads with the table: flat or
            # coarse tables are still tables, so surface smoothness cannot veto.
            # Header records reach this point only after the record scan accepted
            # their counts and axes (flat value blocks included, see axis_records).
            axis_backed=m.record_layout in ('candidate:code-reference','candidate:code-call','candidate:pointer-descriptor','candidate:nx,ny,x,y,z') and bool(m.axes_x) and bool(m.axes_y)
            if not ev['valid']:
                if not axis_backed:
                    reject(m,'insufficient-surface-evidence');continue
                ev={'valid':True,'score':ev.get('score',0.),'horizontal_jump':ev.get('horizontal_jump',0.),
                    'vertical_jump':ev.get('vertical_jump',0.),
                    'reason':'Größe durch Kopf-Datensatz mit Achsen belegt' if m.record_layout=='candidate:nx,ny,x,y,z'
                    else 'Größe durch vom Code geladene Achsen belegt'}
            if not axis_backed and narrower_storage_alias(image,m,ev):
                reject(m,'storage-width-ambiguous');continue
            # A trained synthetic-only model is an optional audit hint,
            # never a verification gate or semantic classifier. No rejection,
            # no offset relocation and no confidence inflation from its score.
            synthetic_hint=None
            if advisor is not None:
                try:
                    synthetic_hint=advisor.assess(a)
                except (TypeError,ValueError,OverflowError):
                    pass
            ambiguous=False
            if m.width>1 and m.dtype in ('u16','s16','u32','s32') and not m.equation:
                other=MapDefinition(**m.asdict())
                other.endian='little' if m.endian=='big' else 'big'
                b=image.matrix(other)
                alt=surface_evidence(b)
                ambiguous=bool(alt['valid'] and alt['score']>=ev['score']-.025)
            strength=.65*ev['score']+.35*min(1.,max(0.,m.confidence)/.45)
            if ambiguous:strength*=.76
            if m.record_layout in ('candidate:nx,ny,x,y,z','candidate:code-reference','candidate:code-call','candidate:pointer-descriptor'):strength+=.12
            if synthetic_hint is not None:
                # Gentle prioritisation only, never removal. Unvalidated real
                # domain: synthetic training is NOT a safe negative gate.
                strength*=.88+.12*synthetic_hint['score']
            preset_score=None
            if preset_advisor is not None:
                preset_score=preset_advisor.assess(a)['score']
                # Open ECU presets improve ordering only; no domain-validated
                # OEM rejection gate, semantic confidence, or address changes.
                strength*=.8+.2*preset_score
            evaluated.append((strength,m,ev,ambiguous,synthetic_hint,preset_score))
        except (IndexError,ValueError,OverflowError,TypeError):
            reject(m,'invalid-layout-or-values');continue
    # Evidenced candidates win overlaps, unless their own header lies inside a
    # smoothness candidate that starts earlier: smooth tables contain runs that
    # read like a count header with axes (then strength decides, as before).
    inside=_header_inside([z[1] for z in evaluated if z[1].record_layout not in EVIDENCED_LAYOUTS])
    evaluated.sort(key=lambda z:(not _priority(z[1],inside),-z[0],z[1].offset,z[1].length))
    selected=[]
    spans=[]
    plain=0
    for strength,m,ev,ambiguous,synthetic_hint,preset_score in evaluated:
        # The limit bounds smoothness-only guesses. Header records, code
        # references and descriptors carry their own evidence and are not cut.
        evidenced=m.record_layout in EVIDENCED_LAYOUTS
        if not evidenced and plain>=max_results:
            continue
        start=m.candidate_region_start if m.candidate_region_start is not None else m.offset
        end=m.offset+m.length
        # Heuristics are competing hypotheses, not definition-backed aliases.
        # Even partial overlap must not yield contradictory editable tables.
        if any(start<e and s<end for s,e in spans):
            reject(m,'competing-overlapping-layout')
            continue
        m.confidence=round(min(.49, .48*strength),4)
        note=('Präzisionsprüfung: '+ev['reason']+'; normierte Kanten-Sprünge '
              f'H={ev["horizontal_jump"]:.3f}, V={ev["vertical_jump"]:.3f}. '
              'Reine Strukturwertung, KEIN bestätigter Kennfeldtyp.')
        if ambiguous:note+=' Byte-Reihenfolge NICHT eindeutig.'
        if synthetic_hint is not None:
            note+=(' Synthetisch trainierter KI-Strukturwert '
                   f'{synthetic_hint["score"]:.3f}; nicht auf echten ECU-/TCU-Holdouts validiert.')
        if preset_score is not None:
            note+=f' Open-ECU-Preset-Rangwert {preset_score:.3f}; keine OEM-Funktionsbestätigung.'
        m.notes=(m.notes+' '+note).strip()
        m.label_evidence=(m.label_evidence+' '+note).strip()
        m.label_origin=(m.label_origin+' · Präzisionsprüfung').strip(' ·') if m.label_origin else 'Ungeprüfter 2D-Strukturkandidat'
        m.kind='Unbekannt'
        m.type_score=0.
        m.verified=False
        selected.append(m);spans.append((start,end))
        plain+=not evidenced
    if diagnostics is not None:
        diagnostics['accepted']=[{'offset':m.offset,'rows':m.rows,'cols':m.cols,'dtype':m.dtype,
            'endian':m.endian,'source':m.source,'verified':m.verified} for m in selected]
    return sorted(selected,key=lambda m:m.offset)


def narrower_storage_alias(image, m, evidence=None) -> bool:
    """Abstain if packed subwords explain the same bytes at least as well.

    Smooth bytes/words grouped into u32 create convincing billion-valued
    surfaces. Compare the SAME physical span and row pitch, not unrelated
    windows. This is width ambiguity, not proof of a replacement table shape.
    Genuine large 32-bit values remain supported; no magnitude cap is used.
    Explicit XDF/A2L layouts never pass through this heuristic gate.
    """
    if m.width <= 1 or m.dtype not in ('u16','s16','u32','s32'):
        return False
    if m.storage_order != 'row-major' or m.major_stride_bits or m.minor_stride_bits:
        return False
    ev = evidence or surface_evidence(image.matrix(m))
    for width in (1,2):
        if width >= m.width:continue
        for endian in (['big'] if width == 1 else ['big','little']):
            ratio=m.width//width
            for rows,cols in ((m.rows,m.cols*ratio),(m.rows*ratio,m.cols)):
                other=MapDefinition('Subword-Prüfung',m.offset,rows,cols,
                                    dtype='u'+str(width*8),endian=endian)
                # Compare both row-pitch hypotheses over the SAME complete
                # byte span; a wrong u32 width can also halve the row count.
                alt=surface_evidence(image.matrix(other),min_unique=4)
                # Pairing words suppresses low-half detail and can artificially
                # improve smoothness. A small ranking lead is not width evidence.
                # An alternative only needs to create doubt, not qualify as a
                # newly discovered map. Use a wider structural envelope here;
                # otherwise arbitrary discovery cutoffs manufacture certainty.
                plausible=(alt['valid'] or (
                    alt.get('horizontal_jump',1)<.30 and alt.get('vertical_jump',1)<.35 and
                    alt.get('tail_jump',1)<.9 and
                    .008<alt.get('row_variation',0)<2 and .008<alt.get('column_variation',0)<2))
                if plausible and alt['score'] >= ev['score']-.08:
                    return True
    return False
