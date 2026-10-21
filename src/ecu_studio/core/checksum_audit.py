"""Conservative ECU checksum verification and calibration export auditing.

A generic CRC does not establish ECU flash checksum validity. Only a locally
reviewed manifest pinned to the ORIGINAL binary hash can validate its declared
regions. Checksum locations are never guessed.

Correction is prepared, not improvised: ``plan_checksum_correction`` refuses
unless the reviewed profile verifies on the unmodified original (proving that
algorithm, ranges and storage are right), and ``apply_checksum_correction``
writes the planned values only if every slot verifies afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
import zlib

from .model import BinaryImage, MapDefinition

# algorithm -> width of the stored value in bytes
SUPPORTED = {'crc32-ieee': 4, 'crc16-ccitt': 2, 'sum16-bytes': 2, 'sum32-bytes': 4,
             'sum16-words-be': 2, 'sum16-words-le': 2, 'sum32-words-be': 4, 'sum32-words-le': 4,
             'sum32-dwords-be': 4, 'sum32-dwords-le': 4}
WORD_ALIGN = {'sum16-words-be': 2, 'sum16-words-le': 2, 'sum32-words-be': 2, 'sum32-words-le': 2,
              'sum32-dwords-be': 4, 'sum32-dwords-le': 4}
COMPLEMENTS = ('none', 'ones', 'twos')   # stored value, ~value, or -value (sum + stored = 0)
MAX_PROFILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ChecksumSlot:
    name: str
    algorithm: str
    start: int
    end: int           # end-exclusive
    storage_offset: int
    endian: str = 'big'
    # Further [start, end) ranges covered by the same value (e.g. split blocks).
    extra_ranges: tuple[tuple[int, int], ...] = ()
    complement: str = 'none'

    @property
    def ranges(self) -> tuple[tuple[int, int], ...]:
        return ((self.start, self.end),) + tuple(self.extra_ranges)

    @property
    def width(self) -> int:
        return SUPPORTED[self.algorithm]

    def check(self, size: int) -> None:
        if not self.name.strip() or self.algorithm not in SUPPORTED:
            raise ValueError('Ungültiger Prüfbereich oder nicht unterstützter Algorithmus')
        width = SUPPORTED[self.algorithm]
        if not all(type(v) is int for r in self.ranges for v in r) or type(self.storage_offset) is not int:
            raise ValueError('Offsets müssen Ganzzahlen sein')
        if len(self.ranges) > 16:
            raise ValueError('Höchstens 16 Teilbereiche je Prüffeld')
        if not 0 <= self.storage_offset <= size - width:
            raise ValueError('Prüfbereich oder Feld außerhalb der Datei')
        for start, end in self.ranges:
            if not 0 <= start < end <= size:
                raise ValueError('Prüfbereich oder Feld außerhalb der Datei')
            if end > self.storage_offset and start < self.storage_offset + width:
                raise ValueError('Prüffeld liegt im geprüften Bereich (Selbstreferenz nicht unterstützt)')
            align = WORD_ALIGN.get(self.algorithm, 1)
            if (end - start) % align:
                raise ValueError('Bereichslänge passt nicht zur Wortbreite des Algorithmus')
        spans = sorted(self.ranges)
        if any(b[0] < a[1] for a, b in zip(spans, spans[1:])):
            raise ValueError('Teilbereiche überlappen sich')
        if self.endian not in ('big','little'):
            raise ValueError('Unbekannte Byte-Reihenfolge')
        if self.complement not in COMPLEMENTS:
            raise ValueError('Unbekannte Komplementbildung')


@dataclass(frozen=True)
class ChecksumProfile:
    firmware_sha256: str
    source: str
    reviewer: str
    reviewed: bool
    slots: tuple[ChecksumSlot, ...]

    def check(self, image: BinaryImage) -> None:
        if not (isinstance(self.firmware_sha256, str) and len(self.firmware_sha256) == 64 and
                all(ch in '0123456789abcdef' for ch in self.firmware_sha256)):
            raise ValueError('Ungültiger SHA-256')
        if self.firmware_sha256 != image.digest:
            raise ValueError('Prüfprofil gehört nicht zur Original-Firmware (SHA-256 abweichend)')
        if (not isinstance(self.source,str) or not self.source.strip() or
            not isinstance(self.reviewer,str) or not self.reviewer.strip() or self.reviewed is not True):
            raise ValueError('Nur manuell geprüfte Profile mit Herkunft und Prüfer zulässig')
        if not self.slots or len(self.slots) > 32:
            raise ValueError('1 bis 32 Prüfsummenbereiche erforderlich')
        seen=set()
        for slot in self.slots:
            slot.check(image.size)
            if slot.name in seen: raise ValueError('Doppelter Bereichsname')
            seen.add(slot.name)
        # A stored value inside another slot's range makes the result depend on
        # the correction order; not supported rather than silently wrong.
        for slot in self.slots:
            for other in self.slots:
                if other is not slot and any(e > slot.storage_offset and s < slot.storage_offset + slot.width
                                             for s, e in other.ranges):
                    raise ValueError(f'Prüffeld „{slot.name}“ liegt im Bereich von „{other.name}“ '
                                     '(verkettete Prüfsummen nicht unterstützt)')


def load_checksum_profile(path: str | Path, image: BinaryImage) -> ChecksumProfile:
    p=Path(path)
    if p.stat().st_size > MAX_PROFILE_BYTES: raise ValueError('Prüfprofil zu groß')
    obj=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(obj,dict) or obj.get('format') != 1:
        raise ValueError('Ungültiges Checksum-Profilformat')
    slots=obj.get('slots')
    if not isinstance(slots,list): raise ValueError('slots muss eine Liste sein')
    items=[]
    for row in slots:
        if not isinstance(row,dict): raise ValueError('Ungültiger Prüffeldeintrag')
        if any(key not in ('name','algorithm','start','end','storage_offset','endian','extra_ranges','complement')
               for key in row):
            raise ValueError('Unbekanntes Checksum-Feld')
        row=dict(row)
        extra=row.pop('extra_ranges',[])
        if not isinstance(extra,list) or not all(isinstance(r,list) and len(r)==2 for r in extra):
            raise ValueError('extra_ranges muss eine Liste von [start, end] sein')
        items.append(ChecksumSlot(**row,extra_ranges=tuple(tuple(r) for r in extra)))
    profile=ChecksumProfile(
        firmware_sha256=obj['firmware_sha256'],source=obj['source'],
        reviewer=obj['reviewer'],reviewed=obj['reviewed'],slots=tuple(items))
    profile.check(image)
    return profile


def _crc16_ccitt(payload: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), table-driven."""
    table = _CRC16_TABLE
    for b in payload:
        crc = ((crc << 8) & 0xFFFF) ^ table[((crc >> 8) ^ b) & 0xFF]
    return crc


