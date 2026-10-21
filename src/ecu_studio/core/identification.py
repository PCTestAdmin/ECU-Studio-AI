"""ECU identity from markers stored in the image: family, hardware and software numbers.

Only what is literally in the file is reported, each with its offset. Nothing
is inferred from size or layout. Markers that disagree (e.g. two family names)
are reported as ambiguous instead of picking one.

Sources (measured on local reference images, see docs/ECU_SUPPORT.md):
- Bosch EPK string ``<n>/1/<family>/...`` (ME7, ME7.5, M4.4, MED9.1, EDC17CP09).
  Placeholder EPKs (``X000``, ``____``) as in BMW EDC16 dumps are ignored.
- Bosch hardware ``0261…`` (petrol) / ``0281…`` (diesel), software ``1037…``/``1039…``.
- VAG part numbers of engine control units (``8V0907404A``, ``06A906032HS``).
- Siemens/Continental hardware ``5WK9…`` and plain-text family names (Simos, SID, MSV, MSD).
  These patterns are not yet measured on real Continental files (none available).
Calibration-only dumps (MSD80/MSD85, ME9.2.1) often hold none of these; their
identity comes from a matching A2L (EPK check in a2l.py).
"""
from __future__ import annotations
import collections
import re
from dataclasses import dataclass, field
from .model import BinaryImage

EPK = re.compile(rb'(?<![0-9])([0-9]{1,3})/1/([A-Z][A-Z0-9_.]{2,15})/([A-Za-z0-9_./ -]{0,60})')
BOSCH_HW = re.compile(rb'(02[68][01][0-9]{6})')   # often directly next to the SW number
BOSCH_SW = re.compile(rb'(103[79][0-9]{6})')
VAG_PN = re.compile(rb'(?<![0-9A-Z])([0-9][0-9A-Z][0-9A-Z]90[67][0-9]{3}[A-Z]{0,3})(?![0-9A-Z])')
SIEMENS_HW = re.compile(rb'(?<![0-9A-Z])(5WK9[0-9]{3,4})(?![0-9])')
FAMILY_TEXT = re.compile(rb'(?<![A-Z0-9])(EDC1[567](?:_?C[P]?[0-9]{2})?|MEV?D?1[67](?:\.[0-9]{1,2}){0,3}|MED9[0-9.]{0,4}|ME7(?:\.[0-9])?'
                         rb'|MD1C[PS][0-9]{3}|MG1C[PS][0-9]{3}'
                         # Continental / Siemens VDO plain-text family names
                         rb'|SIMOS ?[0-9]{1,2}(?:\.[0-9]{1,2})?|SID ?[0-9]{3}(?:EVO)?|MSV ?[78]0|MSD ?8[0157])(?![A-Z0-9])')
PLACEHOLDER = re.compile(r'X000|_{4,}|999/')


def _family_name(raw: str) -> str:
    """Bosch notation: EDC17_CP09 -> EDC17CP09, MED91 -> MED9.1, ME701 -> ME7.0.1; 'SIMOS 18.1' -> SIMOS18.1."""
    s = raw.replace('_', '').replace(' ', '')
    m = re.fullmatch(r'(MED9|ME7)([0-9])([0-9]?)', s)
    if m and '.' not in s:
        return m.group(1) + '.' + m.group(2) + ('.' + m.group(3) if m.group(3) else '')
    return s


@dataclass
class Marker:
    kind: str
    value: str
    offset: int


@dataclass
class Identity:
    family: str | None = None
    family_evidence: str = ''
    ambiguous: list[str] = field(default_factory=list)
    hardware: list[str] = field(default_factory=list)
    software: list[str] = field(default_factory=list)
    part_numbers: list[str] = field(default_factory=list)
    epk: str | None = None
    markers: list[Marker] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.family:
            parts.append(f'Familie {self.family} ({self.family_evidence})')
        elif self.ambiguous:
            parts.append('Familie mehrdeutig: ' + ', '.join(self.ambiguous))
        else:
            parts.append('Familie: keine Kennung in der Datei')
        if self.hardware:
            parts.append('HW ' + ', '.join(self.hardware))
        if self.software:
            parts.append('SW ' + ', '.join(self.software))
        if self.part_numbers:
            parts.append('Teilenummer ' + ', '.join(self.part_numbers))
        return ' · '.join(parts)


def _first(pattern, data: bytes, kind: str, limit: int = 3) -> list[Marker]:
    seen, out = set(), []
    for m in pattern.finditer(data):
        v = m.group(1).decode('latin-1')
        if v not in seen:
            seen.add(v)
            out.append(Marker(kind, v, m.start(1)))
            if len(out) >= limit:
                break
    return out


def identify(image: BinaryImage) -> Identity:
    data = image.read(0, image.size)
    ident = Identity()
    epks = [m for m in EPK.finditer(data)]
    real = [m for m in epks if not PLACEHOLDER.search(m.group(0).decode('latin-1'))]
    if real:
        m = real[0]
        ident.epk = m.group(0).decode('latin-1').rstrip('/ ')
        ident.markers.append(Marker('EPK', ident.epk, m.start()))
        families = collections.OrderedDict((_family_name(x.group(2).decode('latin-1')), x.start()) for x in real)
        if len(families) == 1:
            ident.family, off = next(iter(families.items()))
            ident.family_evidence = f'Bosch-EPK @ 0x{off:X}'
        else:
            ident.ambiguous = list(families)
    if ident.family is None and not ident.ambiguous:
        texts = collections.Counter(_family_name(x.group(1).decode('latin-1')) for x in FAMILY_TEXT.finditer(data))
        # Only a single, specific name counts (EDC16 dumps name C31 and C35 alike).
        specific = [t for t in texts if t not in ('EDC16', 'EDC17', 'MED17', 'EDC15')]
        if len(specific) == 1:
            ident.family = specific[0]
            off = next(x.start() for x in FAMILY_TEXT.finditer(data) if _family_name(x.group(1).decode('latin-1')) == specific[0])
            ident.family_evidence = f'Familienname im Klartext @ 0x{off:X}'
        elif len(specific) > 1:
            ident.ambiguous = sorted(specific)
    for kind, pattern, target in (('Bosch-HW', BOSCH_HW, ident.hardware), ('Siemens-HW', SIEMENS_HW, ident.hardware),
                                  ('Bosch-SW', BOSCH_SW, ident.software), ('VAG-Teilenummer', VAG_PN, ident.part_numbers)):
        for marker in _first(pattern, data, kind):
            target.append(marker.value)
            ident.markers.append(marker)
    return ident
