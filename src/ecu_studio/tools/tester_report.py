"""Local tester report: measure detection, axis references and function identification on one's own file
with its own definition, and export only aggregated counts after preview and consent (quality phases 3/4).

Guided (no programming knowledge needed; asks for the two files and the line, shows the preview, asks for
consent):
  python -m ecu_studio.tools.tester_report --assistent

Scripted:
  python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l|xdf|csv --line "Bosch MEVD17.2"
         [--anchor 0x80000000] [--exakt]
      -> measures locally and prints the COMPLETE export as a preview, plus a consent code. Writes nothing.
  python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l --line "..." --export report.json --consent CODE
      -> measures again and writes the export only when CODE belongs to exactly this content.

What the export contains: counts (detection against the definition, axis references by status, function
identification under anchor splits), the program version and the line name the tester typed in (checked:
no software numbers, paths or file names). Counts from 100 upwards are rounded to two significant digits
unless --exakt is given: exact totals (e.g. the number of tables in a definition) together with line and
version can point to one particular software version, above all when only a few people send reports.
What it never contains: firmware bytes, definition contents, map / axis / function names, addresses,
file names, file sizes, hashes, paths or time stamps. Run time is rounded to whole seconds.

Everything runs locally; nothing is sent anywhere, and the tool has no network code. The tester decides
whether and to whom to pass the file on. Use only files you may lawfully use. A report made with this
tool is one tester's own measurement, not an independent validation of ECU Studio.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import re
import sys
import warnings
from pathlib import Path

FORMAT = 'ecu-studio-tester-report/2'
DETECTION_KEYS = ('reference_2d', 'found_2d', 'exact_2d', 'type_exact_2d', 'with_axes', 'axes_correct',
                  'axis_address_with_2d', 'axis_address_correct_2d', 'group_pairs_reference', 'group_pairs_found',
                  'group_pairs_agree', 'reference_1d', 'found_1d', 'exact_1d')
SPLITS = (('table', .5), ('table', .25), ('table', .1), ('table', .05), ('table', .01), ('block', .5),
          ('function', .5))
SALTS = ('0', '1', '2')
SCORE_KEYS = ('evaluable', 'reachable', 'correct', 'wrong', 'unknown', 'withheld')
ROUND_FROM = 100          # counts below stay exact (they do not single out a software version)
NOTE = ('Zählwerte einer lokalen Messung eines Testers; keine Namen, Adressen, Hashes oder Dateiinhalte. '
        'Keine unabhängige Validierung.')
PRIVACY_WARNING = (
    'Hinweis zur Wiedererkennbarkeit: Auch reine Zählwerte können zusammen mit Linie und Programmversion auf '
    'einen bestimmten Softwarestand oder auf dich hindeuten, besonders wenn nur wenige Personen Berichte '
    'abgeben. Deshalb sind Werte ab 100 standardmäßig gerundet. Gib den Bericht nur weiter, wenn du damit '
    'einverstanden bist.')

# The line is the only free text in the export: short, plain characters, nothing that looks like a part or
# software number, a VIN, an address, a path or one of the tester's own file names.
LINE_ALLOWED = re.compile(r"[A-Za-z0-9 .,+/()_-]{2,40}")
LINE_NUMBER = re.compile(r"\d{6,}|0x[0-9a-f]+|[0-9a-f]{8,}", re.IGNORECASE)
LINE_VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")


class TesterError(Exception):
    """A refusal the tester can read; the message never contains paths or file contents."""


def check_line(line: str, *files: str) -> str:
    """The cleaned line name, or TesterError when it may carry something private."""
    text = ' '.join((line or '').split())
    if text != (line or '').strip() or not LINE_ALLOWED.fullmatch(text):
        raise TesterError('Linie: 2 bis 40 Zeichen, nur Buchstaben, Ziffern, Leerzeichen und . , + / ( ) _ - '
                          '(z. B. "Bosch MEVD17.2").')
    if LINE_NUMBER.search(text) or LINE_VIN.search(text.upper()):
        raise TesterError('Linie: bitte nur Hersteller und Steuergerätelinie, keine Software-, Teile- oder '
                          'Fahrgestellnummern und keine Adressen.')
    low = text.lower()
    for f in files:
        stem = Path(f).stem.lower()
        if len(stem) >= 4 and (stem in low or low in stem):
            raise TesterError('Linie: bitte nicht den Dateinamen verwenden, sondern die Steuergerätelinie.')
    return text


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


def round_count(n):
    """Two significant digits from ROUND_FROM upwards (1158 -> 1200, 812 -> 810); smaller counts unchanged."""
    if isinstance(n, bool) or not isinstance(n, int) or abs(n) < ROUND_FROM:
        return n
    digits = len(str(abs(n))) - 2
    return int(round(n, -digits))


def coarsen(x):
    if isinstance(x, dict):
        return {k: coarsen(v) for k, v in x.items()}
    return round_count(x)


@contextlib.contextmanager
def quiet():
    """No log records or warnings during the measurement: they may name offsets, files or table names."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            yield
    finally:
        logging.disable(previous)


