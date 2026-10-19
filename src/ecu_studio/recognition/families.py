"""Extensible *name registry*, not family detection from arbitrary byte strings.

Bosch MD1 and MG1 are broad ECU platforms, not single binary memory layouts.
No address conversion or semantic map classification is inferred here.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class FamilySupport:
    name: str
    vendors: tuple[str,...]
    domain: str
    data_needed: str
    autodetect_ready: bool = False
    verified_labels: int = 0

FAMILIES={x.name:x for x in (
    FamilySupport('Bosch MD1',('Bosch',),'Engine/Diesel','Genauer MD1-Variantencode, Software-ID, signiertes Speicherlayout, passende A2L/KP, Binärabbild'),
    FamilySupport('Bosch MG1',('Bosch',),'Engine/Gasoline','Genauer MG1-Variantencode, Software-ID, Speichersegmente, A2L/KP, Binärabbild'),
    FamilySupport('Bosch EDC17',('Bosch',),'Engine/Diesel','EDC17-Variante, HW/SW-Kennung, ECU-Adresssegmente und passende Definition'),
    FamilySupport('Bosch EDC16',('Bosch',),'Engine/Diesel','EDC16-Typ, HW/SW-Kennung, Definition'),
    FamilySupport('Bosch EDC15',('Bosch',),'Engine/Diesel','EDC15-Typ, HW/SW-Kennung, Definition'),
    FamilySupport('Bosch MED/ME',('Bosch',),'Engine/Gasoline','Präziser Typ, HW/SW-Kennung, Definition'),
    FamilySupport('Continental SIMOS',('Continental','Siemens'),'Engine/Gasoline','Simos-Version, Software-ID, Definition'),
    FamilySupport('Continental SID',('Continental','Siemens'),'Engine/Diesel','SID-Version, Software-ID, Definition'),
    FamilySupport('Delphi DCM',('Delphi',),'Engine/Diesel','DCM-Version, HW/SW-Kennung, Definition'),
    FamilySupport('Denso',('Denso',),'Engine','Passende lokale RomRaider-XML mit interner ROM-ID/Größe oder XDF/A2L; kein OEM-Paket enthalten'),
    FamilySupport('Siemens MS43',('Siemens',),'Engine/Gasoline','Sechs Standard-Softwarestände, 64K/512K-XDFs offline; Variante ungeprüft',True),
    FamilySupport('Siemens MS42',('Siemens',),'Engine/Gasoline','0110C6 Standard 32K/512K offline; weitere Stände mit lokaler Definition',True),
    FamilySupport('Siemens MS41',('Siemens',),'Engine/Gasoline','1429861 Standard-XDF 24K/256K offline; realer BIN-Nachweis ausstehend'),
    FamilySupport('Siemens GS20',('Siemens',),'Transmission','Genaue GS20-Kalibrierkennung und passende XDF/A2L',True),
    FamilySupport('ZF TCU',('ZF',),'Transmission','TCU-Generation, HW/SW-ID und Getriebe-Definition'),
    FamilySupport('Hitachi 5EAT TCU',('Hitachi',),'Transmission','Subaru M32R, Kalibrier-ID, genau zugeordnete RomRaider-Definition'),
    FamilySupport('Denso 5EAT TCU',('Denso',),'Transmission','Subaru SH705x, Kalibrier-ID und verifiziertes Tabellenlayout'),
    FamilySupport('VAG DQ250 TCU',('Volkswagen','Bosch','Continental'),'Transmission','Getriebesteuergerät-Teilenummer, SW-Stand und passende Definition'),
    FamilySupport('VAG DQ381 TCU',('Volkswagen','Continental'),'Transmission','Genaue DQ381-Variante und softwarestandgebundene Kalibrierdaten'),
    FamilySupport('Continental SIM2K',('Continental',),'Engine/Gasoline','Hyundai/Kia Softwarestand und verifizierte XDF/BIN-Paarung'),
    FamilySupport('Bosch ME7 Volvo',('Bosch',),'Engine/Gasoline','Volvo ME7 Softwarekennung, Referenz-XDF, Firmware-Hash'),
    FamilySupport('Delco GM 68HC11',('Delco',),'Engine/Transmission','Controller-ID, Bank-Mapping und verifizierte Referenzdefinition'),
)}

def require_family(name:str)->FamilySupport:
    if name not in FAMILIES:
        raise ValueError(f'Nicht registrierte ECU-Familie: {name!r}. Bitte explizit neues Profil anlegen.')
    return FAMILIES[name]
