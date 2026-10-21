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
           'complete_reference': complete, 'size': image.size, 'sha256': image.digest,
           'reference_2d': len(tables), 'found_2d': s2['candidates'], 'recall_2d': s2['recall'],
           'exact_2d': s2['exact_layouts'], 'reference_1d': len(lines), 'found_1d': s1['candidates'],
           'exact_1d': s1['exact'], 'seconds': round(elapsed, 2), 'peak_mb': round(peak / 2**20, 1) if peak is not None else None}
    row.update(axes_agreement(areas, tables))
    row['type_exact_2d'] = type_agreement(image, areas, tables)
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
    return {'format': 1, 'rows': rows,
            'independent_pairs': len(independent),
            'note': ('Nur role=test zählt als unabhängig. Präzision nur bei vollständiger Referenz. '
                     'Gruppen = nahezu identische Softwarestände.')}


def markdown(result: dict) -> str:
    head = ('| Paar | Familie | Rolle | Gruppe | Ref 2D | gefunden | Recall | exakt | Typ richtig | Achsen richtig | '
            'Präzision | FP | FN | Ref 1D | exakt 1D | s | MB |\n|' + '---|' * 17)
    out = [head]
    for r in result['rows']:
        prec = f"{r['precision_2d']:.0%}" if r['complete_reference'] else '–'
        mb = r['peak_mb'] if r['peak_mb'] is not None else '–'
        fp = r.get('false_positives_2d', '–'); fn = r.get('false_negatives_2d', '–')
        out.append(f"| {r['name']} | {r['family']} | {r['role']} | {r['group']} | {r['reference_2d']} | "
                   f"{r['found_2d']} | {r['recall_2d']:.0%} | {r['exact_2d']} | {r.get('type_exact_2d', '–')} | {r['axes_correct']}/{r['with_axes']} | "
                   f"{prec} | {fp} | {fn} | {r['reference_1d']} | {r['exact_1d']} | {r['seconds']} | {mb} |")
    return '\n'.join(out)


def main(argv=None):
    from ecu_studio.core import parallel
    parallel.enable()   # guarded entry point: scans may use several CPU cores
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--markdown', type=Path)
    parser.add_argument('--memory', action='store_true', help='Spitzenspeicher in einem zweiten Lauf messen')
    args = parser.parse_args(argv)
    result = run(json.loads(args.manifest.read_text(encoding='utf-8')), memory=args.memory)
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    table = markdown(result)
    if args.markdown:
        args.markdown.write_text(table + '\n', encoding='utf-8')
    print(table)


if __name__ == '__main__':
    main()
