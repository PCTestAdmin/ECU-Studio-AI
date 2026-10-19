"""Local, searchable project metadata index; projects remain portable JSON files."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from .model import load_project


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
        p=Path(path).resolve()
        image,maps,_,notes=load_project(str(p))
        search=' '.join((p.stem,notes,*(f'{m.name} {m.kind} {m.folder}' for m in maps))).casefold()
        with self.connect() as c:
            c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                      'name=excluded.name, original_sha256=excluded.original_sha256, bytes=excluded.bytes, '
                      'maps=excluded.maps, notes=excluded.notes, search_text=excluded.search_text, modified=excluded.modified',
                      (str(p),p.stem,image.digest,image.size,len(maps),notes,search,p.stat().st_mtime))

    def search(self,query='',limit=500):
        if not 1<=limit<=5000:
            raise ValueError('Ungültiges Suchlimit')
        pattern='%'+query.casefold().replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        with self.connect() as c:
            c.row_factory=sqlite3.Row
            return [dict(row) for row in c.execute(
                "SELECT path,name,original_sha256,bytes,maps,notes,modified FROM projects WHERE search_text LIKE ? ESCAPE '!' ORDER BY modified DESC LIMIT ?",
                (pattern,limit))]
