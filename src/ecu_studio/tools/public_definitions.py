"""Prefilled public source index and opt-in, revision-pinned definition import."""
import argparse
import json
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.recognition.catalog import DefinitionCatalog
from ecu_studio.recognition.public_sources import (
    source_rows, map_hints, public_stats, candidates, fetch_and_index,attach_ms43_preview)

def execute(args):
    db=DefinitionCatalog(args.db)
    if args.action=='stats':return {**db.stats(), 'public_sources_detail':source_rows(db)}
    if args.action=='list':
        if args.bin:return {'candidates':candidates(db,BinaryImage.from_file(args.bin)),
                            'important':'Software- und Größenabgleich ist KEIN Patch-/Kalibrierfreigabenachweis.'}
        return {'sources':source_rows(db),'hints_ms43':len(map_hints(db))}
    if args.action in ('fetch-index','preview-ms43'):
        if not args.bin:raise ValueError('--bin fehlt')
        image=BinaryImage.from_file(args.bin)
        if args.action=='preview-ms43':
            return attach_ms43_preview(db,image,acknowledged_variant=args.acknowledge_variant)
        if not args.source_id:raise ValueError('--source-id fehlt')
        return fetch_and_index(db,image,args.source_id,
                cache_dir=args.cache_dir,acknowledged_variant=args.acknowledge_variant)
    raise ValueError(args.action)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['stats','list','preview-ms43','fetch-index'])
    p.add_argument('--db');p.add_argument('--bin');p.add_argument('--source-id')
    p.add_argument('--cache-dir');p.add_argument('--acknowledge-variant',action='store_true')
    p.add_argument('--json')
    args=p.parse_args()
    try: data=execute(args)
    except (ValueError,OSError) as e:p.exit(2,'Fehler: '+str(e)+'\n')
    serialized=json.dumps(data,ensure_ascii=False,indent=2)
    if args.json:Path(args.json).write_text(serialized,encoding='utf8')
    print(serialized)
if __name__=='__main__':main()
