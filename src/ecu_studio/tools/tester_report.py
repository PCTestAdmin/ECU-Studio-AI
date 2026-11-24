"""Local tester report: measure detection, axis references and function identification on one's own file
with its own definition, and export only aggregated counts after preview and consent (quality phase 3).

Usage:
  python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l|xdf|csv --line "Bosch MEVD17.2"
         [--anchor 0x80000000]
      -> measures locally and prints the COMPLETE export as a preview, plus a consent code. Writes nothing.
  python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l --line "..." --export report.json --consent CODE
      -> measures again and writes the export only when CODE belongs to exactly this content.

What the export contains: counts (detection against the definition, axis references by status, function
identification under anchor splits), the program version and the line name the tester typed in.
What it never contains: firmware bytes, definition contents, map / axis / function names, addresses,
file names, file sizes, hashes, paths or time stamps. Run time is rounded to whole seconds.

Everything runs locally; nothing is sent anywhere. The tester decides whether and to whom to pass the
file on. Use only files you may lawfully use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

FORMAT = 'ecu-studio-tester-report/1'
DETECTION_KEYS = ('reference_2d', 'found_2d', 'exact_2d', 'type_exact_2d', 'with_axes', 'axes_correct',
                  'axis_address_with_2d', 'axis_address_correct_2d', 'group_pairs_reference', 'group_pairs_found',
                  'group_pairs_agree', 'reference_1d', 'found_1d', 'exact_1d')
SPLITS = (('table', .5), ('table', .25), ('table', .1), ('table', .05), ('table', .01), ('block', .5),
          ('function', .5))
SALTS = ('0', '1', '2')
SCORE_KEYS = ('evaluable', 'reachable', 'correct', 'wrong', 'unknown', 'withheld')


def _reference_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {'.a2l': 'a2l', '.xdf': 'xdf', '.csv': 'csv'}.get(suffix, 'other')


def function_counts(maps) -> dict:
    """Function identification under anchor splits (tools/function_benchmark), three salts summed."""
    from ..core import function_id as F
    from . import function_benchmark as B
    rels = F.relations(maps)
    out = {'tables_with_function': sum(1 for m in maps if B.truth_of(m)),
           'functions': len({f for m in maps for f in B.truth_of(m)})}
    for mode, fraction in SPLITS:
        total = B.Score()
        for salt in SALTS:
            total.add(B.score(maps, B.split(maps, mode, fraction, salt), rels))
        out[f'{mode}@{fraction:g}'] = {k: getattr(total, k) for k in SCORE_KEYS}
    return out


def measure(bin_path: str, reference: str, line: str, *, anchor: str | None = None) -> dict:
    """The complete export (aggregated counts only)."""
    from .. import __version__
    from ..core import axis_refs
    from ..core.model import BinaryImage
    from .benchmark_suite import run
    from .structure_benchmark import _reference
    entry = {'name': 'tester', 'family': line, 'bin': bin_path, 'reference': reference, 'role': 'test'}
    if anchor:
        entry['anchor'] = anchor
    row = run([entry])['rows'][0]
    image = BinaryImage.from_file(bin_path)
    maps = [m for m in _reference(reference, image, int(anchor, 0) if anchor else None) if m.rows * m.cols >= 2]
    return {'format': FORMAT, 'version': __version__, 'line': line, 'reference_kind': _reference_kind(reference),
            'detection': {k: row.get(k) for k in DETECTION_KEYS} | {'seconds': round(row['seconds'])},
            'axis_references': axis_refs.summary(maps),
            'function_identification': function_counts(maps),
            'note': 'Zählwerte einer lokalen Messung; keine Namen, Adressen, Hashes oder Dateiinhalte.'}


def canonical(report: dict) -> str:
    return json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True)


def consent_code(report: dict) -> str:
    """Short code bound to the exact content: a changed report needs a new preview."""
    return hashlib.sha256(canonical(report).encode('utf-8')).hexdigest()[:10]


FORBIDDEN = ('sha256', 'digest', 'offset', 'address', 'name', 'path', 'size', 'bin', 'file')


def check_private(report: dict) -> None:
    """Refuse an export that carries anything beyond counts (defence against later changes)."""
    def walk(x, where=''):
        if isinstance(x, dict):
            for k, v in x.items():
                if k.lower() in FORBIDDEN:
                    raise ValueError(f'Feld {where}{k} darf nicht exportiert werden')
                walk(v, f'{where}{k}.')
        elif isinstance(x, list):
            raise ValueError(f'Listen sind im Export nicht erlaubt ({where})')
        elif isinstance(x, str) and where not in ('format.', 'version.', 'line.', 'reference_kind.', 'note.'):
            raise ValueError(f'Text im Feld {where} darf nicht exportiert werden')
    walk(report)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('bin')
    p.add_argument('reference', help='eigene Definition (A2L / XDF / CSV) zu genau dieser Datei')
    p.add_argument('--line', required=True, help='Steuergerätelinie, wie sie im Bericht stehen soll')
    p.add_argument('--anchor', help='A2L-Speicheradresse des Dateianfangs (sonst automatisch)')
    p.add_argument('--export', type=Path, help='Datei für den Export (nur zusammen mit --consent)')
    p.add_argument('--consent', help='Zustimmungscode aus der Vorschau')
    a = p.parse_args(argv)
    report = measure(a.bin, a.reference, a.line, anchor=a.anchor)
    check_private(report)
    code = consent_code(report)
    if a.export is None:
        print('Vorschau – genau dieser Inhalt würde exportiert (sonst nichts):')
        print(canonical(report))
        print(f'\nNichts wurde gespeichert oder gesendet. Zum Export nach Prüfung: --export DATEI --consent {code}')
        return 0
    if a.consent != code:
        print('Zustimmungscode passt nicht zu diesem Inhalt. Erst die Vorschau ansehen (ohne --export).',
              file=sys.stderr)
        return 2
    if a.export.exists():
        print(f'{a.export} existiert bereits – wird nicht überschrieben.', file=sys.stderr)
        return 2
    a.export.write_text(canonical(report) + '\n', encoding='utf-8')
    print(f'Gespeichert: {a.export} (nur Zählwerte). Weitergabe entscheidest du selbst.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
