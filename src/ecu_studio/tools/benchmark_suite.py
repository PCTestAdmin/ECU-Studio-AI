"""Reproducible detection benchmark over a manifest of local BIN/reference pairs.

Usage: python -m ecu_studio.tools.benchmark_suite MANIFEST.json [--out result.json] [--markdown table.md]

Manifest (JSON list; firmware stays local, only counts are reported):
  {"name": "...", "family": "Bosch MED17.1.62", "bin": "path", "reference": "path.xdf|.a2l|.xml|.csv",
   "complete": false, "role": "test|development|training", "anchor": "0x80000000" (optional, A2L only)}

Rules that keep the numbers honest:
- Precision, false positives and false negatives are only reported for
  ``complete`` references; partial XDFs give recall and exact layouts only.
- ``role`` says whether a pair was used to train (model/calibration) or to tune
  the detector (development). Only ``test`` pairs count as independent.
- Near-identical images (>= SAME_IMAGE byte agreement, e.g. software versions of
  one calibration) form one group; group means are reported so a family is not
  weighted by how many sister versions happen to be available.
- Data type: an exactly matched candidate has the right type when width, byte
  order and sign agree; the sign only counts where the bytes decide it.
- Axes: an exactly matched candidate counts as "axes correct" when its raw axis
  values are a linear image of the reference axis (correlation > .999) and the
  point counts agree. Factors/units are not scored: candidates carry raw values.
"""
from __future__ import annotations
import argparse
import json
import time
import tracemalloc
from pathlib import Path
import numpy as np
from ecu_studio import __version__
from ecu_studio.core.axis_groups import compare_with_reference
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.tools.structure_benchmark import reference_tables, reference_lines, score, score_lines

SAME_IMAGE = .9
ROLES = ('test', 'development', 'training')


def _linear(a, b) -> bool:
    if len(a) != len(b) or len(a) < 2:
        return False
    a, b = np.asarray(a, float), np.asarray(b, float)
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return bool(np.ptp(a) == np.ptp(b) == 0)
    return bool(abs(np.corrcoef(a, b)[0, 1]) > .999)


def axes_agreement(found, reference) -> dict:
    """Exactly matched 2-D candidates with axes, and how many of those axes are right."""
    ref = {(m.offset, m.width): m for m in reference}
    with_axes = correct = 0
    for m in found:
        r = ref.get((m.offset, m.width))
        if r is None or {m.rows, m.cols} != {r.rows, r.cols} or not m.axes_x:
            continue
        with_axes += 1
        # Orientation may be transposed; accept either pairing.
        pairs = [(m.axes_x, r.axes_x), (m.axes_y, r.axes_y)], [(m.axes_x, r.axes_y), (m.axes_y, r.axes_x)]
        if any(all(not c or _linear(c, d) for c, d in p) and any(c for c, _ in p) for p in pairs):
            correct += 1
    return {'with_axes': with_axes, 'axes_correct': correct}


def type_agreement(image, found, reference) -> int:
    """Exactly matched 2-D candidates whose data type is right: width, byte order and sign.

    The sign only counts where the stored bytes decide it: if no value has its top
    bit set, signed and unsigned readings are identical and either is correct.
    """
    ref = {(m.offset, m.width): m for m in reference}
    correct = 0
    for m in found:
        r = ref.get((m.offset, m.width))
        if r is None or {m.rows, m.cols} != {r.rows, r.cols}:
            continue
        if m.width > 1 and m.endian != r.endian:
            continue
        if m.dtype[0] != r.dtype[0]:
            raw = np.frombuffer(image.read(m.offset, m.length), np.uint8)
            top = raw[::m.width] if m.endian == 'big' or m.width == 1 else raw[m.width - 1::m.width]
            if np.any(top >= 0x80):
                continue
        correct += 1
    return correct


