"""ECU support matrix: what is measured for which ECU family, in four status levels.

The data lives in recognition/data/ecu_support.json (single source for the app
dialog and docs/ECU_SUPPORT.md). Metrics there are copied by
tools/support_matrix.py from benchmark_suite results; nothing is typed in by hand.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'ecu_support.json'
STATUSES = {
    'validiert': 'Mit echten, passenden Firmware- und vollständigen Referenzdateien gemessen.',
    'teilweise': 'Einzelne Funktionen oder Softwarestände nachweislich gemessen (z. B. nur Teil-Referenz).',
    'experimentell': 'Erkennung läuft, aber nicht ausreichend gegen Referenzen geprüft.',
    'nicht validiert': 'Keine belastbaren Testdaten vorhanden – Ergebnisse sind ungeprüft.',
}


@dataclass
class SupportEntry:
    family: str
    status: str
    processor: str = ''
    match: list[str] = field(default_factory=list)
    software: list[str] = field(default_factory=list)
    reference: str = ''
    role: str = ''
    metrics: dict = field(default_factory=dict)
    limits: str = ''
    needed: str = ''

    def quality(self) -> str:
        m = self.metrics
        if not m:
            return 'nicht gemessen'
        text = f"{m['exact_2d']} von {m['reference_2d']} Kennfeldern exakt"
        if m.get('precision_2d') is not None:
            text += f", Präzision {m['precision_2d']:.0%}"
        if m.get('exact_1d'):
            text += f", {m['exact_1d']} Kennlinien/Achsen exakt"
        return text


@lru_cache(maxsize=1)
def load() -> tuple[SupportEntry, ...]:
    raw = json.loads(DATA.read_text(encoding='utf-8'))
    return tuple(SupportEntry(**e) for e in raw['entries'])


def lookup(family: str | None) -> SupportEntry | None:
    """Entry whose match names equal the identified family (case-insensitive, no dots/underscores)."""
    if not family:
        return None
    key = family.upper().replace('.', '').replace('_', '').replace(' ', '')
    for e in load():
        if any(key == m.upper().replace('.', '').replace('_', '').replace(' ', '') for m in e.match):
            return e
    return None
