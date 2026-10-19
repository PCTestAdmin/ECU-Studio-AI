"""Opt-in, SQLite-backed definition catalog with provenance and audit.

Does not store ECU binaries. A *verified* record includes only a small raw map
sample needed for cross-firmware matching, and is never created implicitly.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import math
import sqlite3
import time

from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.profiles import identify_profile

SCHEMA = 2


def default_catalog() -> Path:
    return Path.home() / '.ecu_studio_ai' / 'recognition-v1.sqlite3'


def _file_sha(path: str | Path) -> str:
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(2**20), b''):
            sha.update(data)
    return sha.hexdigest()


@dataclass(frozen=True)
class Reference:
    id: int
    firmware_sha: str
    family: str
    software: str
    name: str
    kind: str
    map_data: MapDefinition
    raw: list[list[int]]
    source_sha: str
    verified: bool


class DefinitionCatalog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_catalog()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA:
                raise ValueError('Erkennungsdatenbank stammt aus einer neueren Version')
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS firmware(
                   sha TEXT PRIMARY KEY, family TEXT NOT NULL,
                   software TEXT NOT NULL, byte_count INTEGER NOT NULL,
                   inserted_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS definition(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   firmware_sha TEXT NOT NULL REFERENCES firmware(sha),
                   map_key TEXT NOT NULL, name TEXT NOT NULL,
                   kind TEXT NOT NULL, origin TEXT NOT NULL,
                   source_sha TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
                   verified_at INTEGER, map_json TEXT NOT NULL,
                   sample_json TEXT, UNIQUE(firmware_sha,map_key,source_sha)
                );
                CREATE INDEX IF NOT EXISTS idx_firmware ON definition(firmware_sha);
                CREATE INDEX IF NOT EXISTS idx_kind ON definition(kind, verified);
            ''')
            conn.execute('''CREATE TABLE IF NOT EXISTS firmware_provenance(
                firmware_sha TEXT PRIMARY KEY REFERENCES firmware(sha),
                independence_group TEXT NOT NULL, hardware TEXT NOT NULL,
                source_url TEXT NOT NULL, license TEXT NOT NULL,
                reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL)''')
            conn.execute('CREATE INDEX IF NOT EXISTS provenance_group ON firmware_provenance(independence_group)')
            if version < 2:
                # Normalize newly introduced default metadata once. Reimporting
                # an unchanged v1 definition must not erase its human review.
                for record_id,data in conn.execute('SELECT id,map_json FROM definition').fetchall():
                    try:
                        normalized=json.dumps(MapDefinition(**json.loads(data)).asdict(),ensure_ascii=False,allow_nan=False)
                    except (ValueError,TypeError,KeyError):
                        continue
                    conn.execute('UPDATE definition SET map_json=? WHERE id=?',(normalized,record_id))
            conn.execute('PRAGMA user_version=2')
        # Public source registry is separate from verified, firmware-bound definitions.
        from .public_sources import install_public_index
        install_public_index(self)
        from .source_registry import install_discovery_sources
        install_discovery_sources(self)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=10)
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=10000')
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def key(m: MapDefinition) -> str:
        return f'{m.offset:X}:{m.rows}x{m.cols}:{m.dtype}:{m.endian}:{m.name}'

    def import_maps(self, image: BinaryImage, maps: list[MapDefinition], *,
                    origin: str, source_path: str | Path | None = None,
                    source_identity: str | None = None) -> dict:
        """Import as *unverified* until a separate explicit manual review.

        Synthetic, heuristic and transferred maps are not authoritative data.
        """
        if not origin.strip():
            raise ValueError('Herkunft muss dokumentiert werden')
        source_sha = (source_identity if source_identity else
                      (_file_sha(source_path) if source_path is not None else 'manual:' + image.digest))
        if source_identity and (len(source_identity)>160 or not source_identity.startswith('gitblob:')):
            raise ValueError('Ungültiger Quellidentitätsnachweis')
        profile = identify_profile(image)
        loaded = 0
        rejected = []
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO firmware VALUES(?,?,?,?,?)',
                      (image.digest, profile.family, profile.software_version or profile.calibration_id or '',
                       image.size, int(time.time())))
            for m in maps:
                try:
                    m.validate(image.size)
                    if m.source in ('heuristic', 'transfer-proposed', 'ml-proposed'):
                        raise ValueError('Keine bestätigte Quelldefinition')
                    payload = json.dumps(m.asdict(), ensure_ascii=False, allow_nan=False)
                    c.execute('''INSERT INTO definition
                        (firmware_sha,map_key,name,kind,origin,source_sha,map_json)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(firmware_sha,map_key,source_sha)
                        DO UPDATE SET
                        verified=CASE WHEN definition.map_json=excluded.map_json
                                      THEN definition.verified ELSE 0 END,
                        verified_at=CASE WHEN definition.map_json=excluded.map_json
                                         THEN definition.verified_at ELSE NULL END,
                        sample_json=CASE WHEN definition.map_json=excluded.map_json
                                         THEN definition.sample_json ELSE NULL END,
                        map_json=excluded.map_json, name=excluded.name,
                        kind=excluded.kind, origin=excluded.origin''',
                        (image.digest, self.key(m), m.name, m.kind, origin, source_sha, payload))
                    loaded += 1
                except (ValueError, KeyError, OverflowError) as e:
                    rejected.append((m.name, str(e)))
        return {'indexed': loaded, 'rejected': rejected, 'firmware_sha': image.digest,
                'source_sha': source_sha}

    def firmware_maps(self, image: BinaryImage) -> list[MapDefinition]:
        """Byte-identical lookup only. Metadata is source-bound, not auto-verified."""
        with self.connect() as c:
            rows = c.execute('SELECT map_json, verified FROM definition WHERE firmware_sha=?',
                             (image.digest,)).fetchall()
        maps = []
        for data, verified in rows:
            try:
                m = MapDefinition(**json.loads(data))
                m.validate(image.size)
                m.verified = bool(verified)
                maps.append(m)
            except (ValueError, TypeError, KeyError):
                continue
        return maps

    def verify(self, record_id: int, image: BinaryImage, *,
               confirm: bool = False) -> None:
        """Human review operation; never triggered from an importer or an ML result."""
        if not confirm:
            raise ValueError('Eine ausdrückliche fachliche Bestätigung ist erforderlich')
        if image.dirty_bytes:
            raise ValueError('Referenzprüfung benötigt die unveränderte Originaldatei; MOD-Werte dürfen nicht dem ORI-Hash zugeordnet werden')
        with self.connect() as c:
            row = c.execute('SELECT firmware_sha,map_json FROM definition WHERE id=?',
                            (record_id,)).fetchone()
            if row is None or row[0] != image.digest:
                raise ValueError('Datensatz gehört nicht zu dieser byteidentischen Firmware')
            m = MapDefinition(**json.loads(row[1]))
            m.validate(image.size)
            if m.kind == 'Unbekannt' or not m.name.strip():
                raise ValueError('Kennfeld muss fachlich identifiziert sein')
            if m.rows * m.cols > 4096:
                raise ValueError('Maximal 4096 Werte pro Referenz (Speicherschutz)')
            raw = [[image.raw_value(m, y, x) for x in range(m.cols)]
                   for y in range(m.rows)]
            c.execute('UPDATE definition SET verified=1,verified_at=?,sample_json=? WHERE id=?',
                      (int(time.time()), json.dumps(raw), record_id))

    def records(self, *, firmware_sha: str | None = None) -> list[dict]:
        with self.connect() as c:
            q = '''SELECT d.id,d.firmware_sha,f.family,f.software,d.name,d.kind,
                   d.origin,d.source_sha,d.verified,d.map_json,d.sample_json
                   FROM definition d JOIN firmware f ON d.firmware_sha=f.sha'''
            rows = c.execute(q + (' WHERE d.firmware_sha=?' if firmware_sha else '') + ' ORDER BY d.id',
                             (firmware_sha,) if firmware_sha else ()).fetchall()
        keys = ('id','firmware_sha','family','software','name','kind','origin',
                'source_sha','verified','map_json','sample_json')
        return [dict(zip(keys, row)) for row in rows]

    def review_training_provenance(self, payload):
        """Explicit human provenance, separate from map verification and public hints."""
        required=('firmware_sha','independence_group','hardware','source_url','license','reviewer','reviewed_at')
        if not isinstance(payload,dict) or any(not isinstance(payload.get(k),str) or not payload[k].strip() for k in required):
            raise ValueError('Hash, unabhängige Gruppe, Hardware, Quelle, Lizenz, Prüfer und Prüfdatum erforderlich')
        if payload.get('rights_confirmed') is not True or payload.get('independence_reviewed') is not True:
            raise ValueError('Nutzungsrechte und Unabhängigkeit müssen fachlich bestätigt sein')
        with self.connect() as c:
            c.execute('INSERT INTO firmware_provenance VALUES(?,?,?,?,?,?,?) ON CONFLICT(firmware_sha) DO UPDATE SET '
                      'independence_group=excluded.independence_group,hardware=excluded.hardware,source_url=excluded.source_url,'
                      'license=excluded.license,reviewer=excluded.reviewer,reviewed_at=excluded.reviewed_at',
                      tuple(payload[k].strip() for k in required))

    def training_provenance(self):
        with self.connect() as c:
            rows=c.execute('SELECT firmware_sha,independence_group,hardware,source_url,license,reviewer,reviewed_at FROM firmware_provenance').fetchall()
        keys=('firmware_sha','independence_group','hardware','source_url','license','reviewer','reviewed_at')
        return {row[0]:dict(zip(keys,row)) for row in rows}

    def verified_references(self, *, family: str | None = None,
                            except_firmware: str | None = None) -> list[Reference]:
        refs = []
        for row in self.records():
            if not row['verified'] or not row['sample_json'] or (family and row['family'] != family):
                continue
            if except_firmware and row['firmware_sha'] == except_firmware:
                continue
            try:
                m = MapDefinition(**json.loads(row['map_json']))
                vals = json.loads(row['sample_json'])
                if m.rows * m.cols > 4096 or len(vals) != m.rows or any(len(v) != m.cols for v in vals):
                    continue
                refs.append(Reference(row['id'],row['firmware_sha'],row['family'],row['software'],
                                      row['name'],row['kind'],m,vals,row['source_sha'],True))
            except (ValueError, TypeError, KeyError):
                continue
        return refs

    def stats(self) -> dict:
        with self.connect() as c:
            f = c.execute('SELECT COUNT(*) FROM firmware').fetchone()[0]
            d, v = c.execute('SELECT COUNT(*),COALESCE(SUM(verified),0) FROM definition').fetchone()
            families = c.execute('SELECT family,COUNT(*) FROM firmware GROUP BY family ORDER BY family').fetchall()
        result={'firmwares': f, 'definitions': d, 'verified_maps': v, 'families': dict(families)}
        from .public_sources import public_stats
        result.update(public_stats(self))
        return result
