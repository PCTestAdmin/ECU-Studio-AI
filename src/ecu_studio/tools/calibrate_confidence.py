"""Measure hit rates per evidence class on BIN/definition pairs with complete references.

A candidate counts as a hit when it starts exactly at an object of the
reference definition (table, curve or axis of any size). Use only definitions
that cover a family completely; partial XDFs understate the rates.

Usage: python -m ecu_studio.tools.calibrate_confidence --pair BIN XDF|A2L[@ANCHOR] [--pair ...] [--out FILE]
Writes counts and hashes only, no firmware bytes.
"""
from __future__ import annotations
import argparse
import collections
import datetime
import json
from pathlib import Path
from ecu_studio.core.confidence import DATA, evidence_class
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.profiles import identify_profile
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.tools.structure_benchmark import _reference


def measure(pairs) -> dict:
    """Rates per evidence class, pooled and per ECU family (profile family name;
    'Unbekannt' collects images without a known profile)."""
    counts = collections.defaultdict(lambda: [0, 0, set()])
    by_family = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    sources = []
    for bin_path, ref_path in pairs:
        image = BinaryImage.from_file(bin_path)
        family = identify_profile(image).family
        # 'file.a2l@0x8000' gives the A2L anchor explicitly (e.g. converted HEX images).
        anchor = None
        if '@' in Path(ref_path).name:
            ref_path, _, at = ref_path.rpartition('@')
            anchor = int(at, 0)
        starts = {m.offset for m in _reference(ref_path, image, anchor)}
        if Path(ref_path).suffix.lower() == '.xdf':
            # Axes referenced by tables count as reference objects too.
            from ecu_studio.core.xdf import xdf_axis_offsets
            starts |= xdf_axis_offsets(ref_path)
        for m in scan_calibration_candidates(image, use_definitions=False):
            if m.source != 'heuristic':
                continue
            cls, hit = evidence_class(m), m.offset in starts
            row = counts[cls]
            row[0] += 1; row[1] += hit; row[2].add(family)
            fam = by_family[family][cls]
            fam[0] += 1; fam[1] += hit
        sources.append({'sha256': image.digest, 'family': family, 'reference': Path(ref_path).name})
    def table(rows):
        return {k: {'n': n, 'hits': h, 'rate': round(h / n, 4)} for k, (n, h) in sorted(rows.items())}
    return {'format': 2, 'measured_on': datetime.date.today().isoformat(),
            'definition': 'share of candidates starting exactly at a reference object',
            'sources': sources,
            'classes': {k: {'n': n, 'hits': h, 'rate': round(h / n, 4), 'families': sorted(f)}
                        for k, (n, h, f) in sorted(counts.items())},
            'families': {fam: table({k: tuple(v) for k, v in rows.items()}) for fam, rows in sorted(by_family.items())}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', nargs=2, action='append', required=True, metavar=('BIN', 'REF'))
    parser.add_argument('--out', type=Path, default=DATA)
    args = parser.parse_args(argv)
    result = measure(args.pair)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    for k, row in result['classes'].items():
        print(f"{k:22s} n={row['n']:4d} rate={row['rate']:.0%}")


if __name__ == '__main__':
    main()
