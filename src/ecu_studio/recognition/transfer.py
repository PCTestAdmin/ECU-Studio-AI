"""Conservative cross-firmware recognition using opt-in VERIFIED source maps.

Searches contiguous same-shape matrices inside a known ECU family, retaining
independent alternatives. Never treats shape similarity as proof of semantics.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.profiles import identify_profile
from .catalog import DefinitionCatalog, Reference


@dataclass
class TransferHit:
    reference_id: int
    source_name: str
    source_firmware: str
    proposed: MapDefinition
    score: float  # normalized similarity, not probability
    runner_up: float
    evidence: str
    uniquely_located: bool


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    x = a - np.mean(a)
    y = b - np.mean(b)
    d = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    return float(np.dot(x, y) / d) if d > 1e-10 else 0.0


def _layout_ok(m: MapDefinition) -> bool:
    return (m.storage_order == 'row-major' and
            m.major_stride_bits in (0,m.width*8) and m.minor_stride_bits == 0 and
            m.rows >= 3 and m.cols >= 3 and 9 <= m.rows*m.cols <= 1024 and
            m.dtype in ('u8','s8','u16','s16','u32','s32'))


def _dt(m: MapDefinition):
    t = {'u':'u', 's':'i'}[m.dtype[0]] + str(m.width)
    return np.dtype(('>' if m.endian=='big' else '<') + t)


def _similarity(a: np.ndarray, b: np.ndarray) -> float:
    correlation = _corr(a.ravel(), b.ravel())
    # Derivative similarity makes featureless ramps less likely to score well.
    gradients = []
    for axis in (0,1):
        if a.shape[axis] > 2:
            gradients.append(_corr(np.diff(a,axis=axis).ravel(),
                                   np.diff(b,axis=axis).ravel()))
    if not gradients:
        return 0.0
    return max(0., min(1., .62*correlation + .38*np.mean(gradients)))


def match_verified(image: BinaryImage, catalog: DefinitionCatalog, *,
                   min_score: float = 0.92, uniqueness_margin: float = 0.055,
                   max_references: int = 24, search_range: tuple[int,int] | None = None
                   ) -> list[TransferHit]:
    """Search verified reference surfaces. Returns *unverified proposals* only.

    Requires ECU-family evidence. Does not transfer unsupported strided layouts,
    infer ECU family, or silently label unknown binaries.
    """
    profile = identify_profile(image)
    if not profile.identified:
        return []
    refs = catalog.verified_references(family=profile.family,except_firmware=image.digest)
    if search_range is None:
        if profile.cal_start is None or profile.cal_end is None:
            return []
        start, end = profile.cal_start, profile.cal_end
    else:
        start,end = search_range
    if start < 0 or end > image.size or start >= end:
        raise ValueError('Ungültiger Speicherbereich')
    hits: list[TransferHit] = []
    for ref in refs[:max_references]:
        m = ref.map_data
        if not _layout_ok(m):
            continue
        count = m.rows*m.cols
        a = np.array(ref.raw, dtype=np.float64)
        if float(np.std(a)) < 2.0 or np.unique(a).size < 8:
            continue
        size = m.width
        length = end-start
        length -= length % size
        if length < count*size:
            continue
        raw=image.read(start,length)
        vals=np.frombuffer(raw,dtype=_dt(m)).astype(np.float64,copy=False)
        n=len(vals)-count+1
        # Pre-screen anchors across the surface. For 1024 cells scan remains
        # inexpensive: only ~12 anchor values per byte-aligned candidate.
        anchor=np.unique(np.linspace(0,count-1,min(16,count),dtype=np.int32))
        baseline=a.ravel()[anchor]
        baseline=baseline-np.mean(baseline)
        norm=float(np.linalg.norm(baseline))
        if norm<1e-9:continue
        starts=np.arange(n,dtype=np.intp)
        probes=vals[starts[:,None]+anchor[None,:]]
        centered=probes-probes.mean(axis=1,keepdims=True)
        denom=np.linalg.norm(centered,axis=1)*norm
        corr=np.divide(centered@baseline,denom,out=np.zeros(n,dtype=float),where=denom>1e-9)
        # Guard against 100s of nearly identical windows dominating budget.
        promising=np.flatnonzero(corr >= .83)
        if len(promising)>120:
            sample=np.argpartition(corr[promising],-120)[-120:]
            promising=promising[sample]
        scored=[]
        for p in promising:
            matrix=vals[int(p):int(p)+count].reshape(m.rows,m.cols)
            score=_similarity(a,matrix)
            if score >= min_score - .20:
                scored.append((score,int(p)))
        if not scored:
            continue
        scored.sort(reverse=True)
        best_score,best_pos=scored[0]
        # Search for a spatially distinct competitor; adjacent shifted windows
        # are not independent matches of the same shape.
        alternatives=[s for s,p in scored[1:] if abs(p-best_pos)>=count//2]
        second=max(alternatives,default=0.0)
        unique = best_score>=min_score and (best_score-second)>=uniqueness_margin
        if best_score < min_score:
            continue
        offset=start+best_pos*size
        proposed=MapDefinition(**m.asdict())
        proposed.offset=offset
        proposed.candidate_region_start=None
        proposed.axis_x_offset=proposed.axis_y_offset=None   # similar values do not locate axes
        proposed.source='transfer-proposed'
        proposed.verified=False
        proposed.confidence=round(best_score,4)
        proposed.label_origin='Ähnliche Struktur aus anderer Firmware – ungeprüft'
        proposed.label_evidence=(f'Verifizierte Referenz #{ref.id} aus {ref.software or "unbekanntem Stand"}; '
           f'Similarität {best_score:.3f}, alternative Stelle {second:.3f}. '
           'Name, Achsen und Skalierung NICHT auf Zielfirmware validiert.')
        proposed.notes=proposed.label_evidence
        hits.append(TransferHit(ref.id,ref.name,ref.firmware_sha,proposed,
                               float(best_score),float(second),proposed.label_evidence,unique))
    # Competing references suggesting different functions at same address are
    # never promoted as unambiguous.
    for i,hit in enumerate(hits):
        for other in hits[i+1:]:
            if abs(hit.proposed.offset-other.proposed.offset) < min(hit.proposed.length,other.proposed.length)//2 \
                    and hit.proposed.kind!=other.proposed.kind:
                hit.uniquely_located=False
                other.uniquely_located=False
    return sorted(hits,key=lambda x:(not x.uniquely_located,-x.score))
