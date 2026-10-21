# ECU-Unterstützung: was gemessen ist und was nicht (Stand 21.10.2026)

Diese Seite und das Fenster **Hilfe → Unterstützte Steuergeräte …** in der App zeigen dieselben Daten
(`src/ecu_studio/recognition/data/ecu_support.json`, erzeugt mit `python -m ecu_studio.tools.support_matrix`
aus Ergebnissen von `benchmark_suite`). Keine Zahl ist von Hand eingetragen.

## Status

| Status | Bedeutung |
|---|---|
| ✅ **validiert** | Mit echter Firmware und **vollständiger** Referenz (Hersteller-A2L oder vollständige Community-XDF) gemessen. |
| 🟡 **teilweise** | Echte Firmware, aber nur **Teil-Referenz**: Abdeckung und exakte Funde messbar, Präzision nicht. |
| 🧪 **experimentell** | Auf echter Firmware gelaufen, aber ohne jede Referenz. |
| ⚪ **nicht validiert** | Keine Firmware/Referenz-Paare vorhanden. Die Erkennung läuft auch hier, ihre Qualität ist **unbekannt**. |

**Messgrößen:** *exakt* = gleicher Start, gleiche Größe (Zeilen × Spalten, auch vertauscht) und gleiche Zellbreite
wie das Referenzkennfeld (2D, ab 4 × 4). *Typ richtig* = zusätzlich Byte-Reihenfolge und Vorzeichen richtig (das
Vorzeichen zählt nur, wo die Bytes es entscheiden). *Achsen richtig* = Rohachsen linear zur Referenzachse.
*Abdeckung* = Anteil der Referenzkennfelder, die ein Fund zu ≥ 50 % überdeckt. *Präzision* = Anteil der Funde auf
einem echten Kennfeld – **nur bei vollständiger Referenz**. *Fehlfunde* = Funde ohne Referenzkennfeld.
**Rolle:** *test* = nie zum Einstellen der Erkennung verwendet, *development* = Regeln daran gemessen, *training* =
Lernmodell/Konfidenz daran kalibriert. Die Referenzdateien und die Firmware liegen nicht im Repository.

## Matrix

