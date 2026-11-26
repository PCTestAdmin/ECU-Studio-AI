"""Shared core of the local recognition check (quality phase 6).

Used by the command line (tools/tester_report.py) and by the graphical assistant (ui/tester_assistant.py), so
both measure, round, check and export in exactly the same way:

  * ``check_firmware``  real format check of the chosen file (containers, HEX/S-Record text, definitions,
    programs, text, empty or filled images are refused with a reason; no path in any message);
  * ``check_reference`` reads the definition (A2L, XDF or CSV) against the image and judges whether it belongs
    to this file (A2L: confirmed base address; all kinds: objects inside the image, rising axes);
  * ``measure``         detection on the image bytes only (the scanner never sees the definition), then the
    comparison with the definition, axis references and function identification; cancellable between and
    inside the steps;
  * ``build_report`` / ``coarsen`` / ``check_private`` / ``consent_code`` / ``write_export``  the export:
    aggregate counts only, rounded from 100 upwards unless exact counts are chosen, bound to a consent code
    of exactly the content shown, never overwriting a file.

Everything runs locally. There is no network code here, and nothing is sent anywhere: the tester decides
whether and to whom to pass a saved file on. A tester's measurement is not an independent validation.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import re
import warnings
from pathlib import Path

FORMAT = 'ecu-studio-tester-report/2'
FEEDBACK_FORMAT = 'ecu-studio-tester-feedback/1'
DETECTION_KEYS = ('reference_2d', 'found_2d', 'exact_2d', 'type_exact_2d', 'with_axes', 'axes_correct',
                  'axis_address_with_2d', 'axis_address_correct_2d', 'group_pairs_reference', 'group_pairs_found',
                  'group_pairs_agree', 'reference_1d', 'found_1d', 'exact_1d')
SPLITS = (('table', .5), ('table', .25), ('table', .1), ('table', .05), ('table', .01), ('block', .5),
          ('function', .5))
SALTS = ('0', '1', '2')
SCORE_KEYS = ('evaluable', 'reachable', 'correct', 'wrong', 'unknown', 'withheld')
ROUND_FROM = 100          # counts below stay exact (they do not single out a software version)
MAX_IMAGE = 128 * 1024 * 1024
MIN_IMAGE = 1024
REFERENCE_KINDS = {'.a2l': 'a2l', '.xdf': 'xdf', '.csv': 'csv'}
MIN_RISING = .5           # share of reference axes that must rise for the definition to fit the file
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

# Voluntary feedback: fixed choices only, no free text (free text can carry names, numbers or paths).
FEEDBACK_RATINGS = ('hilfreich', 'teilweise hilfreich', 'nicht hilfreich')
FEEDBACK_TOPICS = ('zu viele falsche Kandidaten', 'Kennfelder fehlen', 'Achsen falsch', 'Datentypen falsch',
                   'Funktionen falsch zugeordnet', 'zu langsam', 'Bedienung unklar')


class TesterError(Exception):
    """A refusal the tester can read; the message never contains paths or file contents."""


class Cancelled(Exception):
    """The tester stopped the measurement; nothing was kept."""


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


def reference_kind(path: str) -> str:
    return REFERENCE_KINDS.get(Path(path).suffix.lower(), 'other')


# ---------------------------------------------------------------------------------------------- input checks

def check_firmware(path: str):
    """The image of a plausible raw firmware file, or TesterError with the reason (no path in the text)."""
    from ..core.model import BinaryImage
    from ..formats.sniff import container_reason
    p = Path(path or '')
    if not path or not p.is_file():
        raise TesterError('Die Firmwaredatei wurde nicht gefunden. Bitte den Pfad prüfen.')
    size = p.stat().st_size
    if size < MIN_IMAGE:
        raise TesterError('Die Firmwaredatei ist leer oder zu klein für ein Steuergeräte-Abbild.')
    if size > MAX_IMAGE:
        raise TesterError('Die Firmwaredatei ist größer als 128 MiB und wird nicht unterstützt.')
    try:
        data = p.read_bytes()
    except OSError:
        raise TesterError('Die Firmwaredatei kann nicht gelesen werden (Zugriff verweigert oder gesperrt).') from None
    reason = container_reason(data[:512], p.name)
    if reason:
        raise TesterError('Keine Rohfirmware: ' + reason)
    sample = data[:65536]
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in sample)
    if printable > .97 * len(sample):
        raise TesterError('Die Datei ist eine Textdatei, keine Rohfirmware (BIN/ORI).')
    if size - data.count(b'\x00') - data.count(b'\xff') < 16:
        raise TesterError('Die Datei enthält nur Füllbytes (00 oder FF) – kein auswertbares Abbild.')
    return BinaryImage(data)


def check_reference(path: str, image, anchor: int | None = None) -> dict:
    """Read the definition against the image; TesterError when it cannot be read or does not fit."""
    from .structure_benchmark import _reference
    p = Path(path or '')
    if not path or not p.is_file():
        raise TesterError('Die Definitionsdatei wurde nicht gefunden. Bitte den Pfad prüfen.')
    kind = reference_kind(path)
    if kind == 'other':
        raise TesterError('Definition: nur A2L, XDF oder CSV werden unterstützt.')
    if p.stat().st_size == 0:
        raise TesterError('Die Definitionsdatei ist leer.')
    try:
        with quiet():
            maps = list(_reference(str(p), image, anchor))
    except Exception:   # noqa: BLE001 - reduced to a plain reason (messages can name files or tables)
        raise TesterError('Die Definition konnte nicht gelesen werden oder passt nicht zu dieser Firmware '
                          '(z. B. andere Software, falsches Format oder beschädigte Datei).') from None
    inside = [m for m in maps if 0 <= m.offset and m.offset + m.length <= image.size]
    tables = [m for m in inside if min(m.rows, m.cols) > 1]
    axes = [list(map(float, a)) for m in tables for a in (m.axes_x, m.axes_y) if len(a) >= 3 and len(set(a)) > 1]
    rising = sum(all(b >= a for a, b in zip(ax, ax[1:])) or all(b <= a for a, b in zip(ax, ax[1:])) for ax in axes)
    result = {'kind': kind, 'objects': len(maps), 'inside': len(inside), 'tables_2d': len(tables),
              'axes': len(axes), 'axes_rising': rising}
    if not tables:
        raise TesterError('Die Definition enthält keine Kennfelder (2D), die in dieser Firmware liegen – '
                          'sie gehört vermutlich zu einer anderen Datei.')
    if len(inside) < .8 * len(maps):
        raise TesterError('Mehr als ein Fünftel der Definition liegt außerhalb dieser Firmware – sie gehört '
                          'vermutlich zu einer anderen Datei oder Speicheraufteilung.')
    if axes and rising < MIN_RISING * len(axes):
        raise TesterError('Die Achsen der Definition ergeben in dieser Firmware überwiegend keine geordneten '
                          'Stützstellen – die Definition passt vermutlich nicht zu dieser Datei.')
    return result


# ----------------------------------------------------------------------------------------------- measurement

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


def function_counts(maps, cancelled=None) -> dict:
    """Function identification under anchor splits (tools/function_benchmark), three salts summed."""
    from ..core import function_id as F
    from . import function_benchmark as B
    rels = F.relations(maps)
    out = {'tables_with_function': sum(1 for m in maps if B.truth_of(m)),
           'functions': len({f for m in maps for f in B.truth_of(m)})}
    for mode, fraction in SPLITS:
        total = B.Score()
        for salt in SALTS:
            _stop(cancelled)
            total.add(B.score(maps, B.split(maps, mode, fraction, salt), rels))
        out[f'{mode}@{fraction:g}'] = {k: getattr(total, k) for k in SCORE_KEYS}
    return out


def _stop(cancelled):
    if cancelled is not None and cancelled():
        raise Cancelled()


STEPS = ('Firmware prüfen', 'Definition prüfen', 'Kennfelder suchen (ohne Definition)',
         'Mit der Definition vergleichen', 'Achsbezüge und Funktionen auswerten')


def measure_counts(bin_path: str, reference: str, *, anchor: str | None = None, cancelled=None,
                   progress=None) -> dict:
    """Exact counts of one measurement (not yet rounded). ``progress(step_index, text)`` is called per step;
    ``cancelled()`` is polled between and inside the steps (Cancelled is raised)."""
    from ..core import axis_refs
    from ..core.model import BinaryImage
    from ..core.scoped_scan import scan_calibration_candidates
    from .benchmark_suite import run_pair
    from .structure_benchmark import _reference

    def step(i):
        _stop(cancelled)
        if progress:
            progress(i, STEPS[i])
    base = int(anchor, 0) if anchor else None
    with quiet():
        step(0)
        image = check_firmware(bin_path)
        step(1)
        check_reference(reference, image, base)
        step(2)
        entry = {'name': 'tester', 'family': 'tester', 'bin': bin_path, 'reference': reference, 'role': 'test'}
        if anchor:
            entry['anchor'] = anchor

        def detector(target):
            # Bytes only: the definition is never passed to the scanner (run_pair checks the image stays unchanged).
            found = scan_calibration_candidates(target, use_definitions=False, cancelled=cancelled)
            _stop(cancelled)
            return found
        row = run_pair(entry, detector=detector)
        step(3)
        maps = [m for m in _reference(reference, image, base) if m.rows * m.cols >= 2]
        step(4)
        counts = {'detection': {k: row.get(k) for k in DETECTION_KEYS} | {'seconds': round(row['seconds'])},
                  'axis_references': axis_refs.summary(maps, axis_refs.objects(maps, data=image.materialize())),
                  'function_identification': function_counts(maps, cancelled)}
    _stop(cancelled)
    return counts


def build_report(counts: dict, line: str, reference: str, *, exact: bool = False) -> dict:
    """The export for exactly these counts (rounded unless ``exact``)."""
    from .. import __version__
    body = counts if exact else coarsen(counts)
    return {'format': FORMAT, 'version': __version__, 'line': line, 'reference_kind': reference_kind(reference),
            'precision': 'exakt' if exact else 'gerundet', **json.loads(json.dumps(body)), 'note': NOTE}


def measure(bin_path: str, reference: str, line: str, *, anchor: str | None = None, exact: bool = False,
            cancelled=None, progress=None) -> dict:
    """The complete export (aggregated counts only)."""
    line = check_line(line, bin_path, reference)
    counts = measure_counts(bin_path, reference, anchor=anchor, cancelled=cancelled, progress=progress)
    return build_report(counts, line, reference, exact=exact)


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


def summary(report: dict) -> dict:
    """Shares for the result view: recall (exact layouts of the reference found), type and axis agreement,
    candidates the definition does not contain (not evaluable: a tester's definition is rarely complete)."""
    d = report.get('detection', {})
    ref, found, exact = d.get('reference_2d') or 0, d.get('found_2d') or 0, d.get('exact_2d') or 0

    def share(a, b):
        return (a / b) if b else None
    return {'recall_2d': share(exact, ref), 'type_2d': share(d.get('type_exact_2d') or 0, exact),
            'axes_2d': share(d.get('axes_correct') or 0, d.get('with_axes') or 0),
            'recall_1d': share(d.get('exact_1d') or 0, d.get('reference_1d') or 0),
            'not_evaluable_2d': max(found - exact, 0), 'reference_2d': ref, 'found_2d': found, 'exact_2d': exact,
            'precision_2d': None}


# --------------------------------------------------------------------------------------------------- export

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
    if report.get('format') != FORMAT or report.get('note', NOTE) != NOTE:
        raise ValueError('Format oder Hinweis des Exports wurde verändert')
    if report.get('precision') not in ('exakt', 'gerundet') or report.get('reference_kind', 'other') not in (
            *REFERENCE_KINDS.values(), 'other'):
        raise ValueError('Unbekannter Wert in Genauigkeit oder Definitionsart')
    walk(report)
    try:
        check_line(report.get('line', ''))
    except TesterError as e:
        raise ValueError(str(e)) from None
    if report.get('precision') != 'exakt' and coarsen(report) != report:
        raise ValueError('Gerundeter Export enthält ungerundete Zählwerte')


def feedback_report(rating: str | None, topics=()) -> dict:
    """Voluntary feedback: fixed choices only (no free text)."""
    from .. import __version__
    if rating is not None and rating not in FEEDBACK_RATINGS:
        raise ValueError('Unbekannte Bewertung')
    unknown = set(topics) - set(FEEDBACK_TOPICS)
    if unknown:
        raise ValueError('Unbekanntes Thema im Feedback')
    return {'format': FEEDBACK_FORMAT, 'version': __version__, 'rating': rating or 'keine Angabe',
            **{f'topic_{i + 1}': t in topics for i, t in enumerate(FEEDBACK_TOPICS)}}


def check_feedback(feedback: dict) -> None:
    allowed = {'format', 'version', 'rating'} | {f'topic_{i + 1}' for i in range(len(FEEDBACK_TOPICS))}
    if not isinstance(feedback, dict) or set(feedback) != allowed or feedback['format'] != FEEDBACK_FORMAT:
        raise ValueError('Unbekannte Felder im Feedback')
    if feedback['rating'] not in (*FEEDBACK_RATINGS, 'keine Angabe') or not isinstance(feedback['version'], str):
        raise ValueError('Unbekannter Wert im Feedback')
    if any(not isinstance(feedback[k], bool) for k in allowed - {'format', 'version', 'rating'}):
        raise ValueError('Unbekannter Wert im Feedback')


def write_export(target: Path, content: dict, code: str | None = None) -> None:
    """Write a report (or feedback) after the checks; never overwrites, needs the consent code of the content."""
    target = Path(target)
    if target.suffix.lower() != '.json':
        raise TesterError('Die Zieldatei muss auf .json enden.')
    if content.get('format') == FEEDBACK_FORMAT:
        check_feedback(content)
    else:
        try:
            check_private(content)
        except ValueError as e:
            raise TesterError(f'Export abgelehnt: {e}') from None
    if code is not None and code != consent_code(content):
        raise TesterError('Zustimmungscode passt nicht zu diesem Inhalt. Erst die Vorschau ansehen.')
    try:
        with open(target, 'x', encoding='utf-8') as f:
            f.write(canonical(content) + '\n')
    except FileExistsError:
        raise TesterError('Die Zieldatei existiert bereits – sie wird nicht überschrieben. '
                          'Bitte anderen Namen wählen.') from None
    except OSError:
        raise TesterError('Die Zieldatei konnte nicht geschrieben werden (Ordner schreibgeschützt?).') from None


__all__ = ['Cancelled', 'FORMAT', 'FEEDBACK_FORMAT', 'NOTE', 'PRIVACY_WARNING', 'STEPS', 'TesterError',
           'build_report', 'canonical', 'check_feedback', 'check_firmware', 'check_line', 'check_private',
           'check_reference', 'coarsen', 'consent_code', 'feedback_report', 'measure', 'measure_counts',
           'round_count', 'summary', 'write_export']
