"""v1.7 auditable offline workstation workflows (headless, read-only)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.definitions import import_definitions
from ecu_studio.core.compare_maps import compare_images, export_map_comparison_csv, export_cell_comparison_csv
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.axis_inference import suggest_adjacent_axes
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.identity_registry import identify_vehicle, import_identity_manifest,identity_stats
from ecu_studio.recognition.source_registry import discovery_sources, BRANDS


def build_parser():
    parser=argparse.ArgumentParser(description='ECU Studio AI v1.7 · Offline-Fingerprints, Kennfelder, ORI/MOD und Datenabdeckung')
    parser.add_argument('--db',default=None,help='Optionale SQLite-Katalogdatei')
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('identify',help='SHA-256/Familienidentifikation ohne Fahrzeugraten')
    a.add_argument('bin')
    a=sub.add_parser('import-identities',help='Manuell bestätigtes, hash-belegtes JSON-Manifest')
    a.add_argument('manifest')
    a=sub.add_parser('compare',help='ORI/MOD binär und kennfeldbezogen vergleichen')
    a.add_argument('original');a.add_argument('modified')
    a.add_argument('--maps',help='Aus exakt passender BIN importierte Kennfeld-CSV')
    a.add_argument('--csv',help='Kennfeld-Zusammenfassung als CSV')
    a.add_argument('--cells-csv',help='Geänderte Zellen als CSV (bis 20000)')
    a=sub.add_parser('scan',help='Ungeprüfte Struktur- und Achsenkandidaten')
    a.add_argument('bin');a.add_argument('--axes',action='store_true')
    a=sub.add_parser('coverage',help='Quelle vs. tatsächlich verifizierte Trainingsdaten')
    a.add_argument('--brand',choices=BRANDS)
    for obj in (sub.choices['identify'],sub.choices['import-identities'],sub.choices['compare'],
                sub.choices['scan'],sub.choices['coverage']):
        obj.add_argument('--out',help='JSON-Ergebnis in Datei speichern')
    return parser


def execute(args):
    db=DefinitionCatalog(args.db)
    if args.command=='identify':
        image=BinaryImage.from_file(args.bin)
        info=identify_vehicle(image,db).asdict()
        info.update({'firmware_sha256':image.digest,'byte_count':image.size})
        return info
    if args.command=='import-identities':
        return import_identity_manifest(db,args.manifest,require_files=True)
    if args.command=='compare':
        a=BinaryImage.from_file(args.original);b=BinaryImage.from_file(args.modified)
        maps=import_definitions(args.maps,a.size) if args.maps else []
        report=compare_images(a,b,maps)
        if args.csv:export_map_comparison_csv(report,args.csv)
        if args.cells_csv:export_cell_comparison_csv(report,args.cells_csv)
        return report
    if args.command=='scan':
        image=BinaryImage.from_file(args.bin)
        maps=scan_calibration_candidates(image)
        records=[]
        for m in maps:
            row={'offset':m.offset,'rows':m.rows,'cols':m.cols,'dtype':m.dtype,
                 'endian':m.endian,'score_not_probability':m.confidence,
                 'name':'Unbekannt','verified':False}
            if args.axes:
                row['adjacent_axis_hints']=[x.__dict__ for x in suggest_adjacent_axes(image,m)]
            records.append(row)
        return {'sha256':image.digest,'count':len(records),
                'note':'Strukturerkennung, keine sichere Funktionsklassifizierung',
                'candidates':records}
    if args.command=='coverage':
        sources=discovery_sources(db,args.brand)
        known=db.stats()
        # Brand-specific training counts cannot be derived reliably from ECU family:
        # one family is shared between multiple car manufacturers.
        return {'brand':args.brand or 'alle',
                'source_records':len(sources),'source_records_by_brand':
                    {brand:sum(x['brand']==brand for x in sources) for brand in BRANDS
                     if args.brand is None or args.brand==brand},
                'indexed_firmwares':known['firmwares'],
                'verified_firmware_maps_across_all_brands':known['verified_maps'],
                'reviewed_hash_identities':identity_stats(db),
                'source_only_not_training':sum(x['training_approved']==0 for x in sources),
                'note':'Eine Quellenreferenz ist KEIN geprüftes BIN/XDF-Trainingspaar. '
                       'ECU-Familie belegt keine Fahrzeugmarke.'}
    raise AssertionError('unreachable')


def main(argv=None):
    args=build_parser().parse_args(argv)
    result=execute(args)
    if args.out:
        Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
