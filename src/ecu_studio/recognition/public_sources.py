"""Curated, source-attributed reference index, separate from *verified* map database.

The data contains XDF-derived *preview* metadata; it is NOT automatically
mapped to an arbitrary BIN or used as verified ML labels.
"""
from __future__ import annotations
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from .catalog import DefinitionCatalog
from ecu_studio.core.profiles import identify_profile, xdf_match_status
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.xdf import read_xdf, _affine
from ecu_studio.core.intelligence import label_from_metadata

DATA = Path(__file__).parent / 'data'


def sources() -> list[dict]:
    return json.loads((DATA / 'public_sources.json').read_text(encoding='utf-8'))


def install_public_index(db: DefinitionCatalog) -> dict:
    """Idempotent seed; source metadata never sets `verified` to true."""
    items = sources()
    with db.connect() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS public_source(
              id TEXT PRIMARY KEY, family TEXT NOT NULL, software TEXT NOT NULL,
              size INTEGER NOT NULL, variant TEXT NOT NULL, repository TEXT NOT NULL,
              path TEXT NOT NULL, git_blob TEXT NOT NULL, license TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS public_map_hint(
              source_id TEXT NOT NULL REFERENCES public_source(id),
              name TEXT NOT NULL, relative_offset INTEGER NOT NULL,
              rows INTEGER NOT NULL, cols INTEGER NOT NULL, bits INTEGER NOT NULL,
              flags INTEGER NOT NULL, equation TEXT NOT NULL, unit TEXT NOT NULL,
              PRIMARY KEY(source_id,name,relative_offset)
            );
        ''')
        for item in items:
            path = item.get('path') or ('definitions/' + item['filename'])
            c.execute('''INSERT OR IGNORE INTO public_source
              (id,family,software,size,variant,repository,path,git_blob,license)
              VALUES (?,?,?,?,?,?,?,?,?)''',
              (item['id'],item['family'],item['software'],item['size'],item['variant'],
               item['repository'],path,item['git_blob'],item['license']))
        for filename in ('ms43_430069_3d_sample.tsv','ms41_ms42_samples.tsv'):
            with (DATA / filename).open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.strip() or line.startswith('#'):continue
                    parts=line.strip().split(';')
                    if len(parts)==8:
                        source_id='ms43-430069-512'
                        name,address,rows,cols,bits,flags,equation,unit=parts
                    else:
                        source_id,name,address,rows,cols,bits,flags,equation,unit=parts
                    _affine(equation)
                    c.execute('''INSERT OR IGNORE INTO public_map_hint VALUES (?,?,?,?,?,?,?,?,?)''',
                        (source_id,name,int(address,16),int(rows),int(cols),
                         int(bits),int(flags),equation,unit))
    return public_stats(db)


def public_stats(db: DefinitionCatalog) -> dict:
    with db.connect() as c:
        n=c.execute('SELECT COUNT(*) FROM public_source').fetchone()[0]
        h=c.execute('SELECT COUNT(*) FROM public_map_hint').fetchone()[0]
        f=c.execute('SELECT COUNT(DISTINCT family) FROM public_source').fetchone()[0]
    return {'public_sources':n,'public_map_hints':h,'public_families':f}


def source_rows(db: DefinitionCatalog) -> list[dict]:
    with db.connect() as c:
        rows=c.execute('SELECT id,family,software,size,variant,repository,path,git_blob,license FROM public_source ORDER BY family,software,size').fetchall()
    fields=('id','family','software','size','variant','repository','path','git_blob','license')
    return [dict(zip(fields,r)) for r in rows]


def map_hints(db: DefinitionCatalog, source_id='ms43-430069-512') -> list[dict]:
    with db.connect() as c:
        rows=c.execute('''SELECT name,relative_offset,rows,cols,bits,flags,equation,unit
                          FROM public_map_hint WHERE source_id=? ORDER BY relative_offset''',(source_id,)).fetchall()
    fields=('name','relative_offset','rows','cols','bits','flags','equation','unit')
    return [dict(zip(fields,r)) for r in rows]


def candidates(db: DefinitionCatalog, image: BinaryImage) -> list[dict]:
    """Return exact family/software/size hints only; NOT proof of binary match."""
    p=identify_profile(image)
    software=p.software_version or p.calibration_id or ''
    return [r for r in source_rows(db)
            if p.identified and r['family']==p.family
            and r['size']==image.size and r['software'].upper()==software.upper()]


def fetch_pinned_source(item: dict, cache_dir: str|Path | None = None) -> Path:
    """Only curated source records; Git blob hash is pinned. Opt-in network use."""
    path=item['path']; repo=item['repository']
    if not (re.fullmatch(r'[\w.-]+/[\w.-]+',repo) and
            re.fullmatch(r'[\w./-]+\.xdf',path,re.I) and '..' not in Path(path).parts and
            re.fullmatch(r'[0-9a-f]{40}',item['git_blob'])):
        raise ValueError('Nicht autorisierte Quelle oder Hash')
    url=f'https://raw.githubusercontent.com/{repo}/main/{path}'
    req=urllib.request.Request(url,headers={'User-Agent':'ECU-Studio-AI-public-definitions/1.4'})
    with urllib.request.urlopen(req,timeout=30) as response:
        payload=response.read(16*1024*1024+1)
    if not (100<len(payload)<=16*1024*1024):
        raise ValueError('XDF-Größe außerhalb der erlaubten Grenzen')
    actual=hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()
    if actual!=item['git_blob']:
        raise ValueError('Quelldatei weicht von der geprüften Git-Version ab; nicht übernehmen')
    cache=Path(cache_dir or (Path.home()/'.ecu_studio_ai'/'external_definitions'))
    cache.mkdir(parents=True,exist_ok=True)
    target=cache/Path(path).name
    if target.exists() and target.read_bytes()==payload:return target
    temp=target.with_suffix('.xdf.tmp')
    temp.write_bytes(payload)
    temp.replace(target)
    return target


def fetch_and_index(db: DefinitionCatalog, image: BinaryImage, item_id: str,
                    *, cache_dir: str|Path|None=None, acknowledged_variant=False) -> dict:
    """Explicit only. Auto-reject known mismatch or unidentifiable ECU.

    Even if matched by family/software, third-party source remains unverified.
    """
    if image.dirty_bytes:raise ValueError('Nur unveränderte Originaldateien')
    by_id={x['id']:x for x in source_rows(db)}
    if item_id not in by_id:raise ValueError('Unbekannte Definitionsquelle')
    item=by_id[item_id]
    if item not in candidates(db,image):
        raise ValueError('ECU-Familie, Softwarestand oder Dateigröße passen nicht zur Quelle')
    if not acknowledged_variant:
        raise ValueError('Firmware-/Patchvarianten und Lizenz müssen explizit bestätigt werden')
    path=fetch_pinned_source(item,cache_dir)
    status,message=xdf_match_status(identify_profile(image),str(path))
    if status=='rejected':raise ValueError(message)
    result=read_xdf(str(path),image)
    output=db.import_maps(image,result.maps,origin='Öffentliche XDF: '+item['repository']+'/'+item['path']+' (UNGEPRÜFT)',source_path=path)
    return {'source_id':item_id,'downloaded_xdf':str(path),'imported':output['indexed'],
            'all_definitions':result.table_count+result.constant_count,
            'import_coverage':round(result.coverage,4),'excluded':dict(result.excluded),
            'compatibility':status,'notice':message,'verified':0}


def attach_ms43_preview(db: DefinitionCatalog, image: BinaryImage, *,acknowledged_variant=False) -> dict:
    """81 incomplete hints into an exact-firmware index after user acknowledgement.

    No axes provided: these are NOT a substitute for importing the actual XDF.
    """
    cands=candidates(db,image)
    if not any(s['id']=='ms43-430069-512' for s in cands):
        raise ValueError('Nur für erkannte MS43 430069 512 KiB')
    if not acknowledged_variant:
        raise ValueError('Extended-Load-Patchstand muss explizit bestätigt werden')
    if image.dirty_bytes:raise ValueError('Nur unveränderte Originaldateien')
    maps=[];bad=[]
    for hint in map_hints(db):
        try:
            fac,bias=_affine(hint['equation'])
            flags=hint['flags']
            m=MapDefinition(name=hint['name'],offset=0x70000+hint['relative_offset'],
                rows=hint['rows'],cols=hint['cols'],dtype=('s' if flags&1 else 'u')+str(hint['bits']),
                endian='little' if flags&2 else 'big',factor=fac,bias=bias,unit=hint['unit'],
                source='xdf-preview',kind='Unbekannt',
                ecu_address=hint['relative_offset'],notes='Ausschnitt öffentlicher MS4X-XDF v1.14; KEINE Achsen; kein unabhängiger Layout-/Patchabgleich',
                axes_info='Achsen NICHT importiert; Indexansicht',
                label_origin='Quellmetadaten, nicht verifiziert',verified=False)
            m.validate(image.size)
            # Probe actual raw values to catch out-of-range storage access.
            image.raw_value(m,0,0)
            image.raw_value(m,m.rows-1,m.cols-1)
            maps.append(m)
        except (ValueError,IndexError) as exc:bad.append((hint['name'],str(exc)))
    out=db.import_maps(image,maps,origin='MS4X GPL-3.0 MS43 430069 XDF Preview OHNE Achsen, ungeprüft',
                       source_identity='gitblob:9b76a7f9887cd4bc2fafe50c9313f01e7d9ca4e0:partial-z-metadata')
    out['rejected_preview']=bad
    out['important']='Nur Quellhinweise! Vollständige XDF für Achsen, Strides und korrekte Patchvariante importieren.'
    return out
