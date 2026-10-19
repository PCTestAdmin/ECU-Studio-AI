"""Offline, reproducible training on GPL open-ECU calibration presets.

Whole source groups are held out BEFORE encoding augmentation. Near-duplicate
normalised surfaces are purged across splits. Non-map negatives are generated
corruptions, not independently identified OEM executable code.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from ecu_studio.recognition.structure_rejector import StructureRejector,structural_features,installed_rejector,FEATURES

DATA=Path(__file__).resolve().parents[1]/'recognition'/'data'
SEED=20261017


def fingerprint(a):
    a=np.asarray(a,dtype=float);span=np.ptp(a)
    if span==0:return np.zeros(64)
    from ecu_studio.recognition.ml import _resize
    return _resize((a-a.min())/span).ravel()


def load_corpus(path):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if doc['format']!=1 or doc['repository']!='rusefi/rusefi':raise ValueError('Unknown training corpus')
    for source in doc['sources']:
        payload=(Path(path).parent/source['file']).read_bytes()
        if hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()!=source['git_blob']:
            raise ValueError('Training source hash mismatch')
    records=[];seen=set()
    for row in doc['records']:
        a=np.asarray(row['values'],dtype=float)
        if (a.shape!=(row['rows'],row['cols']) or min(a.shape)<3 or a.size>4096
                or not np.isfinite(a).all()):raise ValueError('Invalid source table')
        if np.ptp(a)==0 or len(np.unique(a))<8:continue
        key=tuple(np.round(fingerprint(a),5))
        if key in seen:continue
        seen.add(key);records.append(row)
    return doc,records


def examples(records,seed,repeats=8):
    rng=np.random.default_rng(seed);features=[];labels=[]
    for record in records:
        a=np.asarray(record['values'],dtype=float)
        normal=(a-a.min())/np.ptp(a)
        for _ in range(repeats):
            scale=int(rng.choice([255,4095,32767,60000]))
            values=np.rint(normal*scale+rng.integers(0,500))
            if rng.random()<.5:values=values.T.copy()
            features.append(structural_features(values));labels.append(1)
            # Deliberately generated negatives share the parent group's split.
            shuffled=rng.permutation(values.ravel()).reshape(values.shape)
            block=values.copy()
            for r in range(len(block)):block[r]=np.roll(block[r],int(rng.integers(0,block.shape[1])))
            noise=rng.integers(0,65536,values.shape)
            for bad in (shuffled,block,noise):
                features.append(structural_features(bad));labels.append(0)
            if values.shape[1]%2==0 and values.shape[1]//2>=3:
                wrong=np.frombuffer(values.astype('>u2').tobytes(),dtype='>u4').reshape(values.shape[0],-1)
                features.append(structural_features(wrong));labels.append(0)
    return np.asarray(features),np.asarray(labels)


def metrics(scores,y,threshold):
    p=np.asarray(scores)>=threshold;y=np.asarray(y)==1
    tp=int(np.sum(p&y));fp=int(np.sum(p&~y));fn=int(np.sum(~p&y));tn=int(np.sum(~p&~y))
    precision=tp/max(tp+fp,1);recall=tp/max(tp+fn,1)
    return {'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':round(precision,4),
            'recall':round(recall,4),'balanced_accuracy':round((recall+tn/max(tn+fp,1))/2,4)}


def train(corpus_path=DATA/'training'/'calibration_corpus.json'):
    from sklearn.ensemble import ExtraTreesClassifier
    doc,rows=load_corpus(corpus_path)
    holdout=[r for r in rows if r['engine_group'] in ('honda','hyundai')]
    validation=[r for r in rows if r['engine_group']=='mazda']
    training=[r for r in rows if r['engine_group'] not in ('honda','hyundai','mazda')]
    def purge(pool,against):
        return [r for r in pool if all(np.mean(np.abs(fingerprint(r['values'])-fingerprint(a['values'])))>.015 for a in against)]
    validation=purge(validation,holdout);training=purge(training,validation+holdout)
    if min(len(training),len(validation),len(holdout))<2:raise ValueError('Insufficient independent source groups after duplicate purge')
    x,y=examples(training,SEED);xv,yv=examples(validation,SEED+1);xh,yh=examples(holdout,SEED+2)
    classifier=ExtraTreesClassifier(n_estimators=32,max_depth=6,min_samples_leaf=3,
        class_weight='balanced',n_jobs=1,random_state=SEED)
    classifier.fit(x,y);sv=classifier.predict_proba(xv)[:,1]
    candidates=np.linspace(.25,.95,71)
    # Select only on validation groups, never on the held-out Honda/Hyundai.
    threshold=float(max(candidates,key=lambda t:metrics(sv,yv,t)['balanced_accuracy']))
    trees=[]
    for estimator in classifier.estimators_:
        t=estimator.tree_
        trees.append({'feature':[int(v) for v in t.feature],
            'threshold':[float(v) for v in t.threshold],'left':[int(v) for v in t.children_left],
            'right':[int(v) for v in t.children_right],'prob':[float(v) for v in t.value[:,0,1]]})
    baseline=installed_rejector()
    # Score the frozen original baseline on the exact same held-out feature set.
    def old_scores(features):
        result=[]
        for f in features:
            estimates=[]
            for t in baseline.trees:
                n=0
                while t['feature'][n]>=0:n=t['left'][n] if f[t['feature'][n]]<=t['threshold'][n] else t['right'][n]
                estimates.append(t['prob'][n])
            result.append(np.mean(estimates))
        return result
    val=metrics(sv,yv,threshold);held=metrics(classifier.predict_proba(xh)[:,1],yh,threshold)
    old=metrics(old_scores(xh),yh,baseline.threshold)
    split={k:[r['id'] for r in v] for k,v in [('train',training),('validation',validation),('holdout',holdout)]}
    report={'domain':'open-ECU-calibration-presets + generated encoding corruptions; NOT OEM ground truth',
        'sources':doc['sources'],'source_commit':doc['commit'],'corpus_records':len(doc['records']),
        'informative_deduplicated_tables':len(rows),'split_base_maps':{k:len(v) for k,v in split.items()},
        'split_source_groups':{k:sorted(set(r['engine_group'] for r in v)) for k,v in [('train',training),('validation',validation),('holdout',holdout)]},
        'split_ids':split,'near_duplicate_purge_mean_normalized_distance':.015,
        'train_examples':len(y),'validation_examples':len(yv),'holdout_examples':len(yh),
        'validation':val,'holdout':held,'original_synthetic_model_same_holdout':old,
        'ranking_release_gate':val['balanced_accuracy']>=.7 and held['balanced_accuracy']>=old['balanced_accuracy'],
        'algorithm':'ExtraTrees 32 trees, max depth 6; JSON inference; seed 20261017',
        'real_heldout_oem_firmwares':0,'verified_function_labels':0,'private_bin_training':False,
        'limitations':'Small open-project preset corpus. Augmentations are not independent ECUs. Negative corruptions are generated. No engine function or universal map probability is learned.'}
    h=hashlib.sha256(Path(corpus_path).read_bytes()+json.dumps(split,sort_keys=True).encode()+str(SEED).encode()).hexdigest()
    return StructureRejector([0.]*FEATURES,[1.]*FEATURES,[0.]*FEATURES,0.,threshold,report,h,trees=trees)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,default=DATA/'calibration_ranker_v113.json');parser.add_argument('--report',type=Path,default=Path('TRAINING_REPORT_V113.json'))
    args=parser.parse_args();model=train();model.save(args.out)
    args.report.write_text(json.dumps({'training_hash':model.training_hash,'threshold':model.threshold,**model.metrics},indent=2),encoding='utf-8')
    print(json.dumps({k:model.metrics[k] for k in ('split_base_maps','validation','holdout','original_synthetic_model_same_holdout','ranking_release_gate')},indent=2))


if __name__=='__main__':main()
