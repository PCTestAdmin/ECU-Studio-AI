# ECU-Unterstützung: was gemessen ist und was nicht (Stand 20.10.2026)

Jede Zeile nennt **konkrete Dateien**, gegen die gemessen wurde. „Gefunden“ = Anteil der 2D-Referenzkennfelder
(≥ 4×4), die ein Fund zu ≥ 50 % überdeckt; „exakt“ = gleicher Start, gleiche Form und Breite. Präzision ist nur
bei **vollständigen** Referenzen (Hersteller-A2L, vollständige Community-XDF) belastbar. Die Referenzdateien
liegen nicht im Repository.

## Validiert mit vollständiger Referenz

| Variante | Prozessor | Referenz | gefunden | exakt | Präzision | Code-Verweise |
|---|---|---|---:|---:|---:|---|
| Siemens MS43 430069 | C167 | MS4x-XDF (GPL-3.0) | 67 % | 197/379 | 80 % | ✅ Seite+Offset, Lookup |
| Siemens MS42 0110C6 | C167 | MS4x-XDF | 50 % | 22/213 | 72 % | ◐ |
| BMW ME9 770115XE | „GoldenOak“ (A2L) | **Hersteller-A2L** | 35 % | 38/233 | 50 % | ❌ |
| BMW ME9.2.1 725D601B | „GoldenOak“ (A2L) | **Hersteller-A2L** | 38 % | 56/460 | 63 % | ❌ |
| Siemens MS45 4520D30S | – | **Hersteller-A2L** | 18 % | 28/472 | 67 % | ❌ |

## Gemessen mit unvollständiger Referenz (Präzision nicht belastbar)

| Variante | Prozessor | gefunden | exakt | Bemerkung |
|---|---|---:|---:|---|
| Bosch ME7 (Volvo, 3 Stände) | C167 | 55–66 % | 6–7 | Lookup-Aufrufe |
| Bosch ME7.5 VAG 06A906032HS / 8E0909518AK | C167 | 46 % / 57 % | 59 / 37 | Basis 0x800000, Kennfeldköpfe |
| Denso Subaru 5EAT (9 ROMs) | SH-2 | 93–100 % | 147–178 | Beschreibungsblöcke |
| GM P01 | 68k | 35 % | 10 | Absolutoperanden |
| Bosch M4.4 (Volvo) | 8051 | 54 % | 8 | nur bestätigend |
| Bosch MED17.1.62 (8V0907404A/E/H/J, 8S0907404G/L – Kennung in der Datei; 496-KB-Dumps zu 85–91 % Daten, also Kalibrierbereich ohne Programm) | TriCore | 11–16 % | 38–53 | ohne Programmcode keine Code-Verweise möglich |
| Bosch MED9 (XDF „1K090711S“, 2 MB) | PowerPC | 51 % | 9 | XDF mit 43 Kennfeldern |

## Nicht unterstützt / nicht validiert

| Familie | Grund |
|---|---|
| **Bosch EDC17, MD1, MG1, Continental Simos 18/19** | Keine rechtmäßig frei verfügbaren BIN-/Definitionspaare gefunden. Die Kennfeldsuche läuft auf solchen Dateien (generische Datenmuster, A2L-Import mit RECORD_LAYOUT und EPK-Prüfung), ist aber **ungemessen**. Keine Code-Verweise für TriCore/PowerPC. |
| Opel E78, Peugeot IAW 8P | Die verfügbaren XDFs sind selbst Suchergebnisse – keine unabhängige Referenz. |
| Hyundai SIM2K (TriCore), BMW MSS54 (CPU32) | gemessen, aber nur Datenmuster + Lernmodell; Code-Verweise über Basisregister nicht gelöst. |

## Definitionen und Identität

- **A2L/ASAP2:** RECORD_LAYOUT (STD/COM/FIX_AXIS, Ausrichtung), Speicherbasis aus der Firmware, **EPK-Prüfung**
  (`MOD_PAR EPK` an `ADDR_EPK`, aufgelöst über Anker **oder** Segmenttabelle): passt die EPK nicht, wird nichts verknüpft; liegt `ADDR_EPK` nicht in der Abbildung, gibt es eine Warnung. Ältere A2L ohne EPK (ME9, MS45, ME7.2)
  werden nur über die Achsprüfung gekoppelt – das belegt die Adresslage, nicht den Softwarestand.
- **Abgewiesen statt vorgetäuscht:** WinOLS-Projekte (`.ols`), WinOLS-Mappacks (`.kp`), ZIP, ELF/EXE, sowie HEX/S19
  beim Öffnen als Rohdatei (dafür gibt es den Speicherabbild-Import).
