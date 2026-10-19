"""CLI: evidence-based catalog, transfer and ML, with JSON audit.

Examples:
  python -m ecu_studio.tools.recognition_v13 --bin file.bin --catalog stats
  python -m ecu_studio.tools.recognition_v13 --bin file.bin --xdf matched.xdf --catalog index
  python -m ecu_studio.tools.recognition_v13 --catalog train --model trained.json
  python -m ecu_studio.tools.recognition_v13 --bin file.bin --catalog predict --model trained.json
"""
import argparse
import json
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.xdf import read_xdf
from ecu_studio.core.profiles import identify_profile, xdf_match_status
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.transfer import match_verified
from ecu_studio.recognition.ml import train, Model


def execute(args):
    catalog=DefinitionCatalog(args.db)
    if args.catalog=='stats':
        return catalog.stats()
    if args.catalog=='batch':
        if not args.manifest:raise ValueError('--manifest ist erforderlich')
        manifest=Path(args.manifest).resolve(strict=True)
        content=json.loads(manifest.read_text(encoding='utf8'))
        pairs=content.get('pairs', [])
        if not isinstance(pairs,list) or len(pairs)>2000:
            raise ValueError('Batchliste muss 0 bis 2000 Paare enthalten')
        all_results=[]
        for row in pairs:
            try:
                if not isinstance(row,dict):raise ValueError('Ungültiger Paareintrag')
                binary=(manifest.parent/row['bin']).resolve(strict=True)
                xdf=(manifest.parent/row['xdf']).resolve(strict=True)
                if xdf.suffix.lower()!='.xdf':raise ValueError('Nicht unterstütztes Definitionsformat in Batch: '+xdf.suffix)
                image=BinaryImage.from_file(str(binary))
                status,reason=xdf_match_status(identify_profile(image),str(xdf))
                if status=='rejected':raise ValueError('Definition passt nicht: '+reason)
                result=read_xdf(str(xdf),image)
                report=catalog.import_maps(image,result.maps,origin='Batch-Index: '+str(xdf),source_path=xdf)
                all_results.append({'bin':str(binary),'xdf':str(xdf),'status':status,
                                    'indexed':report['indexed'],'import_coverage':round(result.coverage,4),
                                    'excluded':dict(result.excluded),
                                    'verified_count':0})
            except (OSError,ValueError,KeyError,TypeError) as exc:
                all_results.append({'pair':str(row),'error':str(exc)})
        return {'pairs':len(all_results),'indexed':sum(x.get('indexed',0) for x in all_results),
                'successful':sum('error' not in x for x in all_results), 'results':all_results,
                'important':'Importierte Definitionen sind UNGEPRÜFT. Keine automatische ML-Freigabe.'}
    if args.catalog=='train':
        trained=train(catalog)
        trained.save(args.model)
        return {'trained':True,'model':str(args.model),'labels':trained.labels,
                'metrics':trained.metrics}
    if not args.bin:
        raise ValueError('--bin ist für diese Operation erforderlich')
    image=BinaryImage.from_file(args.bin)
    profile=identify_profile(image)
    if args.catalog=='index':
        if not args.xdf:raise ValueError('--xdf erforderlich')
        status,reason=xdf_match_status(profile,args.xdf)
        if status=='rejected':raise ValueError('Unpassende Definition: '+reason)
        result=read_xdf(args.xdf,image)
        out=catalog.import_maps(image,result.maps,origin='TunerPro XDF (ungeprüfte Quelle)',
                                source_path=args.xdf)
        out.update({'xdf_coverage':round(result.coverage,4),'excluded':dict(result.excluded),
                    'compatibility':status,'reason':reason})
        return out
    if args.catalog=='predict':
        transfer=match_verified(image,catalog,max_references=args.max_references)
        items=[{'source':h.source_name,'offset':f'0x{h.proposed.offset:X}',
                'score':round(h.score,4),'runner_up':round(h.runner_up,4),
                'unique':h.uniquely_located,'note':h.evidence} for h in transfer]
        model_data=[]
        if args.model and Path(args.model).exists():
            model=Model.load(args.model)
            if model.family==profile.family and model.metrics.get('release_gate'):
                for m in scan_calibration_candidates(image)[:args.max_candidates]:
                    matrix=[[image.raw_value(m,y,x) for x in range(m.cols)] for y in range(m.rows)]
                    prediction=model.predict(matrix, family=profile.family)
                    model_data.append({'offset':f'0x{m.offset:X}',**prediction})
        return {'identity':profile.asdict(),'exact_definitions':len(catalog.firmware_maps(image)),
                'verified_other_firmware_suggestions':items,'ml_suggestions':model_data,
                'caveat':'Similarity/model scores are not verified ECU map meanings; no BIN writes.'}
    raise ValueError('Unbekannte Aktion')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',choices=['stats','index','batch','train','predict'],required=True)
    p.add_argument('--bin');p.add_argument('--xdf');p.add_argument('--db');p.add_argument('--manifest')
    p.add_argument('--model',default=str(Path.home()/'.ecu_studio_ai'/'trained-map-model.json'))
    p.add_argument('--max-references',type=int,default=24)
    p.add_argument('--max-candidates',type=int,default=100)
    p.add_argument('--json')
    args=p.parse_args()
    try:
        result=execute(args)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        p.exit(2, 'Erkennung/Import nicht möglich: '+str(exc)+'\n')
    data=json.dumps(result,ensure_ascii=False,indent=2)
    if args.json:Path(args.json).write_text(data,encoding='utf8')
    print(data)

if __name__=='__main__':main()
