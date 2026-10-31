"""Local, searchable project metadata index; projects remain portable JSON files.

The index is a cache: everything except the user's tags and comments is read
from the project files and can be rebuilt. Listing and searching never open a BIN.

Compatibility: the ``projects`` table and ``user_version`` 1 are unchanged, so
older versions keep opening and writing the same database. Newer metadata lives
in additional tables (``project_meta``, ``annotations``); rows indexed by an
older version simply have no metadata until they are indexed again.

Hardware and software numbers are also kept one per row in ``identifiers``
(indexed), so opening a BIN finds projects and map packs with the same numbers
without scanning text. Rows written before that table existed are filled from
the stored metadata when the index is opened; no BIN is read for that.
"""
from __future__ import annotations
import bisect
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
from .model import load_project, read_project_snapshots

META = ('family', 'hardware', 'software', 'definition_sources', 'app_version', 'created',
        'verified', 'unverified', 'changed_maps', 'versions')
DETECTED_SOURCES = ('heuristic', 'reference-shape', 'transfer-proposed', 'ml-proposed', 'tcu-pair-heuristic')
# How a local project or map pack relates to an opened BIN, strongest first. Only "exact" is proof.
RELATIONS = {
    'exact': ('nachgewiesen', 'Identische Datei (SHA-256)'),
    'software+hardware': ('wahrscheinlich', 'Gleiche Hardware- und Softwarenummer – Kalibrierung kann trotzdem '
                                            'abweichen (z. B. geänderte Datei)'),
    'software': ('wahrscheinlich', 'Gleiche Softwarenummer – Hardware nicht bestätigt'),
    'hardware': ('mehrdeutig', 'Nur gleiche Hardwarenummer – anderer Softwarestand möglich'),
    'related': ('mehrdeutig', 'Nur gleiche Steuergerätefamilie – nur zum Vergleich'),
}
RANK = {name: i for i, name in enumerate(RELATIONS)}
MATCH_LIMIT = 200     # rows per hardware/software number
FAMILY_LIMIT = 50     # rows per family-only lookup (weakest relation, as before)
BATCH = 200           # projects per transaction in index_many


def _ids(values) -> list[str]:
    """Normalised identifier list from a list or a comma-separated text."""
    if isinstance(values, str):
        values = values.split(',')
    return sorted({str(v).strip().upper() for v in values if str(v).strip()})