def measure(bin_path: str, reference: str, line: str, *, anchor: str | None = None, exact: bool = False) -> dict:
    """The complete export (aggregated counts only)."""
    from .. import __version__
    from ..core import axis_refs
    from ..core.model import BinaryImage
    from .benchmark_suite import run
    from .structure_benchmark import _reference
    line = check_line(line, bin_path, reference)
    entry = {'name': 'tester', 'family': line, 'bin': bin_path, 'reference': reference, 'role': 'test'}
    if anchor:
        entry['anchor'] = anchor
    with quiet():
        row = run([entry])['rows'][0]
        image = BinaryImage.from_file(bin_path)
        maps = [m for m in _reference(reference, image, int(anchor, 0) if anchor else None) if m.rows * m.cols >= 2]
        counts = {'detection': {k: row.get(k) for k in DETECTION_KEYS} | {'seconds': round(row['seconds'])},
                  'axis_references': axis_refs.summary(maps, axis_refs.objects(maps, data=image.materialize())),
                  'function_identification': function_counts(maps)}
    if not exact:
        counts = coarsen(counts)
    return {'format': FORMAT, 'version': __version__, 'line': line, 'reference_kind': _reference_kind(reference),
            'precision': 'exakt' if exact else 'gerundet', **counts, 'note': NOTE}


def canonical(report: dict) -> str:
    return json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True)


def consent_code(report: dict) -> str:
    """Short code bound to the exact content: a changed report needs a new preview."""
    return hashlib.sha256(canonical(report).encode('utf-8')).hexdigest()[:10]


FORBIDDEN = ('sha256', 'digest', 'offset', 'address', 'name', 'path', 'size', 'bin', 'file')
TEXT_FIELDS = ('format.', 'version.', 'line.', 'reference_kind.', 'precision.', 'note.')
TOP_LEVEL = {'format', 'version', 'line', 'reference_kind', 'precision', 'detection', 'axis_references',
             'function_identification', 'note'}


def check_private(report: dict) -> None:
    """Refuse an export that carries anything beyond counts (defence against later changes)."""
    def walk(x, where=''):
        if isinstance(x, dict):
            for k, v in x.items():
                if not isinstance(k, str) or k.lower() in FORBIDDEN or not re.fullmatch(r'[a-zäöüß0-9_@.]{1,40}', k):
                    raise ValueError(f'Feld {where}{k!s:.40} darf nicht exportiert werden')
                walk(v, f'{where}{k}.')
        elif isinstance(x, (list, tuple, set, bytes, bytearray)):
            raise ValueError(f'Listen und Bytes sind im Export nicht erlaubt ({where})')
        elif isinstance(x, str):
            if where not in TEXT_FIELDS:
                raise ValueError(f'Text im Feld {where} darf nicht exportiert werden')
        elif not (x is None or isinstance(x, (bool, int, float))):
            raise ValueError(f'Wert im Feld {where} darf nicht exportiert werden')
    if not isinstance(report, dict) or set(report) - TOP_LEVEL:
        raise ValueError('Unbekannte Felder im Export')
    walk(report)
    try:
        check_line(report.get('line', ''))
    except TesterError as e:
        raise ValueError(str(e)) from None
    if report.get('precision') != 'exakt' and coarsen(report) != report:
        raise ValueError('Gerundeter Export enthält ungerundete Zählwerte')


def _preview(report: dict, out) -> None:
    print('Vorschau – genau dieser Inhalt würde exportiert (sonst nichts):', file=out)
    print(canonical(report), file=out)
    print('\n' + PRIVACY_WARNING, file=out)
    print('Dieser Bericht ist deine eigene Messung und keine unabhängige Validierung von ECU Studio.', file=out)


def _write(target: Path, report: dict) -> None:
    if target.suffix.lower() != '.json':
        raise TesterError('Die Zieldatei muss auf .json enden.')
    try:
        with open(target, 'x', encoding='utf-8') as f:
            f.write(canonical(report) + '\n')
    except FileExistsError:
        raise TesterError('Die Zieldatei existiert bereits – sie wird nicht überschrieben. '
                          'Bitte anderen Namen wählen.') from None


