"""Auditable ECU/TCU firmware-held-out evaluation; never treats XDF names as truth.

Evaluates *location coverage*, not function-classification accuracy. Only users
with independently verified definitions may promote findings to verified labels.
Do not bundle unlicensed OEM firmware in the project.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.xdf import read_xdf
from ecu_studio.recognition.tcu_curves import scan_paired_u16_curves


def _reference_maps(image: BinaryImage, entry:dict, root:Path):
    path=root/entry['definition']
    if path.suffix.lower() == '.xdf':
        r=read_xdf(str(path),image)
        return r.maps,{'format':'XDF','mapped':len(r.maps),'excluded':dict(r.excluded)}
    if path.suffix.lower() == '.json':
        raw=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw,list) or len(raw)>20000:raise ValueError('Definitionen müssen eine begrenzte Liste sein')
        maps=[MapDefinition(**x) for x in raw]
        for m in maps:m.validate(image.size)
        return maps,{'format':'JSON','mapped':len(maps),'excluded':{}}
    raise ValueError('Nur XDF oder explizite JSON-MapDefinitionen im Benchmark')


def _span(map_:MapDefinition)->tuple[int,int]:
    # Supports strided/column-major definitions without assuming packed layout.
    return map_.offset,map_.offset+map_.length


def _overlap(a:MapDefinition,b:MapDefinition)->float:
    a0,a1=_span(a);b0,b1=_span(b)
    inter=max(0,min(a1,b1)-max(a0,b0))
    return inter/max(1,min(a1-a0,b1-b0))


def _matches(predictions:list[MapDefinition],truth:list[MapDefinition], threshold:float=.60)->dict:
    # One-to-one greedy matching, deterministic, matches 1-D with 1-D only.
    options=[]
    for pi,p in enumerate(predictions):
        for ti,t in enumerate(truth):
            if (p.rows==1 or p.cols==1)!=(t.rows==1 or t.cols==1):continue
            score=_overlap(p,t)
            if score>=threshold:options.append((score,pi,ti))
    used_p=set();used_t=set();examples=[]
    for ov,pi,ti in sorted(options,key=lambda v:(-v[0],v[1],v[2])):
        if pi in used_p or ti in used_t:continue
        used_p.add(pi);used_t.add(ti)
        if len(examples)<12:examples.append({'predicted_offset':hex(predictions[pi].offset),
                                             'reference_offset':hex(truth[ti].offset),
                                             'overlap':round(ov,3)})
    tp=len(used_p);fp=len(predictions)-tp;fn=len(truth)-tp
    return {'predicted':len(predictions),'reference':len(truth),'matched':tp,
            'unmatched_predictions':fp,'missed_definitions':fn,
            'location_precision_proxy':round(tp/len(predictions),4) if predictions else None,
            'definition_recall_proxy':round(tp/len(truth),4) if truth else None,
            'matches_sample':examples}


def _content_blocks(payload:bytes, block_size:int=2048)->set[str]:
    """Cheap anti-leakage fingerprint. Ignore repetitive flash padding."""
    selected=set()
    for j in range(0,len(payload)-block_size+1,block_size):
        block=payload[j:j+block_size]
        if len(set(block))<12: continue
        selected.add(hashlib.sha256(block).hexdigest())
    return selected


def evaluate_manifest(manifest_path:str|Path, *,max_cases:int=40,limit_mb:int=2)->dict:
    """Manifest: {cases:[{bin,definition,domain,split,sha256,source_license,...}]}.

    A valid strict held-out benchmark requires SHA256 and independent firmwares
    for train/test. Splitting random cells from one binary is rejected.
    """
    location=Path(manifest_path).resolve();root=location.parent
    raw=json.loads(location.read_text(encoding='utf-8'))
    cases=raw.get('cases')
    if not isinstance(cases,list) or not 1<=len(cases)<=max_cases:
        raise ValueError('Manifest muss 1 bis max_cases Fälle enthalten')
    if limit_mb<1 or limit_mb>16:raise ValueError('limit_mb muss 1..16 sein')
    results=[];groups={};blocks_seen=[];errors=[]
    for i,entry in enumerate(cases):
        try:
            if entry.get('split') not in ('train','test','validation'):
                raise ValueError('split muss train, validation oder test sein')
            if entry.get('domain') not in ('ecu','tcu'):
                raise ValueError('domain muss ecu oder tcu sein')
            if not entry.get('source_license'):
                raise ValueError('Rechte-/Herkunftsangabe erforderlich')
            if not entry.get('sha256') or len(entry['sha256'])!=64:
                raise ValueError('SHA-256 erforderlich')
            image=BinaryImage.from_file(str(root/entry['bin']))
            if image.digest.lower()!=entry['sha256'].lower():
                raise ValueError('Firmware-Hash weicht vom Manifest ab')
            if image.digest in groups:
                raise ValueError('Leakage: identische Firmware mehrfach im Benchmark, ggf. über Splits')
            blocks=_content_blocks(image.original)
            for prior_split,prior_size,prior_blocks in blocks_seen:
                if prior_split==entry['split'] or prior_size!=image.size or not blocks or not prior_blocks:continue
                same=len(blocks & prior_blocks)/min(len(blocks),len(prior_blocks))
                if same>=.80:
                    raise ValueError(f'Leakage: sehr ähnliche BIN-Dateien in unterschiedlichen Splits (Blockgleichheit {same:.1%})')
            groups[image.digest]=entry['split']
            blocks_seen.append((entry['split'],image.size,blocks))
            truth,ref_info=_reference_maps(image,entry,root)
            # Exclude unsupported scalars by reporting separate match types;
            # strict 2D coverage is not inflated by definitions of constants.
            target_2d=[m for m in truth if m.rows>=3 and m.cols>=3]
            target_1d=[m for m in truth if (m.rows==1 or m.cols==1) and max(m.rows,m.cols)>=5]
            predictions=scan_calibration_candidates(image,limits=(35,15,10,10))
            data_2d=_matches(predictions,target_2d)
            data_1d=None
            if entry['domain']=='tcu':
                opts=scan_paired_u16_curves(image,end=min(image.size,limit_mb*1024*1024))
                data_1d=_matches(opts,target_1d)
            results.append({'id':entry.get('id',f'case_{i+1}'),'domain':entry['domain'],
                            'split':entry['split'],'sha256':image.digest,'bytes':image.size,
                            'source_license':entry['source_license'],
                            'definition_status':entry.get('definition_status','unverified-source'),
                            'reference_import':ref_info,'scan_2d':data_2d,'scan_1d':data_1d})
        except (ValueError,OSError,IndexError,KeyError,TypeError) as err:
            errors.append({'id':entry.get('id',f'case_{i+1}'),'error':str(err)})
    test_results=[x for x in results if x['split']=='test']
    return {'metric_type':'Definitionen zu Kandidaten: räumliche Deckung, KEINE semantische Trefferquote',
            'cases_processed':len(results),'cases_failed':len(errors),'heldout_firmware_count':len(test_results),
            'heldout_2d_matched_total':sum(x['scan_2d']['matched'] for x in test_results),
            'heldout_2d_reference_total':sum(x['scan_2d']['reference'] for x in test_results),
            'heldout_2d_recall_proxy':(round(sum(x['scan_2d']['matched'] for x in test_results)/sum(x['scan_2d']['reference'] for x in test_results),4)
                if sum(x['scan_2d']['reference'] for x in test_results) else None),
            'results':results,'errors':errors,
            'warning':('XDF-/JSON-Definitionen sind nicht automatisch verifiziert. '
                       'Keine physikalische Funktionsklassifizierung und keine ECU-/TCU-Flashfreigabe.')}
