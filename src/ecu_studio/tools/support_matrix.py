"""Write recognition/data/ecu_support.json from benchmark_suite results.

Usage: python -m ecu_studio.tools.support_matrix RESULT.json [RESULT.json ...] [--out FILE] [--markdown FILE]

Status rules (applied here, not chosen per family by hand):
- validiert:      at least one pair with a COMPLETE reference (manufacturer A2L or
                  complete community XDF) was measured, with precision >= MIN_PRECISION.
                  Below that the family is 'teilweise' and says so.
- teilweise:      only partial references measured (recall and exact maps only).
- experimentell:  scanned on real firmware of the family, but without any reference.
- nicht validiert: no firmware of the family was available at all.
Families without measurements are listed with the files needed to validate them.
Only counts are written, never firmware bytes or names from the definitions.
"""
from __future__ import annotations
import argparse
import datetime
import json
from pathlib import Path
from ecu_studio.core.support import DATA

# (family, identification names, processor, benchmark name prefixes, limits, files needed)
FAMILIES = [
    ('Bosch EDC17CP09', ['EDC17CP09'], 'Infineon TriCore', ['EDC17CP09'],
     'Ein Softwarestand (BMW). Gruppenkennfelder mit gemeinsamen Achsen (MapG) werden kaum erkannt; '
     'TriCore-Code-Verweise auf Kennfelder ließen sich nicht nutzen (Zugriff nicht über movh.a/lea).', ''),
    ('Siemens MSD80', ['MSD80'], 'PowerPC', ['MSD80'], 'Kalibrierbereich aus S19; Identität nur über A2L-EPK.', ''),
    ('Siemens MSD85', ['MSD85'], 'PowerPC', ['MSD85'], 'Ein Softwarestand; Identität nur über A2L-EPK.', ''),
    ('Bosch EDC16C35', ['EDC16C35'], 'PowerPC (MPC5xx)', ['EDC16C35'],
     'Ein Softwarestand. Datei nennt C31 und C35 – Familie per Kennung mehrdeutig.', ''),
    ('Bosch EDC16C31', ['EDC16C31'], 'PowerPC (MPC5xx)', ['EDC16C31'],
     'Ein Softwarestand. Datei nennt C31 und C35 – Familie per Kennung mehrdeutig.', ''),
    ('BMW ME9', ['ME9'], 'PowerPC', ['ME9 '], 'Ein Softwarestand.', ''),
    ('BMW ME9.2.1', ['ME9.2.1'], 'PowerPC', ['ME9.2.1'], 'Ein Softwarestand; keine Kennung in der Datei.', ''),
    ('Siemens MS45', ['MS45'], 'C167', ['MS45'], 'Niedrige Abdeckung (Datensatzformat ohne Kopf).', ''),
    ('Siemens MS43', ['MS43'], 'C167', ['MS43'], 'Community-XDF; zum Trainieren verwendet.', ''),
    ('Siemens MS42', ['MS42'], 'C167', ['MS42'], 'Community-XDF; zum Trainieren verwendet.', ''),
    ('Bosch MED17.1.62', ['MED17.1.62', 'MED17.1'], 'Infineon TriCore', ['MED17.1.62'],
     'Nur Kalibrierbereich (496 KB) mit Teil-XDF: Präzision nicht messbar.', 'Hersteller-A2L zu einem der Stände'),
    ('Bosch MED9.1', ['MED9.1', 'MED9'], 'PowerPC', ['MED9'], 'Teil-XDF mit 43 Kennfeldern.', 'vollständige A2L'),
    ('Bosch ME7.5', ['ME7.5'], 'C167', ['ME7.5'], 'Community-XDFs (Teilreferenz).', ''),
    ('Bosch ME7 (Volvo)', ['ME7.0.1', 'ME7'], 'C167', ['ME7 '], 'Community-XDFs (Teilreferenz).', ''),
    ('Bosch M4.4', ['M4.4'], '8051', ['Volvo M4.4'], 'Teil-XDF.', ''),
    ('GM P01', [], 'Motorola 68k', ['GM P01'], 'Teil-XDF; keine Kennung in der Datei.', ''),
    ('Denso SH-2 (Subaru 5EAT)', [], 'Hitachi SH-2', ['Subaru'], 'RomRaider-Auswahl (Teilreferenz).', ''),
    ('Hyundai/Kia SIM2K (Hyundai N)', [], 'Infineon TriCore', ['SIM2K'],
     'Community-XDF; zur Konfidenz-Kalibrierung verwendet. Code-Verweise über Basisregister nicht gelöst.', ''),
    ('BMW MSS54', ['MSS54'], 'Motorola CPU32', ['MSS54'], 'Community-XDF; zur Konfidenz-Kalibrierung verwendet.', ''),
    # Families of the target list without any local firmware/reference pair.
    ('Bosch EDC17CP14 / CP20 / CP44 / CP45 / CP46', ['EDC17CP14', 'EDC17CP20', 'EDC17CP44', 'EDC17CP45', 'EDC17CP46'],
     'Infineon TriCore/AURIX', [], '', 'Original-BIN (vollständiger Flash) + passende Hersteller-A2L mit EPK, je 2 Softwarestände'),
    ('Bosch EDC17C46 / C64 / C74', ['EDC17C46', 'EDC17C64', 'EDC17C74'], 'Infineon TriCore', [], '',
     'Original-BIN + passende A2L, je 2 Softwarestände'),
    ('Bosch EDC17CP02', ['EDC17CP02'], 'Infineon TriCore', [], 'Nur A2L vorhanden (4P1C2558), keine Firmware.',
     'Firmware zum Softwarestand 4P1C2558'),
    ('Bosch MED17.5 / 17.5.5 / 17.5.25 / 17.7 / 17.7.2', ['MED17.5', 'MED17.5.5', 'MED17.5.25', 'MED17.7', 'MED17.7.2'],
     'Infineon TriCore', [], '', 'Original-BIN + passende A2L'),
    ('Bosch MEVD17.2.x / MEVD17.4.6', ['MEVD17.2', 'MEVD17.4.6'], 'Infineon TriCore', [],
     'MEVD17.4.6: nur WinOLS-Projekt (.ols), Inhalt nicht verifizierbar lesbar.', 'Original-BIN + A2L'),
    ('Bosch MD1 (MD1CS001, MD1CS004, MD1CP002)', ['MD1CS001', 'MD1CS004', 'MD1CP002'], 'Infineon AURIX', [], '',
     'Original-BIN + passende A2L (DAMOS) mit EPK'),
    ('Bosch MG1 (MG1CS001, MG1CS002, MG1CS011, MG1CS201)', ['MG1CS001', 'MG1CS002', 'MG1CS011', 'MG1CS201'],
     'Infineon AURIX', [], '', 'Original-BIN + passende A2L mit EPK'),
    ('Continental Simos 8 / 10 / 12 / 18.1 / 18.2 / 18.10 / 19', ['SIMOS8', 'SIMOS10', 'SIMOS12', 'SIMOS18', 'SIMOS19'],
     'Infineon TriCore', [], '', 'Original-BIN + A2L'),
    ('Continental SID208 / SID807 / SID807EVO / SID310 / SID321', ['SID208', 'SID807', 'SID310', 'SID321'],
     'Infineon TriCore', [], '', 'Original-BIN + A2L'),
    ('Siemens MSD81 / MSV70 / MSV80', ['MSD81', 'MSV70', 'MSV80'], 'PowerPC / C167', [], '', 'Original-BIN + A2L'),
    ('Bosch EDC16C34 / EDC16CP34', ['EDC16C34', 'EDC16CP34'], 'PowerPC (MPC5xx)', [], '', 'Original-BIN + A2L'),
    ('Siemens MSS60', ['MSS60'], 'PowerPC', [], 'Nur WinOLS-Projekt (.ols) vorhanden.', 'Original-BIN + A2L'),
]
MIN_PRECISION = .5
# Families scanned on real firmware without any reference (identity and plausibility only).
EXPERIMENTAL: set[str] = set()


