"""Build the labelled data set for the data-only candidate scorer, with provenance.

Usage: python -m ecu_studio.tools.build_candidate_dataset MANIFEST.json OUT.jsonl

Manifest: the benchmark_suite format (name, family, bin, reference, complete,
role) plus optional "group", "source" and "license". Writes OUT.jsonl (one row
per candidate: family, group, pair, role, complete, cls, y, x) and
OUT.meta.json (tool and app version, feature list, per pair: SHA-256 of BIN and
reference, source, licence, role, counts; SHA-256 of the JSONL). No firmware
bytes and no names from the definitions are written - only features and labels.

Rules that keep the data honest:
- The scan runs WITHOUT bundled definitions (they would leak the labels, e.g.
  the MS43 XDF) and WITHOUT the shipped scorer (its drop threshold would bias
  the candidate set towards what the old model already liked).
- Label y = the candidate starts exactly at a reference object (as in 1.16).
- Rows of partial references keep complete=false: their negatives are not
  known to be negatives, so the trainer leaves them out by default.
- The role is copied from the manifest; the trainer never fits on role "test".
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from ecu_studio import __version__
from ecu_studio.core import scoped_scan
from ecu_studio.core.candidate_features import FEATURES, candidate_features
from ecu_studio.core.candidate_model import DATA_ONLY_CLASSES
from ecu_studio.core.confidence import evidence_class
from ecu_studio.core.data_regions import data_mask
from ecu_studio.core.model import BinaryImage
from ecu_studio.tools.structure_benchmark import _reference

FORMAT = 1


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pair_rows(pair: dict) -> list[dict]:
    """Candidate rows of one BIN/reference pair (scan without definitions and without the scorer)."""
    image = BinaryImage.from_file(pair['bin'])
    anchor = int(pair['anchor'], 16) if pair.get('anchor') else None
    starts = {m.offset for m in _reference(pair['reference'], image, anchor)}
    model = scoped_scan.load_model
    scoped_scan.load_model = lambda: None
    try:
        candidates = scoped_scan.scan_calibration_candidates(image, use_definitions=False)
    finally:
        scoped_scan.load_model = model
    mask = data_mask(image.read(0, image.size))
    rows = []
    for m in candidates:
        cls = evidence_class(m)
        if m.source != 'heuristic' or cls not in DATA_ONLY_CLASSES:
            continue
        x = candidate_features(image, m, mask)
        if x is None:
            continue
        rows.append({'family': pair['family'], 'group': pair.get('group') or pair['name'], 'pair': pair['name'],
                     'role': pair.get('role', 'development'), 'complete': bool(pair.get('complete')),
                     'cls': cls, 'y': int(m.offset in starts), 'x': [round(float(v), 6) for v in x]})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    lines, pairs = [], []
    for pair in manifest:
        rows = pair_rows(pair)
        lines += [json.dumps(r, ensure_ascii=False) for r in rows]
        pairs.append({k: pair.get(k) for k in ('name', 'family', 'group', 'role', 'complete', 'source', 'license')}
                     | {'bin_sha256': _sha(pair['bin']), 'reference_sha256': _sha(pair['reference']),
                        'rows': len(rows), 'positives': sum(r['y'] for r in rows)})
        print(f"{pair['name']}: {len(rows)} Kandidaten, {pairs[-1]['positives']} Treffer", flush=True)
    text = '\n'.join(lines) + '\n'
    args.out.write_text(text, encoding='utf-8')
    meta = {'format': FORMAT, 'created': datetime.datetime.now().isoformat(timespec='seconds'),
            'app_version': __version__, 'features': list(FEATURES), 'classes': list(DATA_ONLY_CLASSES),
            'label': 'Kandidat beginnt exakt an einem Referenzobjekt', 'pairs': pairs,
            'data_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'firmware_bytes_included': False}
    args.out.with_suffix('.meta.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding='utf-8')
    print('Datensatz:', args.out, '·', len(lines), 'Zeilen · SHA-256', meta['data_sha256'][:16])


if __name__ == '__main__':
    main()
