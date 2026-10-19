"""Read-only cross-version map matching in physical coordinates.

Geometry/name agreement is evidence, never automatic verification. Changes in
addresses, datatypes, scale and grid density are handled through definitions.
"""
from dataclasses import dataclass,asdict,replace
import numpy as np
from .model import BinaryImage
from .interpolation import resample_surface
from .profiles import identify_profile


@dataclass(frozen=True)
class MapMatch:
    source_index:int
    target_index:int
    source_name:str
    target_name:str
    source_offset:int
    target_offset:int
    score:float
    rmse:float
    normalized_rmse:float
    maximum_difference:float
    correlation:float
    interpolated:bool
    name_agrees:bool
    unique:bool
    source_verified:bool
    target_verified:bool
    evidence:str


def compare_surfaces(source,target,m,t):
    """Compare ORIGINAL baselines. Edits are deliberately excluded from matching."""
    m.validate(source.size);t.validate(target.size)
    if not m.unit.strip() or m.unit!=t.unit:
        raise ValueError('Belegte gleiche Werteinheiten für mathematischen Abgleich erforderlich')
    a=(source if not source.dirty_bytes else BinaryImage(source.original)).matrix(m,physical=True)
    b=(target if not target.dirty_bytes else BinaryImage(target.original)).matrix(t,physical=True)
    aligned=resample_surface(a,m,t)
    if not np.isfinite(b).all():raise ValueError('Nichtendliche Zieloberfläche')
    difference=b-aligned
    rmse=float(np.sqrt(np.mean(difference**2)))
    span=max(float(np.ptp(aligned)),float(np.ptp(b)),abs(float(np.mean(aligned)))*.01,1e-12)
    norm=rmse/span
    if not np.isfinite([rmse,span,norm]).all():raise ValueError('Numerischer Bereich des Abgleichs überschritten')
    x=aligned.ravel()-aligned.mean();y=b.ravel()-b.mean()
    denom=float(np.linalg.norm(x)*np.linalg.norm(y))
    corr=float(np.clip(np.dot(x,y)/denom,-1,1)) if denom>1e-12 else 0.
    same=np.array_equal(aligned,b)
    # Same shape alone is insufficient: absolute physical differences matter.
    score=float(np.exp(-4*norm)*(.5+.5*max(0.,corr))) if denom>1e-12 else float(same)
    interpolated=(a.shape!=b.shape or m.axes_x!=t.axes_x or m.axes_y!=t.axes_y)
    return {'score':score,'rmse':rmse,'normalized_rmse':norm,
            'maximum_difference':float(np.max(np.abs(difference))),
            'correlation':corr,'interpolated':interpolated,
            'distinctive':bool(np.ptp(aligned)>1e-9 and np.unique(aligned).size>=8)},aligned,b


