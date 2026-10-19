"""Conservative self-supervised ECU map-shape model.

Real raw surfaces from source-attributed, but UNVERIFIED, metadata train a PCA
embedding. Predictions are reference SIMILARITY ONLY, never a map function,
probability, editing permission, or evidence of correct calibration.

No ECU bytes or firmware images are saved in the model.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import hashlib
import json
import numpy as np

from .ml import features
from ecu_studio.core.precision import surface_evidence
from .catalog import DefinitionCatalog
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.profiles import identify_profile

FORMAT=1
FEATURES=80
MAX_BYTES=2_500_000

@dataclass
class ShapeModel:
    format: int
    family: str
    software: str
    firmware_sha: str
    training_data_sha256: str
    count: int
    location_count: int
    feature_mean: list[float]
    feature_scale: list[float]
    components: list[list[float]]
    reference_codes: list[list[float]]
    reference_names: list[str]
    reference_offsets: list[int]
    heldout_nearest_distance_p90: float
    novelty_threshold: float
    report: dict

    def save(self, path: str | Path) -> None:
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
        payload=json.dumps(asdict(self),ensure_ascii=False,allow_nan=False,indent=2)
        if len(payload)>MAX_BYTES:raise ValueError('Strukturmodell zu groß')
        tmp=p.with_suffix(p.suffix+'.tmp')
        tmp.write_text(payload,encoding='utf-8');tmp.replace(p)

    @classmethod
    def load(cls,path: str | Path) -> 'ShapeModel':
        p=Path(path)
        if p.stat().st_size>MAX_BYTES:raise ValueError('Strukturmodell zu groß')
        obj=cls(**json.loads(p.read_text(encoding='utf-8')))
        if obj.format!=FORMAT or not (8<=obj.count<=100_000) or len(obj.reference_names)!=obj.count:
            raise ValueError('Inkompatibles Strukturmodell')
        if len(obj.feature_mean)!=FEATURES or len(obj.feature_scale)!=FEATURES:
            raise ValueError('Falsche Merkmalsdimension')
        comp=np.asarray(obj.components,dtype=np.float64)
        codes=np.asarray(obj.reference_codes,dtype=np.float64)
        if comp.ndim!=2 or comp.shape[1]!=FEATURES or comp.shape[0]>24 or codes.shape!=(obj.count,comp.shape[0]):
            raise ValueError('Falsche Projektionsdimension')
        for arr in (comp,codes,np.asarray(obj.feature_mean),np.asarray(obj.feature_scale)):
            if not np.all(np.isfinite(arr)):raise ValueError('Nichtendliche Modelldaten')
        if np.min(obj.feature_scale)<=0 or len(obj.reference_offsets)!=obj.count:
            raise ValueError('Ungültige Normierung')
        return obj

    def similar(self, surface, *, family: str, software: str,
                max_matches: int=3) -> dict:
        # Fail closed for ECU families and software versions not trained on.
        if family!=self.family or software!=self.software:
            return {'status':'abstain','reason':'Andere ECU-Familie oder Softwareversion; keine validierte Übertragbarkeit.', 'candidates':[]}
        a=np.asarray(surface,dtype=np.float64)
        evidence=surface_evidence(a)
        # A perfect affine plane occurs in code, counters and synthetic ramps,
        # as well as in some *genuine* calibrations. Abstain rather than
        # assigning an unreviewed source name on generic shape alone.
        if not evidence['valid']:
            return {'status':'abstain','reason':'Keine ausreichend belastbare 2D-Struktur.',
                    'candidates':[], 'predicted_map_function':None,'verified':False}
        span=max(float(np.percentile(a,95)-np.percentile(a,5)),1.)
        bends=[np.percentile(np.abs(np.diff(a,n=2,axis=axis)),75)/span
               for axis in (0,1) if a.shape[axis]>=4]
        if not bends or max(bends)<.002:
            return {'status':'abstain','reason':'Generische lineare Ebene: Referenzidentifikation nicht eindeutig.',
                    'candidates':[], 'predicted_map_function':None,'verified':False}
        x=features(surface)
        avg=np.asarray(self.feature_mean);scale=np.asarray(self.feature_scale)
        y=np.clip((x-avg)/scale,-6.,6.)@np.asarray(self.components).T
        codes=np.asarray(self.reference_codes)
        distances=np.linalg.norm(codes-y[None,:],axis=1)
        sorted_idx=np.argsort(distances,kind='stable')[:max(1,min(max_matches,10))]
        ranked=[]
        for i in sorted_idx:
            i=int(i)
            ranked.append({'source_name':self.reference_names[i],
                           'source_offset':int(self.reference_offsets[i]),
                           'distance':round(float(distances[i]),5),
                           'evidence':'Formähnlichkeit zu unbestätigter XDF-Quelle, KEINE Typ-Identifikation'})
        low=float(distances[sorted_idx[0]])
        return {'status':'shape-similar' if low<=self.novelty_threshold else 'abstain',
                'distance':round(low,5),
                'threshold':round(self.novelty_threshold,5),
                'reason':('Ähnlicher Verlauf zu Quellenmetadaten (KEIN Funktionsnachweis).' if low<=self.novelty_threshold
                          else 'Außerhalb des trainierten Strukturraums oder unbekanntes Kennfeld.'),
                'candidates':ranked,
                'predicted_map_function':None,
                'verified':False}


def _training_rows(db: DefinitionCatalog,image: BinaryImage) -> tuple[np.ndarray,list[str],list[int],dict]:
    records=db.records(firmware_sha=image.digest)
    selected=[]; names=[]; offsets=[]; skipped={}
    for r in records:
        # Only reference-origin definitions; model never calls them verified.
        if not (r['origin'].startswith('MS4X ') or r['origin'].startswith('Öffentliche XDF:')):
            continue
        try:
            m=MapDefinition(**json.loads(r['map_json']))
            m.validate(image.size)
            if m.rows<3 or m.cols<3 or m.rows*m.cols>4096:
                raise ValueError('Kleine/übergroße Form')
            a=np.array([[image.raw_value(m,y,x) for x in range(m.cols)] for y in range(m.rows)],dtype=np.float64)
            if np.unique(a).size<6 or np.std(a)<2:
                raise ValueError('Zu wenig Struktur')
            f=features(a)
            selected.append(f);names.append(m.name);offsets.append(m.offset)
        except (ValueError,TypeError,KeyError,OverflowError,IndexError) as e:
            skipped[str(e)]=skipped.get(str(e),0)+1
    if len(selected)<12:
        raise ValueError('Zu wenige strukturierte Kennfeldhinweise für ein echtes Strukturtraining')
    return np.stack(selected),names,offsets,{'sources_considered':len(records),'excluded':skipped}


def train_shape_model(db:DefinitionCatalog,image:BinaryImage,*,dimensions:int=12)->ShapeModel:
    if image.dirty_bytes: raise ValueError('Nur unveränderte Originaldatei für reproduzierbares Training')
    profile=identify_profile(image)
    if not profile.identified or not (profile.software_version or profile.calibration_id):
        raise ValueError('Unbekannte ECU/Software: kein modellübergreifender Trainingsschluss erlaubt')
    x,names,offsets,info=_training_rows(db,image)
    avg=x.mean(axis=0)
    # Robust-ish scales, bound invalid and extreme feature magnitudes.
    scale=np.std(x,axis=0)
    scale[scale<.025]=1.0
    normalized=np.clip((x-avg)/scale,-6,6)
    # Native SVD is a learned representation, not a hardcoded table-lookup.
    _,singular,v=np.linalg.svd(normalized,full_matrices=False)
    k=min(dimensions,24,len(names)-1)
    basis=v[:k]
    codes=normalized@basis.T
    distance=np.linalg.norm(codes[:,None,:]-codes[None,:,:],axis=2)
    np.fill_diagonal(distance,np.inf)
    # Do not use in-sample same-vector fit as quality measurement.
    loo=np.min(distance,axis=1)
    p90=float(np.quantile(loo,.90))
    threshold=max(0.1,float(np.quantile(loo,.90)*1.05))
    source_hash=hashlib.sha256(json.dumps({'names':names,'offsets':offsets,'binsha':image.digest},sort_keys=True).encode()).hexdigest()
    family=profile.family;sw=profile.software_version or profile.calibration_id or ''
    return ShapeModel(FORMAT,family,sw,image.digest,source_hash,len(names),
        len(set(offsets)),avg.tolist(),scale.tolist(),basis.tolist(),codes.tolist(),names,offsets,
        round(p90,6),round(threshold,6),
        {'method':'PCA-SVD, nicht überwachtes Strukturtraining',
         'features':FEATURES,'components':k,'actual_source':'Benannte XDF-Vorschaumetadaten + echte binäre Rohwerte',
         'source_verified':False,'correct_map_type_claims':0,
         'heldout_firmware_evaluation':False,
         'loo_nearest_distance_p90':round(p90,6),
         'firmware':sw,'family':family,'training_rows':len(names),
         'exclusions':info['excluded'],
         'warning':'Ein einzelner Firmwarestand erlaubt KEINE sichere Funktionsklassifizierung oder MD1/MG1-Generalisation.'})
