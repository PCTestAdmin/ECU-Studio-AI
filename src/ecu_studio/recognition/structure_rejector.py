"""Learned, *synthetic-domain* structure discrimination (not map identification).

All targets for this binary model are generated from documented geometric
processes. The score is NOT a probability that an ECU location is a real map.
Never supplies map names, units, axes, or verification status.
No scikit-learn dependency at inference or training time.
"""
from __future__ import annotations
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
import json
import numpy as np

FORMAT = 1
FEATURES = 20
MODEL_FILE = 'structure_rejector_v110.json'


def structural_features(values) -> np.ndarray:
    a = np.asarray(values, dtype=np.float64)
    if a.ndim != 2 or min(a.shape) < 3 or a.size > 4096 or not np.isfinite(a).all():
        raise ValueError('Ungültige 2D-Oberfläche')
    p05, p95 = np.percentile(a, [5, 95])
    scale = max(1., float(p95-p05))
    z = np.clip((a-np.median(a))/scale, -6., 6.)
    dx,dy = np.diff(z,axis=1), np.diff(z,axis=0)
    ax,ay = np.abs(dx),np.abs(dy)
    def pct(x,p):return float(np.percentile(x,p)) if x.size else 0.
    ddx=np.diff(z,n=2,axis=1) if z.shape[1]>3 else np.array([0.])
    ddy=np.diff(z,n=2,axis=0) if z.shape[0]>3 else np.array([0.])
    flat=z.ravel()
    return np.array([
        float(np.log1p(a.shape[0])),float(np.log1p(a.shape[1])),
        float(np.std(z)),pct(ax,50),pct(ay,50),pct(ax,90),pct(ay,90),
        pct(ax,99),pct(ay,99),pct(np.abs(ddx),75),pct(np.abs(ddy),75),
        float(np.std(z.mean(axis=0))),float(np.std(z.mean(axis=1))),
        float(np.mean(ax < .004)),float(np.mean(ay < .004)),
        float(np.mean(dx>0)),float(np.mean(dy>0)),
        float(np.mean((np.abs(flat)<.03))),
        float(np.unique(a).size/a.size),
        float(max(a.max()-a.min(),0.)/max(scale,1.)),
    ],dtype=np.float64)


def sigmoid(x):
    return float(1./(1.+np.exp(-np.clip(x,-35.,35.))))


@dataclass(frozen=True)
class StructureRejector:
    mean: list[float]
    scale: list[float]
    weights: list[float]
    bias: float
    threshold: float
    metrics: dict
    training_hash: str
    format: int = FORMAT
    trees: list[dict] | None = None

    def assess(self, surface) -> dict:
        f=structural_features(surface)
        if self.trees:
            estimate=0.
            for t in self.trees:
                node=0
                # Rigidly bounded traversal; no eval/pickle/external code.
                for _ in range(32):
                    feat=t['feature'][node]
                    if feat<0:
                        estimate+=t['prob'][node]
                        break
                    node=t['left'][node] if f[feat]<=t['threshold'][node] else t['right'][node]
                else:
                    raise ValueError('Beschädigter Baum im Strukturmodell')
            score=estimate/len(self.trees)
        else:
            z=np.clip((f-np.asarray(self.mean))/np.asarray(self.scale),-6,6)
            score=sigmoid(float(z@np.asarray(self.weights))+self.bias)
        # Never claim real-world recall, map presence, or semantic confidence.
        return {'score':round(score,4),'plausible_synthetic_geometry':score>=self.threshold,
                'status':'synthetic-structure-only',
                'note':'Trainiert auf künstlichen Oberflächen; KEIN Nachweis für ein echtes Kennfeld oder dessen Funktion.'}

    @classmethod
    def load(cls,path:str|Path) -> 'StructureRejector':
        p=Path(path)
        if p.stat().st_size>1024*1024:raise ValueError('Modell zu groß')
        d=json.loads(p.read_text(encoding='utf8'))
        obj=cls(**d)
        if obj.format!=FORMAT or not 0<obj.threshold<1 or len(obj.training_hash)!=64:
            raise ValueError('Ungültiges Modellformat')
        for v in (obj.mean,obj.scale,obj.weights):
            if len(v)!=FEATURES or not np.isfinite(v).all():
                raise ValueError('Ungültige Feature-Dimension oder Gewichte')
        if any(x<=0 for x in obj.scale) or not np.isfinite(obj.bias):
            raise ValueError('Ungültige Skalierung/Bias')
        if obj.trees is not None:
            if not 1<=len(obj.trees)<=80:raise ValueError('Ungültige Anzahl an Bäumen')
            for t in obj.trees:
                cols=('feature','threshold','left','right','prob')
                if any(c not in t for c in cols):raise ValueError('Ungültige Baumdaten')
                count=len(t['feature'])
                if not 1<=count<=1023 or any(len(t[c])!=count for c in cols):
                    raise ValueError('Falsche Baumdimensionen')
                for i,feat in enumerate(t['feature']):
                    if not isinstance(feat,int) or feat>=FEATURES or feat<-2:
                        raise ValueError('Ungültiger Baum-Split')
                    if feat>=0 and (t['left'][i]<=i or t['right'][i]<=i
                                    or t['left'][i]>=count or t['right'][i]>=count):
                        raise ValueError('Zyklische oder ungültige Baumkanten')
                if not np.isfinite(t['threshold']).all() or not np.isfinite(t['prob']).all():
                    raise ValueError('Ungültige Baumwerte')
                if any(not 0<=p<=1 for p in t['prob']):raise ValueError('Ungültige Blattwahrscheinlichkeiten')
        return obj

    def save(self,path:str|Path):
        from dataclasses import asdict
        Path(path).write_text(json.dumps(asdict(self),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')


def installed_rejector() -> StructureRejector|None:
    """Shipped immutable model. The app works when the optional model is absent."""
    try:
        p=files('ecu_studio.recognition').joinpath('data',MODEL_FILE)
        return StructureRejector.load(p)
    except (OSError,ValueError,TypeError,KeyError):
        return None
