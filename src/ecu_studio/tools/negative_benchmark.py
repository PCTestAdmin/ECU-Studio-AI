"""False-find benchmark on program-code images (open firmware without a tune).

Usage:
  python -m ecu_studio.tools.negative_benchmark MANIFEST.json --out result.json [--markdown table.md]
         [--scanner-src PATH] [--baseline earlier.json] [--pair NAME_A NAME_B]

Manifest (JSON list; firmware stays local, only counts and offsets are reported):
  {"name": "rusEFI 2026-11-01", "family": "rusEFI", "architecture": "ARM",
   "path": "....bin | .hex | .srec", "srec": "optional .srec of the same build (load address check)"}

What is measured per image: architecture (expected and detected), size, SHA-256,
all candidates of the automatic scan by evidence level, candidates per MiB, scan
time and peak Python memory (tracemalloc, in a fresh process per image).

Which candidates are certainly wrong is decided by the bytes only, never by the
detector under test (core/region_classes):
  text            >= 90 % of the candidate lies in runs of NUL-terminated text strings
  pointer         >= 90 % lies in aligned tables of addresses into the image's own
                  flash/SRAM windows or in the Cortex-M vector table (ARM; the
                  pointer format must be known), or a header record / axis
                  record whose axes are address words (rusEFI table objects)
  foreign code    code evidence on an image whose architecture has no code
                  decoder in ECU Studio (ARM, AVR): the evidence itself is wrong,
                  whatever lies at that address
Everything else is "unclear": program images also hold real constant tables
(lookup curves, trigger patterns), which cannot be told apart from false finds
without symbols. No precision is computed: there is no complete reference.

``--scanner-src`` runs the scan with another source tree (e.g. a worktree of
v1.19.0) while classification stays the same, so before/after numbers are
comparable. ``--pair`` compares two near-identical builds (version stability).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ecu_studio.core.architecture import detect_architecture, ARM, AVR
from ecu_studio.core.region_classes import text_spans, pointer_spans, address_word_spans, classify

CHILD = r'''
import json, sys, time, tracemalloc
from ecu_studio import __version__
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.confidence import evidence_class
path = sys.argv[1]
if path.lower().endswith(('.hex', '.ihx', '.srec', '.s19', '.s28', '.s37', '.mot')):
    from ecu_studio.formats.records import read_memory_file
    image = BinaryImage(read_memory_file(path).to_binary(fill=0xFF))
else:
    image = BinaryImage.from_file(path)
tracemalloc.start()
t = time.perf_counter()
maps = scan_calibration_candidates(image)
elapsed = time.perf_counter() - t
peak = tracemalloc.get_traced_memory()[1]
out = {'version': __version__, 'elapsed': round(elapsed, 3), 'peak_mb': round(peak / 2**20, 1), 'finds': [
    {'offset': m.offset, 'rows': m.rows, 'cols': m.cols, 'dtype': m.dtype, 'width': m.width,
     'endian': m.endian, 'length': m.length, 'tier': m.evidence_tier or '', 'class': evidence_class(m),
     'layout': m.record_layout or '', 'origin': m.label_origin or '',
     'axis_x_offset': m.axis_x_offset, 'axes_x': list(m.axes_x or []),
     'axis_y_offset': m.axis_y_offset, 'axes_y': list(m.axes_y or [])} for m in maps]}
print(json.dumps(out))
'''

DECODERLESS = (ARM, AVR)   # architectures without a code decoder in ECU Studio


def load_bytes(path: str) -> bytes:
    if path.lower().endswith(('.hex', '.ihx', '.srec', '.s19', '.s28', '.s37', '.mot')):
        from ecu_studio.formats.records import read_memory_file
        return read_memory_file(path).to_binary(fill=0xFF)
    return Path(path).read_bytes()


def load_address(data: bytes, entry: dict) -> dict:
    """Load address of a .bin from the .srec of the same build: where the SREC payload sits inside the BIN.

    Update images may differ in a few header bytes (rusEFI: 12 bytes of checksum/length fields), so the
    position is taken from several anchors that must agree, and the differing bytes are reported.
    """
    if entry['path'].lower().endswith(('.hex', '.ihx')):
        from ecu_studio.formats.records import read_memory_file
        return {'load_address': f"0x{read_memory_file(entry['path']).start:X}", 'source': 'Intel-HEX'}
    if not entry.get('srec'):
        return {}
    import numpy as np
    from ecu_studio.formats.records import read_memory_file
    img = read_memory_file(entry['srec'])
    payload = img.to_binary(fill=0xFF)
    from collections import Counter
    anchors = [o for o in (0x100, 0x1000, len(payload) // 4, len(payload) // 2, 3 * len(payload) // 4)
               if 0 <= o < len(payload) - 64]
    votes = Counter(data.find(payload[o:o + 64]) - o for o in anchors if data.find(payload[o:o + 64]) >= 0)
    k, n = votes.most_common(1)[0] if votes else (-1, 0)
    unclear = {'srec_check': 'SREC-Inhalt nicht eindeutig in der BIN gefunden'}
    if n < 3 or k < 0 or k + len(payload) > len(data):
        return unclear
    differ = int((np.frombuffer(data[k:k + len(payload)], np.uint8) != np.frombuffer(payload, np.uint8)).sum())
    if differ > len(payload) // 1000:
        return unclear
    return {'load_address': f'0x{img.start - k:X}', 'source': 'SREC desselben Builds',
            'srec_range': f'0x{img.start:X}-0x{img.end:X}', 'srec_offset_in_bin': k, 'srec_differing_bytes': differ}


def scan(path: str, scanner_src: str | None) -> dict:
    env = dict(os.environ)
    src = scanner_src or str(Path(__file__).resolve().parents[2])
    env['PYTHONPATH'] = src
    env.setdefault('OPENBLAS_NUM_THREADS', '1')
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run([sys.executable, '-c', CHILD, path], env=env, capture_output=True, text=True,
                       encoding='utf-8', timeout=1800)
    if r.returncode:
        raise RuntimeError(f'Scan fehlgeschlagen ({path}): {r.stderr[-2000:]}')
    return json.loads(r.stdout.strip().splitlines()[-1])


def evaluate(entry: dict, scanner_src: str | None = None) -> dict:
    data = load_bytes(entry['path'])
    arch = detect_architecture(data)
    from types import SimpleNamespace
    from ecu_studio.core.scoped_scan import _axes_are_pointers
    text, pointers, addresses = text_spans(data), pointer_spans(data, arch), address_word_spans(data, arch)
    res = scan(entry['path'], scanner_src)
    finds = res['finds']
    rows = []
    for f in finds:
        cls = classify(f['offset'], f['offset'] + f['length'], text, pointers)
        if not cls and len(addresses):
            m = SimpleNamespace(offset=f['offset'], length=f['length'], record_layout=f['layout'],
                                axis_x_offset=f.get('axis_x_offset'), axes_x=f.get('axes_x') or [],
                                axis_y_offset=f.get('axis_y_offset'), axes_y=f.get('axes_y') or [])
            cls = 'pointer' if _axes_are_pointers(m, addresses) else ''
        foreign = f['tier'] == 'Code-Beleg' and (entry.get('architecture') in DECODERLESS
                                                  or arch.name in DECODERLESS)
        f['wrong'] = 'foreign-code' if foreign else cls
        rows.append(f)
    tiers = Counter(f['tier'] or 'ohne' for f in rows)
    wrong = Counter(f['wrong'] for f in rows if f['wrong'])
    by_tier = {t: dict(Counter(f['wrong'] or 'unclear' for f in rows if (f['tier'] or 'ohne') == t)) for t in tiers}
    size = len(data)
    return {
        'name': entry['name'], 'family': entry.get('family', ''),
        'architecture_expected': entry.get('architecture', ''), 'architecture_detected': arch.name,
        'architecture_evidence': arch.describe(), 'architecture_signs': arch.signs,
        'size': size, 'sha256': hashlib.sha256(data).hexdigest(), **load_address(data, entry),
        'scanner_version': res['version'], 'elapsed_s': res['elapsed'], 'peak_mb': res['peak_mb'],
        'finds': len(rows), 'finds_per_mib': round(len(rows) / (size / 2**20), 1),
        'tiers': dict(tiers), 'classes': dict(Counter(f['class'] for f in rows)),
        'certainly_wrong': sum(wrong.values()), 'wrong': dict(wrong),
        'unclear': sum(not f['wrong'] for f in rows), 'by_tier': by_tier,
        'text_bytes': int((text.ends - text.starts).sum()), 'pointer_bytes': int((pointers.ends - pointers.starts).sum()),
        'detail': [{k: f[k] for k in ('offset', 'rows', 'cols', 'dtype', 'width', 'tier', 'class', 'wrong')}
                   for f in rows],
    }


def stability(a: dict, b: dict, data_a: bytes, data_b: bytes, window: int = 0x4000) -> dict:
    """Finds of build A found again in near-identical build B: same bytes nearby, then same shape/type/level."""
    index = {}
    for f in b['detail']:
        index.setdefault((f['rows'], f['cols'], f['dtype']), []).append(f)
    stats = Counter()
    unexplained = []
    matched_b = set()
    for f in a['detail']:
        size = f['rows'] * f['cols'] * f['width']
        raw = data_a[f['offset']:f['offset'] + size]
        lo = max(0, f['offset'] - window)
        k = data_b.find(raw, lo, f['offset'] + window + size) if len(raw) >= 8 else -1
        if k < 0:
            stats['bytes changed'] += 1
            continue
        same = [g for g in index.get((f['rows'], f['cols'], f['dtype']), []) if g['offset'] == k]
        if same:
            matched_b.add(k)
            stats['stable' if same[0]['tier'] == f['tier'] else 'stable, other level'] += 1
        else:
            stats['bytes equal, not found again'] += 1
            unexplained.append({'offset_a': f['offset'], 'offset_b': k, 'rows': f['rows'], 'cols': f['cols'],
                                'dtype': f['dtype'], 'tier': f['tier'], 'wrong': f['wrong']})
    stats['only in B'] = sum(g['offset'] not in matched_b for g in b['detail'])
    return {'a': a['name'], 'b': b['name'], 'stats': dict(stats), 'unexplained': unexplained[:50],
            'unexplained_count': len(unexplained),
            'unexplained_certainly_wrong': sum(bool(u['wrong']) for u in unexplained)}


def markdown(results: list[dict], baseline: dict | None) -> str:
    base = {r['name']: r for r in (baseline or {}).get('images', [])}
    head = ('| Firmware | Architektur (erwartet/erkannt) | Funde | je MiB | Code | Struktur | Datenmuster | Text | '
            'Zeiger | fremde Code-Belege | sicher falsch | unklar | s | MB |\n|' + '---|' * 14 + '\n')
    out = []
    for r in results:
        b = base.get(r['name'])
        def cell(value, key=None, sub=None):
            if b is None:
                return str(value)
            old = b[key] if sub is None else b[key].get(sub, 0)
            return f'{old} → {value}' if old != value else str(value)
        t, w = r['tiers'], r['wrong']
        out.append(f"| {r['name']} | {r['architecture_expected']}/{r['architecture_detected']} | "
                   f"{cell(r['finds'], 'finds')} | {r['finds_per_mib']} | "
                   f"{cell(t.get('Code-Beleg', 0), 'tiers', 'Code-Beleg')} | "
                   f"{cell(t.get('Strukturbeleg', 0), 'tiers', 'Strukturbeleg')} | "
                   f"{cell(t.get('Datenmuster-Vermutung', 0), 'tiers', 'Datenmuster-Vermutung')} | "
                   f"{cell(w.get('text', 0), 'wrong', 'text')} | {cell(w.get('pointer', 0), 'wrong', 'pointer')} | "
                   f"{cell(w.get('foreign-code', 0), 'wrong', 'foreign-code')} | "
                   f"{cell(r['certainly_wrong'], 'certainly_wrong')} | {cell(r['unclear'], 'unclear')} | "
                   f"{cell(r['elapsed_s'], 'elapsed_s')} | {cell(r['peak_mb'], 'peak_mb')} |")
    return head + '\n'.join(out) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('manifest', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--markdown', type=Path)
    p.add_argument('--scanner-src')
    p.add_argument('--baseline', type=Path)
    p.add_argument('--pair', nargs=2, metavar=('NAME_A', 'NAME_B'))
    a = p.parse_args()
    entries = json.loads(a.manifest.read_text(encoding='utf-8'))
    results = []
    for e in entries:
        r = evaluate(e, a.scanner_src)
        results.append(r)
        print(f"{r['name']}: {r['architecture_detected']}, {r['finds']} Funde, sicher falsch {r['certainly_wrong']} "
              f"{r['wrong']}, unklar {r['unclear']}, {r['elapsed_s']} s, {r['peak_mb']} MB", flush=True)
    report = {'format': 1, 'scanner_src': a.scanner_src or 'this tree', 'images': results,
              'totals': {'finds': sum(r['finds'] for r in results),
                         'certainly_wrong': sum(r['certainly_wrong'] for r in results),
                         'unclear': sum(r['unclear'] for r in results),
                         'wrong': dict(sum((Counter(r['wrong']) for r in results), Counter())),
                         'tiers': dict(sum((Counter(r['tiers']) for r in results), Counter()))}}
    if a.pair:
        by = {e['name']: e for e in entries}
        ra = next(r for r in results if r['name'] == a.pair[0])
        rb = next(r for r in results if r['name'] == a.pair[1])
        report['stability'] = stability(ra, rb, load_bytes(by[a.pair[0]]['path']), load_bytes(by[a.pair[1]]['path']))
        print('Stabilität:', report['stability']['stats'], flush=True)
    a.out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    if a.markdown:
        base = json.loads(a.baseline.read_text(encoding='utf-8')) if a.baseline else None
        a.markdown.write_text(markdown(results, base), encoding='utf-8')
    print(json.dumps(report['totals'], ensure_ascii=False))



if __name__ == '__main__':
    main()