def _crc16_table():
    out = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else c << 1
        out.append(c & 0xFFFF)
    return tuple(out)


_CRC16_TABLE = _crc16_table()


def _checksum(payload: bytes, algorithm: str) -> int:
    import numpy as np
    if algorithm == 'crc32-ieee': return zlib.crc32(payload) & 0xFFFFFFFF
    if algorithm == 'crc16-ccitt': return _crc16_ccitt(payload)
    if algorithm == 'sum16-bytes': return sum(payload) & 0xFFFF
    if algorithm == 'sum32-bytes': return sum(payload) & 0xFFFFFFFF
    if algorithm in WORD_ALIGN:
        size = WORD_ALIGN[algorithm]
        order = '>' if algorithm.endswith('-be') else '<'
        words = np.frombuffer(payload, order + ('u2' if size == 2 else 'u4')).astype(np.uint64)
        total = int(words.sum(dtype=np.uint64))
        return total & (0xFFFF if algorithm.startswith('sum16') else 0xFFFFFFFF)
    raise ValueError('Nicht unterstützter Algorithmus')


def slot_value(image: BinaryImage, slot: ChecksumSlot) -> int:
    """The value the ECU expects in the storage field for the current bytes."""
    algorithm = slot.algorithm
    mask = (1 << (8 * slot.width)) - 1
    if algorithm.startswith('crc'):
        if algorithm == 'crc32-ieee':
            value = 0
            for s, e in slot.ranges:
                value = zlib.crc32(image.read(s, e - s), value)
            value &= 0xFFFFFFFF
        else:
            value = 0xFFFF
            for s, e in slot.ranges:
                value = _crc16_ccitt(image.read(s, e - s), value)
    else:
        value = sum(_checksum(image.read(s, e - s), algorithm) for s, e in slot.ranges) & mask
    if slot.complement == 'ones':
        value = ~value & mask
    elif slot.complement == 'twos':
        value = -value & mask
    return value


