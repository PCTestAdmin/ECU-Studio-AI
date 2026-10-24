"""Local, searchable project metadata index; projects remain portable JSON files.

The index is a cache: everything except the user's tags and comments is read
from the project files and can be rebuilt. Listing and searching never open a BIN.

Compatibility: the ``projects`` table and ``user_version`` 1 are unchanged, so
older versions keep opening and writing the same database. Newer metadata lives
in additional tables (``project_meta``, ``annotations``); rows indexed by an
older version simply have no metadata until they are indexed again.
"""
from __future__ import annotations
import bisect
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from .model import load_project, read_project_snapshots

META = ('family', 'hardware', 'software', 'definition_sources', 'app_version', 'created',
        'verified', 'unverified', 'changed_maps', 'versions')
DETECTED_SOURCES = ('heuristic', 'reference-shape', 'transfer-proposed', 'ml-proposed', 'tcu-pair-heuristic')


class ProjectStore:
    SCHEMA=1
    def __init__(self,path=None):
        self.path=Path(path) if path else Path.home()/'.ecu_studio_ai'/'projects.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            version=c.execute('PRAGMA user_version').fetchone()[0]
            if version>self.SCHEMA:
                raise ValueError('Projektdatenbank stammt aus einer neueren Version')
            if version==0:
                c.execute('CREATE TABLE IF NOT EXISTS projects(path TEXT PRIMARY KEY, name TEXT NOT NULL, '
                          'original_sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, maps INTEGER NOT NULL, '
                          'notes TEXT NOT NULL, search_text TEXT NOT NULL, modified REAL NOT NULL)')
                c.execute('CREATE INDEX IF NOT EXISTS project_hash ON projects(original_sha256)')
                c.execute('CREATE INDEX IF NOT EXISTS project_modified ON projects(modified DESC)')
                c.execute('PRAGMA user_version=1')
            # Additive tables: invisible to older versions, which never read them.
            c.execute("CREATE TABLE IF NOT EXISTS project_meta(path TEXT PRIMARY KEY, family TEXT NOT NULL, "
                      "hardware TEXT NOT NULL, software TEXT NOT NULL, definition_sources TEXT NOT NULL, "
                      "app_version TEXT NOT NULL, created REAL NOT NULL, verified INTEGER NOT NULL, "
                      "unverified INTEGER NOT NULL, changed_maps INTEGER NOT NULL, versions INTEGER NOT NULL)")
            c.execute('CREATE INDEX IF NOT EXISTS project_meta_family ON project_meta(family)')
            c.execute('CREATE TABLE IF NOT EXISTS annotations(path TEXT PRIMARY KEY, tags TEXT NOT NULL, '
                      'comment TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS map_packs(path TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, '
                      'family TEXT NOT NULL, hardware TEXT NOT NULL, software TEXT NOT NULL, maps INTEGER NOT NULL)')
            c.execute('CREATE INDEX IF NOT EXISTS pack_hash ON map_packs(source_sha256)')

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=10)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def index(self,path):
        from ecu_studio import __version__
        from .identification import identify
        p=Path(path).resolve()
        image,maps,_,notes=load_project(str(p))
        versions=len(read_project_snapshots(str(p),image))
        ident=identify(image)
        patches=sorted(image._patches)
        changed=sum(1 for m in maps if (k:=bisect.bisect_left(patches,m.offset))<len(patches)
                    and patches[k]<m.offset+m.length)
        verified=sum(1 for m in maps if m.verified)
        search=' '.join((p.stem,notes,ident.family or '',*ident.hardware,*ident.software,
                         *(f'{m.name} {m.kind} {m.folder}' for m in maps))).casefold()
        modified=p.stat().st_mtime
        meta={'family':ident.family or (', '.join(ident.ambiguous) if ident.ambiguous else ''),
              'hardware':', '.join(ident.hardware),'software':', '.join(ident.software),
              'definition_sources':', '.join(sorted({m.source for m in maps if m.source not in DETECTED_SOURCES})),
              'app_version':__version__,'created':modified,'verified':verified,'unverified':len(maps)-verified,
              'changed_maps':changed,'versions':versions}
        self._upsert((str(p),p.stem,image.digest,image.size,len(maps),notes,search,modified),meta)

    def _upsert(self,row:tuple,meta:dict):
        """One project row (the layout older versions write) plus its metadata; ``created`` keeps its first value."""
        updates=', '.join(f'{k}=excluded.{k}' for k in META if k!='created')
        with self.connect() as c:
            c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                      'name=excluded.name, original_sha256=excluded.original_sha256, bytes=excluded.bytes, '
                      'maps=excluded.maps, notes=excluded.notes, search_text=excluded.search_text, modified=excluded.modified',
                      row)
            c.execute(f'INSERT INTO project_meta(path,{",".join(META)}) VALUES({",".join("?"*(len(META)+1))}) '
                      f'ON CONFLICT(path) DO UPDATE SET {updates}',(row[0],*(meta[k] for k in META)))

    def annotate(self,path,tags:list[str],comment:str=''):
        clean=sorted({t.strip() for t in tags if t.strip()})
        if any(',' in t or len(t)>40 for t in clean) or len(clean)>30 or len(comment)>10_000:
            raise ValueError('Tags: höchstens 30, je bis 40 Zeichen ohne Komma; Kommentar bis 10 000 Zeichen')
        with self.connect() as c:
            c.execute('INSERT INTO annotations VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET tags=excluded.tags, '
                      'comment=excluded.comment',(str(Path(path).resolve()),','.join(clean),comment))

    def families(self) -> list[str]:
        with self.connect() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT family FROM project_meta WHERE family!='' ORDER BY family")]

    def index_pack(self, path):
        import json
        from .map_pack import read_pack
        pack = read_pack(path)
        ident = pack.document.get('identity', {'family': '', 'hardware': [], 'software': []})
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO map_packs VALUES(?,?,?,?,?,?)',
                      (str(Path(path).resolve()), pack.sha256, ident['family'], json.dumps(ident['hardware']),
                       json.dumps(ident['software']), len(pack.document['maps'])))

    def suggestions(self, image):
        """Local index lookup only; suggestions never load or apply definitions."""
        from .identification import identify
        ident = identify(image)
        out = []
        with self.connect() as c:
            c.row_factory = sqlite3.Row
            for r in c.execute('SELECT path,source_sha256,family,hardware,software,maps FROM map_packs '
                               'WHERE source_sha256=? OR (family=? AND family!=\'\') LIMIT 50',
                               (image.digest, ident.family or '')):
                exact = r['source_sha256'] == image.digest
                out.append(dict(r, kind='pack', relation='exact' if exact else 'related'))
            for r in c.execute('SELECT p.path,p.original_sha256 AS source_sha256,COALESCE(m.family,\'\') AS family,p.maps '
                               'FROM projects p LEFT JOIN project_meta m ON m.path=p.path '
                               'WHERE p.original_sha256=? OR (m.family=? AND m.family!=\'\') LIMIT 50',
                               (image.digest, ident.family or '')):
                out.append(dict(r, kind='project', relation='exact' if r['source_sha256'] == image.digest else 'related'))
        return sorted(out, key=lambda r: (r['relation'] != 'exact', r['kind'], r['path']))

    def search(self,query='',limit=500,*,family='',tag=''):
        if not 1<=limit<=5000:
            raise ValueError('Ungültiges Suchlimit')
        escape=lambda s:s.replace('!','!!').replace('%','!%').replace('_','!_')
        text=lambda k:f"COALESCE(m.{k},'') AS {k}"
        number=lambda k:f'COALESCE(m.{k},0) AS {k}'
        sql=('SELECT p.path,p.name,p.original_sha256,p.bytes,p.maps,p.notes,p.modified,'
             + ','.join(text(k) for k in ('family','hardware','software','definition_sources','app_version')) + ','
             + ','.join(number(k) for k in ('created','verified','unverified','changed_maps','versions'))
             + ",COALESCE(a.tags,'') AS tags,COALESCE(a.comment,'') AS comment FROM projects p "
             "LEFT JOIN project_meta m ON m.path=p.path LEFT JOIN annotations a ON a.path=p.path "
             "WHERE (p.search_text LIKE ? ESCAPE '!' OR LOWER(COALESCE(a.comment,'')) LIKE ? ESCAPE '!' "
             "OR LOWER(COALESCE(a.tags,'')) LIKE ? ESCAPE '!')")
        pattern='%'+escape(query.casefold())+'%'
        args=[pattern,pattern,pattern]
        if family:
            sql+=' AND m.family=?';args.append(family)
        if tag:
            sql+=" AND (','||COALESCE(a.tags,'')||',') LIKE ? ESCAPE '!'";args.append('%,'+escape(tag.strip())+',%')
        sql+=' ORDER BY p.modified DESC LIMIT ?';args.append(limit)
        with self.connect() as c:
            c.row_factory=sqlite3.Row
            return [dict(row) for row in c.execute(sql,args)]
