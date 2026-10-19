"""Evidence-based ECU calibration labels.

Only *metadata* or a user-verified reference can suggest semantics. Arbitrary
binary patterns are not a reliable oracle for ECU purpose. Scores are rule
strength / resemblance measures, NOT calibrated probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
import csv
import math
import re
import unicodedata
from pathlib import Path

import numpy as np

from .model import BinaryImage, MapDefinition, FORMATS


@dataclass(frozen=True)
class Prediction:
    kind: str
    score: float
    origin: str
    evidence: str
    alternatives: tuple[str, ...] = ()


# Exact ECU IDs can have meanings dependent on software family! Use only descriptive
# words and unambiguous, well-known prefixes; DO NOT infer from raw magnitude alone.
# Entries are ordered by specificity; broader families are last.
LEXICON: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('Ladedruck-Sollwert', ('boost target', 'boost request', 'boost setpoint', 'boost pressure request', 'boost pressure target', 'boost pressure setpoint', 'requested boost',
       'desired boost', 'ladedruck soll', 'ladedruck wunsch', 'charge pressure target', 'charge pressure request',
       'charge pressure setpoint', 'pboost request', 'boost pressure target')),
    ('Ladedruckbegrenzung', ('boost limit', 'boost limiter', 'boost pressure limiter', 'boost pressure limit', 'max boost', 'maximum boost', 'ladedruck begrenz',
       'charge pressure limit', 'overboost limit', 'turbo pressure limit')),
    ('Ladedruck-Regelung', ('boost control', 'boost regulator', 'boost pid', 'ladedruck regler',
       'charge pressure control', 'charge pressure regulator')),
    ('AGR-Sollwert / Rate', ('egr rate', 'egr target', 'egr request', 'egr setpoint', 'egr desired',
       'agr rate', 'agr soll', 'agr wunsch', 'agr anforderung', 'exhaust gas recirculation rate')),
    ('AGR-Begrenzung', ('egr limit', 'egr limiter', 'agr begrenz', 'maximum egr', 'max egr')),
    ('AGR-Regelung', ('egr valve', 'egr control', 'egr regulator', 'agr ventil', 'agr regler',
       'exhaust gas recirculation control')),
    ('Fahrerwunsch / Pedal', ('driver wish', 'driver demand', 'driver request torque',
       'fahrerwunsch', 'pedal request', 'accelerator pedal map', 'pedal demand', 'pedal position')),
    ('Drehmomentbegrenzung', ('torque limiter', 'torquelimiter', 'torque limit', 'maximum torque', 'max torque',
       'torque maximum', 'torque max', 'drehmoment begrenz', 'drehmoment maximum', 'moment limiter', 'moment begrenz')),
    ('Drehmomentmodell', ('torque model', 'indicated torque', 'torque structure', 'torque conversion',
       'momentenmodell', 'drehmoment modell', 'kfmirl', 'kfmio')),
    ('Einspritzmenge', ('injection quantity', 'injection amount', 'fuel quantity',
       'einspritzmenge', 'fuel mass request', 'iq request', 'injected quantity')),
    ('Einspritzdauer', ('injection duration', 'injection time', 'injector duration',
       'einspritzdauer', 'einspritz zeit', 'energizing duration')),
    ('Einspritzbeginn / SOI', ('start of injection', 'injection start', 'injection timing',
       'einspritzbeginn', 'soi request', 'soi target', 'soi map')),
    ('Voreinspritzung', ('pilot injection', 'pre injection', 'preinjection', 'voreinspritz')),
    ('Nacheinspritzung', ('post injection', 'nacheinspritz', 'postinjection')),
    ('Raildruck-Sollwert', ('rail pressure target', 'rail pressure request', 'rail pressure setpoint',
       'rail pressure desired', 'raildruck soll', 'raildruck wunsch', 'rail setpoint', 'rail target',
       'desired rail pressure')),
    ('Raildruckbegrenzung', ('rail pressure limit', 'rail pressure max', 'raildruck begrenz',
       'rail max pressure')),
    ('Raildruckregelung', ('rail pressure control', 'rail pressure regulator', 'raildruck regler',
       'fuel pressure regulator', 'fuel pressure control')),
    ('Zündwinkel', ('ignition angle', 'ignition advance', 'spark advance', 'spark angle',
       'zundwinkel', 'zundkennfeld', 'zundzeitpunkt', 'ignition timing')),
    ('Klopfregelung', ('knock control', 'knock threshold', 'knock correction', 'klopfregel',
       'knock retard', 'knock limit')),
    ('Lambda-Sollwert', ('lambda target', 'lambda desired', 'lambda request', 'lambda setpoint',
       'lambda soll', 'afr target', 'air fuel ratio target', 'fuel air equivalence target')),
    ('Lambda-Begrenzung / Rauch', ('smoke limiter', 'smoke limit', 'smoke limitation', 'rauchbegrenz',
       'lambda limiter', 'lambda limit', 'smoke map')),
    ('Luftmasse-Sollwert', ('air mass target', 'air mass request', 'airflow target',
       'luftmasse soll', 'luftmasse wunsch', 'maf target', 'air mass setpoint')),
    ('Luftmassen-Sensorik', ('maf sensor', 'air mass sensor', 'mass airflow sensor',
       'luftmassenmesser', 'maf characteristic')),
    ('Saugrohrdruck-Sensorik', ('map sensor', 'manifold absolute pressure sensor',
       'saugrohrdruck sensor', 'charge pressure sensor')),
    ('VTG/VNT-Stellung', ('vtg position', 'vnt position', 'vgt position', 'variable nozzle',
       'turbo vane', 'vtg stell', 'vtg soll', 'vnt duty')),
    ('Wastegate-Steuerung', ('wastegate duty', 'wastegate control', 'wastegate request',
       'wastegate target', 'wastegate position')),
    ('Drosselklappe', ('throttle valve', 'throttle angle', 'throttle target',
       'drosselklappe', 'throttle position')),
    ('Drallklappen / Swirl', ('swirl flap', 'swirl control', 'drallklappe', 'swirl valve')),
    ('Leerlauf-Sollwert', ('idle speed target', 'idle speed request', 'idle speed setpoint',
       'leerlauf soll', 'leerlauf drehzahl', 'idle target', 'target idle')),
    ('Drehzahlbegrenzung', ('rpm limiter', 'rpm limit', 'engine speed limit',
       'drehzahl begrenz', 'drehzahl limit', 'rev limiter')),
    ('Geschwindigkeitsbegrenzung', ('vehicle speed limiter', 'vehicle speed limit',
       'speed limiter', 'vmax limiter', 'geschwindigkeits begrenz')),
    ('Temperaturschutz', ('thermal protection', 'temperature protection', 'overtemperature',
       'thermischer schutz', 'temperatur schutz', 'heat protection')),
    ('Kühlmittelregelung', ('coolant temperature target', 'coolant control', 'coolant fan',
       'kuhlmittel regel', 'kuhlmittel soll')),
    ('Nockenwellenverstellung', ('camshaft angle', 'camshaft timing', 'camshaft target',
       'nockenwellen verstell', 'variable valve timing', 'vvt target')),
    ('DPF-Regeneration', ('dpf regeneration', 'filter regeneration', 'regeneration target',
       'particulate regeneration', 'partikelfilter regener')),
    ('DPF-Differenzdruck', ('dpf differential pressure', 'particulate filter pressure',
       'partikelfilter differenzdruck')),
    ('SCR / AdBlue-Dosierung', ('scr dosing', 'urea dosing', 'adblue dosing', 'harnstoff dosier',
       'urea injection', 'reductant dosing')),
    ('NOx-Sensorik / Modell', ('nox sensor', 'nox model', 'nox conversion', 'nitrogen oxides model')),
    ('Diagnoseschwelle / DTC', ('diagnostic threshold', 'diagnostic limit', 'dtc threshold',
       'diagnoseschwelle', 'fault threshold', 'diagnostic fault')),
    ('Getriebemoment / Begrenzung', ('transmission torque', 'gearbox torque', 'gear torque limit',
       'getriebe moment', 'gearbox protection')),
    ('Ladedruck / Boost', ('boost pressure', 'ladedruck', 'charge pressure', 'boost map')),
    ('AGR / EGR', ('egr', 'agr', 'exhaust gas recirculation', 'abgasruckfuhr')),
    ('Drehmoment', ('torque', 'drehmoment', 'momentenanforderung')),
    ('Einspritzung', ('injection', 'einspritz', 'injector')),
    ('Kraftstoffdruck', ('rail pressure', 'raildruck', 'fuel pressure', 'kraftstoffdruck')),
    ('Lambda / Gemisch', ('lambda', 'air fuel ratio', 'afr')),
    ('Zündung', ('ignition', 'zundung', 'spark')),
    ('Temperatur', ('temperature', 'temperatur', 'coolant temp', 'intake temp')),
    ('Diagnose', ('diagnostic', 'diagnose', 'fault code')),
)

# Avoid semantic conflicts when multiple labels have similarly specific evidence.
GENERAL = {'Ladedruck / Boost', 'AGR / EGR', 'Drehmoment', 'Einspritzung',
           'Kraftstoffdruck', 'Lambda / Gemisch', 'Zündung', 'Temperatur', 'Diagnose'}


def normalize(value: str) -> str:
    value = unicodedata.normalize('NFKD', value.casefold()).replace('ß', 'ss')
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])', ' ', value)
    return ' ' + re.sub(r'[^a-z0-9]+', ' ', value).strip() + ' '


def classify_metadata(name: str, description: str = '', unit: str = '', axes: str = '') -> Prediction:
    """Return ranked, explainable *label suggestions from descriptive metadata*.

    Unit/axes act only as context, never prove the map purpose. Never classify
    anonymous bytes by numeric ranges. When top specific labels tie, abstain.
    """
    n = normalize(name)
    d = normalize(description)
    ranks = []
    for kind, aliases in LEXICON:
        matched_name = [a for a in aliases if normalize(a) in n]
        matched_desc = [a for a in aliases if normalize(a) in d]
        if not matched_name and not matched_desc:
            continue
        # A long/descriptive token is more discriminatory than 'egr' or 'torque'.
        best = max(matched_name + matched_desc, key=len)
        specificity = min(4.0, max(0, len(best.split()) - 1) * 1.9 + len(best) / 24)
        strength = 5.0 * bool(matched_name) + 3.0 * bool(matched_desc) + specificity
        if kind in GENERAL:
            strength -= 2.0
        ranks.append((strength, kind, best, bool(matched_name)))
    if not ranks:
        return Prediction('Unbekannt', 0., 'Keine Metadatenübereinstimmung',
                          'Kein belastbarer Begriff in Name/Beschreibung; Rohwerte liefern keinen sicheren ECU-Typ.')
    ranks.sort(key=lambda x: (-x[0], -len(x[2]), x[1]))
    top = ranks[0]
    second = next((x for x in ranks[1:] if x[1] != top[1] and x[1] not in GENERAL), None)
    alts = tuple(x[1] for x in ranks if x[1] != top[1] and x[1] not in GENERAL)[:3]
    if second and second[0] >= top[0] - 0.7 and top[1] not in GENERAL:
        return Prediction('Unbekannt', 0.0, 'Mehrdeutig',
                          f'Widersprüchliche Metadaten: {top[1]} und {second[1]}. Manuell prüfen.',
                          (top[1], second[1]) + alts[2:])
    # Approximate rule strength indicator, not trained probability.
    score = min(.90, round(.49 + .04 * top[0], 2))
    place = 'Name' if top[3] else 'Beschreibung'
    evidence = f'{place} enthält „{top[2]}“; A2L/Definition und ECU-Softwarestand unabhängig prüfen.'
    if unit.strip():
        evidence += f' Einheit laut Quelle: {unit.strip()}.'
    return Prediction(top[1], score, 'Metadaten-Regel', evidence, alts)


def classify_raw_without_metadata() -> Prediction:
    return Prediction('Unbekannt', 0.0, 'Rohdaten',
                      'Tabellenform erkannt; keine belastbare Zuordnung zu einer ECU-Funktion ohne passende Referenz.')


def label_from_metadata(m: MapDefinition, *, description: str = '', overwrite: bool = False) -> bool:
    """Suggest labels only for unverified records with no explicit user type."""
    if m.verified or (not overwrite and m.kind not in ('Unbekannt', 'Andere')):
        return False
    pred = classify_metadata(m.name, description, m.unit, m.axes_info)
    if pred.kind == 'Unbekannt':
        return False
    m.kind = pred.kind
    m.label_origin = pred.origin
    m.label_evidence = pred.evidence
    m.type_alternatives = list(pred.alternatives)
    m.type_score = pred.score
    return True


def _normalized_surface(image: BinaryImage, m: MapDefinition) -> np.ndarray | None:
    """Normalized shape, for references only; no meaning from magnitude alone."""
    if m.length > 8192 or m.length < 128 or m.rows < 6 or m.cols < 6:
        return None
    arr = np.array([[image.raw_value(m,r,c) for c in range(m.cols)]
                    for r in range(m.rows)],dtype=np.float64)
    if not np.isfinite(arr).all():return None
    # Compare *shape* rather than raw amplitude and avoid nearly-flat references.
    span = np.percentile(arr, 95) - np.percentile(arr, 5)
    if span < 1 or np.std(arr) < span * 0.05:
        return None
    arr = (arr - np.mean(arr)) / max(np.std(arr), 1e-6)
    # Common linear ramps, which appear in unrelated maps, are not distinctive.
    texture = (np.mean(np.abs(np.diff(arr, n=2, axis=0))) +
               np.mean(np.abs(np.diff(arr, n=2, axis=1))))
    if texture < .018:
        return None
    return arr


def suggest_reference_shapes(image: BinaryImage, maps: list[MapDefinition], signatures: list,
                             max_signatures: int = 160) -> int:
    """Conservative *visual reference* suggestions for already found candidates.

    Never marks a match verified. A smooth surface resembling another smooth map
    can easily have an unrelated function. Distinct matched references are required
    for high shape strength, and displayed as unverified reference hints.
    """
    if not signatures:
        return 0
    indexed = defaultdict(list)
    for sig in signatures[:max_signatures]:
        if sig.rows * sig.cols > 2048 or sig.rows < 6 or sig.cols < 6:
            continue
        try:
            payload = bytes.fromhex(sig.payload_hex)
            refmap = MapDefinition(sig.name, 0, sig.rows, sig.cols, sig.dtype, sig.endian)
            sample = _normalized_surface(BinaryImage(payload), refmap)
            if sample is not None:
                indexed[(sig.rows, sig.cols, sig.dtype, sig.endian)].append((sig, sample))
        except (ValueError, TypeError, OverflowError):
            continue
    changed = 0
    for m in maps:
        if m.verified or m.source != 'heuristic' or m.kind not in ('Unbekannt', 'Boost-Verdacht', 'AGR-Verdacht'):
            continue
        refs = indexed.get((m.rows, m.cols, m.dtype, m.endian), [])
        if not refs:
            continue
        try:
            sample = _normalized_surface(image, m)
        except ValueError:
            continue
        if sample is None:
            continue
        hit = []
        for sig, surface in refs:
            # Pearson similarity + normalized mean absolute error; both required.
            corr = float(np.mean(sample * surface))
            error = float(np.mean(np.abs(sample - surface)))
            if corr >= .997 and error <= .045:
                hit.append((corr, sig.kind, sig.name))
        if not hit:
            continue
        hit.sort(reverse=True)
        # Display a *specific* proposed type but never treat as verified.
        primary = hit[0]
        kinds = sorted({h[1] for h in hit})
        if len(kinds) > 1:
            m.kind = 'Unbekannt'
            m.type_alternatives = kinds[:4]
            m.label_evidence = 'Mehrdeutige Formähnlichkeit zu mehreren Referenztypen: ' + ', '.join(kinds[:4])
            m.label_origin = 'Referenzform (mehrdeutig)'
            m.type_score = 0.0
        else:
            m.kind = primary[1]
            m.label_origin = 'Referenzform (ungeprüft)'
            m.type_score = min(.68, round(primary[0] * .67, 2))
            m.label_evidence = (f'Normierter Oberflächenverlauf ähnlich zu manuell gespeicherter Referenz '
                                f'„{primary[2]}“ (r={primary[0]:.4f}). Gleiche Funktion ist NICHT bewiesen.')
            m.type_alternatives = []
        changed += 1
    return changed


def export_detection_report(path: str, maps: list[MapDefinition]) -> None:
    with Path(path).open('w', encoding='utf-8-sig', newline='') as file:
        w = csv.writer(file, delimiter=';')
        w.writerow(['Name', 'Offset', 'Typ / Vorschlag', 'Quelle', 'Nachweisart',
                    'Regelstaerke_keine_Wahrscheinlichkeit', 'Manuell_verifiziert',
                    'Begruendung', 'Alternativen', 'Datentyp', 'Groesse'])
        for m in maps:
            w.writerow([m.name, f'0x{m.offset:X}', m.kind, m.source, m.label_origin,
                        f'{m.type_score:.2f}', 'ja' if m.verified else 'nein',
                        m.label_evidence or m.notes, ', '.join(m.type_alternatives),
                        m.dtype, f'{m.rows}x{m.cols}'])


def enrich_with_exact_references(maps: list[MapDefinition], references: list[MapDefinition]) -> int:
    """Link unlabeled *metadata-defined* maps to identical verified-reference payloads.

    Requires same file offset AND dimensions, byte order, data type; refuses
    conflicting labels or an existing user-defined type. The linked A2L record
    remains unverified (even if the fingerprint came from a verified source).
    """
    by_key = defaultdict(set)
    for ref in references:
        if ref.source == 'exact-reference' and ref.kind not in ('Unbekannt', 'Andere'):
            by_key[(ref.offset,ref.rows,ref.cols,ref.dtype,ref.endian)].add(ref.kind)
    n = 0
    for m in maps:
        if m.verified or m.kind not in ('Unbekannt', 'Andere'):
            continue
        kinds = by_key.get((m.offset,m.rows,m.cols,m.dtype,m.endian), set())
        if len(kinds) != 1:
            continue
        m.kind = next(iter(kinds))
        m.label_origin = 'A2L/Definition + exakte Referenz (ungeprüft)'
        m.label_evidence = ('Gleicher Offset und vollständiger Byte-Fingerprint wie eine lokal geprüfte Referenz. '
                            'Identischer Verwendungszweck/Softwarestand ist dadurch nicht bewiesen.')
        m.type_score = .9
        m.type_alternatives = []
        n += 1
    return n
