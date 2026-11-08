"""Checksums and integrity: one interface over the checksum methods of ECU Studio AI.

Every file ends in exactly one of five states, which are never conflated:

  gueltig             Unterstützt und gültig: every checksum known for this ECU was
                      checked with a validated method and matches; nothing known is
                      left unchecked.
  ungueltig           Unterstützt und ungültig: at least one proven checksum does not
                      match the current bytes.
  unvollstaendig      Unvollständige Prüfung: the checked checksums match, but further
                      checksums, regions or the completeness itself are not covered.
  nicht_unterstuetzt  Nicht unterstützt: the ECU family is identified, but no method
                      applies to this file.
  unbekannt           Unbekannt: neither the family nor any method is established.

A method only counts when the file itself proves it: a self-describing structure
(range, stored value, complement or magic) whose stored values the UNMODIFIED
original reproduces. A generic CRC or sum that happens to give a matching number
never makes a file valid. Signatures are reported separately; this module never
checks, creates, alters or removes a signature, and a corrected checksum never
replaces a required manufacturer signature.

The per-method parsers live in checksum_tables, edc17_checksum, edc16_checksum and
checksum_audit; this module combines them and adds the status, the correction
plan, the independent re-check and the corrected copy. Nothing here keeps firmware
in a module-level cache: every call works on the image it is given, so a worker
thread can run it on a snapshot (BinaryImage.snapshot) without sharing state.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import checksum_tables as tables
from . import edc16_checksum as edc16
from . import edc17_checksum as edc17
from .checksum_audit import ChecksumProfile, plan_checksum_correction, verify_checksums
from .model import BinaryImage

M32 = 0xFFFFFFFF

VALID, INVALID, INCOMPLETE, UNSUPPORTED, UNKNOWN = (
    'gueltig', 'ungueltig', 'unvollstaendig', 'nicht_unterstuetzt', 'unbekannt')
STATUS_TEXT = {
    VALID: 'Unterstützt und gültig',
    INVALID: 'Unterstützt und ungültig',
    INCOMPLETE: 'Unvollständige Prüfung',
    UNSUPPORTED: 'Nicht unterstützt',
    UNKNOWN: 'Unbekannt',
}
# Region states
OK, BAD, UNPROVEN = 'ok', 'fehler', 'unbestaetigt'
REGION_TEXT = {OK: 'stimmt', BAD: 'FEHLER', UNPROVEN: 'nicht bestätigt'}

# How a method's correctness is established (docs/CHECKSUMMEN.md has the evidence).
VALIDATION_TEXT = {
    'referenz': 'unabhängig belegt',
    'gemessen': 'am Original gemessen, nicht unabhängig belegt',
    'manuell': 'manuell geprüftes Profil',
    'experimentell': 'experimentell',
}


@dataclass(frozen=True)
class Method:
    id: str
    title: str
    families: str
    validation: str
    evidence: str
    limits: str


METHODS = {
    'bosch-multipoint': Method(
        'bosch-multipoint', 'Bosch-Multipoint-Prüfsummentabelle', 'ME7.x, ME9, MED9', 'referenz',
        'Herstellerwerte aus drei unveränderten Originalen reproduziert (ME7.5, ME9, MED9.1; 199 Einträge, '
        'je 32-Bit-Wert und Komplement); Verfahren stimmt mit dem quelloffenen ME7Sum überein.',
        'Nur die Multipoint-Tabellen. Weitere Prüfsummen der Familie und Signaturen werden nicht geprüft.'),
    'bosch-edc17': Method(
        'bosch-edc17', 'Bosch MED17/EDC17-Prüfsummenblöcke', 'MED17, EDC17', 'gemessen',
        'Auf einer EDC17CP09-Datei 8 von 11 Strukturen reproduziert; kein unabhängiger Nachweis.',
        'Korrektur nur mit signiertem OEM-Nachweis; CRC32-Blöcke werden nur geprüft.'),
    'bosch-edc16': Method(
        'bosch-edc16', 'Bosch EDC16-Prüfsummenbereiche', 'EDC16 (MPC5xx)', 'gemessen',
        'Auf je einer EDC16C31- und EDC16C35-Datei 1 von 1 Bereich reproduziert; kein unabhängiger Nachweis.',
        'Korrektur nur mit signiertem OEM-Nachweis.'),
    'profil': Method(
        'profil', 'Geprüftes Checksummenprofil (SHA-256-gebunden)', 'beliebig', 'manuell',
        'Vom Prüfer für genau diese Originaldatei angegeben.',
        'Deckt nur die deklarierten Bereiche ab, außer der Prüfer bestätigt die Vollständigkeit.'),
    'tabelle-generisch': Method(
        'tabelle-generisch', 'Selbstbeschreibende Tabelle (generisches Verfahren)', 'unbekannt', 'experimentell',
        'Am Original reproduziert, aber ohne Referenz für dieses Verfahren.',
        'Nur Prüfung, keine Korrektur.'),
}

# What each family has beyond the implemented methods. Sources: ME7Sum (ME7.x checks),
# the Bosch block layout (MED17/EDC17). Unknown families are never assumed complete.
FAMILY_RULES = (
    (re.compile(r'^ME7'), ('ROMSYS-Prüfsummen', 'CRC-Tabelle', 'Haupt-Datenprüfsummen',
                           'Programmseiten', 'Hintergrund- und Hauptprogramm-Prüfsummen'),
     ('RSA-Signatur über Programmbereiche (ME7.x)', 'erwartet')),
    (re.compile(r'^MED?9'), ('weitere Prüfsummen dieser Familie (nicht dokumentiert)',),
     ('Herstellersignatur', 'unbekannt')),
    (re.compile(r'^(MED17|EDC17|MEV?D?17|ME17)'), (),
     ('RSA-Signatur der Anwendungsblöcke (MED17/EDC17)', 'erwartet')),
    (re.compile(r'^EDC16'), ('weitere Prüfungen dieser Familie (nicht dokumentiert)',),
     ('Herstellersignatur', 'unbekannt')),
)
SIGNATURE_TEXT = {'erwartet': 'bei dieser Familie üblich – nicht geprüft',
                  'erkannt': 'Struktur vorhanden – nicht geprüft',
                  'unbekannt': 'unbekannt – nicht geprüft'}
EDC17_SIGNATURE_BLOCKS = ('Tuning protection', 'Customer Tuning protection', 'Application Attestation')
MAX_PASSES = 6


class Cancelled(Exception):
    """The caller asked to stop; nothing was changed."""


@dataclass
class Region:
    method: str
    name: str
    start: int                 # first covered byte (file offset)
    end: int                   # last covered byte (inclusive)
    storage: int               # file offset of the stored value
    storage_len: int
    algorithm: str
    stored: int | None
    computed: int | None
    state: str                 # ok / fehler / unbestaetigt
    note: str = ''
    correctable: bool = False

    def asdict(self) -> dict:
        return asdict(self)


@dataclass
class MethodResult:
    method: str
    regions: list[Region] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    correction: str = ''       # '' = correction possible; otherwise the reason it is locked

    @property
    def info(self) -> Method:
        return METHODS[self.method]

    def count(self, state: str) -> int:
        return sum(r.state == state for r in self.regions)

    @property
    def coverage(self) -> str:
        if not self.regions or not self.count(OK) + self.count(BAD):
            return 'keine'
        return 'vollständig' if not self.count(UNPROVEN) else 'teilweise'

    def asdict(self) -> dict:
        return {'method': self.method, 'title': self.info.title, 'validation': self.info.validation,
                'coverage': self.coverage, 'ok': self.count(OK), 'fehler': self.count(BAD),
                'unbestaetigt': self.count(UNPROVEN), 'correction': self.correction or 'möglich',
                'notes': list(self.notes), 'regions': [r.asdict() for r in self.regions]}


@dataclass(frozen=True)
class Signature:
    kind: str
    state: str                 # erwartet / erkannt / unbekannt – never "gültig"
    detail: str = ''


@dataclass
class IntegrityReport:
    status: str
    reasons: list[str]
    family: str | None
    identification: str
    software: list[str]
    hardware: list[str]
    methods: list[MethodResult]
    signatures: list[Signature]
    unchecked: list[str]
    candidates: int
    size: int
    sha256_original: str
    sha256_current: str
    seconds: float = 0.

    @property
    def status_text(self) -> str:
        return STATUS_TEXT[self.status]

    @property
    def regions(self) -> list[Region]:
        return [r for m in self.methods for r in m.regions]

    @property
    def errors(self) -> list[Region]:
        return [r for r in self.regions if r.state == BAD]

    @property
    def correctable(self) -> bool:
        """At least one wrong checksum that an unlocked method can correct."""
        return any(r.state == BAD and r.correctable for m in self.methods if not m.correction for r in m.regions)

    def summary(self) -> str:
        checked = sum(r.state != UNPROVEN for r in self.regions)
        return (f'{self.status_text} · {len(self.methods)} Verfahren · {checked} Bereiche geprüft · '
                f'{len(self.errors)} Fehler')

    def asdict(self) -> dict:
        return {'status': self.status, 'status_text': self.status_text, 'reasons': list(self.reasons),
                'family': self.family, 'identification': self.identification, 'software': list(self.software),
                'hardware': list(self.hardware), 'methods': [m.asdict() for m in self.methods],
                'signatures': [asdict(s) for s in self.signatures], 'unchecked': list(self.unchecked),
                'candidates': self.candidates, 'size': self.size, 'sha256_original': self.sha256_original,
                'sha256_current': self.sha256_current, 'seconds': round(self.seconds, 3),
                'flash_approved': False}

    def text(self) -> str:
        lines = ['CHECKSUMMEN & INTEGRITÄT', '', f'Status: {self.status_text}']
        lines += [f'  • {r}' for r in self.reasons]
        lines += ['', f'Steuergerät: {self.family or "nicht identifiziert"} ({self.identification})']
        if self.software:
            lines.append(f'Software: {", ".join(self.software)}')
        if self.hardware:
            lines.append(f'Hardware: {", ".join(self.hardware)}')
        lines += [f'Original SHA-256: {self.sha256_original}', f'Aktuell SHA-256:  {self.sha256_current}', '']
        if not self.methods:
            lines.append('Kein Prüfsummenverfahren in dieser Datei nachgewiesen.')
        for m in self.methods:
            lines.append(f'Verfahren: {m.info.title} ({VALIDATION_TEXT[m.info.validation]})')
            lines.append(f'  Bereiche: {len(m.regions)} · stimmen {m.count(OK)} · Fehler {m.count(BAD)} · '
                         f'nicht bestätigt {m.count(UNPROVEN)} · Abdeckung {m.coverage}')
            lines.append(f'  Korrektur: {m.correction or "möglich (Vorschau zeigt jedes Byte)"}')
            lines += [f'  Hinweis: {n}' for n in m.notes]
            for r in m.regions:
                stored = '–' if r.stored is None else f'0x{r.stored:08X}'
                computed = '–' if r.computed is None else f'0x{r.computed:08X}'
                lines.append(f'  [{REGION_TEXT[r.state]}] {r.name}: 0x{r.start:X}–0x{r.end:X}, '
                             f'Prüffeld 0x{r.storage:X}, {r.algorithm}, gespeichert {stored}, berechnet {computed}'
                             + (f' – {r.note}' if r.note else ''))
            lines.append('')
        if self.unchecked:
            lines.append(f'Nicht geprüft: {", ".join(self.unchecked)}')
        for s in self.signatures:
            lines.append(f'Signatur: {s.kind} – {SIGNATURE_TEXT[s.state]}{f" ({s.detail})" if s.detail else ""}')
        if self.candidates:
            lines.append(f'{self.candidates} unbestätigte Tabellenkandidaten ignoriert '
                         '(Füllmuster oder unbekanntes Verfahren).')
        lines += ['', 'Prüfsummen und Signaturen sind getrennte Prüfungen. Kein Ergebnis dieser Prüfung ist eine '
                  'Flash-, Abgas- oder Straßenfreigabe.']
        return '\n'.join(lines)


# --- helpers -------------------------------------------------------------------

def _word_sum(data: bytes, start: int, end: int, endian: str) -> int | None:
    """Sum of 16-bit words (CPU byte order) over [start, end], modulo 2^32."""
    chunk = data[start:end + 1]
    if len(chunk) % 2 or not chunk:
        return None
    return int(np.frombuffer(chunk, ('<' if endian == 'little' else '>') + 'u2').sum(dtype=np.uint64)) & M32


def reference_word_sum(data: bytes, start: int, end: int, endian: str) -> int:
    """Second, deliberately plain implementation of the multipoint sum (no numpy), for re-checks."""
    fmt = '<H' if endian == 'little' else '>H'
    total = 0
    for pos in range(start, end + 1, 2):
        total = (total + struct.unpack_from(fmt, data, pos)[0]) & M32
    return total


def _pair(value: int, endian: str) -> bytes:
    return value.to_bytes(4, endian) + (~value & M32).to_bytes(4, endian)


def _check(cancelled):
    if cancelled is not None and cancelled():
        raise Cancelled()


def _family_rules(family: str | None):
    for pattern, unchecked, signature in FAMILY_RULES:
        if family and pattern.search(family.upper()):
            return list(unchecked), signature
    return None, None


# --- methods -------------------------------------------------------------------

def _table_runs(records):
    """Contiguous 16-byte-stride runs of records with the same byte order."""
    runs = []
    for b in sorted(records, key=lambda r: (r.endian, r.record)):
        if runs and b.endian == runs[-1][-1].endian and b.record == runs[-1][-1].record + 16:
            runs[-1].append(b)
        else:
            runs.append([b])
    return runs


def _tables(original: bytes, current: bytes) -> tuple[MethodResult | None, MethodResult | None, int]:
    """Multipoint tables (reference-validated word sum) and other proven table records."""
    multipoint, generic, candidates = MethodResult('bosch-multipoint'), MethodResult('tabelle-generisch'), 0
    for run in _table_runs(tables.find_checksum_tables(original)):
        proven = [b for b in run if _word_sum(original, b.start, b.end, b.endian) == b.stored]
        bases = {b.base for b in proven}
        for b in run:
            fields_now = current[b.record + 8:b.record + 16]
            stored = int.from_bytes(fields_now[:4], b.endian)
            coherent = int.from_bytes(fields_now[4:], b.endian) == ~stored & M32
            moved = current[b.record:b.record + 8] != original[b.record:b.record + 8]
            name = f'Tabelle 0x{b.record:X}'
            if proven:
                computed = _word_sum(current, b.start, b.end, b.endian)
                words = f'sum32-words-{"le" if b.endian == "little" else "be"}'
                if b not in proven and b.base not in bases:
                    multipoint.regions.append(Region('bosch-multipoint', name, b.start, b.end, b.record + 8, 8, words,
                                                     stored, computed, UNPROVEN,
                                                     'Adresslage weicht von der bestätigten Tabelle ab'))
                    continue
                good = computed == stored and coherent and not moved
                note = ('Tabelleneintrag (Adressen) verändert' if moved else
                        '' if b in proven else 'am geöffneten Original nicht bestätigt – Datei war bereits verändert')
                multipoint.regions.append(Region('bosch-multipoint', name, b.start, b.end, b.record + 8, 8, words,
                                                 stored, computed, OK if good else BAD, note, not moved))
            elif b.verified:
                computed = tables.compute(current, b)
                good = computed == stored and coherent and not moved
                generic.regions.append(Region('tabelle-generisch', name, b.start, b.end, b.record + 8, 8,
                                              b.algorithm, stored, computed, OK if good else BAD,
                                              'Tabelleneintrag (Adressen) verändert' if moved else ''))
            else:
                candidates += 1
    if multipoint.regions:
        self_cov = sum(tables._self_covering(tables.ChecksumBlock(int(r.storage - 8), r.start, r.end, 0, 'little', 0,
                                                                  r.algorithm)) for r in multipoint.regions)
        if self_cov:
            multipoint.notes.append(f'{self_cov} Eintrag/Einträge decken die eigene Tabelle ab '
                                    '(bei Wortsummen unkritisch: Wert und Komplement ergeben eine Konstante).')
    if generic.regions:
        generic.correction = 'gesperrt: Verfahren experimentell (keine Referenz)'
    return (multipoint if multipoint.regions else None, generic if generic.regions else None, candidates)


def _edc17(image: BinaryImage, original: bytes, current: bytes) -> tuple[MethodResult | None, list[Signature]]:
    blocks = edc17.find_blocks(original)
    if not blocks:
        return None, []
    result, signatures = MethodResult('bosch-edc17'), []
    for block in blocks:
        if block.name in EDC17_SIGNATURE_BLOCKS:
            signatures.append(Signature(f'Bosch-Block „{block.name}“', 'erkannt', f'@ 0x{block.bin_start:X}'))
        if block.unprogrammed:
            result.notes.append(f'{block.name} @ 0x{block.bin_start:X}: unprogrammierte Partition, übersprungen')
            continue
        for cs in block.structures:
            edc17._evaluate(original, cs)
            changed = current[cs.offset:cs.offset + edc17.STRUCT_SIZE] != original[cs.offset:cs.offset + edc17.STRUCT_SIZE]
            now = replace(cs, computed=None, valid=None)
            edc17._evaluate(current, now)
            name = f'{block.name} · {cs.algo_name}'
            if cs.valid:
                state, note = (BAD, 'Strukturdaten verändert') if changed else (OK if now.valid else BAD, '')
            else:
                state = UNPROVEN
                note = ('Bereich liegt außerhalb des Blocks' if not cs.in_bounds else
                        'Verfahren unbekannt' if cs.valid is None else 'stimmt am geöffneten Original nicht')
            result.regions.append(Region('bosch-edc17', name, cs.start_file, cs.end_file, cs.offset + 16, 4,
                                         cs.algo_name, cs.expected, now.computed, state, note,
                                         cs.algorithm in edc17.CORRECTABLE and state == BAD and not changed))
    try:
        edc17.plan_correction(image)
    except ValueError as exc:
        result.correction = f'gesperrt: {exc}'
    if any(r.algorithm == 'CRC32' and r.state == BAD for r in result.regions):
        result.notes.append('CRC32-Blöcke werden nur geprüft, nicht korrigiert (mögliche Signatur-/Sicherheitsfelder).')
    return result, signatures


def _edc16(image: BinaryImage, original: bytes, current: bytes) -> MethodResult | None:
    statuses = edc16.analyze(original)
    if not statuses:
        return None
    result = MethodResult('bosch-edc16')
    for s in statuses:
        r = s.region
        total = edc16.sum_region(current, r)
        stored = int.from_bytes(current[r.checksum_offset:r.checksum_offset + 4], 'big')
        name = f'Bereich 0x{r.start:X}'
        if s.valid:
            state, note = (OK if total == edc16.TARGET_SUM else BAD), ''
        else:
            state, note = UNPROVEN, 'Zielsumme am geöffneten Original nicht erreicht'
        result.regions.append(Region('bosch-edc16', name, r.start, r.end, r.checksum_offset, 4, 'sum32-dwords-be',
                                     stored, total, state, note, state == BAD))
    try:
        edc16.plan_correction(image)
    except ValueError as exc:
        result.correction = f'gesperrt: {exc}'
    return result


def _profile(image: BinaryImage, profile: ChecksumProfile | None) -> MethodResult | None:
    if profile is None:
        return None
    result = MethodResult('profil')
    try:
        state = verify_checksums(image, profile)
    except ValueError as exc:
        result.notes.append(f'Profil nicht anwendbar: {exc}')
        result.correction = 'gesperrt: Profil nicht anwendbar'
        return result
    by_name = {s.name: s for s in profile.slots}
    for row in state['regions']:
        slot = by_name[row['name']]
        result.regions.append(Region('profil', row['name'], row['start'], row['end'] - 1, row['storage_offset'],
                                     slot.width, row['algorithm'], row['stored'], row['expected'],
                                     OK if row['match'] else BAD, '', True))
    if getattr(profile, 'complete', False):
        result.notes.append(f'Prüfer {profile.reviewer} bestätigt: Profil deckt alle Prüfsummen dieser Datei ab.')
    else:
        result.notes.append('Profil deckt nur die deklarierten Bereiche ab (Vollständigkeit nicht bestätigt).')
    try:
        plan_checksum_correction(image, profile)
    except ValueError as exc:
        result.correction = f'gesperrt: {exc}'
    return result


# --- check ---------------------------------------------------------------------

def check_integrity(image: BinaryImage, *, profile: ChecksumProfile | None = None,
                    progress=None, cancelled=None) -> IntegrityReport:
    """Check every applicable method on ``image`` (original proves, current is checked).

    ``progress(percent, text)`` and ``cancelled()`` are optional callables; a
    cancelled check raises Cancelled and changes nothing.
    """
    from .identification import identify
    started = time.perf_counter()
    say = progress or (lambda pct, text: None)
    original = image.original
    say(5, 'Steuergerät identifizieren …')
    ident = identify(BinaryImage(original))
    _check(cancelled)
    current = image.read(0, image.size)
    say(20, 'Multipoint-Tabellen prüfen …')
    multipoint, generic, candidates = _tables(original, current)
    _check(cancelled)
    say(50, 'MED17/EDC17-Blöcke prüfen …')
    e17, signatures = _edc17(image, original, current)
    _check(cancelled)
    say(75, 'EDC16-Bereiche prüfen …')
    e16 = _edc16(image, original, current)
    _check(cancelled)
    say(90, 'Checksummenprofil prüfen …')
    prof = _profile(image, profile)
    methods = [m for m in (multipoint, e17, e16, prof, generic) if m is not None]

    family = ident.family
    unchecked, signature = _family_rules(family)
    if signature and not any(s.state == 'erkannt' for s in signatures):
        signatures.insert(0, Signature(signature[0], signature[1]))
    reasons = []
    regions = [r for m in methods for r in m.regions]
    bad = [r for r in regions if r.state == BAD]
    checked = [r for r in regions if r.state != UNPROVEN]
    profile_complete = (prof is not None and prof.regions and getattr(profile, 'complete', False))
    if bad:
        status = INVALID
        reasons.append(f'{len(bad)} geprüfte Prüfsumme(n) stimmen nicht mit den aktuellen Bytes überein.')
    elif checked:
        incomplete = []
        unproven = [r for r in regions if r.state == UNPROVEN]
        if unproven:
            incomplete.append(f'{len(unproven)} Bereich(e) nicht bestätigt und daher ungeprüft.')
        # A measured method counts as validated only once its signed OEM record unlocks it.
        weak = sorted({METHODS[m.method].title for m in methods
                       if METHODS[m.method].validation in ('gemessen', 'experimentell') and m.count(OK)
                       and not (m.method in ('bosch-edc17', 'bosch-edc16') and not m.correction)})
        if weak:
            incomplete.append(f'Verfahren ohne unabhängigen Nachweis: {", ".join(weak)}.')
        if not profile_complete:
            if ident.level != 'eindeutig' or not family:
                incomplete.append('Steuergerät nicht eindeutig identifiziert – Vollständigkeit der Prüfung nicht belegbar.')
            elif unchecked is None:
                incomplete.append(f'Für {family} ist nicht dokumentiert, welche Prüfsummen das Steuergerät prüft.')
            elif unchecked:
                incomplete.append(f'Weitere Prüfsummen von {family} werden nicht geprüft: {", ".join(unchecked)}.')
        if incomplete:
            status = INCOMPLETE
            reasons.append(f'{len(checked)} geprüfte Prüfsumme(n) stimmen.')
            reasons += incomplete
        else:
            status = VALID
            reasons.append(f'Alle {len(checked)} bekannten Prüfsummen geprüft und gültig.')
    elif family:
        status = UNSUPPORTED
        reasons.append(f'Für {family} ist in dieser Datei kein unterstütztes Prüfsummenverfahren nachweisbar.')
    else:
        status = UNKNOWN
        reasons.append('Weder Steuergerät noch Prüfsummenverfahren nachweisbar.')
    if any(s.state in ('erwartet', 'erkannt') for s in signatures):
        reasons.append('Signaturen werden nicht geprüft; eine Prüfsummenkorrektur ersetzt keine gültige '
                       'Herstellersignatur.')
    if unchecked and not profile_complete:
        unchecked = list(unchecked)
    else:
        unchecked = []
    say(100, 'Fertig')
    return IntegrityReport(
        status=status, reasons=reasons, family=family,
        identification=f'{ident.level}: {ident.level_reason}', software=list(ident.software),
        hardware=list(ident.hardware), methods=methods, signatures=signatures, unchecked=unchecked,
        candidates=candidates, size=image.size, sha256_original=image.digest,
        sha256_current=hashlib.sha256(current).hexdigest(), seconds=time.perf_counter() - started)


# --- correction ----------------------------------------------------------------

@dataclass(frozen=True)
class CorrectionStep:
    method: str
    region: str
    offset: int
    old: bytes
    new: bytes
    note: str = ''


@dataclass
class CorrectionPlan:
    sha256_current: str
    revision: int
    steps: list[CorrectionStep]
    refused: list[tuple[str, str]]
    warnings: list[str]
    status_before: str

    @property
    def positions(self) -> set[int]:
        return {s.offset + i for s in self.steps for i in range(len(s.new)) if s.old[i] != s.new[i]}

    def text(self) -> str:
        lines = ['KORREKTURVORSCHAU', '', f'Status vorher: {STATUS_TEXT[self.status_before]}', '']
        if self.steps:
            lines.append(f'{len(self.steps)} Prüffeld(er), {len(self.positions)} Byte würden geändert '
                         '(nur diese Positionen):')
            for s in self.steps:
                lines.append(f'  • {METHODS[s.method].title} · {s.region} @ 0x{s.offset:08X}: '
                             f'{s.old.hex(" ").upper()} → {s.new.hex(" ").upper()}' + (f' ({s.note})' if s.note else ''))
        else:
            lines.append('Keine Korrektur möglich oder nötig.')
        for method, reason in self.refused:
            lines.append(f'Nicht korrigiert – {METHODS[method].title}: {reason}')
        if self.warnings:
            lines.append('')
            lines += [f'Achtung: {w}' for w in self.warnings]
        lines += ['', 'Die Korrektur wird danach unabhängig nachgeprüft; schlägt das fehl, bleibt die Datei '
                  'unverändert. Keine Flashfreigabe.']
        return '\n'.join(lines)


def _plan_multipoint(current: bytearray, method: MethodResult) -> list[CorrectionStep]:
    targets = [r for r in method.regions if r.state == BAD and r.correctable]
    if not targets:
        return []
    start = bytes(current)
    endian = {r.storage: ('little' if r.algorithm.endswith('le') else 'big') for r in method.regions}
    for _ in range(MAX_PASSES):
        changed = False
        for r in targets:
            value = _word_sum(bytes(current), r.start, r.end, endian[r.storage])
            new = _pair(value, endian[r.storage])
            if bytes(current[r.storage:r.storage + 8]) != new:
                current[r.storage:r.storage + 8] = new
                changed = True
        if not changed:
            break
    else:
        raise ValueError('Tabellen kommen nicht zur Ruhe (Prüffeld liegt ungünstig im eigenen Bereich)')
    for r in method.regions:     # every entry of the established tables must hold afterwards
        if r.state != UNPROVEN:
            e = endian[r.storage]
            if bytes(current[r.storage:r.storage + 8]) != _pair(_word_sum(bytes(current), r.start, r.end, e), e):
                raise ValueError(f'{r.name} stimmt nach der Planung nicht')
    return [CorrectionStep('bosch-multipoint', r.name, r.storage, start[r.storage:r.storage + 8],
                           bytes(current[r.storage:r.storage + 8]),
                           r.note if 'nicht bestätigt' in r.note else '')
            for r in targets if start[r.storage:r.storage + 8] != bytes(current[r.storage:r.storage + 8])]


def plan_correction(image: BinaryImage, report: IntegrityReport | None = None, *,
                    profile: ChecksumProfile | None = None) -> CorrectionPlan:
    """Byte-exact plan for every correctable method; nothing is written here."""
    report = report or check_integrity(image, profile=profile)
    current = bytearray(image.read(0, image.size))
    steps, refused = [], []
    for m in report.methods:
        if not m.count(BAD):
            continue
        if m.correction:
            refused.append((m.method, m.correction))
            continue
        try:
            if m.method == 'bosch-multipoint':
                steps += _plan_multipoint(current, m)
            elif m.method == 'bosch-edc17':
                found, skipped = edc17.plan_correction(image)
                steps += [CorrectionStep('bosch-edc17', 'Kompensationswort', o, old, new) for o, old, new in found]
                if skipped:
                    refused.append(('bosch-edc17', f'CRC32-Blöcke nur geprüft: {", ".join(skipped)}'))
            elif m.method == 'bosch-edc16':
                steps += [CorrectionStep('bosch-edc16', 'Kompensationswort', o, old, new)
                          for o, old, new in edc16.plan_correction(image)]
            elif m.method == 'profil':
                steps += [CorrectionStep('profil', s.slot, s.storage_offset, s.old, s.new)
                          for s in plan_checksum_correction(image, profile)]
            else:
                refused.append((m.method, 'keine Korrektur für dieses Verfahren'))
        except ValueError as exc:
            refused.append((m.method, str(exc)))
    taken = {}
    for s in steps:
        for i in range(len(s.new)):
            if taken.setdefault(s.offset + i, s.method) != s.method:
                raise ValueError(f'Korrekturen überschneiden sich bei 0x{s.offset + i:X} – Korrektur verweigert')
    warnings = []
    if report.unchecked:
        warnings.append(f'Weitere Prüfsummen werden nicht geprüft und nicht korrigiert: {", ".join(report.unchecked)}. '
                        'Die Datei ist dadurch nicht flashbereit.')
    if any(s.state in ('erwartet', 'erkannt') for s in report.signatures):
        warnings.append('Eine Prüfsummenkorrektur ersetzt keine gültige Herstellersignatur; Signaturen bleiben '
                        'ungeprüft und unverändert.')
    if any(r.state == UNPROVEN for r in report.regions):
        warnings.append('Nicht bestätigte Bereiche werden weder geprüft noch korrigiert.')
    return CorrectionPlan(report.sha256_current, image.revision, sorted(steps, key=lambda s: s.offset),
                          refused, warnings, report.status)


def _fresh(plan: CorrectionPlan, image: BinaryImage) -> bytes:
    data = image.read(0, image.size)
    if image.revision != plan.revision or hashlib.sha256(data).hexdigest() != plan.sha256_current:
        raise ValueError('Datei hat sich seit der Vorschau geändert – bitte neu prüfen')
    for s in plan.steps:
        if data[s.offset:s.offset + len(s.old)] != s.old:
            raise ValueError('Vorschau passt nicht zu den aktuellen Bytes – bitte neu prüfen')
    return data


def corrected_bytes(image: BinaryImage, plan: CorrectionPlan) -> bytes:
    """Current bytes with the plan applied (the image itself is not changed)."""
    out = bytearray(_fresh(plan, image))
    for s in plan.steps:
        out[s.offset:s.offset + len(s.new)] = s.new
    return bytes(out)


def image_with(original_image: BinaryImage, data: bytes) -> BinaryImage:
    """A new image with the same original and ``data`` as current bytes (overlay only)."""
    fresh = BinaryImage(original_image.original, original_image.path)
    if len(data) != fresh.size:
        raise ValueError('Größe weicht vom Original ab')
    diff = np.flatnonzero(np.frombuffer(fresh.original, np.uint8) != np.frombuffer(data, np.uint8))
    fresh._patches = {int(p): data[p] for p in diff}
    return fresh


def recheck(image: BinaryImage, before: bytes, after: bytes, plan: CorrectionPlan, *,
            profile: ChecksumProfile | None = None) -> IntegrityReport:
    """Independent re-check of a correction result; ValueError if anything is off.

    1. Byte guard: only the planned positions differ between ``before`` and ``after``.
    2. Fresh full check on a new image built from ``after`` (no state shared with the plan).
    3. Corrected multipoint fields are recomputed with a second, plain implementation.
    """
    a, b = np.frombuffer(before, np.uint8), np.frombuffer(after, np.uint8)
    changed = set(np.flatnonzero(a != b).tolist())
    if not changed <= plan.positions:
        raise ValueError(f'{len(changed - plan.positions)} Byte außerhalb der dokumentierten Positionen geändert')
    report = check_integrity(image_with(image, after), profile=profile)
    by_storage = {r.storage: r for r in report.regions}
    for s in plan.steps:
        region = by_storage.get(s.offset)
        if region is not None and region.state != OK:
            raise ValueError(f'Nachprüfung: {region.name} stimmt nach der Korrektur nicht')
        if s.method == 'bosch-multipoint':
            if region is None:
                raise ValueError(f'Nachprüfung: Tabelleneintrag @ 0x{s.offset:X} nicht wiedergefunden')
            e = 'little' if region.algorithm.endswith('le') else 'big'
            if after[s.offset:s.offset + 8] != _pair(reference_word_sum(after, region.start, region.end, e), e):
                raise ValueError(f'Nachprüfung (Referenzrechnung): {region.name} stimmt nicht')
    corrected = {s.method for s in plan.steps}
    if any(r.state == BAD and r.method in corrected for r in report.regions):
        raise ValueError('Nachprüfung: nach der Korrektur stimmen nicht alle Bereiche der korrigierten Verfahren')
    return report


def apply_correction(image: BinaryImage, plan: CorrectionPlan, *,
                     profile: ChecksumProfile | None = None) -> IntegrityReport:
    """Write the plan into the session as ONE undo step, re-check, roll back on any doubt."""
    if not plan.steps:
        raise ValueError('Nichts zu korrigieren')
    before = _fresh(plan, image)
    after = corrected_bytes(image, plan)
    report = recheck(image, before, after, plan, profile=profile)    # before anything is written
    changes = [(p, before[p], after[p]) for p in sorted(plan.positions)]
    image.commit(changes, label='Prüfsummenkorrektur', expected_revision=plan.revision)
    if image.read(0, image.size) != after:
        image.undo()
        raise ValueError('Korrektur nicht vollständig übernommen – zurückgesetzt')
    return report


def change_log(image: BinaryImage, plan: CorrectionPlan, after: bytes, report: IntegrityReport,
               target: str | None = None) -> dict:
    from .. import __version__
    return {'format': 1, 'tool': f'ECU Studio AI {__version__}',
            'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'input': image.path, 'output': target,
            'sha256_original': image.digest, 'sha256_input': plan.sha256_current,
            'sha256_output': hashlib.sha256(after).hexdigest(),
            'status_before': STATUS_TEXT[plan.status_before], 'status_after': report.status_text,
            'changed_bytes': len(plan.positions),
            'steps': [{'method': s.method, 'region': s.region, 'offset': f'0x{s.offset:X}',
                       'old': s.old.hex(), 'new': s.new.hex(), 'note': s.note} for s in plan.steps],
            'refused': [{'method': m, 'reason': r} for m, r in plan.refused],
            'warnings': list(plan.warnings),
            'flash_approved': False}


def write_corrected_copy(image: BinaryImage, plan: CorrectionPlan, target: str | Path, *,
                         profile: ChecksumProfile | None = None) -> dict:
    """Corrected COPY at ``target`` plus ``<target>.korrektur.json``; session and original stay unchanged.

    Every check runs before the first byte is written; the copy is written
    atomically (existing target kept as .bak). If the change log cannot be
    written, the copy is removed again: there is never a partial result.
    """
    from .storage import atomic_write
    if not plan.steps:
        raise ValueError('Nichts zu korrigieren')
    target = Path(target)
    log_path = target.with_name(target.name + '.korrektur.json')
    if image.path and target.resolve() == Path(image.path).resolve():
        raise ValueError('Originaldatei darf nicht überschrieben werden')
    before = _fresh(plan, image)
    after = corrected_bytes(image, plan)
    report = recheck(image, before, after, plan, profile=profile)
    log = change_log(image, plan, after, report, str(target))
    payload = json.dumps(log, indent=2, ensure_ascii=False).encode('utf-8')
    previous = target.read_bytes() if target.exists() else None
    atomic_write(target, after, backup=True, protected=(image.path,))
    try:
        atomic_write(log_path, payload, protected=(image.path,))
    except Exception:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            atomic_write(target, previous, protected=(image.path,))
        raise
    if Path(target).read_bytes() != after:
        raise ValueError('Gespeicherte Kopie weicht ab')
    return log


def write_report_json(path: str | Path, report: IntegrityReport) -> None:
    from .storage import atomic_write
    atomic_write(path, json.dumps(report.asdict(), indent=2, ensure_ascii=False).encode('utf-8'))