def _row_metrics(r: dict) -> dict:
    out = {k: r.get(k) for k in ('reference_2d', 'found_2d', 'exact_2d', 'type_exact_2d', 'axes_correct',
                                  'with_axes', 'reference_1d', 'exact_1d', 'seconds', 'peak_mb')}
    out['recall_2d'] = r['recall_2d']
    out['precision_2d'] = r.get('precision_2d')
    out['false_positives_2d'] = r.get('false_positives_2d')
    return out


def build(results: list[dict]) -> dict:
    rows = [r for res in results for r in res['rows']]
    entries = []
    for family, match, cpu, prefixes, limits, needed in FAMILIES:
        experimental = family in EXPERIMENTAL
        mine = [r for r in rows if any(r['name'].startswith(p) for p in prefixes)]
        software = [{'name': r['name'], 'role': r['role'], 'complete_reference': r['complete_reference'],
                     'group': r['group'], **_row_metrics(r)} for r in mine]
        complete = [r for r in mine if r['complete_reference']]
        if complete and max(r['precision_2d'] for r in complete) >= MIN_PRECISION:
            status = 'validiert'
        elif complete:
            status = 'teilweise'
            limits = (limits + ' Gemessen, Erkennung unzureichend '
                      f"(Präzision höchstens {max(r['precision_2d'] for r in complete):.0%}).").strip()
        elif mine:
            status = 'teilweise'
        elif experimental:
            status = 'experimentell'
        else:
            status = 'nicht validiert'
        entries.append({'family': family, 'status': status, 'processor': cpu, 'match': match,
                        'software': software, 'limits': limits, 'needed': needed})
    return {'format': 1, 'measured_on': datetime.date.today().isoformat(),
            'note': 'Messwerte aus benchmark_suite; Rolle test = nie zum Einstellen verwendet.',
            'entries': entries}


