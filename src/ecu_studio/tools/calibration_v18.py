"""Offline v1.8 map grouping and checksum/plausibility audit.

Examples:
    python -m ecu_studio.tools.calibration_v18 audit firmware.bin --maps definitions.csv --out report.json
    python -m ecu_studio.tools.calibration_v18 audit firmware.bin --profile checksum_profile.json
    python -m ecu_studio.tools.calibration_v18 groups firmware.bin definitions.csv --csv grouped.csv
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ..core.model import BinaryImage
from ..core.definitions import import_definitions
from ..core.checksum_audit import load_checksum_profile,audit_export,write_audit_json
from ..core.map_groups import group_maps,export_groups_csv


def main(argv=None):
    parser=argparse.ArgumentParser(description='ECU Studio v1.8 · Offlineprüfungen')
    sub=parser.add_subparsers(dest='action',required=True)
    audit=sub.add_parser('audit',help='Prüffelder und Kennfeldplausibilität bewerten')
    audit.add_argument('bin')
    audit.add_argument('--maps',help='CSV-Definitionen')
    audit.add_argument('--profile',help='Geprüftes, hashgebundenes Checksum-Profil (JSON)')
    audit.add_argument('--out',help='JSON-Bericht')
    audit.add_argument('--mod',help='Optional: modifizierte BIN identischer Größe')
    groups=sub.add_parser('groups',help='Gruppen/Ähnlichkeitscluster für Kennfelder')
    groups.add_argument('bin')
    groups.add_argument('maps',help='Definitions-CSV')
    groups.add_argument('--csv',help='Ausgabe CSV')
    args=parser.parse_args(argv)
    img=BinaryImage.from_file(args.bin)
    if args.action=='groups':
        maps=import_definitions(args.maps,img.size)
        found=group_maps(maps)
        if args.csv:export_groups_csv(args.csv,found,maps)
        result={'group_count':len(found),'map_count':len(maps),
                'groups':[{'title':g.title,'basis':g.basis,'offsets':[maps[i].offset for i in g.indices],
                           'verified_members':g.verified_members} for g in found]}
    else:
        maps=import_definitions(args.maps,img.size) if args.maps else []
        if args.mod:
            payload=Path(args.mod).read_bytes()
            if len(payload)!=img.size:parser.error('ORI und MOD haben unterschiedliche Größe')
            # Apply only differences, without writing into original bytes on disk.
            for i,(a,b) in enumerate(zip(img.original,payload)):
                if a!=b:img._patches[i]=b
            img.revision+=1
        profile=load_checksum_profile(args.profile,img) if args.profile else None
        result=audit_export(img,maps,profile)
        if args.out:write_audit_json(args.out,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