| Steuergerät | Prozessor | Status | Softwarestände | exakt 2D (Spanne der Stände) | Präzision 2D | Grenzen / benötigt |
|---|---|---|---:|---|---|---|
| Bosch EDC17CP09 | Infineon TriCore | ✅ validiert | 1 | 463/703 | 85% | Ein Softwarestand (BMW). Gruppenkennfelder mit gemeinsamen Achsen (MapG) werden kaum erkannt; TriCore-Code-Verweise auf Kennfelder ließen sich nicht nutzen (Zugriff nicht über movh.a/lea). |
| Siemens MSD80 | PowerPC | ✅ validiert | 6 | 217–224 von 864 | 81% / 82% | Kalibrierbereich aus S19; Identität nur über A2L-EPK. |
| Siemens MSD85 | PowerPC | ✅ validiert | 1 | 279/1026 | 81% | Ein Softwarestand; Identität nur über A2L-EPK. |
| Bosch EDC16C35 | PowerPC (MPC5xx) | ✅ validiert | 1 | 283/387 | 81% | Ein Softwarestand. Datei nennt C31 und C35 – Familie per Kennung mehrdeutig. |
| Bosch EDC16C31 | PowerPC (MPC5xx) | ✅ validiert | 1 | 272/364 | 82% | Ein Softwarestand. Datei nennt C31 und C35 – Familie per Kennung mehrdeutig. |
| BMW ME9 | PowerPC | ✅ validiert | 1 | 98/233 | 62% | Ein Softwarestand. |
| BMW ME9.2.1 | PowerPC | ✅ validiert | 1 | 170/460 | 72% | Ein Softwarestand; keine Kennung in der Datei. |
| Siemens MS45 | C167 | ✅ validiert | 1 | 30/472 | 66% | Niedrige Abdeckung (Datensatzformat ohne Kopf). |
| Siemens MS43 | C167 | ✅ validiert | 1 | 197/379 | 79% | Community-XDF; zum Trainieren verwendet. |
| Siemens MS42 | C167 | ✅ validiert | 1 | 22/213 | 72% | Community-XDF; zum Trainieren verwendet. |
| Bosch MED17.1.62 | Infineon TriCore | 🟡 teilweise | 6 | 121/1137, 128/1323, 133/1337, 134/1337, 136/1337, 145/1223 | – | Nur Kalibrierbereich (496 KB) mit Teil-XDF: Präzision nicht messbar. **Benötigt:** Hersteller-A2L zu einem der Stände. |
| Bosch MED9.1 | PowerPC | 🟡 teilweise | 1 | 11/43 | – | Teil-XDF mit 43 Kennfeldern. **Benötigt:** vollständige A2L. |
| Bosch ME7.5 | C167 | 🟡 teilweise | 2 | 43/129, 85/266 | – | Community-XDFs (Teilreferenz). |
| Bosch ME7 (Volvo) | C167 | 🟡 teilweise | 2 | 11/48, 7/38 | – | Community-XDFs (Teilreferenz). |
| Bosch M4.4 | 8051 | 🟡 teilweise | 1 | 8/28 | – | Teil-XDF. |
| GM P01 | Motorola 68k | 🟡 teilweise | 1 | 10/43 | – | Teil-XDF; keine Kennung in der Datei. |
| Denso SH-2 (Subaru 5EAT) | Hitachi SH-2 | 🟡 teilweise | 3 | 147/147, 147/147, 178/192 | – | RomRaider-Auswahl (Teilreferenz). |
| Hyundai/Kia SIM2K (Hyundai N) | Infineon TriCore | 🟡 teilweise | 2 | 15/555, 9/524 | 15% / 18% | Community-XDF; zur Konfidenz-Kalibrierung verwendet. Code-Verweise über Basisregister nicht gelöst. Gemessen, Erkennung unzureichend (Präzision höchstens 18%). |
| BMW MSS54 | Motorola CPU32 | ✅ validiert | 1 | 97/128 | 73% | Community-XDF; zur Konfidenz-Kalibrierung verwendet. |
| Bosch EDC17CP14 / CP20 / CP44 / CP45 / CP46 | Infineon TriCore/AURIX | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN (vollständiger Flash) + passende Hersteller-A2L mit EPK, je 2 Softwarestände. |
| Bosch EDC17C46 / C64 / C74 | Infineon TriCore | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + passende A2L, je 2 Softwarestände. |
| Bosch EDC17CP02 | Infineon TriCore | ⚪ nicht validiert | 0 | offen | offen | Nur A2L vorhanden (4P1C2558), keine Firmware. **Benötigt:** Firmware zum Softwarestand 4P1C2558. |
| Bosch MED17.5 / 17.5.5 / 17.5.25 / 17.7 / 17.7.2 | Infineon TriCore | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + passende A2L. |
| Bosch MEVD17.2.x / MEVD17.4.6 | Infineon TriCore | ⚪ nicht validiert | 0 | offen | offen | MEVD17.4.6: nur WinOLS-Projekt (.ols), Inhalt nicht verifizierbar lesbar. **Benötigt:** Original-BIN + A2L. |
| Bosch MD1 (MD1CS001, MD1CS004, MD1CP002) | Infineon AURIX | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + passende A2L (DAMOS) mit EPK. |
| Bosch MG1 (MG1CS001, MG1CS002, MG1CS011, MG1CS201) | Infineon AURIX | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + passende A2L mit EPK. |
| Continental Simos 8 / 10 / 12 / 18.1 / 18.2 / 18.10 / 19 | Infineon TriCore | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + A2L. |
| Continental SID208 / SID807 / SID807EVO / SID310 / SID321 | Infineon TriCore | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + A2L. |
| Siemens MSD81 / MSV70 / MSV80 | PowerPC / C167 | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + A2L. |
| Bosch EDC16C34 / EDC16CP34 | PowerPC (MPC5xx) | ⚪ nicht validiert | 0 | offen | offen | **Benötigt:** Original-BIN + A2L. |
| Siemens MSS60 | PowerPC | ⚪ nicht validiert | 0 | offen | offen | Nur WinOLS-Projekt (.ols) vorhanden. **Benötigt:** Original-BIN + A2L. |

**Einzelmessungen** (Rolle *test* = nie zum Einstellen verwendet; Gruppe = nahezu identische Stände)

