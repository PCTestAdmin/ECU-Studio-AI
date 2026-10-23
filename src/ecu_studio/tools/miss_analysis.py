"""Why reference maps are missed: per-cause counts for BIN/reference pairs.

Usage: python -m ecu_studio.tools.miss_analysis MANIFEST.json [--out misses.json] [--markdown misses.md] [--limits]

Same manifest as tools/benchmark_suite. Each reference map (2-D, >= 4 x 4) that is
not found exactly gets ONE outcome (what the scan produced there) and any number
of structural attributes (why it may be hard). Only counts and offsets are
written; no firmware bytes.

Outcomes:
  kein Kandidat        no 2-D candidate overlaps >= 50 % of the map
  falscher Start       overlapped, but no candidate starts at the map
  falsche Größe        same start, other rows x cols
  falsche Zellbreite   same start and size, other cell width

Attributes:
  Achsen getrennt      the reference stores an axis away from the map (not a header in front)
  gemeinsame Achse     the map shares a stored axis with another reference map
  gleiche Geometrie    a neighbouring reference map (<= 1 KiB) has the same rows x cols x width
  flache Werte         fewer than 4 distinct values: no surface evidence possible
  Code-Verweis         the start is referenced by C16x page+offset loads (C16x images only)
  Ergebnislimit        found exactly when the scan runs with 10x larger limits (--limits)
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np
from ecu_studio.core.axis_groups import group_index, shared_axis_groups
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.structure_scan import c16x_reference_positions
from ecu_studio.tools.structure_benchmark import reference_tables

OUTCOMES = ('kein Kandidat', 'falscher Start', 'falsche Größe', 'falsche Zellbreite')
ATTRIBUTES = ('Achsen getrennt', 'gemeinsame Achse', 'gleiche Geometrie', 'flache Werte', 'Code-Verweis',
              'Ergebnislimit')
HEADER_REACH = 256    # an axis this close in front of the map counts as its record header


def _key(m: MapDefinition):
    return m.offset, frozenset((m.rows, m.cols)), m.width


def outcome(r: MapDefinition, found: list[MapDefinition]) -> str | None:
    """None if found exactly, else the outcome class."""
    lo, hi = r.offset, r.offset + r.length
    same_start = [m for m in found if m.offset == r.offset]
    if any({m.rows, m.cols} == {r.rows, r.cols} and m.width == r.width for m in same_start):
        return None
    if any({m.rows, m.cols} == {r.rows, r.cols} for m in same_start):
        return 'falsche Zellbreite'
    if same_start:
        return 'falsche Größe'
    overlap = max((min(hi, m.offset + m.length) - max(lo, m.offset) for m in found), default=0)
    return 'falscher Start' if overlap >= .5 * (hi - lo) else 'kein Kandidat'


def analyse(image: BinaryImage, reference: list[MapDefinition], found: list[MapDefinition],
            wide: list[MapDefinition] | None = None) -> dict:
    areas = [m for m in found if min(m.rows, m.cols) > 1]
    wide_keys = {_key(m) for m in wide} if wide is not None else None
    in_group = group_index(shared_axis_groups(reference))
    data = image.read(0, image.size)
    lo, hi = min((m.offset for m in reference), default=0), max((m.offset + m.length for m in reference), default=0)
    refs = c16x_reference_positions(data, 0, image.size) if reference else {}
    shapes = sorted((m.offset, m.rows, m.cols, m.width) for m in reference)
    misses, outcomes, attributes = [], Counter(), Counter()
    for i, r in enumerate(reference):
        result = outcome(r, areas)
        if result is None:
            continue
        attrs = []
        for at in (r.axis_x_offset, r.axis_y_offset):
            if at is not None and not r.offset - HEADER_REACH <= at < r.offset:
                attrs.append('Achsen getrennt')
                break
        if i in in_group:
            attrs.append('gemeinsame Achse')
        if any(o != r.offset and abs(o - r.offset) <= 1024 and (rr, cc, w) == (r.rows, r.cols, r.width)
               for o, rr, cc, w in shapes):
            attrs.append('gleiche Geometrie')
        if np.unique(image.matrix(r)).size < 4:
            attrs.append('flache Werte')
        if r.offset in refs:
            attrs.append('Code-Verweis')
        if wide_keys is not None and _key(r) in wide_keys:
            attrs.append('Ergebnislimit')
        outcomes[result] += 1
        attributes.update(attrs)
        misses.append({'offset': r.offset, 'rows': r.rows, 'cols': r.cols, 'width': r.width,
                       'outcome': result, 'attributes': attrs})
    combos = Counter(' + '.join(m['attributes']) or '(keins)' for m in misses)
    return {'reference_2d': len(reference), 'missed': len(misses), 'outcomes': dict(outcomes),
            'attributes': dict(attributes), 'combinations': dict(combos.most_common(12)), 'misses': misses,
            'scope': [lo, hi]}


def run_pair(entry: dict, limits: bool = False) -> dict:
    image = BinaryImage.from_file(entry['bin'])
    anchor = int(entry['anchor'], 0) if isinstance(entry.get('anchor'), str) else entry.get('anchor')
    reference = reference_tables(entry['reference'], image, anchor=anchor)
    found = scan_calibration_candidates(image, use_definitions=False)
    wide = None
    if limits:
        wide = scan_calibration_candidates(image, use_definitions=False, limits=(700, 400, 300, 250),
                                           structure_limit=4000)
        wide = [m for m in wide if min(m.rows, m.cols) > 1]
    result = analyse(image, reference, found, wide)
    result.update(name=entry['name'], family=entry['family'], role=entry.get('role', 'development'))
    return result


def markdown(rows: list[dict]) -> str:
    head = ('| Paar | Rolle | Ref 2D | verfehlt | ' + ' | '.join(OUTCOMES) + ' | ' + ' | '.join(ATTRIBUTES) +
            ' |\n|' + '---|' * (4 + len(OUTCOMES) + len(ATTRIBUTES)))
    out = [head]
    for r in rows:
        out.append(f"| {r['name']} | {r['role']} | {r['reference_2d']} | {r['missed']} | " +
                   ' | '.join(str(r['outcomes'].get(k, 0)) for k in OUTCOMES) + ' | ' +
                   ' | '.join(str(r['attributes'].get(k, 0)) for k in ATTRIBUTES) + ' |')
    return '\n'.join(out)


def main(argv=None):
    from ecu_studio.core import parallel
    parallel.enable()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--markdown', type=Path)
    parser.add_argument('--limits', action='store_true', help='zweiter Lauf mit 10-fachen Grenzen (langsam)')
    args = parser.parse_args(argv)
    rows = [run_pair(e, args.limits) for e in json.loads(args.manifest.read_text(encoding='utf-8'))]
    if args.out:
        args.out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    table = markdown(rows)
    if args.markdown:
        args.markdown.write_text(table + '\n', encoding='utf-8')
    print(table)


if __name__ == '__main__':
    main()
