"""Standalone repeatable ECU/TCU structural holdout report.

Use only local files that you have the right to analyze. Public web links
are evidence pointers, not auto-approved training labels.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ecu_studio.recognition.holdout_eval import evaluate_manifest
from ecu_studio.recognition.tcu_curves import scan_paired_u16_curves
from ecu_studio.core.model import BinaryImage


def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('eval');a.add_argument('--manifest',required=True);a.add_argument('--out',required=True)
    a=s.add_parser('tcu-curves');a.add_argument('--bin',required=True);a.add_argument('--out',required=True)
    a.add_argument('--start',type=lambda x:int(x,0),default=0)
    a.add_argument('--end',type=lambda x:int(x,0));a.add_argument('--limit',type=int,default=80)
    a=s.add_parser('sources');a.add_argument('--out',required=True)
    args=p.parse_args(argv)
    if args.command=='eval': result=evaluate_manifest(args.manifest)
    elif args.command=='tcu-curves':
        image=BinaryImage.from_file(args.bin)
        candidates=scan_paired_u16_curves(image,start=args.start,end=args.end,max_results=args.limit)
        result={'sha256':image.digest,'candidates':[{'offset':hex(x.offset),'points':x.cols,
                 'endian':x.endian,'x':x.axes_x,'confidence_heuristic':x.confidence,
                 'verified':x.verified,'warning':x.label_evidence} for x in candidates],
                'notice':'Strukturkandidaten – keine bestätigten TCU-Kennfelder oder Schaltdrücke'}
    else:
        path=Path(__file__).resolve().parents[1]/'recognition'/'data'/'new_ecu_tcu_sources.json'
        result=json.loads(path.read_text(encoding='utf-8'))
    outfile=Path(args.out);outfile.parent.mkdir(parents=True,exist_ok=True)
    outfile.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'saved_report':str(outfile),'summary':{
        k:v for k,v in result.items() if k in ('cases_processed','cases_failed','heldout_firmware_count','heldout_2d_recall_proxy','sha256','notice')}},ensure_ascii=False))
    return result

if __name__=='__main__':cli()