| Softwarestand | Rolle | Gruppe | Ref 2D | gefunden | Abdeckung | exakt | Typ richtig | Achsen richtig | Präzision | Fehlfunde | exakt 1D | s | MB |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EDC17CP09 6P8KB574 | development | EDC17CP09 6P8KB574 | 703 | 590 | 71% | 463 | 446 | 456/456 | 85% | 89 | 946 | 35.7 | – |
| MSD80 37IIAFAA | test | MSD80 37IIAFAA | 864 | 400 | 38% | 217 | 183 | 201/202 | 82% | 73 | 439 | 10.27 | 36.1 |
| MSD80 37IIAGAA | test | MSD80 37IIAFAA | 864 | 400 | 38% | 219 | 189 | 200/201 | 82% | 71 | 439 | 10.33 | 36.1 |
| MSD80 37IIAKAA | test | MSD80 37IIAFAA | 864 | 403 | 38% | 219 | 187 | 202/203 | 82% | 74 | 441 | 10.12 | – |
| MSD80 37IIALAA | test | MSD80 37IIAFAA | 864 | 403 | 39% | 223 | 195 | 204/205 | 82% | 71 | 447 | 9.94 | – |
| MSD80 37IIAMAA | test | MSD80 37IIAFAA | 864 | 404 | 38% | 220 | 188 | 202/203 | 81% | 75 | 441 | 9.49 | – |
| MSD80 37IIANAA | test | MSD80 37IIAFAA | 864 | 405 | 38% | 224 | 196 | 204/205 | 82% | 74 | 447 | 10.54 | – |
| MSD85 791I200S | test | MSD85 791I200S | 1026 | 452 | 36% | 279 | 223 | 272/272 | 81% | 85 | 642 | 12.3 | 45.7 |
| EDC16C35 4M702389 | test | EDC16C35 4M702389 | 387 | 380 | 80% | 283 | 270 | 277/277 | 81% | 72 | 562 | 19.1 | 84.2 |
| EDC16C31 6m661411 | test | EDC16C31 6m661411 | 364 | 371 | 84% | 272 | 255 | 267/267 | 82% | 67 | 544 | 23.28 | 189.1 |
| ME9 770115XE | development | ME9 770115XE | 233 | 212 | 56% | 98 | 90 | 96/96 | 62% | 81 | 205 | 11.76 | – |
| ME9.2.1 725D601B | development | ME9.2.1 725D601B | 460 | 340 | 54% | 170 | 139 | 155/155 | 72% | 94 | 385 | 7.89 | – |
| MS45 4520D30S | development | MS45 4520D30S | 472 | 124 | 18% | 30 | 29 | 9/9 | 66% | 42 | 176 | 8.25 | – |
| MS43 430069 | training | MS43 430069 | 379 | 315 | 66% | 197 | 184 | 175/178 | 79% | 65 | 743 | 4.16 | – |
| MS42 0110C6 | training | MS42 0110C6 | 213 | 143 | 50% | 22 | 22 | 0/0 | 72% | 40 | 398 | 2.19 | – |
| MED17.1.62 404A | development | MED17.1.62 404A | 1337 | 738 | 24% | 134 | 110 | 115/115 | – | – | 133 | 29.17 | – |
| MED17.1.62 404E | development | MED17.1.62 404A | 1337 | 741 | 25% | 136 | 111 | 117/117 | – | – | 135 | 28.98 | – |
| MED17.1.62 404G | development | MED17.1.62 404A | 1337 | 735 | 24% | 133 | 109 | 114/114 | – | – | 133 | 27.44 | – |
| MED17.1.62 404H | development | MED17.1.62 404H | 1223 | 722 | 26% | 145 | 124 | 111/111 | – | – | 133 | 26.8 | – |
| MED17.1.62 404J | development | MED17.1.62 404J | 1323 | 699 | 24% | 128 | 104 | 109/109 | – | – | 132 | 28.87 | – |
| MED17.1.62 404L | development | MED17.1.62 404L | 1137 | 776 | 28% | 121 | 99 | 100/100 | – | – | 121 | 24.49 | – |
| MED9 1K090711S | test | MED9 1K090711S | 43 | 379 | 56% | 11 | 9 | 6/6 | – | – | 0 | 17.4 | 85.0 |
| ME7.5 06A906032HS | development | ME7.5 06A906032HS | 266 | 266 | 53% | 85 | 70 | 71/75 | – | – | 134 | 10.61 | – |
| ME7.5 8E0909518AK | development | ME7.5 8E0909518AK | 129 | 346 | 60% | 43 | 35 | 31/35 | – | – | 43 | 11.94 | – |
| ME7 40LNHJ | development | ME7 40LNHJ | 48 | 271 | 65% | 11 | 11 | 8/10 | – | – | 8 | 12.97 | – |
| ME7 50GMHJ | development | ME7 50GMHJ | 38 | 274 | 55% | 7 | 7 | 5/6 | – | – | 0 | 14.09 | – |
| Volvo M4.4 | development | Volvo M4.4 | 28 | 85 | 54% | 8 | 8 | 0/0 | – | – | 0 | 2.82 | – |
| GM P01 | development | GM P01 | 43 | 155 | 35% | 10 | 9 | 0/0 | – | – | 21 | 10.09 | – |
| Subaru 5AT_3.272_LEGAS_EJDM20 | development | Subaru 5AT_3.272_LEGAS_EJDM20 | 147 | 321 | 100% | 147 | 147 | 147/147 | – | – | 0 | 12.58 | – |
| Subaru 5AT_3.583_LEGASE_JDM20 | development | Subaru 5AT_3.583_LEGASE_JDM20 | 147 | 325 | 100% | 147 | 147 | 147/147 | – | – | 0 | 12.36 | – |
| Subaru 8EFB206000_08FB2WA0_14 | development | Subaru 8EFB206000_08FB2WA0_14 | 192 | 340 | 93% | 178 | 178 | 178/178 | – | – | 0 | 18.38 | – |
| SIM2K CNNKKM___TAA | training | SIM2K CNNKKM___TAA | 524 | 288 | 9% | 9 | 9 | 0/0 | 15% | 244 | 0 | 31.26 | – |
| SIM2K JSNNJMK__S2A | training | SIM2K JSNNJMK__S2A | 555 | 278 | 9% | 15 | 15 | 0/0 | 18% | 229 | 0 | 31.9 | – |
| MSS54 211322001501J424 | training | MSS54 211322001501J424 | 128 | 144 | 82% | 97 | 83 | 96/97 | 73% | 39 | 0 | 2.83 | – |

