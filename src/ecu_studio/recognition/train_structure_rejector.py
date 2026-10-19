"""Reproducibly train a conservative *structural* model using generated data.

This trainer does NOT create real verified ECU labels, pseudo-verified records,
or a released ECU/TCU semantics classifier. Synthetic holdouts are reported
honestly as such. No network access or dependency beyond numpy needed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .structure_rejector import StructureRejector, structural_features, sigmoid

SEED=20261016


def surface(rng:np.random.Generator, positive:bool, kind:int) -> np.ndarray:
    h=int(rng.choice([6,8,10,12,16,20]))
    w=int(rng.choice([6,8,10,12,16,20]))
    x=np.linspace(-1,1,w)[None,:]
    y=np.linspace(-1,1,h)[:,None]
    noise=rng.normal(0,1,(h,w))
    p=rng.uniform(-1,1,5)
    if positive:
        # Non-affine, two-dimensional, smoothly varying calibration-like forms.
        if kind==0:
            z=.6*np.tanh((x-p[0])*3)+.5*np.tanh((y-p[1])*2)+.3*x*y
        elif kind==1:
            z=.6*x*x+.75*y*y + .38*x*y+.2*np.sin(3*x+2*y)
        elif kind==2:
            z=.7*np.tanh(3*x)*np.tanh(2*y)+.5*x+.27*y
        elif kind==3:
            z=.7*np.exp(-2*(x-p[0])**2-3*(y-p[1])**2)+.4*x-.3*y
        elif kind==4:
            z=.7*np.sin(1.3*x+.8*y)+.35*x*y + .2*y
        elif kind==5: # training: knee / saturation.
            z=.75*np.maximum(-.5,np.minimum(.5,x+y*.7-p[0]))+.35*x*y+.2*y*y
        else: # holdout: smooth curved cross-fade / bowl.
            z=.3*x*y+.45*np.tanh(2*x-y)+.45*(x+y)**2
        z+=rng.uniform(.001,.028)*noise
    else:
        # Hard negatives: disassembled-word noise, constant axes, affine ramps,
        # counters, repeated segments, one-dimensional values and impulses.
        if kind==0: z=noise
        elif kind==1: z=.4*x+.6*y+np.zeros((h,w))
        elif kind==2: z=np.tile(np.linspace(0,1,w),(h,1))
        elif kind==3: z=np.tile(np.linspace(0,1,h)[:,None],(1,w))
        elif kind==4: z=np.sign(x+y-p[0])+.04*noise
        elif kind==5: z=rng.integers(0,8,(h,w)).astype(float)
        elif kind==6: z=np.full((h,w),rng.integers(100,1000),dtype=float)
        elif kind==7: z=np.cumsum(noise,axis=1)
        elif kind==8: z=((np.indices((h,w)).sum(axis=0)%2)*.8).astype(float)
        elif kind==9: z=(x+y)*.5+np.where(rng.random((h,w))<.045,noise*8,0)
        elif kind==10: z=np.repeat(rng.normal(0,1,(h,1)),w,axis=1)+.05*noise
        elif kind==11: z=.5*np.sin(7*x)+.5*np.sin(11*y)
        elif kind==12: z=rng.integers(0,65536,(h,w)).astype(float)
        elif kind==13: # training: periodic code/data discontinuities
            z=.6*x+.25*y+np.where((np.indices((h,w))[1]//3)%2,1.,-1.)
        else: # holdout: nonperiodic block transitions
            blocks=np.cumsum(rng.normal(0,1,(h,1)),axis=0)
            z=.6*x+.25*y+np.where((np.indices((h,w))[0]//2)%2,1.2,-1.2)+.12*blocks
    return np.rint((z-z.min())*rng.uniform(120,17000)+rng.uniform(50,3000)).astype(float)


def make_set(seed:int, count_per_class:int, *,heldout:bool=False):
    rng=np.random.default_rng(seed)
    positives,negatives=[],[]
    pkind=6 if heldout else None
    nkind=14 if heldout else None
    for _ in range(count_per_class):
        positives.append(structural_features(surface(rng,True,pkind if heldout else int(rng.integers(0,6)))))
        negatives.append(structural_features(surface(rng,False,nkind if heldout else int(rng.integers(0,14)))))
    return np.stack(positives+negatives),np.array([1]*count_per_class+[0]*count_per_class)


def train(seed=SEED, samples_per_class:int=2000, *,epochs:int=700,
          algorithm:str='forest') -> StructureRejector:
    if not 50<=samples_per_class<=15000:raise ValueError('50 bis 15000 Beispiele pro Klasse')
    X,y=make_set(seed,samples_per_class)
    mu=X.mean(axis=0);sd=X.std(axis=0);sd[sd<.0001]=1
    Z=np.clip((X-mu)/sd,-6,6)
    weights=np.zeros(Z.shape[1]);bias=0.
    forest=None
    if algorithm=='forest':
        try:
            from sklearn.ensemble import ExtraTreesClassifier
        except ImportError as exc:
            raise RuntimeError('Optionales Trainingspaket scikit-learn fehlt. '
                               'Installiere ecu-studio-ai[train] oder wähle --algorithm linear.') from exc
        # Compact portable trees, no sklearn/pickle needed by Windows app.
        clf=ExtraTreesClassifier(n_estimators=24,max_depth=5,
               min_samples_leaf=6,n_jobs=1,random_state=seed)
        clf.fit(X,y)
        forest=[]
        for estimator in clf.estimators_:
            t=estimator.tree_
            forest.append({'feature':[int(x) for x in t.feature],
                'threshold':[round(float(x),10) for x in t.threshold],
                'left':[int(x) for x in t.children_left],
                'right':[int(x) for x in t.children_right],
                'prob':[round(float(x),9) for x in t.value[:,0,1]],
            })
        def scores(X):return clf.predict_proba(X)[:,1]
    elif algorithm=='linear':
        # Deterministic L2 logistic regression fallback (numpy-only).
        for step in range(epochs):
            logit=np.clip(Z@weights+bias,-35,35)
            pred=1/(1+np.exp(-logit))
            diff=pred-y
            rate=.16/(1+.004*step)
            weights-=rate*(Z.T@diff/len(y)+.025*weights)
            bias-=rate*float(diff.mean())
        def scores(X):
            z=np.clip((X-mu)/sd,-6,6)
            raw=np.clip(z@weights+bias,-35,35)
            return 1/(1+np.exp(-raw))
    else:
        raise ValueError('Algorithmus forest oder linear')
    xv,yv=make_set(seed+100,500)
    sv=scores(xv)
    # Choose cutoff on validation negatives to bound simulated FPR to <= 2%.
    cutoff=float(max(.5,np.quantile(sv[yv==0],.985)+1e-5))
    cutoff=min(.99999,cutoff)
    xh,yh=make_set(seed+200,500,heldout=True)
    sh=scores(xh)
    def report(scores,truth):
        predicted=scores>=cutoff
        tp=int(np.sum(predicted & (truth==1)))
        fp=int(np.sum(predicted & (truth==0)))
        fn=int(np.sum(~predicted & (truth==1)))
        tn=int(np.sum(~predicted & (truth==0)))
        return {'TP':tp,'FP':fp,'FN':fn,'TN':tn,
                'precision':round(tp/max(tp+fp,1),4),
                'recall':round(tp/max(tp+fn,1),4),
                'false_positive_rate':round(fp/max(tn+fp,1),4)}
    provenance=f'generator-v2|seed={seed}|samples={samples_per_class}|epochs={epochs}|algorithm={algorithm}'
    metrics={'domain':'synthetic-only; does NOT imply real ECU/TCU accuracy',
             'train_samples':len(X),'validation_samples':len(xv),
             'holdout_samples':len(xh),
             'holdout_generator':'unseen cross-fade maps vs unseen discontinuous row blocks',
             'validation':report(sv,yv),'holdout':report(sh,yh),
             'threshold_selected_on':'validation negative 98.5th percentile, min 0.5',
             'training_method':('ExtraTrees 24x5, reproducible, JSON-only inference' if forest else 'L2 logistic regression, deterministic features'),
             'algorithm':algorithm,
             'real_heldout_firmwares':0,'verified_map_type_labels':0,
             'semantic_model_retrained':False}
    return StructureRejector(mu.tolist(),sd.tolist(),weights.tolist(),float(bias),
                             cutoff,metrics,hashlib.sha256(provenance.encode()).hexdigest(),trees=forest)


def main():
    p=argparse.ArgumentParser(description='Train synthetic-domain structural filter (not ECU semantics).')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--samples-per-class',type=int,default=2000)
    p.add_argument('--report',type=Path)
    p.add_argument('--algorithm',choices=['forest','linear'],default='forest')
    args=p.parse_args()
    obj=train(samples_per_class=args.samples_per_class,algorithm=args.algorithm)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    obj.save(args.out)
    if args.report:
        args.report.write_text(json.dumps({'model_file':str(args.out),'training_hash':obj.training_hash,
                                     'decision_threshold':obj.threshold,**obj.metrics},indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(obj.metrics,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
