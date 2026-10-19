"""Explicit provenance-safe intake for arbitrary ECU families, including MD1/MG1.

Never assumes ECU software identity from byte counts or short string searches.
For family-unidentified images, the operator must provide firmware SHA-256,
family, software ID and the exact address-map metadata. All maps remain
UNVERIFIED until independently checked by a knowledgeable human.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import time
from .catalog import DefinitionCatalog
from .families import require_family
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.a2l import read_a2l
from ecu_studio.core.xdf import read_xdf
from ecu_studio.core.addressing import AddressSegment
from ecu_studio.core.profiles import identify_profile


def register_explicit_firmware(db:DefinitionCatalog, image:BinaryImage, *,
                               family:str,software:str,expected_sha256:str,
                               variant:str,acknowledge:bool=False):
    require_family(family)
    if not acknowledge:raise ValueError('Unabhängige ECU-Identitätsprüfung muss ausdrücklich bestätigt sein')
    if image.dirty_bytes: raise ValueError('Nur unveränderte Original-BIN registrieren')
    if image.digest!=expected_sha256:raise ValueError('Firmware-SHA-256 stimmt nicht überein')
    if not 2<=len(software.strip())<=100 or not 1<=len(variant.strip())<=150:
        raise ValueError('Genaue Software-ID und Variante erforderlich')
    guessed=identify_profile(image)
    if guessed.identified and guessed.family!=family:
        raise ValueError('Widerspruch zum bereits erkannten Controller-Profil; kein Training')
    with db.connect() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS operator_firmware_claim(
            sha TEXT PRIMARY KEY, family TEXT NOT NULL, software TEXT NOT NULL,
            variant TEXT NOT NULL, status TEXT NOT NULL, ts INTEGER NOT NULL)''')
        old=conn.execute('SELECT family,software FROM firmware WHERE sha=?',(image.digest,)).fetchone()
        if old and (old[0]!=family or old[1]!=software):
            raise ValueError('Widersprüchliche Firmware-Zuordnung in der Datenbank')
        conn.execute('INSERT OR IGNORE INTO firmware(sha,family,software,byte_count,inserted_at) VALUES(?,?,?,?,?)',
                     (image.digest,family,software,image.size,int(time.time())))
        conn.execute('INSERT OR REPLACE INTO operator_firmware_claim VALUES(?,?,?,?,?,?)',
                     (image.digest,family,software,variant,'user-declared-unverified',int(time.time())))
    return {'sha256':image.digest,'family':family,'software':software,'variant':variant,
            'status':'user-declared-unverified'}


def ingest_explicit_pair(db:DefinitionCatalog, *,bin_path:str,definition_path:str,
                         family:str,software:str,variant:str,expected_sha256:str,
                         acknowledge=False,segments:list[AddressSegment]|None=None)->dict:
    """Ingest XDF or A2L without ever auto-verifying semantic identities.

    A2L requires an explicit, audited segment mapping: guessing one giant
    ECU base address is unsafe for MD1/MG1 multicore software images.
    """
    img=BinaryImage.from_file(bin_path)
    src=Path(definition_path)
    if src.suffix.lower()=='.a2l':
        if not segments:raise ValueError('A2L-Import: explizite ECU-zu-BIN-Segmente erforderlich')
        linked=read_a2l(str(src)).link(file_size=img.size,segments=segments)
        maps=linked.maps
        skipped=len(linked.unsupported)+len(linked.out_of_range)+len(linked.unlinked)
    elif src.suffix.lower()=='.xdf':
        result=read_xdf(str(src),img)
        maps=result.maps;skipped=sum(result.excluded.values())
    else:
        raise ValueError('Nur .a2l und .xdf werden aktuell unterstützt')
    if not maps:
        raise ValueError('Keine speichertechnisch gültigen Definitionen: keine Firmware-Registrierung')
    claim=register_explicit_firmware(db,img,family=family,software=software,
                                     variant=variant,expected_sha256=expected_sha256,
                                     acknowledge=acknowledge)
    indexed=db.import_maps(img,maps,origin='EXPLIZITE BENUTZERQUELLE (ungeprüft): '+str(src),source_path=src)
    return {'claim':claim,'definitions_indexed':indexed['indexed'],
            'rejected':len(indexed['rejected'])+skipped,'verified':0,
            'training_ready':False,
            'warning':'Benutzerangabe + importierte Definition sind noch kein geprüfter Labeldatensatz.'}