## Identifikation

Beim Öffnen meldet die App, welche Kennungen **wörtlich in der Datei** stehen, jeweils mit Fundstelle
(`core/identification.py`): Bosch-EPK (`33/1/EDC17_CP09/…`), Bosch-Hardware- (`0261…`, `0281…`) und
Softwarenummer (`1037…`), VAG-Teilenummer (`8V0907404A`), Siemens-Hardwarenummer (`5WK9…`). Widersprechen sich
die Angaben, heißt das Ergebnis „mehrdeutig“ (z. B. BMW-EDC16-Dateien, die C31 und C35 nennen). Platzhalter-EPKs
werden ignoriert. Reine Kalibrierbereiche (MSD80/85, ME9.2.1) enthalten meist keine Kennung; ihre Identität belegt
erst die EPK-Prüfung einer passenden A2L.

Gemessen auf den 27 Referenzdateien: Familie aus EPK richtig bei EDC17CP09, MED9.1, ME7.5 (2), ME7 (2), M4.4;
mehrdeutig bei EDC16C31/C35; keine Kennung bei MSD80/85, ME9, ME9.2.1, MS45, MED17.1.62 (nur Teilenummer),
Subaru, GM. Keine falsche Familie.

## Was für die offenen Varianten gebraucht wird

Für jede Variante mit Status ⚪: **Originaldatei** (möglichst vollständiger Flash, sonst Kalibrierbereich mit
bekannter Startadresse) **und** die **passende Hersteller-A2L/DAMOS** desselben Softwarestands (EPK gleich), am
besten zwei verschiedene Softwarestände. Teil-XDFs erlauben nur Abdeckungs-, keine Präzisionsaussage. Dateien
bitte nur verwenden, wenn sie rechtmäßig weitergegeben werden dürfen; sie kommen nicht ins Repository.

## Definitionen und Identität

- **A2L/ASAP2:** RECORD_LAYOUT (STD/COM/FIX_AXIS, Ausrichtung), Speicherbasis aus der Firmware, **EPK-Prüfung**
  (`MOD_PAR EPK` an `ADDR_EPK`, aufgelöst über Anker **oder** Segmenttabelle): passt die EPK nicht, wird nichts
  verknüpft; liegt `ADDR_EPK` nicht in der Abbildung, gibt es eine Warnung. Ältere A2L ohne EPK (ME9, MS45, ME7.2)
  werden nur über die Achsprüfung gekoppelt – das belegt die Adresslage, nicht den Softwarestand.
- **Abgewiesen statt vorgetäuscht:** WinOLS-Projekte (`.ols`), WinOLS-Mappacks (`.kp`), ZIP, ELF/EXE, sowie HEX/S19
  beim Öffnen als Rohdatei (dafür gibt es „Intel HEX / Motorola S-Record importieren …“ bzw. den ZIP-Import).
- **`.ols` geprüft, nicht importiert:** In 7 echten Projekten (Formatversionen 113–290) findet sich die in tune-editor
  (GPL-3.0) beschriebene Versionsstruktur. Die daraus gelesene „Original“-Version stimmt aber nur zu 30 % (EDC17CP09,
  Version 269) bzw. 40–54 % (EDC16C35, Version 113) mit der echten Originaldatei überein – der Inhalt ist offenbar
  kodiert. Ohne verifizierbares Lesen gibt es keinen Import.
- **HEX/S19:** Ein abschließendes DOS-Dateiende-Zeichen (`0x1A`) nach dem Endrecord wird toleriert; andere Daten nach
  dem Endrecord weiterhin nicht.
- **Prüfsummen und Flashen:** Kein Ergebnis dieser Seite ist eine Flashfreigabe. Prüfsummen werden nur mit bekanntem
  Verfahren korrigiert; geänderte Dateien vor dem Flashen mit einem geeigneten Werkzeug prüfen.
