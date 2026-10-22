"""Validate an ECU family with one local BIN + matching definition: identity, detection, data type.

Usage:
  python -m ecu_studio.tools.validate_pair ORIGINAL.bin DEFINITION.a2l|xdf --family "Bosch MG1CS002"
         [--anchor 0x80000000] [--role test|development|training] [--complete] [--results ergebnisse.json]
  python -m ecu_studio.tools.validate_pair ORIGINAL.bin --family "Bosch MG1CS002"     (ohne Definition)

Without a definition nothing can be scored: the row records identification,
found candidates per confidence tier and run time, and the family becomes
'experimentell' (scanned on real firmware, no reference) - never 'validiert'.
Such rows are named by family and hash prefix, not by the file name (customer
files often carry a VIN or a name in the file name).

Prints what the file says about itself (identification), the measured detection
quality (benchmark_suite metrics) and appends the row to a results file. The
support matrix and docs are then regenerated from all result files:
  python -m ecu_studio.tools.support_matrix ergebnisse.json [...] --markdown docs-matrix.md

Only counts are written - no firmware bytes, no definition contents. Use only
files you may lawfully use; they never go into the repository.
"""
from __future__ import annotations
import argparse
import collections
import json
import time
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.identification import identify
from ecu_studio.core.support import lookup
from ecu_studio.tools.benchmark_suite import run


def checksum_summary(image: BinaryImage) -> dict:
    """Measure the actual checksum schemes on the original: Bosch MED17/EDC17
    blocks (CRC32/ADD32/ADD16) and the self-describing tables (ME7.x/MED9/ME9).

    Counts only — a structure is 'proven' when it reproduces the stored value on
    the unmodified file. This is a real checksum measurement, not the map-
    detection benchmark, so the validation command can report EDC17 coverage.
    """
    from ecu_studio.core.edc17_checksum import verify as edc17_verify
    from ecu_studio.core.edc16_checksum import verify as edc16_verify
    from ecu_studio.core.checksum_tables import original_blocks
    e = edc17_verify(image)
    d = edc16_verify(image)
    return {'edc17_blocks': e['blocks'], 'edc17_structures_total': e['structures_total'],
            'edc17_proven': e['proven_on_original'], 'edc17_unverifiable': e['unverifiable'],
            'edc17_coverage': e['coverage'], 'edc17_oem_validated': e['oem_validated'],
            'edc16_regions': d['regions'], 'edc16_proven': d['proven_on_original'],
            'edc16_coverage': d['coverage'], 'edc16_oem_validated': d['oem_validated'],
            'table_blocks_proven': len(original_blocks(image))}


def scan_only(bin_path: str, family: str, *, role: str = 'test') -> dict:
    """Identification and candidate counts of one image without any definition."""
    from ecu_studio.core.scoped_scan import scan_calibration_candidates
    image = BinaryImage.from_file(bin_path)
    ident = identify(image)
    begin = time.perf_counter()
    found = scan_calibration_candidates(image, use_definitions=False)
    elapsed = time.perf_counter() - begin
    areas = [m for m in found if min(m.rows, m.cols) > 1]
    name = f'{family} #{image.digest[:8]}'
    row = {'name': name, 'family': family, 'role': role, 'group': name, 'complete_reference': False,
           'no_reference': True, 'size': image.size, 'sha256': image.digest,
           'identified_family': ident.family, 'found_2d': len(areas), 'found_1d': len(found) - len(areas),
           'tiers_2d': dict(collections.Counter(m.evidence_tier or 'ohne' for m in areas)),
           'seconds': round(elapsed, 2)}
    row['checksums'] = checksum_summary(image)
    known = lookup(ident.family)
    return {'row': row, 'identity': ident.summary(), 'identified_family': ident.family,
            'matrix_entry': known.family if known else None, 'matrix_status': known.status if known else None}


def validate(bin_path: str, reference: str, family: str, *, anchor: str | None = None, role: str = 'test',
             complete: bool = False) -> dict:
    image = BinaryImage.from_file(bin_path)
    ident = identify(image)
    entry = {'name': f'{family} {Path(bin_path).stem}', 'family': family, 'bin': bin_path, 'reference': reference,
             'complete': complete, 'role': role}
    if anchor:
        entry['anchor'] = anchor
    row = run([entry])['rows'][0]
    row['checksums'] = checksum_summary(image)
    known = lookup(ident.family)
    return {'row': row, 'identity': ident.summary(), 'identified_family': ident.family,
            'matrix_entry': known.family if known else None, 'matrix_status': known.status if known else None}


def main(argv=None) -> int:
    from ecu_studio.core import parallel
    parallel.enable()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('bin')
    p.add_argument('reference', nargs='?', help='A2L / XDF / CSV; ohne: nur Kennung und Funde (experimentell)')
    p.add_argument('--family', required=True, help='Name der Familie, wie in der Matrix (z. B. "Bosch MG1CS002")')
    p.add_argument('--anchor', help='A2L-Speicheradresse des Dateianfangs (sonst automatisch)')
    p.add_argument('--role', default='test', choices=('test', 'development', 'training'))
    p.add_argument('--complete', action='store_true', help='Referenz enthält ALLE Kennfelder (Hersteller-A2L)')
    p.add_argument('--results', type=Path, default=Path('validierung.json'))
    a = p.parse_args(argv)
    if a.reference is None:
        out = scan_only(a.bin, a.family, role=a.role)
    else:
        out = validate(a.bin, a.reference, a.family, anchor=a.anchor, role=a.role, complete=a.complete)
    r = out['row']
    print(f"Kennung in der Datei: {out['identity']}")
    print(f"Matrix bisher: {out['matrix_entry'] or 'kein Eintrag'} ({out['matrix_status'] or '–'})")
    if a.reference is None:
        line = (f"Ohne Definition: {r['found_2d']} Kennfeld- und {r['found_1d']} Kennlinien-Kandidaten, "
                f"Konfidenz {r['tiers_2d']}, {r['seconds']} s – nicht bewertbar (experimentell)")
    else:
        line = f"Gemessen: {r['exact_2d']} von {r['reference_2d']} Kennfeldern exakt, Typ richtig {r['type_exact_2d']}, " \
               f"Achsen richtig {r['axes_correct']}/{r['with_axes']}, 1D exakt {r['exact_1d']}, {r['seconds']} s"
        if r.get('precision_2d') is not None:
            line += f", Präzision {r['precision_2d']:.0%}, Fehlfunde {r['false_positives_2d']}"
    print(line)
    cs = r.get('checksums', {})
    if cs:
        print(f"Prüfsummen: EDC17/MED17 {cs['edc17_proven']}/{cs['edc17_structures_total']} Strukturen am Original "
              f"nachgewiesen (Abdeckung {cs['edc17_coverage']}, {cs['edc17_blocks']} Blöcke, "
              f"{cs['edc17_unverifiable']} nicht prüfbar, OEM {'ja' if cs['edc17_oem_validated'] else 'nein'}); "
              f"EDC16 {cs['edc16_proven']}/{cs['edc16_regions']} Bereiche ({cs['edc16_coverage']}, "
              f"OEM {'ja' if cs['edc16_oem_validated'] else 'nein'}); selbstbeschreibende Tabellen {cs['table_blocks_proven']}")
    results = json.loads(a.results.read_text(encoding='utf-8')) if a.results.exists() else {'format': 1, 'rows': []}
    results['rows'] = [x for x in results['rows'] if x['sha256'] != r['sha256']] + [r]
    a.results.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'Gespeichert in {a.results} – Matrix neu erzeugen: python -m ecu_studio.tools.support_matrix {a.results} …')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