def verify_checksums(image: BinaryImage, profile: ChecksumProfile | None = None) -> dict:
    """Report each declared region; unknown != success. No automatic repairs."""
    if profile is None:
        return {'status':'unknown','verified':False,'regions':[],
                'message':'Kein zur Original-Firmware geprüftes ECU-Checksummenprofil geladen.'}
    profile.check(image)
    regions=[]
    for slot in profile.slots:
        expected=slot_value(image,slot)
        width=slot.width
        stored=int.from_bytes(image.read(slot.storage_offset,width),slot.endian)
        regions.append({'name':slot.name,'algorithm':slot.algorithm,'start':slot.start,'end':slot.end,
                        'storage_offset':slot.storage_offset,'expected':expected,'stored':stored,
                        'match':expected==stored})
    good=all(row['match'] for row in regions)
    return {'status':'match' if good else 'mismatch', 'verified':good,
            'regions':regions,'message':('Alle deklarierten Prüffelder stimmen überein. '
            'Keine Flash- oder Herstellerfreigabe.' if good else
            'Mindestens ein deklariertes Prüffeld stimmt NICHT überein.')}


@dataclass(frozen=True)
class CorrectionStep:
    slot: str
    storage_offset: int
    old: bytes
    new: bytes


def plan_checksum_correction(image: BinaryImage, profile: ChecksumProfile) -> list[CorrectionStep]:
    """Storage-field values that make every declared slot match the current bytes.

    Refused unless the profile verifies on the unmodified original: a profile
    that does not explain the factory file must not be used to "repair" a
    modified one. Nothing is written here.
    """
    if profile is None:
        raise ValueError('Ohne geprüftes Checksummenprofil keine Korrektur')
    profile.check(image)
    original = BinaryImage(image.original)
    if not verify_checksums(original, profile)['verified']:
        raise ValueError('Profil stimmt bereits am Original nicht – Korrektur verweigert')
    steps = []
    for slot in profile.slots:
        new = slot_value(image, slot).to_bytes(slot.width, slot.endian)
        old = image.read(slot.storage_offset, slot.width)
        if new != old:
            steps.append(CorrectionStep(slot.name, slot.storage_offset, old, new))
    return steps


def correction_preview(steps: list[CorrectionStep]) -> str:
    """Human-readable plan shown before anything is written."""
    if not steps:
        return 'Alle deklarierten Prüffelder stimmen bereits – nichts zu schreiben.'
    lines = [f'{len(steps)} Prüffeld(er) würden geschrieben (nur diese Bytes, rückgängig machbar):', '']
    for s in steps:
        lines.append(f'• {s.slot} @ 0x{s.storage_offset:08X}: {s.old.hex(" ").upper()}  →  {s.new.hex(" ").upper()}')
    lines += ['', 'Grundlage: geprüftes Profil, am unveränderten Original bestätigt. Nur die im Profil '
              'deklarierten Prüfsummen werden korrigiert; Signaturen oder weitere ECU-Prüfungen nicht. '
              'Keine Flashfreigabe.']
    return '\n'.join(lines)