@dataclass
class IndexResult:
    indexed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)     # (path, reason)
    cancelled: bool = False


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
            c.execute('CREATE INDEX IF NOT EXISTS pack_family ON map_packs(family)')
            c.execute('CREATE TABLE IF NOT EXISTS identifiers(path TEXT NOT NULL, kind TEXT NOT NULL, '
                      'value TEXT NOT NULL, PRIMARY KEY(path, kind, value))')
            c.execute('CREATE INDEX IF NOT EXISTS identifier_value ON identifiers(kind, value)')
            self._backfill(c)

    def _backfill(self, c):
        """Identifiers for rows indexed before the table existed (or by an older version), from stored metadata."""
        for path, hardware, software in c.execute(
                "SELECT path, hardware, software FROM project_meta WHERE (hardware!='' OR software!='') "
                "AND path NOT IN (SELECT path FROM identifiers)").fetchall():
            self._write_ids(c, path, hardware, software)
        for path, hardware, software in c.execute(
                'SELECT path, hardware, software FROM map_packs WHERE path NOT IN (SELECT path FROM identifiers)'
                ).fetchall():
            try:
                self._write_ids(c, path, json.loads(hardware), json.loads(software))
            except (TypeError, ValueError):
                continue

    @staticmethod
    def _write_ids(c, path, hardware, software):
        c.execute('DELETE FROM identifiers WHERE path=?', (path,))
        c.executemany('INSERT OR IGNORE INTO identifiers VALUES(?,?,?)',
                      [(path, 'hw', v) for v in _ids(hardware)] + [(path, 'sw', v) for v in _ids(software)])

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
        self._upsert(*self._record(path))

    def index_many(self, paths, progress=None, cancelled=None) -> IndexResult:
        """Index many project files: few transactions instead of one per file, per-file errors collected.

        ``progress(done, total)`` is called after each file; ``cancelled()`` returning True stops before the
        next file (everything indexed so far is kept).
        """
        paths, result, pending = list(paths), IndexResult(), []

        def flush():
            if pending:
                with self.connect() as c:
                    for row, meta in pending:
                        self._upsert(row, meta, c)
                result.indexed += len(pending)
                pending.clear()
        for done, path in enumerate(paths, 1):
            if cancelled is not None and cancelled():
                result.cancelled = True
                break
            try:
                pending.append(self._record(path))
            except Exception as exc:
                result.errors.append((str(path), str(exc)))
            if len(pending) >= BATCH:
                flush()
            if progress is not None:
                progress(done, len(paths))
        flush()
        return result

    def _record(self, path):
        """(projects row, metadata) of one project file; the expensive part of indexing (loads the project)."""
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
        return (str(p),p.stem,image.digest,image.size,len(maps),notes,search,modified),meta

    def _upsert(self,row:tuple,meta:dict,c=None):
        """One project row (the layout older versions write) plus its metadata; ``created`` keeps its first value."""
        if c is None:
            with self.connect() as c:
                return self._upsert(row,meta,c)
        updates=', '.join(f'{k}=excluded.{k}' for k in META if k!='created')
        c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                  'name=excluded.name, original_sha256=excluded.original_sha256, bytes=excluded.bytes, '
                  'maps=excluded.maps, notes=excluded.notes, search_text=excluded.search_text, modified=excluded.modified',
                  row)
        c.execute(f'INSERT INTO project_meta(path,{",".join(META)}) VALUES({",".join("?"*(len(META)+1))}) '
                  f'ON CONFLICT(path) DO UPDATE SET {updates}',(row[0],*(meta[k] for k in META)))
        self._write_ids(c,row[0],meta['hardware'],meta['software'])

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
            self._write_ids(c, str(Path(path).resolve()), ident['hardware'], ident['software'])

    def suggestions(self, image):
        """Local projects and map packs related to ``image``, strongest relation first (index lookup only).

        Never loads or applies a definition. Each row carries ``relation`` (see RELATIONS), ``level``
        (nachgewiesen / wahrscheinlich / mehrdeutig) and a readable ``evidence``. Only an identical SHA-256 is
        proof; equal hardware/software numbers do not exclude a modified or differently calibrated file.
        """
        from .identification import identify
        ident = identify(image)
        hardware, software = set(_ids(ident.hardware)), set(_ids(ident.software))
        family = ident.family or ''
        rows = {}
        with self.connect() as c:
            c.row_factory = sqlite3.Row
            pack_sql = 'SELECT path,source_sha256,family,hardware,software,maps FROM map_packs WHERE '
            project_sql = ("SELECT p.path,p.original_sha256 AS source_sha256,COALESCE(m.family,'') AS family,"
                           "COALESCE(m.hardware,'') AS hardware,COALESCE(m.software,'') AS software,p.maps "
                           'FROM projects p LEFT JOIN project_meta m ON m.path=p.path WHERE ')
            queries = [(pack_sql + 'source_sha256=?', (image.digest,)),
                       (project_sql + 'p.original_sha256=?', (image.digest,))]
            ids = [('hw', v) for v in hardware] + [('sw', v) for v in software]
            if ids:
                found = {r[0] for kind, value in ids for r in c.execute(
                    'SELECT path FROM identifiers WHERE kind=? AND value=? LIMIT ?', (kind, value, MATCH_LIMIT))}
                found = sorted(found)
                for i in range(0, len(found), 500):
                    chunk = found[i:i + 500]
                    marks = ','.join('?' * len(chunk))
                    queries += [(pack_sql + f'path IN ({marks})', chunk), (project_sql + f'p.path IN ({marks})', chunk)]
            if family:
                queries += [(pack_sql + 'family=? LIMIT ?', (family, FAMILY_LIMIT)),
                            (project_sql + 'm.family=? LIMIT ?', (family, FAMILY_LIMIT))]
            for sql, args in queries:
                kind = 'pack' if sql.startswith(pack_sql) else 'project'
                for r in c.execute(sql, args):
                    row = dict(r, kind=kind)
                    if kind == 'pack':
                        try:
                            own_hw, own_sw = set(_ids(json.loads(row['hardware']))), set(_ids(json.loads(row['software'])))
                        except (TypeError, ValueError):
                            own_hw, own_sw = set(), set()
                    else:
                        own_hw, own_sw = set(_ids(row['hardware'])), set(_ids(row['software']))
                    # Relation from the row's current metadata (an older version may have re-indexed it).
                    if row['source_sha256'] == image.digest:
                        relation = 'exact'
                    elif software & own_sw:
                        relation = 'software+hardware' if hardware & own_hw else 'software'
                    elif hardware & own_hw:
                        relation = 'hardware'
                    elif family and row['family'] == family:
                        relation = 'related'
                    else:
                        continue
                    shared = sorted((software & own_sw) | (hardware & own_hw))
                    level, evidence = RELATIONS[relation]
                    row.update(relation=relation, level=level,
                               evidence=evidence + (f' ({", ".join(shared)})' if shared else
                                                    f' ({family})' if relation == 'related' else ''))
                    key = (kind, row['path'])
                    if key not in rows or RANK[relation] < RANK[rows[key]['relation']]:
                        rows[key] = row
        return sorted(rows.values(), key=lambda r: (RANK[r['relation']], r['kind'], r['path']))

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
