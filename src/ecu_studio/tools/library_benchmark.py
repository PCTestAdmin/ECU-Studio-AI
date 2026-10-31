"""Speed of the local project/map-pack index with a synthetic database (no firmware involved).

    python -m ecu_studio.tools.library_benchmark --projects 20000 --packs 2000 --out result.json

Builds a throwaway SQLite index with synthetic metadata (random hashes, families and Bosch-style hardware and
software numbers from a shared pool, so that numbers repeat like in a real library), then times what the app
does: opening the index, the lookup when a BIN is opened (``suggestions``) and the library search. The images
used for the lookup are synthetic byte strings carrying text markers only.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import random
import statistics
from contextlib import closing
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from ecu_studio.core.model import BinaryImage
from ecu_studio.core.project_store import ProjectStore

FAMILIES = ['ME7.5', 'ME7.1', 'MED17', 'EDC17', 'EDC16', 'SIMOS 18', 'MSD 80', 'MED9']


def _pool(rng, prefix, n):
    return [f'{prefix}{rng.randrange(10 ** 6):06d}' for _ in range(n)]


def _rows(rng, hardware, software, start, count):
    out = []
    for i in range(start, start + count):
        family = rng.choice(FAMILIES)
        hw, sw = rng.choice(hardware), rng.choice(software)
        row = (f'C:/bench/projects/p{i}.ecuproj', f'p{i}', hashlib.sha256(f'p{i}'.encode()).hexdigest(), 1 << 20,
               rng.randrange(50, 900), '', f'p{i} {family} {hw} {sw}'.casefold(), 1.7e9 + i)
        meta = {'family': family, 'hardware': hw, 'software': sw, 'definition_sources': 'xdf', 'app_version': 'bench',
                'created': 1.7e9 + i, 'verified': 0, 'unverified': 0, 'changed_maps': 0, 'versions': 1}
        out.append((row, meta))
    return out


def build(path: Path, projects: int, packs: int, seed: int = 1):
    """Synthetic index in the table layout every version writes (bulk SQL, so filling is not what is measured)."""
    rng = random.Random(seed)
    hardware, software = _pool(rng, '0261', 400), _pool(rng, '1037', 2000)
    ProjectStore(path)                                  # creates the schema of the version under test
    rows = _rows(rng, hardware, software, 0, projects)
    with closing(sqlite3.connect(path)) as c, c:
        c.executemany('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?)', [row for row, _ in rows])
        c.executemany('INSERT INTO project_meta(path,family,hardware,software,definition_sources,app_version,created,'
                      'verified,unverified,changed_maps,versions) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      [(row[0], *meta.values()) for row, meta in rows])
        c.executemany('INSERT OR REPLACE INTO map_packs VALUES(?,?,?,?,?,?)',
                      [(f'C:/bench/packs/k{i}.json', hashlib.sha256(f'k{i}'.encode()).hexdigest(), rng.choice(FAMILIES),
                        json.dumps([rng.choice(hardware)]), json.dumps([rng.choice(software)]), 100)
                       for i in range(packs)])
    return rng, hardware, software


def _index_cost(store, rng, hardware, software, start, count) -> dict:
    """What indexing ``count`` projects costs in the database (loading the project files excluded)."""
    rows = _rows(rng, hardware, software, start, count)
    begin = time.perf_counter()
    for row, meta in rows[:count // 2]:
        store._upsert(row, meta)                        # one transaction per project (ProjectStore.index)
    one_by_one = (time.perf_counter() - begin) / (count // 2)
    result = {'per_project_one_transaction_ms': round(one_by_one * 1000, 2)}
    if 'c' in inspect.signature(store._upsert).parameters:
        begin = time.perf_counter()
        with store.connect() as c:                      # what index_many does per batch
            for row, meta in rows[count // 2:]:
                store._upsert(row, meta, c)
        result['per_project_batched_ms'] = round((time.perf_counter() - begin) / (count - count // 2) * 1000, 3)
    return result


def _image(*markers: str) -> BinaryImage:
    data = bytearray(256 * 1024)
    pos = 0x1000
    for marker in markers:
        data[pos:pos + len(marker)] = marker.encode()
        pos += 0x100
    return BinaryImage(bytes(data))


def _time(fn, repeat: int) -> dict:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {'median_ms': round(statistics.median(samples), 2), 'max_ms': round(max(samples), 2),
            'results': len(result) if hasattr(result, '__len__') else None}


def run(projects: int, packs: int, repeat: int) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'bench.sqlite3'
        rng, hardware, software = build(path, projects, packs)
        start = time.perf_counter()
        store = ProjectStore(path)                      # includes the one-time identifier backfill (new versions)
        first_open = time.perf_counter() - start
        start = time.perf_counter()
        store = ProjectStore(path)
        reopen = time.perf_counter() - start
        known = _image(f'{hardware[0]}{software[0]}', 'ME7.5')
        unknown = _image('0261999999', '1037999999')
        return {
            'projects': projects, 'packs': packs, 'repeat': repeat,
            'first_open_ms': round(first_open * 1000, 1), 'reopen_ms': round(reopen * 1000, 1),
            'suggestions_known_ids': _time(lambda: store.suggestions(known), repeat),
            'suggestions_unknown_ids': _time(lambda: store.suggestions(unknown), repeat),
            'search_all': _time(lambda: store.search('', limit=500), repeat),
            'search_text': _time(lambda: store.search('me7.5', limit=500), repeat),
            'index': _index_cost(store, rng, hardware, software, projects, 1000),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--projects', type=int, default=20000)
    parser.add_argument('--packs', type=int, default=2000)
    parser.add_argument('--repeat', type=int, default=15)
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    result = run(args.projects, args.packs, args.repeat)
    text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
