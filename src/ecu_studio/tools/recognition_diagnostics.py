"""Read-only per-ECU recognition readiness report.

Reports evidence and actual coverage; NEVER implies a universal label detector.
"""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import json
from ..core.model import BinaryImage
from ..core.profiles import identify_profile, xdf_match_status
from ..core.xdf import read_xdf
from ..core.definition_registry import lookup_pair, search_local_xdfs


def diagnose(image: BinaryImage, *, xdf_path: str | None = None,
             directories: list[str] | None = None) -> dict:
    identity=identify_profile(image)
    result={'identity':{
        'family':identity.family,
        'controller':identity.controller,
        'software_version':identity.software_version,
        'calibration_id':identity.calibration_id,
        'file_size':image.size,
        'original_sha256':image.digest,
    },'definition':None,'recognized_named_maps':0,'imported_names':[],
      'unsupported_definitions':0,'heuristic_names_verified':0,
      'warning':'Nicht alle Kennfelder einer unbekannten Firmware können aus Rohbytes benannt werden.'}
    path=xdf_path
    if not path:
        try:pair=lookup_pair(image)
        except (ValueError,OSError,KeyError,TypeError):pair=None
        if pair:path=str(pair.path)
    if not path:
        sources=search_local_xdfs(image,directories or [],max_files=500)
        result['candidates']=[{'name':p.name,'status':st,'reason':reason}
                              for p,st,reason in sources[:40]]
        result['next_action']='Eine nach Softwarestand und Patchvariante geprüfte XDF/A2L zuordnen.'
        return result
    p=Path(path)
    parsed=read_xdf(str(p),image)
    match,reason=xdf_match_status(identity,str(p),parsed.title)
    result['definition']={'filename':p.name,'status':match,'reason':reason,
                          'tables_total':parsed.table_count,
                          'constants_total':parsed.constant_count,
                          'parse_coverage_percent':round(parsed.coverage*100,2),
                          'rejected_reasons':dict(parsed.excluded)}
    result['recognized_named_maps']=(len(parsed.maps) if match!='rejected' else 0)
    result['unsupported_definitions']=sum(parsed.excluded.values())
    result['read_only_nonaffine']=sum(bool(m.equation) for m in parsed.maps)
    result['imported_names']=[{'name':m.name,'offset':f'0x{m.offset:X}',
                              'category':m.kind,'rows':m.rows,'cols':m.cols}
                              for m in parsed.maps[:50]] if match!='rejected' else []
    result['next_action']=('Falsche XDF: Nicht koppeln.' if match=='rejected' else
                           'Adressen, Achsen und ausgewählte physikalische Werte gegen unabhängige Referenz prüfen.')
    return result


def main(argv: list[str] | None = None) -> int:
    ap=argparse.ArgumentParser(description='Belegbare Kennfelderkennung prüfen – ohne ECU-Daten zu ändern')
    ap.add_argument('binary',help='BIN-/ORI-Datei')
    ap.add_argument('--xdf',help='XDF-Datei; wird nicht automatisch als passend angenommen')
    ap.add_argument('--definitions-dir',action='append',default=[],help='lokal nach XDF suchen')
    ap.add_argument('--json',help='Diagnosebericht als JSON speichern')
    args=ap.parse_args(argv)
    report=diagnose(BinaryImage.from_file(args.binary),xdf_path=args.xdf,
                    directories=args.definitions_dir)
    text=json.dumps(report,indent=2,ensure_ascii=False)
    if args.json:Path(args.json).write_text(text+'\n',encoding='utf8')
    print(text)
    return 3 if report.get('definition',{} ) and report['definition']['status']=='rejected' else 0

if __name__=='__main__':
    raise SystemExit(main())