def match_map_catalogs(source,target,source_maps,target_maps,*,tolerance=.15,
                       uniqueness_margin=.05,cancelled=None,max_comparisons=20000):
    """Name matches first, then shape/units/function candidates. Never writes.

    Constant surfaces and ambiguous/colliding matches cannot silently establish
    a shape pairing. Budget exhaustion marks ALL results non-unique, fail closed.
    """
    if not 0<=tolerance<=1 or not 0<uniqueness_margin<1 or not 1<=max_comparisons<=100000:
        raise ValueError('Ungültige Abgleichparameter')
    sp,tp=identify_profile(source),identify_profile(target)
    if sp.identified and tp.identified and sp.family!=tp.family:
        raise ValueError('Unterschiedliche erkannte ECU-Familien')
    source=source if not source.dirty_bytes else BinaryImage(source.original)
    target=target if not target.dirty_bytes else BinaryImage(target.original)
    names={};groups={}
    for j,t in enumerate(target_maps):
        names.setdefault((t.name.casefold(),t.kind,t.unit),[]).append(j)
        groups.setdefault((t.kind,t.unit),[]).append(j)
    hits=[];excluded={};unmatched=[];compared=0;truncated=False;was_cancelled=False
    for i,m in enumerate(source_maps):
        if cancelled and cancelled():was_cancelled=True;break
        named=names.get((m.name.casefold(),m.kind,m.unit),[])
        indices=named or groups.get((m.kind,m.unit),[])
        if not indices:unmatched.append({'source_index':i,'name':m.name,'reason':'Keine Kandidaten mit gleicher Funktion und Einheit'})
        scored=[]
        for j in indices:
            if cancelled and cancelled():was_cancelled=True;break
            if compared>=max_comparisons:truncated=True;break
            compared+=1;t=target_maps[j]
            try:metrics,_,_=compare_surfaces(source,target,m,t)
            except (ValueError,TypeError,OverflowError,ZeroDivisionError) as exc:
                message=str(exc);excluded[message]=excluded.get(message,0)+1;continue
            if not named and (not metrics['distinctive'] or metrics['normalized_rmse']>tolerance or metrics['correlation']<.9):continue
            scored.append((metrics['score'],j,metrics))
        scored.sort(key=lambda item:(-item[0],item[1]))
        for rank,(score,j,metrics) in enumerate(scored[:5]):
            t=target_maps[j]
            unique=rank==0 and (len(scored)==1 or score-scored[1][0]>=uniqueness_margin)
            note=('Gleicher Quellname/Funktion; ' if named else 'Ähnliche physikalische Oberfläche; ')
            note+=('abweichendes Achsenraster interpoliert. ' if metrics['interpolated'] else 'gleiches Achsenraster. ')
            if named and metrics['normalized_rmse']>tolerance:note+='Werte unterscheiden sich deutlich: separat prüfen. '
            note+='Paarung ungeprüft; Rangwert ist keine Wahrscheinlichkeit.'
            hits.append(MapMatch(i,j,m.name,t.name,m.offset,t.offset,score,metrics['rmse'],metrics['normalized_rmse'],
                metrics['maximum_difference'],metrics['correlation'],metrics['interpolated'],bool(named),unique,
                m.verified,t.verified,note))
        if truncated or was_cancelled:break
    # Two source symbols claiming one target are ambiguous even if each search
    # individually returned a high score. Preserve the conflict for inspection.
    targets={}
    for h in hits:
        if h.unique:targets.setdefault(h.target_index,[]).append(h.source_index)
    hits=[replace(h,unique=False,evidence=h.evidence+' Ziel mehrfach beansprucht.')
          if len(targets.get(h.target_index,[]))>1 else h for h in hits]
    if truncated or was_cancelled:
        hits=[replace(h,unique=False,evidence=h.evidence+' Suche unvollständig.') for h in hits]
    return {'source_sha256':source.digest,'target_sha256':target.digest,'compared_pairs':compared,
            'truncated':truncated,'cancelled':was_cancelled,'excluded':excluded,'unmatched_sources':unmatched,
            'matches':[asdict(h) for h in hits],'independently_verified_pairings':0}


