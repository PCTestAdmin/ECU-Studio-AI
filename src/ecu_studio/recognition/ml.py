"""Small trainable, audit-friendly ML classifier; JSON model, no pickle/eval.

Trains ONLY from explicitly verified map records. Firmware-held-out validation
prevents random cells of one firmware appearing in both train and test.
This model cannot learn semantics without diverse independent verified data.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from .catalog import DefinitionCatalog

FEATURE_VERSION=1


def _resize(a: np.ndarray, side: int = 8) -> np.ndarray:
    # Linear interpolation preserves coarse surface without needing SciPy.
    ox=np.linspace(0,1,a.shape[1]); nx=np.linspace(0,1,side)
    oy=np.linspace(0,1,a.shape[0]); ny=np.linspace(0,1,side)
    rows=np.vstack([np.interp(nx,ox,row) for row in a])
    return np.column_stack([np.interp(ny,oy,rows[:,i]) for i in range(side)])


def features(surface: list[list[int]] | np.ndarray) -> np.ndarray:
    data=np.asarray(surface,dtype=np.float64)
    if data.ndim!=2 or min(data.shape)<2 or data.size>4096 or not np.all(np.isfinite(data)):
        raise ValueError('Ungültige Kennfeldoberfläche')
    lo,hi=np.percentile(data,[5,95]); span=float(hi-lo)
    if span < 1e-8:
        span=1.0
    norm=np.clip((data-lo)/span,-2,3)
    sampled=_resize(norm).ravel()
    dx=np.diff(norm,axis=1);dy=np.diff(norm,axis=0)
    stats=np.array([
        np.log1p(data.shape[0]),np.log1p(data.shape[1]),
        np.mean(norm),np.std(norm),np.percentile(norm,25),np.percentile(norm,75),
        np.mean(np.abs(dx)),np.mean(np.abs(dy)),
        np.mean(dx>0),np.mean(dy>0),np.mean(dx<0),np.mean(dy<0),
        np.mean(np.abs(dx)>0.4),np.mean(np.abs(dy)>0.4),
        np.mean((norm<=0.05)),np.mean((norm>=0.95)),
    ])
    return np.concatenate([sampled,stats])


def _softmax(logits: np.ndarray) -> np.ndarray:
    z=logits-np.max(logits,axis=1,keepdims=True)
    exp=np.exp(np.clip(z,-50,50))
    return exp/np.sum(exp,axis=1,keepdims=True)


@dataclass
class Model:
    labels: list[str]
    mean: list[float]
    scale: list[float]
    weights: list[list[float]]
    bias: list[float]
    metrics: dict
    training_hash: str
    family: str = ''

    def predict(self, surface, *, min_score: float = 0.85,
                min_margin: float = 0.20, family: str | None = None) -> dict:
        # A model fitted to one ECU family must never name maps in another.
        # Legacy unscoped models cannot be treated as approved classifiers.
        if not self.family or family!=self.family:
            return {'label':'Unbekannt','suggested_label':None,'model_score':0.,
                    'runner_up_score':0.,'status':'abstain',
                    'note':'Modellscore nicht freigegeben: Keine gesicherte Familienbindung oder ECU-Familie passt nicht.'}
        raw=np.asarray(surface,dtype=np.float64)
        if raw.ndim!=2 or not np.isfinite(raw).all() or np.unique(raw).size<8 or np.std(raw)<2:
            return {'label':'Unbekannt','suggested_label':None,'model_score':0.,
                    'runner_up_score':0.,'status':'abstain',
                    'note':'Modellscore nicht verfügbar: Zu wenig informative Struktur für eine Funktionsprognose.'}
        x=features(raw)
        mu=np.asarray(self.mean);sd=np.asarray(self.scale)
        z=(x-mu)/sd
        x=np.clip(z,-6,6)
        probs=_softmax((x @ np.asarray(self.weights)+np.asarray(self.bias))[None,:])[0]
        order=np.argsort(probs)[::-1]
        best=int(order[0]);runner=float(probs[order[1]]) if len(order)>1 else 0.
        # Softmax on out-of-distribution surfaces can be arbitrarily confident.
        # Use a conservative normalized feature-distance rejection as well.
        # IMPORTANT: 'x' above is already standardized. A second transform
        # incorrectly lets extremely unusual maps through or rejects valid ones.
        normalised=np.abs(z)
        ood=float(np.percentile(normalised,90))
        valid=(self.metrics.get('release_gate') is not None and
               self.metrics.get('heldout_macro_recall',0)>=0.85 and
               all(v>=0.75 for v in self.metrics.get('precision_per_label',{}).values()) and
               all(v>=0.75 for v in self.metrics.get('recall_per_label',{}).values()) and
               ood<=5. and float(probs[best])>=min_score and
               float(probs[best])-runner>=min_margin)
        return {'label':self.labels[best] if valid else 'Unbekannt',
                'suggested_label':self.labels[best],
                'model_score':round(float(probs[best]),4),
                'runner_up_score':round(runner,4),
                'status':'ml-proposed' if valid else 'abstain',
                'note':'Modellscore ist KEINE kalibrierte Wahrscheinlichkeit; kein bestätigter Kennfeldname.'}

    def save(self,path:str|Path) -> None:
        payload={'format':1,'feature_version':FEATURE_VERSION, **self.__dict__}
        from ecu_studio.core.storage import atomic_write
        atomic_write(path,json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'),backup=True)

    @classmethod
    def load(cls,path:str|Path) -> 'Model':
        p=Path(path)
        if p.stat().st_size>2*1024*1024:raise ValueError('Modelldatei zu groß')
        data=json.loads(p.read_text(encoding='utf8'))
        if data.pop('format',None)!=1 or data.pop('feature_version',None)!=FEATURE_VERSION:
            raise ValueError('Nicht unterstütztes ML-Format')
        model=cls(**data)
        if len(model.labels)<2 or len(model.labels)>128 or len(model.mean)!=80 or len(model.scale)!=80:
            raise ValueError('Unplausible ML-Dimensionen')
        if np.asarray(model.weights).shape!=(80,len(model.labels)) or len(model.bias)!=len(model.labels):
            raise ValueError('Ungültige ML-Gewichte')
        if (not np.all(np.isfinite(model.weights)) or not np.all(np.isfinite(model.bias))
                or not np.all(np.isfinite(model.mean)) or not np.all(np.isfinite(model.scale))
                or any(v<=0 for v in model.scale)):
            raise ValueError('Nichtendliche ML-Gewichte')
        return model


def _fit(x:np.ndarray,y:np.ndarray,classes:int,iterations:int=500):
    mu=x.mean(axis=0);sd=x.std(axis=0);sd[sd<1e-6]=1
    x=np.clip((x-mu)/sd,-6,6)
    weights=np.zeros((x.shape[1],classes));bias=np.zeros(classes)
    target=np.eye(classes)[y]
    freq=np.bincount(y,minlength=classes)
    class_weight=np.sqrt(freq.sum()/np.maximum(freq,1)/classes)
    per_sample=class_weight[y][:,None]
    # Deterministic cross-entropy + L2; feature clipping bounds gradients.
    for i in range(iterations):
        pred=_softmax(x@weights+bias)
        delta=(pred-target)*per_sample
        rate=.15/(1+.002*i)
        weights-=rate*(x.T@delta/len(y)+.018*weights)
        bias-=rate*delta.mean(axis=0)
    return mu,sd,weights,bias


def train(catalog:DefinitionCatalog, *, min_per_label:int=6,
          min_firmwares_per_label:int=3) -> Model:
    # Only verified data. Unknown and single-firmware labels cannot train.
    records=catalog.records()
    examples=[]
    for r in records:
        if not r['verified'] or not r['sample_json'] or r['kind']=='Unbekannt':continue
        try:
            x=features(json.loads(r['sample_json']))
        except (TypeError,ValueError):continue
        examples.append((r['kind'],r['firmware_sha'],x))
    labels=sorted(set(item[0] for item in examples))
    families={r['family'] for r in records if r['verified'] and r['sample_json']}
    if len(labels)<2:
        raise ValueError('Mindestens zwei fachlich verifizierte Kennfeldtypen erforderlich')
    if len(families)!=1:
        raise ValueError('Modell darf nur Kennfelder einer einzigen ECU-Familie verwenden')
    family=next(iter(families))
    for label in labels:
        group=[e for e in examples if e[0]==label]
        if len(group)<min_per_label or len(set(e[1] for e in group))<min_firmwares_per_label:
            raise ValueError(f'{label}: zu wenige bestätigte Beispiele oder verschiedene Firmwarestände. '
                             'Keine Pseudo-Trainingsdaten erzeugen.')
    # Avoid optimistic firmware-holdout results when the exact same confirmed
    # raw surface has simply been copied across distinct BIN files.
    fingerprints={}
    for r in records:
        if r['verified'] and r['sample_json'] and r['kind'] in labels:
            try:
                raw=json.loads(r['sample_json'])
                signature=hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest()
            except (TypeError,ValueError):continue
            fingerprints.setdefault(signature,set()).add(r['firmware_sha'])
    leakage=sum(len(group)>1 for group in fingerprints.values())
    if leakage:
        raise ValueError(f'{leakage} identische Kennfeldoberflächen über mehrere Firmwarestände; '
                         'unabhängiger Firmware-Holdout wäre datenleckbehaftet')
    # Hold one independent firmware group per label out; if groups overlap,
    # the *entire* firmware is excluded from training across ALL classes.
    heldout_groups=set()
    for label in labels:
        groups=sorted(set(e[1] for e in examples if e[0]==label))
        heldout_groups.add(groups[-1])
    trainset=[e for e in examples if e[1] not in heldout_groups]
    heldout=[e for e in examples if e[1] in heldout_groups]
    if set(e[0] for e in trainset)!=set(labels) or set(e[0] for e in heldout)!=set(labels):
        raise ValueError('Firmware-getrennter Holdout nicht für alle Klassen möglich')
    key={n:i for i,n in enumerate(labels)}
    X=np.stack([e[2] for e in trainset]); Y=np.array([key[e[0]] for e in trainset]);
    Xv=np.stack([e[2] for e in heldout]); Yv=np.array([key[e[0]] for e in heldout]);
    mu,sd,w,b=_fit(X,Y,len(labels))
    preds=np.argmax(_softmax(np.clip((Xv-mu)/sd,-6,6)@w+b),axis=1)
    recalls={label:float(np.mean(preds[Yv==i]==i)) for i,label in enumerate(labels)}
    macro=float(np.mean(list(recalls.values())))
    heldout_counts={label:int(np.sum(Yv==i)) for i,label in enumerate(labels)}
    precision={label:float(np.mean(Yv[preds==i]==i)) if np.sum(preds==i) else 0.0
               for i,label in enumerate(labels)}
    # Stricter than a single lucky holdout: every independent firmware is
    # evaluated once with *all* of its maps excluded from that fold's fit.
    # Predictions over these folds are never made on training samples.
    all_groups=sorted(set(e[1] for e in examples))
    fold_true=[];fold_pred=[];fold_results=[]
    for group_sha in all_groups:
        fold_train=[e for e in examples if e[1]!=group_sha]
        fold_test=[e for e in examples if e[1]==group_sha]
        if set(e[0] for e in fold_train)!=set(labels):
            raise ValueError('Faltung mit unabhängigem Firmwarestand verliert eine Klasse')
        xf=np.stack([e[2] for e in fold_train]);yf=np.array([key[e[0]] for e in fold_train])
        x_test=np.stack([e[2] for e in fold_test]);y_test=np.array([key[e[0]] for e in fold_test])
        fm,fs,fw,fb=_fit(xf,yf,len(labels))
        yp=np.argmax(_softmax(np.clip((x_test-fm)/fs,-6,6)@fw+fb),axis=1)
        fold_true.extend(y_test.tolist());fold_pred.extend(yp.tolist())
        fold_results.append({'firmware_sha':group_sha, 'test_samples':len(y_test),
                             'accuracy':round(float(np.mean(yp==y_test)),4),
                             'classes_tested':sorted(set(labels[i] for i in y_test))})
    cv_true=np.asarray(fold_true,dtype=np.int64)
    cv_pred=np.asarray(fold_pred,dtype=np.int64)
    cv_recall={label:float(np.mean(cv_pred[cv_true==i]==i)) for i,label in enumerate(labels)}
    cv_precision={label:(float(np.mean(cv_true[cv_pred==i]==i)) if (cv_pred==i).any() else 0.)
                  for i,label in enumerate(labels)}
    cv_macro=float(np.mean(list(cv_recall.values())))
    # Refit on all verified data once holdout quality is reported.
    Xa=np.stack([e[2] for e in examples]);Ya=np.array([key[e[0]] for e in examples]);
    mu,sd,w,b=_fit(Xa,Ya,len(labels))
    digest=hashlib.sha256(('\n'.join(sorted(r['firmware_sha']+r['map_json'] for r in records
                                                if r['verified']))).encode()).hexdigest()
    return Model(labels,mu.tolist(),sd.tolist(),w.tolist(),b.tolist(),
                 {'total_verified':len(examples),'firmware_groups':len(set(e[1] for e in examples)),
                  'train_samples':len(trainset),'holdout_samples':len(heldout),
                  'heldout_macro_recall':round(macro,4),'recall_per_label':recalls,
                  'precision_per_label':precision,'heldout_counts_per_label':heldout_counts,
                  'heldout_firmwares':sorted(heldout_groups),
                  'leave_one_firmware_out':{'firmwares':len(all_groups),
                      'samples':len(cv_true),'macro_recall':round(cv_macro,4),
                      'recall_per_label':cv_recall,'precision_per_label':cv_precision,
                      'groups':fold_results},
                  'warning':'Ein Holdout allein ist kein Nachweis für die Erkennung unbekannter ECU-Familien.'},digest,family)
