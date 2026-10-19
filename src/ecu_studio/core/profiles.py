"""Evidence-based identity hints for ECU and TCU binary images.

No matching Damos/XDF is implied by a family-level identification. In
particular, GS20 GS20/G10C9000 definitions cannot be applied to GADC9010.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import re

from .model import BinaryImage
from .xdf import recognize_ms43


@dataclass(frozen=True)
class ECUProfile:
    family: str = 'Unbekannt'
    controller: str = 'Unbekannt'
    software_version: str | None = None
    calibration_id: str | None = None
    calibration_number: str | None = None
    project_id: str | None = None
    cal_start: int | None = None
    cal_end: int | None = None
    full_read: bool = False
    evidence: tuple[str, ...] = ()
    advice: str = ''

    @property
    def identified(self) -> bool:
        return self.family != 'Unbekannt'

    def asdict(self) -> dict:
        return asdict(self)


def identify_profile(image: BinaryImage) -> ECUProfile:
    """Read a small fixed set of in-file identity signatures, not user secrets."""
    if image.size in (65536, 524288):
        # 64-KiB calibration image OR the corresponding window in a 512-KiB full read.
        base = 0 if image.size == 65536 else 0x10000
        data = image.read(base, 65536)
        # Two independent in-file signatures are required before reporting GS20.
        # The 8-char code varies by software revision. Do not hardcode GADC9010 alone.
        identifier = re.search(rb'G[A-Z0-9]{7}', data[0x160:0x1b0])
        footer = re.search(rb'G2210_[A-Z0-9]{10}', data[0xffb0:0xfff8])
        if identifier and footer:
            cal_id = identifier.group(0).decode('ascii')
            project = footer.group(0).decode('ascii')
            # This string location was established on a user-provided 90C0 sample.
            # Absence does not invalidate another GS20 image.
            sw = data[0x3fd8:0x3fdf]
            sw_version = sw.decode('ascii') if re.fullmatch(rb'[0-9]{7}',sw) else None
            return ECUProfile(
                family='Siemens GS20', controller='Getriebesteuergerät (TCU/EGS)',
                software_version=None, calibration_id=cal_id,
                calibration_number=sw_version,
                project_id=project, cal_start=base, cal_end=base+65536,
                full_read=image.size == 524288,
                evidence=('GS20-typische Kopfkennung im Datenfenster',
                          'GS20-Projektmarker im Footer',
                          '64-KiB-Teilabbild'),
                advice=('Nur XDF/A2L derselben GS20-Kalibrierung verwenden. '
                        'G10C9000-XDF passt nicht automatisch zu '+cal_id+'. '
                        'Heuristische Rohdatenbereiche sind NICHT benannte Kennfelder.'))
    # MS42 identity corroborated on a public stock compatibility image, with
    # both its calibration ID and a matching .DAT marker in the header.
    if image.size in (32768,524288):
        start=0 if image.size==32768 else 0x48000
        head=image.read(start,min(256,image.size-start))
        if b'0110C6' in head and b'ca0110C6.DAT' in head:
            return ECUProfile(family='Siemens MS42',controller='Motorsteuergerät (DME)',
                software_version='0110C6',cal_start=start,cal_end=start+32768,
                full_read=image.size==524288,
                evidence=('MS42-Kalibrierkennung 0110C6','Übereinstimmender .DAT-Projektmarker'),
                advice='MS42 0110C6: zusätzlich Achsen und Firmwarevariante prüfen.')
    if image.size in (24576,262144):
        # Family/SW hint only. Automatic layout use still requires independent,
        # distributed matching axes; never infer the SW from byte count alone.
        text=image.read(0,image.size)
        if b'1429861' in text:
            start=0 if image.size==24576 else 0x14000
            return ECUProfile(family='Siemens MS41',controller='Motorsteuergerät (DME)',
                software_version='1429861',cal_start=start,cal_end=start+24576,
                full_read=image.size==262144,evidence=('MS41-Softwarekennung 1429861 im Abbild',),
                advice='MS41-XDF-Adresskopplung ist ein Quellenhinweis, kein unabhängiger Layoutnachweis.')
    ms43 = recognize_ms43(image)
    if ms43.get('version'):
        start=ms43['cal_start']
        return ECUProfile(family='Siemens MS43', controller='Motorsteuergerät (DME)',
                          software_version=ms43['version'],cal_start=start,
                          cal_end=start+0x10000,full_read=ms43['full_read'],
                          evidence=('MS43-Softwaremarker im Kalibrierfenster',),
                          advice='Für Funktionsnamen genau zum erkannten Softwarestand passende XDF/A2L koppeln.')
    return ECUProfile()


def xdf_match_status(profile: ECUProfile, xdf_file: str, title: str = '') -> tuple[str, str]:
    """File/title-based compatibility triage (not calibration proof).

    "rejected" blocks *known* mismatches. Unknown matches require user review.
    "plausible" is only an ID-size hint, not verified map addresses.
    """
    if not profile.identified:
        return 'unverified', 'ECU/TCU-Signatur nicht erkannt – Definition manuell prüfen.'
    name=(Path(xdf_file).name+' '+title).upper()
    named_families=set(re.findall(r'MS(?:41|42|43)',name))
    own=profile.family.split()[-1]
    if named_families and own not in named_families:
        return 'rejected','Die XDF nennt eine andere Steuergerätefamilie.'
    if profile.family in ('Siemens MS41','Siemens MS42'):
        sizes=[int(s)*1024 for s in re.findall(r'(?<![0-9])(24|32|64|256|512)K',name)]
        if sizes and profile.cal_end and ((profile.full_read and image_size_for_profile(profile) not in sizes)
                                         or (not profile.full_read and profile.cal_end not in sizes)):
            return 'rejected','XDF-Dateigröße passt nicht zum Voll-/Teilabbild.'
        sw=profile.software_version or ''
        if sw in name:return 'plausible','Familie und Softwarekennung stimmen; Achsen/Layout zusätzlich prüfen.'
        return 'unverified','Softwarekennung nicht ausdrücklich in der XDF gefunden.'
    if profile.family=='Siemens GS20':
        if 'MS43' in name or 'MS42' in name:
            return 'rejected','Motorsteuergeräte-XDF darf nicht mit GS20 gekoppelt werden.'
        if '512K' in name and not profile.full_read:
            return 'rejected','512K-Vollread-XDF passt nicht zum 64K-Teilabbild.'
        if '64K' in name and profile.full_read:
            return 'rejected','64K-Teilabbild-XDF passt nicht zum 512K-Vollread.'
        tokens=set(re.findall(r'G[A-Z0-9]{7}',name))
        if tokens and profile.calibration_id not in tokens:
            return 'rejected',f'XDF-Kennung {", ".join(sorted(tokens))} weicht von {profile.calibration_id} ab.'
        # A matching ID in the XDF name is still only a plausibility hint.
        if profile.calibration_id and profile.calibration_id in name:
            return 'plausible','Kalibrierkennung stimmt im XDF-Titel überein; Adressen dennoch prüfen.'
        return 'unverified','Keine explizit übereinstimmende GS20-Kalibrierkennung im XDF-Titel.'
    if profile.family=='Siemens MS43':
        if 'GS20' in name:
            return 'rejected','Getriebesteuergeräte-XDF darf nicht mit MS43 gekoppelt werden.'
        if '64K' in name and profile.full_read:return 'rejected','Teilabbild-XDF passt nicht zum Vollread.'
        if '512K' in name and not profile.full_read:return 'rejected','Vollread-XDF passt nicht zum Teilabbild.'
        declared_versions=set(re.findall(r'(?:MS43)?(4300[0-9]{2})',name))
        if declared_versions and profile.software_version not in declared_versions:
            return 'rejected','XDF nennt einen anderen MS43-Softwarestand: '+', '.join(sorted(declared_versions))
        if profile.software_version and profile.software_version in name:
            return 'plausible','Softwarekennung im XDF-Titel stimmt überein; Firmware-Patchstand prüfen.'
        return 'unverified','XDF-Softwarekennung kann aus Dateiname/Titel nicht bestätigt werden.'
    return 'unverified','Keine ECU-spezifische Kompatibilitätsprüfung verfügbar.'


def image_size_for_profile(profile: ECUProfile) -> int:
    return 262144 if profile.family=='Siemens MS41' else 524288


def local_xdf_candidates(image: BinaryImage, *directories: str | Path) -> list[Path]:
    """Only high-specificity file-name matches; never silently apply a definition.

    No network calls, and *plausible* does not establish patch/layout agreement.
    The caller must explicitly ask whether the user wants to review/import.
    """
    profile = identify_profile(image)
    if not profile.identified:
        return []
    result=[]
    seen=set()
    for directory in directories:
        d=Path(directory).expanduser()
        if not d.is_dir():
            continue
        for entry in sorted(d.glob('*.xdf')):
            if not entry.is_file() or entry.stat().st_size > 25*1024*1024:
                continue
            status,_=xdf_match_status(profile,str(entry))
            if status=='plausible' and entry.resolve() not in seen:
                seen.add(entry.resolve())
                result.append(entry)
    return result