def locate_reference_surfaces(source,target,maps,*,tolerance=.08,search_range=None,
                               max_references=32,cancelled=None):
    """Find shifted, slightly changed raw tables, including odd word addresses.

    Layout is a reference hypothesis; axes/scaling are deliberately NOT copied.
    Competing locations and exhausted budgets abstain. No neural semantic labels.
    """
    from .model import MapDefinition
    if not 0<=tolerance<=.5 or not 1<=max_references<=128:raise ValueError('Ungültige Suchparameter')
    sp,tp=identify_profile(source),identify_profile(target)
    if sp.identified and tp.identified and sp.family!=tp.family:raise ValueError('Unterschiedliche ECU-Familien')
    start,end=search_range or (tp.cal_start or 0,tp.cal_end or target.size)
    if not 0<=start<end<=target.size:raise ValueError('Ungültiger Suchbereich')
    if end-start>8*1024*1024:raise ValueError('Suchbereich auf höchstens 8 MiB eingrenzen')
    blob=target.original[start:end];results=[];declined={};cancelled_run=False
    baseline_source=BinaryImage(source.original)
    for index,m in enumerate(maps[:max_references]):
        if cancelled and cancelled():cancelled_run=True;break
        try:
            m.validate(source.size)
            if (m.storage_order!='row-major' or m.major_stride_bits not in (0,m.width*8) or
                    m.minor_stride_bits or not 16<=m.rows*m.cols<=4096):raise ValueError('Layout nicht unterstützt')
            a=baseline_source.matrix(m).astype(float).ravel()
            span=float(np.ptp(a))
            if not np.isfinite(a).all() or span<1 or len(np.unique(a))<8:raise ValueError('Referenz nicht unterscheidbar')
            count=len(a);anchors=np.unique(np.linspace(0,count-1,min(16,count),dtype=int))
            kind='f' if m.dtype=='f32' else 'u' if m.dtype[0]=='u' else 'i'
            dtype=np.dtype(('>' if m.endian=='big' else '<')+kind+str(m.width))
            scored=[];checked=0;exhausted=False
            for phase in range(m.width):
                data=blob[phase:];data=data[:len(data)//m.width*m.width]
                values=np.frombuffer(data,dtype=dtype)
                n=len(values)-count+1
                for begin in range(0,max(0,n),8192):
                    if cancelled and cancelled():cancelled_run=True;break
                    pos=np.arange(begin,min(n,begin+8192),dtype=np.intp)
                    probes=values[pos[:,None]+anchors].astype(float)
                    err=np.sqrt(np.mean(((probes-a[anchors])/span)**2,axis=1))
                    promising=pos[np.isfinite(err)&(err<=tolerance*1.5+1e-12)]
                    checked+=len(promising)
                    if checked>4096:exhausted=True;break
                    for p in promising:
                        b=values[p:p+count].astype(float)
                        if not np.isfinite(b).all():continue
                        norm=float(np.sqrt(np.mean(((b-a)/span)**2)))
                        if norm>tolerance+1e-12:continue
                        x=a-a.mean();y=b-b.mean();den=float(np.linalg.norm(x)*np.linalg.norm(y))
                        corr=float(np.dot(x,y)/den) if den>1e-12 else 0.
                        if corr<.92:continue
                        scored.append((float(np.exp(-8*norm)*min(1.,corr)),start+phase+int(p)*m.width,norm))
                if exhausted or cancelled_run:break
            scored.sort(key=lambda item:(-item[0],item[1]))
            if scored:
                best,offset,norm=scored[0]
                alternatives=[(s,p,e) for s,p,e in scored[1:] if abs(p-offset)>=m.length//2 or s>1-1e-12]
                second=max((s for s,p,e in alternatives),default=0.)
                unique=not exhausted and not cancelled_run and best-second>=.05
                note=(f'Referenz {m.name}: Formwert {best:.4f}, normierter Fehler {norm:.4f}, '
                      f'Alternative {second:.4f}; nur innerhalb 0x{start:X}..0x{end:X}. '
                      'Zielachsen, Skalierung und Funktion ungeprüft; keine Werteübernahme.')
                proposed=MapDefinition('Referenzstruktur: '+m.name,offset,m.rows,m.cols,m.dtype,m.endian,
                    source='transfer-proposed',verified=False,label_origin='Mathematische Referenzsuche · ungeprüft',
                    label_evidence=note,notes=note)
                results.append({'source_index':index,'target_offset':offset,'score':best,'second_score':second,
                    'normalized_rmse':norm,'unique':unique,'budget_exhausted':exhausted,
                    'alternatives':[{'offset':p,'score':s,'normalized_rmse':e} for s,p,e in alternatives[:5]],
                    'reference_verified':m.verified,'proposed':proposed.asdict()})
        except (ValueError,TypeError,OverflowError) as exc:
            reason=str(exc);declined[reason]=declined.get(reason,0)+1
        if cancelled_run:break
    for i,entry in enumerate(results):
        for other in results[i+1:]:
            a=entry['proposed'];b=other['proposed']
            extent_a=maps[entry['source_index']].length
            extent_b=maps[other['source_index']].length
            if a['offset']<b['offset']+extent_b and b['offset']<a['offset']+extent_a:
                entry['unique']=False;other['unique']=False
                entry['conflict']=other['conflict']='overlapping-reference-claims'
    if cancelled_run:
        for entry in results:entry['unique']=False
    return {'source_sha256':source.digest,'target_sha256':target.digest,'search_range':[start,end],
        'references_considered':min(len(maps),max_references),'references_omitted':max(0,len(maps)-max_references),
        'cancelled':cancelled_run,'declined':declined,'hits':results,'independently_verified_pairings':0}
