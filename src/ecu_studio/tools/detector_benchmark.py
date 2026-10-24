"""Opt-in detector comparison using the existing locked validation and scoring.

python -m ecu_studio.tools.detector_benchmark LOCAL.json --out RESULT.json --markdown RESULT.md --memory
No experimental detector is activated in the application. Full reports stay local.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from ecu_studio.core.experimental_detectors import (scan_pointer_chains, scan_aligned_records,
                                                    combine_conservatively)
from ecu_studio.core.reference_manifest import load_manifest, write_report
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.tools import benchmark_suite, validation_report

ALGORITHMS = {
    'pointer-chain': (scan_pointer_chains, {
        'project': 'BimmerStein Bin Analyzer', 'repository': 'https://github.com/CAATZ/bimmerstein-bin-analyzer',
        'source_commit': 'd3e292169680cc56707c3b60337dddcad090c622',
        'source_file': 'packages/engine/src/structural.ts', 'source_license': 'GPL-3.0-or-later',
        'scope': 'direct u16LE offsets, <=64 KiB; strict counted axes; >=3 packed headers',
    }),
    'aligned-record': (scan_aligned_records, {
        'project': 'xdfkit', 'repository': 'https://github.com/nyetlabs/xdfkit',
        'source_commit': 'a8f985358bc3167b60552ddeba96fa65a4c29a1a',
        'source_file': 'lint/record.go', 'source_license': 'LGPL-3.0-or-later',
        'scope': 'C16x-addressed byte-count records; mixed/aligned little-endian axes; exact next record',
    }),
}


def _bind(report, entries, independent):
    for row, e in zip(report['rows'], entries):
        if row['sha256'] != e['sha256']:
            raise ValueError('Firmware changed between comparison modes')
        row.update({k: e[k] for k in ('software', 'reference_sha256', 'data_kind')})
    report['independent_pairs'] = independent
    return report


def run(entries, *, algorithms=None, memory=False):
    names = tuple(ALGORITHMS) if algorithms is None else tuple(algorithms)
    if not names or len(set(names)) != len(names) or any(n not in ALGORITHMS for n in names):
        raise ValueError('Choose distinct built-in experimental algorithms')
    # Reuse role/hash/near-identity checks, baseline scoring and complete miss analysis.
    baseline = validation_report.run(entries, memory=memory)
    experiments = []
    for name in names:
        scanner, source = ALGORITHMS[name]
        diagnostics = {}
        def experiment(image):
            d = {}; maps = scanner(image, diagnostics=d)
            diagnostics[image.digest] = d
            if d.get('incomplete'): raise ValueError('Experimental resource budget exceeded')
            return maps
        merges = {}
        def combined(image):
            base = scan_calibration_candidates(image, use_definitions=False)
            extra = experiment(image)
            d = {}; result = combine_conservatively(base, extra, diagnostics=d)
            merges[image.digest] = d
            return result
        isolated = _bind(benchmark_suite.run(entries, memory=memory, detector=experiment), entries, baseline['independent_pairs'])
        together = _bind(benchmark_suite.run(entries, memory=memory, detector=combined), entries, baseline['independent_pairs'])
        compared = benchmark_suite.compare_runs(baseline, together)
        for p, entry in zip(compared['pairs'], entries):
            p['evidence_level'] = ('synthetic mechanism only' if entry['data_kind'] == 'synthetic'
                                   else 'independent reference sample' if entry['role'] == 'test'
                                   else 'development or training reference; not independent')
            if entry['data_kind'] == 'synthetic': p['production_verdict'] = 'not established by synthetic data'
            elif not entry['complete']: p['production_verdict'] = 'precision unknown: incomplete reference'
            else: p['production_verdict'] = 'requires cross-family independent validation and calibration'
        experiments.append({'algorithm': dict(source, id=name, implementation='independent Python adaptation v1',
                                              production_enabled=False),
                            'isolated': isolated, 'combined': together, 'comparison': compared,
                            'diagnostics_by_sha256': diagnostics, 'merge_by_sha256': merges})
    for e in entries:
        for key, digest in (('bin', 'sha256'), ('reference', 'reference_sha256')):
            if hashlib.sha256(Path(e[key]).read_bytes()).hexdigest() != e[digest]:
                raise ValueError('Inputs changed during experimental comparison')
    return {'format': 1, 'baseline': baseline, 'experiments': experiments,
            'note': 'Existing IoU precision/recall and exact-layout definition. Python allocation peak, not RSS. '
                    'No promotion, voting or production scanner change. Input paths and firmware bytes excluded.'}


def markdown(result):
    lines = ['# Experimental detector comparison', '',
             'Exact layouts and IoU precision/recall are different metrics. Experimental results are unverified.', '',
             benchmark_suite.markdown(result['baseline'])]
    for e in result['experiments']:
        a = e['algorithm']
        lines.extend(['', f"## {a['id']} ({a['project']}, {a['source_commit']})", '', a['scope'], '',
                      '### Experiment only', '', benchmark_suite.markdown(e['isolated']), '',
                      '### Conservative combination', '', benchmark_suite.markdown(e['combined']), '',
                      benchmark_suite.comparison_markdown(e['comparison'])])
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--markdown', type=Path, required=True)
    parser.add_argument('--algorithm', action='append', choices=tuple(ALGORITHMS))
    parser.add_argument('--memory', action='store_true')
    args = parser.parse_args(argv)
    try:
        entries = load_manifest(args.manifest)
        protected = {args.manifest.resolve(), *(Path(e[k]).resolve() for e in entries for k in ('bin', 'reference'))}
        destinations = {args.out.resolve(), args.markdown.resolve()}
        if len(destinations) != 2 or protected & destinations:
            raise ValueError('Outputs must be distinct from all inputs')
        result = run(entries, algorithms=args.algorithm, memory=args.memory)
        table = markdown(result)
        write_report(args.out, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), entries, protected=protected)
        write_report(args.markdown, table, entries, protected=protected)
        encoding = sys.stdout.encoding or 'utf-8'
        print(table.encode(encoding, errors='backslashreplace').decode(encoding))
        return 0
    except (ValueError, OSError):
        print('Comparison failed: check local inputs, hashes, roles, detector limits and output destinations.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
