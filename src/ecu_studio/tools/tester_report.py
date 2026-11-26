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
import sys
from pathlib import Path

# The measurement, rounding, privacy check, consent and export live in tester_core, shared with the graphical
# assistant (Werkzeuge -> Kennfelderkennung überprüfen), so command line and window give the same export.
from .tester_core import (FORMAT, NOTE, PRIVACY_WARNING, ROUND_FROM, TesterError, canonical,  # noqa: F401
                          check_line, check_private, coarsen, consent_code, function_counts, measure, quiet,
                          round_count)
from .tester_core import reference_kind as _reference_kind  # noqa: F401
from .tester_core import write_export


def _preview(report: dict, out) -> None:
    print('Vorschau – genau dieser Inhalt würde exportiert (sonst nichts):', file=out)
    print(canonical(report), file=out)
    print('\n' + PRIVACY_WARNING, file=out)
    print('Dieser Bericht ist deine eigene Messung und keine unabhängige Validierung von ECU Studio.', file=out)


def _write(target: Path, report: dict) -> None:
    write_export(target, report)


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
