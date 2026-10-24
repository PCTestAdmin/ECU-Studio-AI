"""Hash-locked local detection benchmark plus exhaustive per-map miss report.

python -m ecu_studio.tools.validation_report LOCAL.json --out RESULT.json --markdown RESULT.md
Private inputs stay local; reports contain public aliases, hashes and metrics.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

from ecu_studio.core.reference_manifest import load_manifest, write_report
from ecu_studio.tools import benchmark_suite, miss_analysis


def run(entries, *, memory=False, limits=False):
    # Check every cross-role pair, not only greedy group representatives. This
    # also rejects a near-identical bridge between two declared groups.
    data = [Path(e['bin']).read_bytes() for e in entries]
    for i, a in enumerate(entries):
        if hashlib.sha256(data[i]).hexdigest() != a['sha256']:
            raise ValueError('Firmware changed since manifest validation')
        for j in range(i):
            if a['role'] != entries[j]['role'] and benchmark_suite.similarity(data[i], data[j]) >= benchmark_suite.SAME_IMAGE:
                raise ValueError('Near-identical firmware split across training/development/test')
    del data
    # The original benchmark remains the single source of detection metrics.
    result = benchmark_suite.run(entries, memory=memory)
    # Near-identical binaries may not be split across declared independence groups.
    group_roles = {}
    for row in result['rows']:
        previous = group_roles.setdefault(row['group'], row['role'])
        if previous != row['role']:
            raise ValueError('Near-identical firmware split across training/development/test')
    for row, entry in zip(result['rows'], entries):
        row.update(software=entry['software'], reference_sha256=entry['reference_sha256'],
                   data_kind=entry['data_kind'], declared_group=entry['group'])
    result['miss_analysis'] = [miss_analysis.run_pair(e, limits=limits) for e in entries]
    # An input modified during the run must not produce a hash-locked report.
    for e in entries:
        for key, digest in (('bin', 'sha256'), ('reference', 'reference_sha256')):
            if hashlib.sha256(Path(e[key]).read_bytes()).hexdigest() != e[digest]:
                raise ValueError('Reference inputs changed during validation')
    result['independent_pairs'] = sum(e['role'] == 'test' and e['data_kind'] == 'real' for e in entries)
    result['synthetic_pairs'] = sum(e['data_kind'] == 'synthetic' for e in entries)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--markdown', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--memory', action='store_true')
    parser.add_argument('--limits', action='store_true')
    args = parser.parse_args(argv)
    try:
        entries = load_manifest(args.manifest)
        outputs = [args.out.resolve(), args.markdown.resolve()]
        protected = [args.manifest, *([args.baseline] if args.baseline else [])]
        inputs = {Path(p).resolve() for p in protected + [e[k] for e in entries for k in ('bin', 'reference')]}
        if len(set(outputs)) != 2 or any(p in inputs for p in outputs):
            raise ValueError('Report destinations must be distinct from every input')
        result = run(entries, memory=args.memory, limits=args.limits)
        table = benchmark_suite.markdown(result) + '\n\n' + miss_analysis.markdown(result['miss_analysis'])
        if args.baseline:
            result['comparison'] = benchmark_suite.compare_runs(json.loads(args.baseline.read_text(encoding='utf-8')), result)
            table += '\n\n' + benchmark_suite.comparison_markdown(result['comparison'])
        write_report(args.out, json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), entries, protected=protected)
        write_report(args.markdown, table + '\n', entries, protected=protected)
        encoding = sys.stdout.encoding or 'utf-8'
        print(table.encode(encoding, errors='backslashreplace').decode(encoding))
        return 0
    except (ValueError, OSError):
        # OSError / decoder messages can include private absolute file paths.
        print('Validation failed: check local manifest, hashes, roles and output destinations.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
