"""Auditable, non-training ECU source discovery for multiple vehicle makes.

This is a list of *references*, not ECU dumps, approved XDF/BIN pairs, or
verified semantic labels. Nothing in this list is fetched automatically.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

DATA=Path(__file__).parent/'data'/'brand_sources.json'
BRANDS=('Audi','Mercedes-Benz','BMW','Opel','Lamborghini')


def source_catalog() -> list[dict]:
    entries=json.loads(DATA.read_text(encoding='utf-8'))
    ids=set()
    for item in entries:
        if item['id'] in ids or item['brand'] not in BRANDS:
            raise ValueError('Ungültiger ECU-Quellenindex')
        ids.add(item['id'])
        if item['training_approved'] is not False:
            raise ValueError('Öffentlicher Fund darf niemals als verifiziertes KI-Label gelten')
        if item['git_blob_sha1'] and not re.fullmatch('[0-9a-f]{40}',item['git_blob_sha1']):
            raise ValueError('Ungültiger Git-Quellhash')
        if item['url'] and not item['url'].startswith('https://github.com/'):
            raise ValueError('Nur deklarierte GitHub-Quellenlinks')
    return entries


def install_discovery_sources(db) -> int:
    items=source_catalog()
    with db.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS discovery_source(
            id TEXT PRIMARY KEY, brand TEXT NOT NULL, family TEXT NOT NULL,
            format TEXT NOT NULL, software_hint TEXT NOT NULL, ecu_variant TEXT NOT NULL,
            url TEXT NOT NULL, git_blob_sha1 TEXT NOT NULL,
            status TEXT NOT NULL, rights TEXT NOT NULL,
            training_approved INTEGER NOT NULL DEFAULT 0
            CHECK(training_approved = 0))''')
        for x in items:
            c.execute('''INSERT OR REPLACE INTO discovery_source VALUES(?,?,?,?,?,?,?,?,?,?,0)''',
                      tuple(x[k] for k in ('id','brand','family','format','software_hint',
                              'ecu_variant','url','git_blob_sha1','status','rights')))
    return len(items)


def discovery_sources(db, brand: str | None = None) -> list[dict]:
    if brand is not None and brand not in BRANDS:
        raise ValueError('Unbekannte Marke; gültig: '+', '.join(BRANDS))
    with db.connect() as c:
        cur=c.execute('''SELECT id,brand,family,format,software_hint,ecu_variant,
               url,git_blob_sha1,status,rights,training_approved FROM discovery_source
               WHERE (? IS NULL OR brand=?) ORDER BY brand,id''',(brand,brand))
        fields=[col[0] for col in cur.description]
        return [dict(zip(fields,row)) for row in cur.fetchall()]