def run_pair(entry: dict, memory: bool = False) -> dict:
    image = BinaryImage.from_file(entry['bin'])
    anchor = int(entry['anchor'], 0) if isinstance(entry.get('anchor'), str) else entry.get('anchor')
    tables = reference_tables(entry['reference'], image, anchor=anchor)
    lines = reference_lines(entry['reference'], image, anchor=anchor)
    begin = time.perf_counter()
    found = scan_calibration_candidates(image, use_definitions=False)
    elapsed = time.perf_counter() - begin
    peak = None
    if memory:
        # Separate run: tracing slows the scan and must not distort the timing.
        tracemalloc.start()
        scan_calibration_candidates(image, use_definitions=False)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    areas = [m for m in found if min(m.rows, m.cols) > 1]
    s2, s1 = score(areas, tables), score_lines([m for m in found if min(m.rows, m.cols) == 1], lines)
    complete = bool(entry.get('complete'))
    hits = round(s2['precision'] * s2['candidates'])
    row = {'name': entry['name'], 'family': entry['family'], 'role': entry.get('role', 'development'),
           'complete_reference': complete, 'reference_source': entry.get('source', ''),
           'reference_license': entry.get('license', ''), 'size': image.size, 'sha256': image.digest,
           'reference_2d': len(tables), 'found_2d': s2['candidates'], 'recall_2d': s2['recall'],
           'exact_2d': s2['exact_layouts'], 'reference_1d': len(lines), 'found_1d': s1['candidates'],
           'exact_1d': s1['exact'], 'seconds': round(elapsed, 2), 'peak_mb': round(peak / 2**20, 1) if peak is not None else None}
    row.update(axes_agreement(areas, tables))
    row['type_exact_2d'] = type_agreement(image, areas, tables)
    # Axis storage and shared-axis groups (core/axis_groups): only where the
    # reference states where axes are stored; group pairs among exact matches.
    groups = compare_with_reference(areas, tables)
    row.update({'axis_address_with_2d': groups['axis_with_address'],
                'axis_address_correct_2d': groups['axis_address_correct'],
                'group_pairs_reference': groups['pairs_reference'], 'group_pairs_found': groups['pairs_found'],
                'group_pairs_agree': groups['pairs_agree']})
    if complete:
        row.update(precision_2d=s2['precision'], false_positives_2d=s2['candidates'] - hits,
                   false_negatives_2d=len(tables) - round(s2['recall'] * len(tables)),
                   precision_1d=s1['precision'])
    return row


def similarity(a: bytes, b: bytes) -> float:
    if len(a) != len(b) or not a:
        return 0.
    return float(np.mean(np.frombuffer(a, np.uint8) == np.frombuffer(b, np.uint8)))


def group_images(entries: list[dict]) -> list[int]:
    """Group index per entry; near-identical images (same size, >= SAME_IMAGE equal bytes) share one."""
    data = [Path(e['bin']).read_bytes() for e in entries]
    group = list(range(len(entries)))
    for i in range(len(entries)):
        for j in range(i):
            if group[j] == j and similarity(data[i], data[j]) >= SAME_IMAGE:
                group[i] = j
                break
    return group


def run(entries: list[dict], memory: bool = False) -> dict:
    for e in entries:
        if e.get('role', 'development') not in ROLES:
            raise ValueError(f"{e['name']}: role muss {ROLES} sein")
    groups = group_images(entries)
    rows = []
    for e, g in zip(entries, groups):
        row = run_pair(e, memory)
        row['group'] = entries[g]['name']
        rows.append(row)
    independent = [r for r in rows if r['role'] == 'test']
    return {'format': 1, 'rows': rows, 'version': __version__, 'commit': _commit(),
            'independent_pairs': len(independent),
            'note': ('Nur role=test zählt als unabhängig. Präzision nur bei vollständiger Referenz. '
                     'Gruppen = nahezu identische Softwarestände.')}


def _commit() -> str:
    import subprocess
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parent, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def _ratio(done, total) -> str:
    return f'{done}/{total}' if total else '–'


def markdown(result: dict) -> str:
    head = ('| Paar | Familie | Rolle | Gruppe | Ref 2D | gefunden | Recall | exakt | Typ richtig | Achsen richtig | '
            'Achsadresse richtig | Gruppenpaare gefunden/richtig/Referenz | '
            'Präzision | FP | FN | Ref 1D | exakt 1D | s | MB |\n|' + '---|' * 19)
    out = [head]
    for r in result['rows']:
        prec = f"{r['precision_2d']:.0%}" if r['complete_reference'] else '–'
        mb = r['peak_mb'] if r['peak_mb'] is not None else '–'
        fp = r.get('false_positives_2d', '–'); fn = r.get('false_negatives_2d', '–')
        out.append(f"| {r['name']} | {r['family']} | {r['role']} | {r['group']} | {r['reference_2d']} | "
                   f"{r['found_2d']} | {r['recall_2d']:.0%} | {r['exact_2d']} | {r.get('type_exact_2d', '–')} | {r['axes_correct']}/{r['with_axes']} | "
                   f"{_ratio(r.get('axis_address_correct_2d', 0), r.get('axis_address_with_2d', 0))} | "
                   f"{r.get('group_pairs_found', '–')}/{r.get('group_pairs_agree', '–')}/{r.get('group_pairs_reference', '–')} | "
                   f"{prec} | {fp} | {fn} | {r['reference_1d']} | {r['exact_1d']} | {r['seconds']} | {mb} |")
    return '\n'.join(out)


