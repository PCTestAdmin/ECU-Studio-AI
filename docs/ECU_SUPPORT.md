# ECU-Unterstützung: was gemessen ist und was nicht (Stand 21.10.2026)

Jede Zeile nennt **konkrete Dateien**, gegen die gemessen wurde. „Gefunden“ = Anteil der 2D-Referenzkennfelder
(≥ 4×4), die ein Fund zu ≥ 50 % überdeckt; „exakt“ = gleicher Start, gleiche Form und Breite. Präzision ist nur
bei **vollständigen** Referenzen (Hersteller-A2L, vollständige Community-XDF) belastbar. Die Referenzdateien
liegen nicht im Repository.

## Validiert mit vollständiger Referenz

Reproduzierbar mit `python -m ecu_studio.tools.benchmark_suite MANIFEST.json` (Vorlage:
`examples/templates/benchmark_manifest.template.json`). **Rolle:** *test* = nie zum Einstellen verwendet (unabhängig),
*development* = Schwellen daran gemessen, *training* = Lernmodell/Kalibrierung daran trainiert.
„Achsen richtig“ = exakt gefundene Kennfelder, deren Rohachsen linear zur Referenzachse passen.

### Neu (21.10.2026): moderne Bosch-/Siemens-Steuergeräte mit Hersteller-A2L

| Variante | Prozessor | Rolle | Identität | gefunden | exakt 2D | Präzision 2D | Achsen richtig | exakt 1D (Präzision) |
|---|---|---|---|---:|---:|---:|---:|---:|
| **Bosch EDC17CP09** (BMW, EPK `33/1/EDC17_CP09/11/P_574//V8KB///`, 2 MB mit Programm) | TriCore | development | EPK ✅ | 30 % | 157/703 | 71 % | 150/150 | 332 (85 %) |
| **Siemens MSD85** (EPK `7913F100`) | PowerPC | **test** | EPK ✅ | 24 % | 148/1026 | 74 % | 135/135 | 354 (88 %) |
| **Siemens MSD80** (EPK `80B7I000`, 2 Stände = 1 Gruppe) | PowerPC | **test** | EPK ✅ | 29 % | 133–137/864 | 77–78 % | 107/107 | 241–243 (86 %) |
| **Bosch EDC16C35** (BMW 4M702389) | PowerPC | development | Achsen 940/940 | 40 % | 111/387 | 66 % | 102/102 | 212 (89 %) |
| **Bosch EDC16C31** (BMW 6m661411) | PowerPC | development | Achsen 897/897 | 48 % | 123/364 | 71 % | 116/116 | 242 (92 %) |

Vorher (gleiche Referenzen, Stand vor dieser Runde): EDC17CP09 exakt 46 / Präzision 62 %, MSD85 91 / 72 %,
MSD80 93–96 / 73–74 %, EDC16C35 91 / 64 %, EDC16C31 93 / 69 %; 1D exakt 0–19.

### Ältere Familien

| Variante | Prozessor | Referenz | gefunden | exakt | Präzision | Code-Verweise |
|---|---|---|---:|---:|---:|---|
| Siemens MS43 430069 | C167 | MS4x-XDF (GPL-3.0) | 67 % | 197/379 | 80 % | ✅ Seite+Offset, Lookup |
| Siemens MS42 0110C6 | C167 | MS4x-XDF | 50 % | 22/213 | 72 % | ◐ |
| BMW ME9 770115XE | „GoldenOak“ (A2L) | **Hersteller-A2L** | 36 % | 41/233 | 50 % | ❌ |
| BMW ME9.2.1 725D601B | „GoldenOak“ (A2L) | **Hersteller-A2L** | 44 % | 109/460 | 69 % | ❌ |
| Siemens MS45 4520D30S | – | **Hersteller-A2L** | 18 % | 28/472 | 67 % | ❌ |

## Gemessen mit unvollständiger Referenz (Präzision nicht belastbar)

