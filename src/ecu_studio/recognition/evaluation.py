"""Strict, provenance-bound paired evaluation; no pseudo ground truth.

Exact cell layout is required for a true positive. Partial definition catalogues
cannot measure false alarms: precision/F1 are unavailable for such cases.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from .holdout_eval import _content_blocks
from ..core.model import BinaryImage, MapDefinition
from ..core.storage import atomic_write


def _signature(m):
    return (m.offset,m.rows,m.cols,m.dtype,m.endian,m.storage_order,
            m.major_stride_bits,m.minor_stride_bits)


def detection_metrics(predictions,truth,byte_count,*,exhaustive=False):
    known={_signature(m):m for m in truth}
    used=set()
    exact=0
    address=0
    errors=[]
    semantic_correct=0
    semantic_tested=0
    for p in predictions:
        key=_signature(p)
        if key in known and key not in used:
            exact+=1
            used.add(key)
            if known[key].kind!='Unbekannt':
                semantic_tested+=1
                semantic_correct+=p.kind==known[key].kind
        if truth:
            errors.append(min(abs(p.offset-t.offset) for t in truth))
        address+=any(p.offset==t.offset for t in truth)
    unmatched=len(predictions)-exact
    precision=exact/len(predictions) if predictions and exhaustive else (0. if exhaustive else None)
    recall=exact/len(truth) if truth else None
    f1=(2*precision*recall/(precision+recall) if precision+recall else 0.) if precision is not None and recall is not None else None
    return dict(predictions=len(predictions),truth=len(truth),exact_layout_matches=exact,
                unmatched_predictions=unmatched,missed_maps=len(truth)-exact,
                precision=precision,recall=recall,f1=f1,
                false_alarms_per_mb=unmatched/(byte_count/1024**2) if exhaustive and byte_count else None,
                exact_start_fraction=address/len(predictions) if predictions else None,
                mean_nearest_address_error_bytes=sum(errors)/len(errors) if errors else None,
                semantic_accuracy_on_matched_maps=semantic_correct/semantic_tested if semantic_tested else None,
                exhaustive_ground_truth=exhaustive)


def validate_manifest(path):
    root=Path(path).resolve().parent
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    cases=obj.get('cases')
    if obj.get('schema')!=1 or not isinstance(cases,list) or not 1<=len(cases)<=200:
        raise ValueError('Manifest Schema 1 mit 1–200 Fällen erforderlich')
    loaded=[]
    groups={}
    seen_hashes=set()
    for case in cases:
        required=('id','family','software','independence_group','source_url','source_license','license_reviewer','definition_reviewer')
        if any(not isinstance(case.get(k),str) or not case[k].strip() for k in required):
            raise ValueError('Herkunft, unabhängige Firmwaregruppe und fachliche Prüfer erforderlich')
        if case.get('data_kind') not in ('real','synthetic') or case.get('split') not in ('train','validation','test'):
            raise ValueError('data_kind und split müssen explizit angegeben werden')
        if case.get('license_reviewed') is not True or case.get('definitions_verified') is not True:
            raise ValueError('Rechteprüfung und unabhängige Definitionsprüfung erforderlich')
        image=BinaryImage.from_file(str(root/case['binary']))
        definitions=root/case['definitions']
        if image.digest!=case.get('sha256') or hashlib.sha256(definitions.read_bytes()).hexdigest()!=case.get('definitions_sha256'):
            raise ValueError('Firmware-/Definitionshash stimmt nicht')
        if image.digest in seen_hashes:
            raise ValueError('Leakage: identische Firmware mehrfach')
        seen_hashes.add(image.digest)
        group=case['independence_group']
        if group in groups and groups[group]!=case['split']:
            raise ValueError('Leakage: gleiche unabhängige Firmwaregruppe in mehreren Splits')
        groups[group]=case['split']
        maps=[MapDefinition(**m) for m in json.loads(definitions.read_text(encoding='utf-8'))]
        if ((not maps and case.get('exhaustive') is not True) or any(not m.verified for m in maps)
                or len({_signature(m) for m in maps})!=len(maps)):
            raise ValueError('Bestätigte, eindeutige Definitionen erforderlich')
        for m in maps:
            m.validate(image.size)
        blocks=_content_blocks(image.original)
        for prior,other,_,prior_blocks in loaded:
            if prior['split']==case['split']:
                continue
            if image.size==other.size:
                changed=sum(a!=b for a,b in zip(image.original,other.original))
                if changed/max(1,image.size)<.05:
                    raise ValueError('Leakage: nahezu identische ORI/MOD-Bilder über Splits')
            # Content overlap also catches moved blocks, irrespective of image size.
            if blocks and prior_blocks and len(blocks&prior_blocks)/min(len(blocks),len(prior_blocks))>=.8:
                raise ValueError('Leakage: gleiche Firmwareblöcke über Splits')
        loaded.append((case,image,maps,blocks))
    # Optional harder benchmark: whole ECU families excluded from fit.
    if obj.get('split_strategy')=='family-held-out':
        families={}
        for case,_,_,_ in loaded:
            family=case['family']
            if family in families and families[family]!=case['split']:
                raise ValueError('Leakage: ECU-Familie in mehreren Splits')
            families[family]=case['split']
    return obj,loaded


def evaluate(path,evaluators):
    """Run named baseline/candidate callables on the SAME independent test images."""
    obj,loaded=validate_manifest(path)
    output={name:[] for name in evaluators}
    for case,image,maps,_ in loaded:
        if case['split']!='test':
            continue
        for name,predict in evaluators.items():
            predicted=predict(image)
            output[name].append(dict(id=case['id'],family=case['family'],data_kind=case['data_kind'],
                    sha256=image.digest,independence_group=case['independence_group'],
                    metrics=detection_metrics(predicted,maps,image.size,exhaustive=case.get('exhaustive') is True)))
    by_family={}
    for name,entries in output.items():
        grouped=defaultdict(list)
        for entry in entries:
            grouped[(entry['data_kind'],entry['family'])].append(entry['metrics'])
        by_family[name]=[]
        for (kind,family),metrics in sorted(grouped.items()):
            tp=sum(m['exact_layout_matches'] for m in metrics)
            count=sum(m['predictions'] for m in metrics)
            truth=sum(m['truth'] for m in metrics)
            complete=all(m['exhaustive_ground_truth'] for m in metrics)
            precision=(tp/count if count else 0.) if complete else None
            recall=tp/truth if truth else None
            by_family[name].append(dict(data_kind=kind,family=family,cases=len(metrics),
                precision=precision,recall=recall,
                f1=(2*precision*recall/(precision+recall) if precision+recall else 0.)
                    if precision is not None and recall is not None else None))
    return dict(schema=1,manifest_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                by_family=by_family,
                split_strategy=obj.get('split_strategy','firmware-group-held-out'),results=output,
                real_test_images=sum(c['split']=='test' and c['data_kind']=='real' for c,_,_,_ in loaded),
                synthetic_test_images=sum(c['split']=='test' and c['data_kind']=='synthetic' for c,_,_,_ in loaded),
                interpretation='Exakte Layoutmetrik. Nicht vollständige Ground Truth: Precision/F1/Fehlalarme unbekannt. Keine Flashfreigabe.')


def promotion_gate(report,baseline,candidate):
    """A report can justify review, never silently install new weights."""
    a=report['results'][baseline]
    b=report['results'][candidate]
    real_a={x['sha256']:x for x in a if x['data_kind']=='real'}
    real_b={x['sha256']:x for x in b if x['data_kind']=='real'}
    groups={x['independence_group'] for x in real_b.values()}
    if len(groups)<3 or real_a.keys()!=real_b.keys():
        return {'eligible':False,'reason':'Mindestens drei unabhängige reale Testgruppen und gepaarte Ergebnisse erforderlich'}
    for digest,entry in real_b.items():
        old,new=real_a[digest]['metrics'],entry['metrics']
        if (new['f1'] is None or old['f1'] is None or new['f1']<old['f1'] or
                new['false_alarms_per_mb']>old['false_alarms_per_mb']):
            return {'eligible':False,'reason':'Vollständige geprüfte Ground Truth oder regressionsfreier Vergleich fehlt'}
    improved=any(real_b[h]['metrics']['f1']>real_a[h]['metrics']['f1'] for h in real_b)
    return {'eligible':improved,'reason':'Reale Verbesserung zur manuellen Modellprüfung' if improved else 'Kein nachgewiesener Vorteil'}
