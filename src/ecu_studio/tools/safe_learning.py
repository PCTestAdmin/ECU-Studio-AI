"""CLI: real-data structure training, quality-gated supervised training and family registry."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from dataclasses import asdict
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.profiles import identify_profile
from ecu_studio.recognition.catalog import DefinitionCatalog,default_catalog
from ecu_studio.recognition.structure_model import train_shape_model,ShapeModel
from ecu_studio.recognition.safe_classifier import train_safe
from ecu_studio.recognition.families import FAMILIES
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def cli(argv=None):
    p=argparse.ArgumentParser(description='Konservatives Lernsystem ECU Studio AI')
    s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('families');a.add_argument('--out')
    a=s.add_parser('train-structure');a.add_argument('--db',default=str(default_catalog()));a.add_argument('--bin',required=True);a.add_argument('--out',required=True);a.add_argument('--accept-unverified',action='store_true')
    a=s.add_parser('suggest-structure');a.add_argument('--bin',required=True);a.add_argument('--model',required=True);a.add_argument('--out',required=True);a.add_argument('--limit',type=int,default=120)
    a=s.add_parser('review-queue');a.add_argument('--db',default=str(default_catalog()))
    a.add_argument('--bin',required=True);a.add_argument('--model',required=True)
    a.add_argument('--out',required=True);a.add_argument('--limit',type=int,default=40)
    a=s.add_parser('train-safe');a.add_argument('--db',default=str(default_catalog()));a.add_argument('--family',required=True);a.add_argument('--out',required=True)
    a=s.add_parser('source-discovery');a.add_argument('--db',default=str(default_catalog()));a.add_argument('--brand');a.add_argument('--out')
    a=s.add_parser('train-status');a.add_argument('--db',default=str(default_catalog()))
    a=s.add_parser('intake-pair');a.add_argument('--db',default=str(default_catalog()))
    a.add_argument('--bin',required=True);a.add_argument('--definition',required=True)
    a.add_argument('--family',required=True);a.add_argument('--software',required=True)
    a.add_argument('--variant',required=True);a.add_argument('--sha256',required=True)
    a.add_argument('--address-segments',help='JSON: [{"ecu_start":int,"ecu_end":int,"file_start":int}] für A2L')
    a.add_argument('--acknowledge-identity',action='store_true')
    args=p.parse_args(argv)
    if args.command=='families':
        result={'families':[asdict(f) for f in FAMILIES.values()], 'warning':'Unterstütztes Familienregister ist keine validierte Autodetektion.'}
    elif args.command=='source-discovery':
        from ecu_studio.recognition.source_registry import discovery_sources, BRANDS
        db=DefinitionCatalog(args.db)
        result={'brands':BRANDS,'sources':discovery_sources(db,args.brand),
                'training_approved':0,'notice':'Nur Quellhinweise. Kein ECU-BIN, keine automatische Zuordnung oder verifizierte KI-Labels.'}
    elif args.command=='train-status':
        db=DefinitionCatalog(args.db);r=db.records()
        result={'verified_total':sum(int(x['verified']) for x in r),
                'verified_by_family':{f:sum(int(x['verified']) for x in r if x['family']==f) for f in sorted({x['family'] for x in r})},
                'required':'Mindestens 2 Klassen und pro Klasse 12 unabhängig bestätigte Karten aus mindestens 4 Firmwareständen; erfolgreicher Firmware-Holdout',
                'unverified_public_hints':db.stats().get('public_map_hints')}
    elif args.command=='intake-pair':
        from ecu_studio.recognition.intake import ingest_explicit_pair
        from ecu_studio.core.addressing import AddressSegment
        segments=None
        if args.address_segments:
            raw=json.loads(Path(args.address_segments).read_text(encoding='utf-8'))
            segments=[AddressSegment(**x) for x in raw]
        result=ingest_explicit_pair(DefinitionCatalog(args.db),bin_path=args.bin,
            definition_path=args.definition,family=args.family,software=args.software,
            variant=args.variant,expected_sha256=args.sha256,
            acknowledge=args.acknowledge_identity,segments=segments)
    elif args.command=='train-structure':
        if not args.accept_unverified:
            p.error('Explizit --accept-unverified für ungeprüfte XDF-Proben erforderlich')
        img=BinaryImage.from_file(args.bin)
        m=train_shape_model(DefinitionCatalog(args.db),img)
        m.save(args.out)
        result={'status':'trained_unsupervised','saved_model':str(Path(args.out).resolve()),'report':m.report,
                'notice':'Kein Klassenmodell; keine Funktionstypen freigegeben; Referenz-XDF unbestätigt.'}
    elif args.command=='suggest-structure':
        model=ShapeModel.load(args.model);img=BinaryImage.from_file(args.bin)
        prof=identify_profile(img)
        if prof.family !=model.family or (prof.software_version or prof.calibration_id or '')!=model.software:
            result={'status':'abstain','reason':'Modell kennt diese ECU-Familie/Software nicht', 'suggestions':[]}
        else:
            proposals=[]
            for m in scan_calibration_candidates(img)[:max(1,min(args.limit,300))]:
                try:
                    if m.rows<3 or m.cols<3 or m.rows*m.cols>4096:continue
                    z=[[img.raw_value(m,y,x) for x in range(m.cols)] for y in range(m.rows)]
                    pred=model.similar(z,family=prof.family,software=model.software)
                    if pred['status']=='shape-similar':
                        proposals.append({'offset':hex(m.offset),'rows':m.rows,'cols':m.cols,
                                          'nearest_reference':pred['candidates'][0],
                                          'verified':False,'type':'Unbekannt'})
                except (ValueError,IndexError):continue
            result={'status':'structure_only','suggestions':proposals,
                    'warning':'Weder Formähnlichkeit noch Datenposition beweisen ECU-Funktion, Achsen oder Flashbarkeit.'}
    elif args.command=='review-queue':
        from ecu_studio.recognition.review import review_queue
        img=BinaryImage.from_file(args.bin)
        model=ShapeModel.load(args.model)
        result=review_queue(img,DefinitionCatalog(args.db),model,limit=max(1,min(args.limit,100)))
    elif args.command=='train-safe':
        m=train_safe(DefinitionCatalog(args.db),args.family)
        m.save(args.out)
        result={'status':'trained_supervised','file':str(Path(args.out).resolve()),'metrics':m.metrics,'labels':m.labels}
    if hasattr(args,'out') and args.out and args.command in ('families','suggest-structure','review-queue','source-discovery'):
        Path(args.out).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return result

if __name__=='__main__':cli()