| Variante | Prozessor | gefunden | exakt | Bemerkung |
|---|---|---:|---:|---|
| Bosch ME7 (Volvo, 3 Stände) | C167 | 55–66 % | 6–7 | Lookup-Aufrufe |
| Bosch ME7.5 VAG 06A906032HS / 8E0909518AK | C167 | 48 % / 58 % | 68 / 38 | Basis 0x800000, Kennfeldköpfe |
| Denso Subaru 5EAT (9 ROMs) | SH-2 | 93–100 % | 147–178 | Beschreibungsblöcke |
| GM P01 | 68k | 35 % | 10 | Absolutoperanden |
| Bosch M4.4 (Volvo) | 8051 | 54 % | 8 | nur bestätigend |
| Bosch MED17.1.62 (8V0907404A/E/H/J, 8S0907404G/L – Kennung in der Datei; 496-KB-Dumps zu 85–91 % Daten, also Kalibrierbereich ohne Programm) | TriCore | 13–18 % | 49–64 | ohne Programmcode keine Code-Verweise möglich |
| Bosch MED9 (XDF „1K090711S“, 2 MB) | PowerPC | 51 % | 9 | XDF mit 43 Kennfeldern; Rolle *test* |

## Nicht unterstützt / nicht validiert

| Familie | Grund |
|---|---|
| **Bosch EDC17 außer CP09 (C46, C64, C74, CP14, CP20, CP44–46), MED17.5/17.7, MEVD17, MD1, MG1, Continental Simos 8–19, SID, Delphi DCM** | Keine Referenzpaare gemessen. Die Kennfeldsuche läuft (Kopf-Datensätze, Datenmuster, A2L-Import mit RECORD_LAYOUT und EPK-Prüfung), ist für diese Varianten aber **ungemessen**. Das EDC17CP09-Ergebnis überträgt sich nicht automatisch. Keine Code-Verweise für TriCore/PowerPC. |
| BMW MEVD17.4.6 (N20), MSS60, EDC16 weitere | Nur WinOLS-Projekte (`.ols`) vorhanden – deren Inhalt ließ sich nicht verifizierbar lesen (s. u.). |
| Opel E78, Peugeot IAW 8P | Die verfügbaren XDFs sind selbst Suchergebnisse – keine unabhängige Referenz. |
| Hyundai SIM2K (TriCore), BMW MSS54 (CPU32) | gemessen, aber nur Datenmuster + Lernmodell; Code-Verweise über Basisregister nicht gelöst. |

## Definitionen und Identität

- **A2L/ASAP2:** RECORD_LAYOUT (STD/COM/FIX_AXIS, Ausrichtung), Speicherbasis aus der Firmware, **EPK-Prüfung**
  (`MOD_PAR EPK` an `ADDR_EPK`, aufgelöst über Anker **oder** Segmenttabelle): passt die EPK nicht, wird nichts verknüpft; liegt `ADDR_EPK` nicht in der Abbildung, gibt es eine Warnung. Ältere A2L ohne EPK (ME9, MS45, ME7.2)
  werden nur über die Achsprüfung gekoppelt – das belegt die Adresslage, nicht den Softwarestand.
- **Abgewiesen statt vorgetäuscht:** WinOLS-Projekte (`.ols`), WinOLS-Mappacks (`.kp`), ZIP, ELF/EXE, sowie HEX/S19
  beim Öffnen als Rohdatei (dafür gibt es „Intel HEX / Motorola S-Record importieren …“ bzw. den ZIP-Import).
- **`.ols` geprüft, nicht importiert:** In 7 echten Projekten (Formatversionen 113–290) findet sich die in tune-editor
  (GPL-3.0) beschriebene Versionsstruktur. Die daraus gelesene „Original“-Version stimmt aber nur zu 30 % (EDC17CP09,
  Version 269) bzw. 40–54 % (EDC16C35, Version 113) mit der echten Originaldatei überein – der Inhalt ist offenbar
  kodiert. Ohne verifizierbares Lesen gibt es keinen Import.
- **HEX/S19:** Ein abschließendes DOS-Dateiende-Zeichen (`0x1A`) nach dem Endrecord wird toleriert (echte EDC16-Dateien
  wurden vorher abgewiesen); andere Daten nach dem Endrecord weiterhin nicht.