def apply_checksum_correction(image: BinaryImage, profile: ChecksumProfile,
                              steps: list[CorrectionStep]) -> dict:
    """Write a plan from plan_checksum_correction and verify; rolled back on any doubt."""
    fresh = plan_checksum_correction(image, profile)
    if [(s.slot, s.storage_offset, s.new) for s in fresh] != [(s.slot, s.storage_offset, s.new) for s in steps]:
        raise ValueError('Datei hat sich seit der Planung geändert – bitte neu planen')
    before = {s.storage_offset: image.read(s.storage_offset, len(s.new)) for s in steps}
    for s in steps:
        image.write(s.storage_offset, s.new)
    result = verify_checksums(image, profile)
    if not result['verified']:
        for offset, old in before.items():
            image.write(offset, old)
        raise ValueError('Nach der Korrektur stimmen nicht alle Prüffelder – zurückgesetzt')
    return result


def audit_export(image: BinaryImage, maps: list[MapDefinition],
                 profile: ChecksumProfile | None = None) -> dict:
    """Decode, memory coverage and checksum diagnostics; never certify driveability."""
    from .quality import audit_catalog
    from .impact import uncovered_patches
    status=verify_checksums(image,profile)
    issues=[]
    if not status['verified']:
        issues.append({'level':'warning','code':'checksum-'+status['status'],
                       'message':status['message']})
    # Self-describing checksum tables proven on the original (ME7.x, MED9, ME9).
    from .checksum_tables import check_tables
    tables=check_tables(image)
    if tables['mismatches']:
        issues.append({'level':'warning','code':'checksum-table-mismatch',
                       'message':f"{tables['mismatches']} von {tables['blocks']} am Original bewiesenen Tabellen-Prüfsummen "
                                 'stimmen nicht mehr (Werkzeuge → Prüfsummen-Tabellen der Datei prüfen / korrigieren).'})
    quality=audit_catalog(image,maps,sample_limit=48)
    warnings=sum(bool(q.warnings) for q in quality)
    bad=sum(q.decode_mismatches>0 for q in quality)
    if bad: issues.append({'level':'warning','code':'map-decode',
                           'message':f'{bad} Kennfelddefinitionen enthalten Decode-Widersprüche.'})
    if warnings: issues.append({'level':'info','code':'definition-review',
                                 'message':f'{warnings} Definitionen mit Prüfhinweisen (Achsen/Herkunft/Einheiten).'})
    uncovered_count, _ = uncovered_patches(image,maps)
    from .impact import measure_map_impact
    # Only analyze changed maps. No engine-specific tolerance may be inferred.
    edited_positions=sorted(image._patches)
    import bisect
    affected=[]
    for m in maps:
        lo=bisect.bisect_left(edited_positions,m.offset)
        if lo >= len(edited_positions) or edited_positions[lo] >= m.offset+m.length:
            continue
        try:
            impact=measure_map_impact(image,m)
            if impact.cells_changed:
                affected.append({'name':m.name,'offset':m.offset,'cells_changed':impact.cells_changed,
                    'max_abs_delta':impact.max_abs_delta,'unit':m.unit,'verified_definition':m.verified})
        except (ValueError,OverflowError,IndexError) as exc:
            issues.append({'level':'warning','code':'impact-analysis',
                           'message':f'{m.name}: Änderung nicht dekodierbar: {exc}'})
    if any(not row['verified_definition'] for row in affected):
        issues.append({'level':'warning','code':'unverified-modification',
                       'message':'Mindestens ein verändertes Kennfeld besitzt keine geprüfte Definition.'})
    if uncovered_count: issues.append({'level':'warning','code':'unmapped-patches',
                                       'message':f'{uncovered_count} veränderte Bytes außerhalb bekannter Kennfelder.'})
    return {'checksum_tables':{k:tables[k] for k in ('status','blocks','mismatches')},
            'original_sha256':image.digest,
            'modified_sha256':hashlib.sha256(image.materialize()).hexdigest(),
            'size':image.size,'dirty_bytes':image.dirty_bytes,
            'map_count':len(maps),'map_decode_issues':bad,
            'map_review_hints':warnings,'changed_outside_maps':uncovered_count,
            'changed_maps':affected,'changed_map_count':len(affected),
            'checksums':status,'issues':issues,'flash_approved':False,
            'note':'Prüfergebnis ist keine Aussage zur Flashbarkeit, Motor-/Abgassicherheit oder Straßenzulassung.'}


def write_audit_json(path: str | Path, audit: dict) -> None:
    Path(path).write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
