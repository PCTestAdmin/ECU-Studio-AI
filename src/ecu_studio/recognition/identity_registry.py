"""Exact-hash ECU/vehicle identification records, never a brand guess from binary noise.

A reviewer attests provenance for an *identical* firmware hash. Hash matching proves
binary identity, not that a human supplied a truthful VIN/model. No VIN is stored.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.profiles import identify_profile

HEX_SHA = re.compile(r'^[0-9a-f]{64}$')
FIELDS = ('firmware_sha256', 'byte_count', 'brand', 'model', 'engine', 'ecu',
          'family', 'software', 'source', 'reviewer')


@dataclass(frozen=True)
class IdentityResult:
    level: str
    brand: str = ''
    model: str = ''
    engine: str = ''
    ecu: str = ''
    family: str = 'Unbekannt'
    software: str = ''
    evidence: tuple[str, ...] = ()
    notes: str = ''

    def asdict(self) -> dict:
        return asdict(self)


def install_identity_schema(db):
    with db.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS firmware_identity(
          firmware_sha256 TEXT PRIMARY KEY, byte_count INTEGER NOT NULL,
          brand TEXT NOT NULL, model TEXT NOT NULL, engine TEXT NOT NULL,
          ecu TEXT NOT NULL, family TEXT NOT NULL, software TEXT NOT NULL,
          source TEXT NOT NULL, reviewer TEXT NOT NULL,
          reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK(length(firmware_sha256)=64), CHECK(byte_count>0))''')


def import_identity_manifest(db, path: str | Path, *, require_files: bool = True) -> dict:
    """Import manually reviewed identities with optional binary proof on disk.

    No unreviewed or auto-generated rows become definitive. Read only, no firmware
    bytes persist. Atomic batch: any invalid record rejects the entire manifest.
    """
    install_identity_schema(db)
    p = Path(path)
    manifest = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('format') != 1 or not isinstance(manifest.get('records'), list):
        raise ValueError('Erwartet Identity-Manifest format=1 mit records-Liste')
    records = manifest['records']
    if len(records) > 50000:
        raise ValueError('Zu viele Identitätsdatensätze')
    clean=[]
    seen=set()
    for n, item in enumerate(records, 1):
        if not isinstance(item, dict) or any(field not in item for field in FIELDS):
            raise ValueError(f'Datensatz {n}: Pflichtfelder fehlen')
        sha=item['firmware_sha256']
        if not isinstance(sha,str) or not HEX_SHA.fullmatch(sha) or sha in seen:
            raise ValueError(f'Datensatz {n}: ungültiger/duplizierter SHA-256')
        seen.add(sha)
        size=item['byte_count']
        if type(size) is not int or not 0 < size <= 128*1024*1024:
            raise ValueError(f'Datensatz {n}: ungültige Dateigröße')
        values=[]
        for field in FIELDS[2:]:
            value=item[field]
            if not isinstance(value,str) or len(value)>300 or ('\x00' in value):
                raise ValueError(f'Datensatz {n}: ungültig {field}')
            values.append(value.strip())
        if not values[-1] or not values[-2] or not values[0] or not values[3]:
            raise ValueError(f'Datensatz {n}: Marke, ECU, Quelle und Prüfer müssen angegeben sein')
        if item.get('reviewed') is not True:
            raise ValueError(f'Datensatz {n}: nur explizit bestätigte Metadaten')
        source_file = item.get('firmware_file')
        if require_files and not source_file:
            raise ValueError(f'Datensatz {n}: lokale BIN als Hash-Beleg erforderlich')
        if source_file:
            f=(p.parent/source_file).resolve()
            if not f.is_file() or f.stat().st_size != size:
                raise ValueError(f'Datensatz {n}: BIN fehlt oder Größe abweichend')
            h=hashlib.sha256()
            with f.open('rb') as fp:
                for block in iter(lambda: fp.read(2**20),b''):
                    h.update(block)
            if h.hexdigest()!=sha:
                raise ValueError(f'Datensatz {n}: BIN-SHA-256 stimmt nicht überein')
        clean.append((sha,size,*values))
    with db.connect() as c:
        # Never silently overwrite a previously reviewed conflicting identity.
        for record in clean:
            old=c.execute('SELECT byte_count,brand,model,engine,ecu,family,software,source,reviewer '
                          'FROM firmware_identity WHERE firmware_sha256=?',(record[0],)).fetchone()
            if old is not None and tuple(old)!=tuple(record[1:]):
                raise ValueError('Abweichende Identität für bereits bekannten Hash '+record[0][:16])
        c.executemany('''INSERT OR IGNORE INTO firmware_identity
          (firmware_sha256,byte_count,brand,model,engine,ecu,family,software,source,reviewer)
          VALUES (?,?,?,?,?,?,?,?,?,?)''',clean)
    return {'processed':len(clean),'hash_proof_required':require_files,
            'stored_firmware_bytes':0}


def identify_vehicle(image: BinaryImage, db=None) -> IdentityResult:
    """Exact SHA is a high-specificity reviewer record; family marker only a hint."""
    if db is not None:
        install_identity_schema(db)
        with db.connect() as c:
            row=c.execute('''SELECT brand,model,engine,ecu,family,software,source,reviewer
                  FROM firmware_identity WHERE firmware_sha256=? AND byte_count=?''',
                  (image.digest,image.size)).fetchone()
        if row:
            brand,model,engine,ecu,family,software,source,reviewer=row
            return IdentityResult('hash-reviewed',brand,model,engine,ecu,family,
                software,(f'Exakter SHA-256: {image.digest}',f'Manuell geprüft: {reviewer}',
                          f'Metadatenquelle: {source}'),
                'Hash identisch; Fahrzeugzuordnung wurde vom Prüfer hinterlegt. Keine VIN-Identifikation.')
    p=identify_profile(image)
    if p.identified:
        return IdentityResult('family-hint',ecu=p.controller,family=p.family,
            software=p.software_version or p.calibration_id or '',
            evidence=p.evidence,notes='ECU/Softwarefamilie aus BIN-Merkmalen; Automodell, Motor und Marke nicht nachgewiesen.')
    # A highly constrained header string is a LOW-TRUST family clue only.
    # Many suppliers share a platform; the string never establishes a brand,
    # vehicle model, map offset, memory layout, or software compatibility.
    spans=image.read(0,min(image.size,8192))
    if image.size>8192:spans+=image.read(max(8192,image.size-8192),min(8192,image.size-8192))
    upper=spans.upper()
    if b'BOSCH' in upper:
        for platform,family in ((rb'EDC17[A-Z0-9]{1,10}', 'Bosch EDC17'),
                                (rb'EDC16[A-Z0-9]{1,10}', 'Bosch EDC16'),
                                (rb'MED17[.A-Z0-9]{1,10}', 'Bosch MED/ME'),
                                (rb'MG1[A-Z0-9]{2,10}', 'Bosch MG1'),
                                (rb'MD1[A-Z0-9]{2,10}', 'Bosch MD1')):
            markers=list(re.finditer(rb'(?<![A-Z0-9])'+platform+rb'(?![A-Z0-9])',upper))
            if len(markers)==1:
                value=markers[0].group().decode('ascii')
                return IdentityResult('text-hint',ecu=value,family=family,
                   evidence=('BOSCH-Herstellertext im BIN-Randbereich',
                             'Ungeprüfte ECU-Typzeichenkette: '+value),
                   notes='Nicht unabhängig verifizierter ASCII-Hinweis. Keine Fahrzeug- oder Softwareidentifikation.')
    return IdentityResult('unknown',evidence=('Kein eindeutiger Firmware-Fingerprint vorhanden',),
                          notes='Passende A2L/XDF oder manuell geprüften Hash-Datensatz importieren.')


def identity_stats(db):
    install_identity_schema(db)
    with db.connect() as c:
        return c.execute('SELECT COUNT(*) FROM firmware_identity').fetchone()[0]
