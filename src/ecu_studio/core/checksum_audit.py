"""Conservative ECU checksum verification and calibration export auditing.

A generic CRC does not establish ECU flash checksum validity. Only a locally
reviewed manifest pinned to the ORIGINAL binary hash can validate its declared
regions. Neither this module nor the UI repairs or guesses checksum locations.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
import zlib

from .model import BinaryImage, MapDefinition

SUPPORTED = {'crc32-ieee': 4, 'sum16-bytes': 2, 'sum32-bytes': 4}
MAX_PROFILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ChecksumSlot:
    name: str
    algorithm: str
    start: int
    end: int           # end-exclusive
    storage_offset: int
    endian: str = 'big'

    def check(self, size: int) -> None:
        if not self.name.strip() or self.algorithm not in SUPPORTED:
            raise ValueError('Ungültiger Prüfbereich oder nicht unterstützter Algorithmus')
        width = SUPPORTED[self.algorithm]
        if not all(type(v) is int for v in (self.start, self.end, self.storage_offset)):
            raise ValueError('Offsets müssen Ganzzahlen sein')
        if not (0 <= self.start < self.end <= size and 0 <= self.storage_offset <= size - width):
            raise ValueError('Prüfbereich oder Feld außerhalb der Datei')
        if self.end > self.storage_offset and self.start < self.storage_offset + width:
            raise ValueError('Prüffeld liegt im geprüften Bereich (Selbstreferenz nicht unterstützt)')
        if self.endian not in ('big','little'):
            raise ValueError('Unbekannte Byte-Reihenfolge')


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
        if any(key not in ('name','algorithm','start','end','storage_offset','endian') for key in row):
            raise ValueError('Unbekanntes Checksum-Feld')
        items.append(ChecksumSlot(**row))
    profile=ChecksumProfile(
        firmware_sha256=obj['firmware_sha256'],source=obj['source'],
        reviewer=obj['reviewer'],reviewed=obj['reviewed'],slots=tuple(items))
    profile.check(image)
    return profile


def _checksum(payload: bytes, algorithm: str) -> int:
    if algorithm == 'crc32-ieee': return zlib.crc32(payload) & 0xFFFFFFFF
    if algorithm == 'sum16-bytes': return sum(payload) & 0xFFFF
    if algorithm == 'sum32-bytes': return sum(payload) & 0xFFFFFFFF
    raise ValueError('Nicht unterstützter Algorithmus')


def verify_checksums(image: BinaryImage, profile: ChecksumProfile | None = None) -> dict:
    """Report each declared region; unknown != success. No automatic repairs."""
    if profile is None:
        return {'status':'unknown','verified':False,'regions':[],
                'message':'Kein zur Original-Firmware geprüftes ECU-Checksummenprofil geladen.'}
    profile.check(image)
    regions=[]
    for slot in profile.slots:
        expected=_checksum(image.read(slot.start,slot.end-slot.start),slot.algorithm)
        width=SUPPORTED[slot.algorithm]
        stored=int.from_bytes(image.read(slot.storage_offset,width),slot.endian)
        regions.append({'name':slot.name,'algorithm':slot.algorithm,'start':slot.start,'end':slot.end,
                        'storage_offset':slot.storage_offset,'expected':expected,'stored':stored,
                        'match':expected==stored})
    good=all(row['match'] for row in regions)
    return {'status':'match' if good else 'mismatch', 'verified':good,
            'regions':regions,'message':('Alle deklarierten Prüffelder stimmen überein. '
            'Keine Flash- oder Herstellerfreigabe.' if good else
            'Mindestens ein deklariertes Prüffeld stimmt NICHT überein.')}


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
    return {'original_sha256':image.digest,
            'modified_sha256':hashlib.sha256(image.materialize()).hexdigest(),
            'size':image.size,'dirty_bytes':image.dirty_bytes,
            'map_count':len(maps),'map_decode_issues':bad,
            'map_review_hints':warnings,'changed_outside_maps':uncovered_count,
            'changed_maps':affected,'changed_map_count':len(affected),
            'checksums':status,'issues':issues,'flash_approved':False,
            'note':'Prüfergebnis ist keine Aussage zur Flashbarkeit, Motor-/Abgassicherheit oder Straßenzulassung.'}


def write_audit_json(path: str | Path, audit: dict) -> None:
    Path(path).write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
