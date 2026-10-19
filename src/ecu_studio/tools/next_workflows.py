"""Offline reproducible workflows. All batch inputs are planned before writes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from ecu_studio.core.model import load_project,save_project,read_project_snapshots
from ecu_studio.core.editing import plan_recipe
from ecu_studio.core.workflows import apply_batch
from ecu_studio.core.storage import atomic_write
from ecu_studio.core.smart_transfer import FirmwareIdentity,plan_transfer,apply_transfer
from ecu_studio.recognition.evaluation import evaluate
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def _check_report_path(report,protected):
    target=Path(report).resolve()
    for path in protected:
        if path and (target==Path(path).resolve() or
                     (target.exists() and Path(path).exists() and os.path.samefile(target,path))):
            raise ValueError('Bericht darf keine Eingabe oder Projektausgabe überschreiben')


def batch_recipes(manifest_path,*,commit=False,report_path=None):
    root=Path(manifest_path).resolve().parent
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    jobs=manifest.get('jobs')
    if manifest.get('schema')!=1 or not isinstance(jobs,list) or not 1<=len(jobs)<=200:
        raise ValueError('Batchmanifest Schema 1 mit 1–200 Jobs erforderlich')
    planned=[]
    destinations=set()
    protected={root/job['project'] for job in jobs}
    for job in jobs:
        source=(root/job['project']).resolve()
        target=(root/job['output']).resolve()
        if target.exists() or target in destinations or target in {p.resolve() for p in protected}:
            raise ValueError('Batchausgabe muss ein eindeutiger, neuer Projektpfad sein')
        destinations.add(target)
        image,maps,bookmarks,notes=load_project(source)
        if image.path and target==Path(image.path).resolve():
            raise ValueError('Original darf nicht überschrieben werden')
        recipe=json.loads((root/job['recipe']).read_text(encoding='utf-8'))
        preview=plan_recipe(image,maps,recipe)
        planned.append((target,image,maps,bookmarks,notes,read_project_snapshots(source,image),preview))
    report={'schema':1,'committed':False,'jobs':[{'output':str(p),'sha256':i.digest,'changed_bytes':v.changed_bytes}
                                               for p,i,_,_,_,_,v in planned],
            'atomicity':'Each project is atomic. A disk failure may leave completed new outputs; input projects are never overwritten.'}
    protected=[manifest_path,*[root/job['project'] for job in jobs],*[root/job['recipe'] for job in jobs],
               *[p for p,*_ in planned],*[i.path for _,i,*_ in planned]]
    if report_path:
        _check_report_path(report_path,protected)
    if commit:
        for target,image,maps,bookmarks,notes,snapshots,preview in planned:
            # Exclusive destination check again immediately before each save.
            if target.exists():
                raise FileExistsError(target)
            apply_batch(image,preview)
            save_project(target,image,maps,bookmarks,notes,snapshots,overwrite=False)
        report['committed']=True
    if report_path:
        atomic_write(report_path,json.dumps(report,indent=2,ensure_ascii=False).encode('utf-8'),protected=protected)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='action',required=True)
    batch=sub.add_parser('batch-recipe')
    batch.add_argument('manifest')
    batch.add_argument('--commit',action='store_true',help='explicitly write all prevalidated jobs')
    batch.add_argument('--report',required=True)
    evaluation=sub.add_parser('evaluate')
    evaluation.add_argument('manifest')
    evaluation.add_argument('--report',required=True)
    transfer=sub.add_parser('transfer')
    transfer.add_argument('--source-project',required=True)
    transfer.add_argument('--target-project',required=True)
    transfer.add_argument('--identities',required=True,help='JSON source and target FirmwareIdentity objects')
    transfer.add_argument('--mode',choices=('delta','percent'),default='delta')
    transfer.add_argument('--report',required=True)
    transfer.add_argument('--approve-plan',help='exact SHA-256 of a previously reviewed plan')
    transfer.add_argument('--selected',type=int,nargs='+')
    transfer.add_argument('--output-project')
    args=parser.parse_args(argv)
    if args.action=='batch-recipe':
        batch_recipes(args.manifest,commit=args.commit,report_path=args.report)
        return 0
    elif args.action=='evaluate':
        result=evaluate(args.manifest,{'current':scan_calibration_candidates})
        root=Path(args.manifest).resolve().parent
        cases=json.loads(Path(args.manifest).read_text(encoding='utf-8'))['cases']
        protected=(args.manifest,*[root/c['binary'] for c in cases],*[root/c['definitions'] for c in cases])
    else:
        source,sm,_,_=load_project(args.source_project)
        target,tm,bookmarks,notes=load_project(args.target_project)
        identities=json.loads(Path(args.identities).read_text(encoding='utf-8'))
        plan=plan_transfer(source,target,sm,tm,source_identity=FirmwareIdentity(**identities['source']),
                           target_identity=FirmwareIdentity(**identities['target']),mode=args.mode)
        body=json.dumps(plan.report(),sort_keys=True,separators=(',',':'),ensure_ascii=False)
        token=hashlib.sha256(body.encode('utf-8')).hexdigest()
        result={'plan_sha256':token,'plan':plan.report(),'applied':False}
        protected=(args.source_project,args.target_project,args.identities,source.path,target.path,args.output_project)
        _check_report_path(args.report,protected)
        if args.approve_plan:
            if args.approve_plan!=token or not args.output_project or not args.selected:
                raise ValueError('Exakter Vorschauhash, Auswahl und neuer Ausgabepfad erforderlich')
            output=Path(args.output_project)
            if output.exists():
                raise FileExistsError('Nur neue Ausgabeprojekte zulässig')
            apply_transfer(target,plan,args.selected,confirmed=True)
            target.journal.append({'label':'CLI Smart Transfer Freigabe','plan_sha256':token,'selected':args.selected,'report':plan.report()})
            save_project(output,target,tm,bookmarks,notes,read_project_snapshots(args.target_project,target),overwrite=False)
            result['applied']=True
    atomic_write(args.report,json.dumps(result,indent=2,ensure_ascii=False).encode('utf-8'),protected=protected)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