def _safe(run, debug: bool) -> int:
    """Run a step; failures are reported by kind only (exception texts can contain paths or names)."""
    try:
        return run()
    except TesterError as e:
        print(str(e), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Abgebrochen. Nichts wurde gespeichert.', file=sys.stderr)
        return 130
    except Exception as e:   # noqa: BLE001 - deliberately reduced to the error kind
        if debug:
            raise
        print(f'Die Messung ist fehlgeschlagen ({type(e).__name__}). Nichts wurde gespeichert. Prüfe, ob die '
              'Definition zu genau dieser Datei gehört. Mit --details siehst du die vollständige Meldung nur '
              'lokal (sie kann Dateipfade enthalten; nicht weitergeben).', file=sys.stderr)
        return 1


def assistant(ask=input, out=None, *, exact: bool = False) -> int:
    """Guided flow: two files, line, preview, explicit 'ja', file name. Nothing is written without 'ja'."""
    out = out or sys.stdout
    print('ECU Studio – lokaler Testbericht. Es wird nichts gesendet. Abbruch jederzeit mit Strg+C.', file=out)
    print('Verwende nur Dateien, die du rechtmäßig nutzen darfst.\n', file=out)
    binary = ask('1/3 Pfad zur Originaldatei (.bin): ').strip().strip('"')
    reference = ask('2/3 Pfad zur passenden Definition (.a2l, .xdf oder .csv): ').strip().strip('"')
    for p in (binary, reference):
        if not Path(p).is_file():
            raise TesterError('Eine der beiden Dateien wurde nicht gefunden. Bitte den Pfad prüfen.')
    line = ask('3/3 Steuergerätelinie (z. B. "Bosch MEVD17.2", ohne Software- oder Teilenummer): ').strip()
    line = check_line(line, binary, reference)
    print('\nMessung läuft lokal, das kann einige Minuten dauern ...', file=out)
    report = measure(binary, reference, line, exact=exact)
    check_private(report)
    _preview(report, out)
    if ask('\nDiesen Inhalt als Datei speichern? Tippe "ja" zum Speichern, alles andere bricht ab: ').strip().lower() != 'ja':
        print('Nicht gespeichert.', file=out)
        return 0
    name = ask('Dateiname für den Bericht [ecu-studio-testbericht.json]: ').strip().strip('"') or \
        'ecu-studio-testbericht.json'
    _write(Path(name), report)
    print('Gespeichert (nur Zählwerte). Ob und an wen du die Datei weitergibst, entscheidest du selbst.', file=out)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('bin', nargs='?')
    p.add_argument('reference', nargs='?', help='eigene Definition (A2L / XDF / CSV) zu genau dieser Datei')
    p.add_argument('--assistent', action='store_true', help='geführter Ablauf mit Fragen (empfohlen)')
    p.add_argument('--line', help='Steuergerätelinie, wie sie im Bericht stehen soll')
    p.add_argument('--anchor', help='A2L-Speicheradresse des Dateianfangs (sonst automatisch)')
    p.add_argument('--exakt', action='store_true', help='Zählwerte nicht runden (höheres Wiedererkennungsrisiko)')
    p.add_argument('--export', type=Path, help='Datei für den Export (nur zusammen mit --consent)')
    p.add_argument('--consent', help='Zustimmungscode aus der Vorschau')
    p.add_argument('--details', action='store_true', help='vollständige Fehlermeldung (nur lokal, nicht weitergeben)')
    a = p.parse_args(argv)
    if a.assistent:
        return _safe(lambda: assistant(exact=a.exakt), a.details)
    if not (a.bin and a.reference and a.line):
        p.error('ORIGINAL, DEFINITION und --line angeben, oder --assistent verwenden')

    def scripted():
        report = measure(a.bin, a.reference, a.line, anchor=a.anchor, exact=a.exakt)
        check_private(report)
        code = consent_code(report)
        if a.export is None:
            _preview(report, sys.stdout)
            print(f'\nNichts wurde gespeichert oder gesendet. Zum Export nach Prüfung: --export DATEI --consent {code}')
            return 0
        if a.consent != code:
            raise TesterError('Zustimmungscode passt nicht zu diesem Inhalt. Erst die Vorschau ansehen (ohne --export).')
        _write(a.export, report)
        print('Gespeichert (nur Zählwerte). Weitergabe entscheidest du selbst.')
        return 0
    return _safe(scripted, a.details)


if __name__ == '__main__':
    raise SystemExit(main())
