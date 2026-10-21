"""Validate an ECU family with one local BIN + matching definition: identity, detection, data type.

Usage:
  python -m ecu_studio.tools.validate_pair ORIGINAL.bin DEFINITION.a2l|xdf --family "Bosch MG1CS002"
         [--anchor 0x80000000] [--role test|development|training] [--complete] [--results ergebnisse.json]

Prints what the file says about itself (identification), the measured detection
quality (benchmark_suite metrics) and appends the row to a results file. The
support matrix and docs are then regenerated from all result files:
  python -m ecu_studio.tools.support_matrix ergebnisse.json [...] --markdown docs-matrix.md

Only counts are written - no firmware bytes, no definition contents. Use only
files you may lawfully use; they never go into the repository.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.identification import identify
from ecu_studio.core.support import lookup
from ecu_studio.tools.benchmark_suite import run


def validate(bin_path: str, reference: str, family: str, *, anchor: str | None = None, role: str = 'test',
             complete: bool = False) -> dict:
    image = BinaryImage.from_file(bin_path)
    ident = identify(image)
    entry = {'name': f'{family} {Path(bin_path).stem}', 'family': family, 'bin': bin_path, 'reference': reference,
             'complete': complete, 'role': role}
    if anchor:
        entry['anchor'] = anchor
    row = run([entry])['rows'][0]
    known = lookup(ident.family)
    return {'row': row, 'identity': ident.summary(), 'identified_family': ident.family,
            'matrix_entry': known.family if known else None, 'matrix_status': known.status if known else None}


def main(argv=None) -> int:
    from ecu_studio.core import parallel
    parallel.enable()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('bin'); p.add_argument('reference')
    p.add_argument('--family', required=True, help='Name der Familie, wie in der Matrix (z. B. "Bosch MG1CS002")')
    p.add_argument('--anchor', help='A2L-Speicheradresse des Dateianfangs (sonst automatisch)')
    p.add_argument('--role', default='test', choices=('test', 'development', 'training'))
    p.add_argument('--complete', action='store_true', help='Referenz enthält ALLE Kennfelder (Hersteller-A2L)')
    p.add_argument('--results', type=Path, default=Path('validierung.json'))
    a = p.parse_args(argv)
    out = validate(a.bin, a.reference, a.family, anchor=a.anchor, role=a.role, complete=a.complete)
    r = out['row']
    print(f"Kennung in der Datei: {out['identity']}")
    print(f"Matrix bisher: {out['matrix_entry'] or 'kein Eintrag'} ({out['matrix_status'] or '–'})")
    line = f"Gemessen: {r['exact_2d']} von {r['reference_2d']} Kennfeldern exakt, Typ richtig {r['type_exact_2d']}, " \
           f"Achsen richtig {r['axes_correct']}/{r['with_axes']}, 1D exakt {r['exact_1d']}, {r['seconds']} s"
    if r.get('precision_2d') is not None:
        line += f", Präzision {r['precision_2d']:.0%}, Fehlfunde {r['false_positives_2d']}"
    print(line)
    results = json.loads(a.results.read_text(encoding='utf-8')) if a.results.exists() else {'format': 1, 'rows': []}
    results['rows'] = [x for x in results['rows'] if x['sha256'] != r['sha256']] + [r]
    a.results.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'Gespeichert in {a.results} – Matrix neu erzeugen: python -m ecu_studio.tools.support_matrix {a.results} …')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