MARK = {'validiert': '✅ validiert', 'teilweise': '🟡 teilweise', 'experimentell': '🧪 experimentell',
        'nicht validiert': '⚪ nicht validiert'}


def _pct(v):
    return '–' if v is None else f'{v:.0%}'


def markdown(data: dict) -> str:
    """Support matrix and per-software measurements as Markdown (docs/ECU_SUPPORT.md)."""
    out = ['| Steuergerät | Prozessor | Status | Softwarestände | exakt 2D (Spanne der Stände) | Präzision 2D | Grenzen / benötigt |',
           '|---|---|---|---:|---|---|---|']
    for e in data['entries']:
        sw = e['software']
        if sw:
            ex = sorted(f"{s['exact_2d']}/{s['reference_2d']}" for s in sw)
            exact = ex[0] if len(set(ex)) == 1 else f"{min(s['exact_2d'] for s in sw)}–{max(s['exact_2d'] for s in sw)} von {sw[0]['reference_2d']}"
            exact = exact if len(set(s['reference_2d'] for s in sw)) == 1 else ', '.join(ex)
            prec = sorted({_pct(s.get('precision_2d')) for s in sw})
            prec = ' / '.join(prec)
        else:
            exact = prec = 'offen'
        limits = e['limits'] + (f" **Benötigt:** {e['needed']}." if e['needed'] else '')
        out.append(f"| {e['family']} | {e['processor']} | {MARK[e['status']]} | {len(sw)} | {exact} | {prec} | {limits.strip() or '–'} |")
    out += ['', '**Einzelmessungen** (Rolle *test* = nie zum Einstellen verwendet; Gruppe = nahezu identische Stände)', '',
            '| Softwarestand | Rolle | Gruppe | Ref 2D | gefunden | Abdeckung | exakt | Typ richtig | Achsen richtig | Präzision | Fehlfunde | exakt 1D | s | MB |',
            '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for e in data['entries']:
        for s in e['software']:
            fp = '–' if s.get('false_positives_2d') is None else s['false_positives_2d']
            mb = '–' if s.get('peak_mb') is None else s['peak_mb']
            out.append(f"| {s['name']} | {s['role']} | {s['group']} | {s['reference_2d']} | {s['found_2d']} | "
                       f"{_pct(s['recall_2d'])} | {s['exact_2d']} | {s['type_exact_2d']} | {s['axes_correct']}/{s['with_axes']} | "
                       f"{_pct(s.get('precision_2d'))} | {fp} | {s['exact_1d']} | {s['seconds']} | {mb} |")
    return '\n'.join(out) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('results', nargs='+', type=Path)
    p.add_argument('--out', type=Path, default=DATA)
    p.add_argument('--markdown', type=Path, help='Matrix zusätzlich als Markdown schreiben')
    a = p.parse_args(argv)
    data = build([json.loads(f.read_text(encoding='utf-8')) for f in a.results])
    a.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    if a.markdown:
        a.markdown.write_text(markdown(data), encoding='utf-8')
    for e in data['entries']:
        print(f"{e['status']:16s} {e['family']} ({len(e['software'])} Stände)")


if __name__ == '__main__':
    main()