# A pair counts as improved only by more exact maps; precision (complete references)
# may not fall by more than this. More candidates alone is never an improvement.
PRECISION_TOLERANCE = .01


def compare_runs(before: dict, after: dict) -> dict:
    """Per-pair change between two benchmark results (rows matched by name and image hash)."""
    old = {r['name']: r for r in before['rows']}
    pairs = []
    for r in after['rows']:
        b = old.get(r['name'])
        if b is None or b.get('sha256') != r.get('sha256'):
            pairs.append({'name': r['name'], 'verdict': 'nicht vergleichbar'})
            continue
        d_exact = r['exact_2d'] - b['exact_2d']
        both = r['complete_reference'] and b['complete_reference']
        d_prec = r['precision_2d'] - b['precision_2d'] if both else None
        if d_exact < 0 or (d_prec is not None and d_prec < -PRECISION_TOLERANCE):
            verdict = 'schlechter'
        elif d_exact > 0:
            verdict = 'verbessert'
        elif r['found_2d'] > b['found_2d']:
            verdict = 'nur mehr Kandidaten'
        else:
            verdict = 'unverändert'
        pairs.append({'name': r['name'], 'family': r['family'], 'role': r['role'], 'verdict': verdict,
                      **{k: [b.get(k), r.get(k)] for k in ('exact_2d', 'found_2d', 'recall_2d', 'precision_2d',
                                                            'exact_1d', 'seconds')}})
    return {'format': 1, 'before': {k: before.get(k) for k in ('version', 'commit')},
            'after': {k: after.get(k) for k in ('version', 'commit')}, 'pairs': pairs,
            'regressions': [p['name'] for p in pairs if p['verdict'] == 'schlechter']}


def comparison_markdown(diff: dict) -> str:
    def pct(v):
        return f'{v:.0%}' if v is not None else '–'
    out = [f"Vorher {diff['before'].get('version')} ({diff['before'].get('commit') or '?'}) → "
           f"nachher {diff['after'].get('version')} ({diff['after'].get('commit') or '?'})", '',
           '| Paar | Familie | Rolle | exakt 2D | gefunden 2D | Präzision 2D | exakt 1D | s | Ergebnis |',
           '|' + '---|' * 9]
    for p in diff['pairs']:
        if 'exact_2d' not in p:
            out.append(f"| {p['name']} | | | | | | | | {p['verdict']} |")
            continue
        out.append(f"| {p['name']} | {p['family']} | {p['role']} | {p['exact_2d'][0]} → {p['exact_2d'][1]} | "
                   f"{p['found_2d'][0]} → {p['found_2d'][1]} | {pct(p['precision_2d'][0])} → {pct(p['precision_2d'][1])} | "
                   f"{p['exact_1d'][0]} → {p['exact_1d'][1]} | {p['seconds'][0]} → {p['seconds'][1]} | {p['verdict']} |")
    return '\n'.join(out)


def main(argv=None):
    from ecu_studio.core import parallel
    parallel.enable()   # guarded entry point: scans may use several CPU cores
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--markdown', type=Path)
    parser.add_argument('--memory', action='store_true', help='Spitzenspeicher in einem zweiten Lauf messen')
    parser.add_argument('--baseline', type=Path, help='Ergebnis-JSON eines früheren Laufs: Vorher/Nachher-Vergleich')
    args = parser.parse_args(argv)
    result = run(json.loads(args.manifest.read_text(encoding='utf-8')), memory=args.memory)
    if args.baseline:
        result['comparison'] = compare_runs(json.loads(args.baseline.read_text(encoding='utf-8')), result)
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    table = markdown(result)
    if args.baseline:
        table += '\n\n' + comparison_markdown(result['comparison'])
    if args.markdown:
        args.markdown.write_text(table + '\n', encoding='utf-8')
    print(table)


if __name__ == '__main__':
    main()
