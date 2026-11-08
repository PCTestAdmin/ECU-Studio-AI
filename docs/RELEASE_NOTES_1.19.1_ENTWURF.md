# ECU Studio AI 1.19.1 – Release Notes (Entwurf)

**Entwurf, nicht veröffentlicht.** Für das Release wird der deutsche Teil als Abschnitt `## 1.19.1 (Datum)` in
[CHANGELOG.md](../CHANGELOG.md) übernommen (daraus erzeugt der Release-Workflow den Release-Text) und
`__version__` erhöht. Beides erst nach ausdrücklicher Freigabe. Messungen und Grenzen:
[Entwicklungsbericht 1.19.1](ENTWICKLUNG_1.19.1.md) (§ 1–11 Fehlfunde und Architektur, § 12 letzte Korrekturen).

Kennzeichnung: **unabhängig belegt** = an Daten gezeigt, die nicht zur Entwicklung der Regel dienten, oder durch
einen strukturellen Grund ohne Abstimmung; **nur an Entwicklungsdaten gemessen** = an derselben Datei entwickelt und
gemessen.

---

## Deutsch

Zuverlässigere Kennfelderkennung: weniger Fehlfunde aus Programmcode, Text und Zeigertabellen, korrigierte
Zuordnungen und keine verlorenen exakten Kennfelder.

**Unabhängig belegt**

- **Prozessorarchitektur mit zwei Merkmalen:** TriCore, C16x, ARM (Cortex-M) und AVR gelten nur als erkannt, wenn
  zwei unabhängige Merkmale übereinstimmen; sonst „unbekannt“. Code-Belege entstehen nur auf der belegten
  Architektur. Behoben: falscher C16x-Code-Beleg auf drei MED17-Dateien (0x12600) und auf einer rusEFI-ARM-Firmware.
- **A2L-Zwischenspeicher nach Inhalt:** Eine unter demselben Pfad geänderte A2L wird neu verknüpft (vorher galten in
  Namensübertragung und Versionsvergleich die Kennfelder der alten Fassung).
- **Kein Zwischenspeicher hält ganze Firmwaredateien** über das Schließen eines Projekts hinaus (vorher bis zu
  8 + 4 Images); Speicher über 15 Scans konstant (+0,03 MB).
- **Kein HC11-Code-Beleg auf ME7.5 06A906018CG:** Die HC11-/8051-Suche läuft nur noch auf Images, die in einen
  16-Bit-Adressraum passen (bis 64 KiB). Größere HC11-/8051-Images erhalten keine Code-Belege mehr.
- **Windows-Dateiversion** von EXE und Installer zeigt die Programmversion statt 0.0.0.0.

**Nur an Entwicklungsdaten gemessen**

- **Fehlfunde auf Programm-Images:** sieben offene Firmwarestände ohne Abstimmungsdaten (FOME, rusEFI, Speeduino):
  1795 → 875 Funde, nachweislich falsche (Text, Zeigertabellen, fremde Architektur) 921 → 0, Strukturbelege
  294 → 36. Die 875 übrigen Funde sind **nicht** als richtige Kennfelder bestätigt; ohne Symbole (ELF/Map) ist ihre
  Richtigkeit unbekannt. Die Regeln wurden an diesen Images entwickelt.
- **MSD80 I8A0S:** die in 1.19.0 verlorenen Kennfelder 0x4FB18 (6 × 7 u16) und 0x5604C (6 × 8 u16) werden wieder
  exakt gefunden (84 → 86 von 99, Achsen 74 → 77 richtig). Ursache war eine zu kleine Zahl gehaltener
  Registerzustände im TriCore-Decoder. Keine unabhängige TriCore-Referenz.

**Unverändert** auf allen anderen 14 realen Vergleichspaaren: exakte Kennfelder, Datentypen, Achsen,
Achsadressen. Synthetische Fälle: ein exakter Fund mehr (aligned-padded), Negativkontrollen unverändert.

---

## English

More reliable map recognition: fewer false finds from program code, text and pointer tables, corrected assignments,
no exact map lost.

**Independently shown**

- **Processor architecture from two signs:** TriCore, C16x, ARM (Cortex-M) and AVR count as detected only when two
  independent signs agree; otherwise "unknown". Code evidence is produced only on the proven architecture. Fixed:
  wrong C16x code evidence on three MED17 files (0x12600) and on a rusEFI ARM firmware.
- **A2L cache keyed by content:** an A2L changed under the same path is linked again (name transfer and version
  compare previously used the maps of the old file).
- **No cache keeps whole firmware files** after a project is closed (previously up to 8 + 4 images); memory stays
  constant over 15 scans (+0.03 MB).
- **No HC11 code evidence on ME7.5 06A906018CG:** the HC11/8051 search only runs on images that fit a 16-bit address
  space (up to 64 KiB). Larger HC11/8051 images no longer get code evidence.
- **Windows file version** of the EXE and the installer shows the program version instead of 0.0.0.0.

**Measured on development data only**

- **False finds on program images:** seven open firmware builds without calibration data (FOME, rusEFI,
  Speeduino): 1795 → 875 finds, provably wrong (text, pointer tables, foreign architecture) 921 → 0, structure
  evidence 294 → 36. The remaining 875 are **not** confirmed maps; without symbols (ELF/map) their correctness is
  unknown. The rules were developed on these images.
- **MSD80 I8A0S:** the maps 0x4FB18 (6 × 7 u16) and 0x5604C (6 × 8 u16), lost in 1.19.0, are exact again
  (84 → 86 of 99, axes 74 → 77 correct). Cause: too few register states kept by the TriCore decoder. No independent
  TriCore reference.

**Unchanged** on the other 14 real comparison pairs: exact maps, data types, axes, axis addresses. Synthetic cases:
one more exact find (aligned-padded), negative controls unchanged.
