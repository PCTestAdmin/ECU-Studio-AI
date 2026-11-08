# ECU Studio AI 1.19.1 – Release Notes

**Veröffentlicht am 08.11.2026. Released on 8 Nov 2026.** Die deutsche Fassung ist der Abschnitt
`## 1.19.1 (08.11.2026)` in [CHANGELOG.md](../CHANGELOG.md) (Release-Text und Update-Fenster); sie steht zusammen mit
der englischen Fassung unten im GitHub-Release. Messungen und Grenzen:
[Entwicklungsbericht 1.19.1](ENTWICKLUNG_1.19.1.md).

*Entwicklungsdaten* = an derselben Datei entwickelt und gemessen, keine unabhängige Bestätigung.
*Development data* = developed and measured on the same file, not independently confirmed.

---

## Deutsch

Zuverlässigere Kennfelderkennung: weniger Fehlfunde aus Programmcode, Text und Zeigertabellen, korrigierte
Zuordnungen, kein bisher exaktes Kennfeld verloren.

### Kennfelderkennung

- **Architekturprüfung:** TriCore, C16x, ARM (Cortex-M) und AVR gelten nur als erkannt, wenn zwei unabhängige
  Merkmale übereinstimmen; sonst „unbekannt“.
- **Keine Code-Belege auf fremden Architekturen:** behoben auf drei MED17-Dateien (C16x-Beleg bei 0x12600) und auf
  einer rusEFI-ARM-Firmware.
- **Weniger Fehlfunde auf Text und Zeigertabellen:** sieben offene Firmwarestände (Entwicklungsdaten):
  1795 → 875 Funde, nachweislich falsche 921 → 0.
- **Zwei MSD80-Kennfelder wiederhergestellt:** 0x4FB18 und 0x5604C (in 1.19.0 verloren); MSD80 I8A0S 84 → 86 von
  99 exakt (Entwicklungsdaten).
- **Falscher HC11-Code-Beleg auf ME7.5 06A906018CG behoben:** HC11/8051 nur noch auf Images bis 64 KiB.
- **Keine Regression** auf 15 realen Vergleichspaaren und 14 synthetischen Fällen.

### Stabilität und Speicher

- Keine globalen Zwischenspeicher mit ganzen Firmwaredateien mehr; Speicher über wiederholte Scans konstant.
- A2L-Zwischenspeicher nach Inhalt (SHA-256): keine veralteten Definitionen in Namensübertragung und Versionsvergleich.
- Parallele Zugriffe auf den A2L-Zwischenspeicher abgesichert.

### Windows

- Korrekte Dateiversion in EXE und Installer (bisher 0.0.0.0). Das ist **keine** digitale Signatur; die EXE ist
  weiterhin nicht Authenticode-signiert.
- Build-Prozess abgesichert (eigene, getestete Compiler-Funktion; Prüfung auf undefinierte Namen).
- CodeQL-Prüfung korrigiert (eine Testdatei wurde wegen einer als Kodierung gelesenen Docstring-Zeile übersprungen).

### Bekannte Einschränkungen

- TriCore-Codeerkennung weiterhin **experimentell**; kein unabhängiger, vollständiger TriCore-Blindtest.
- Die 875 verbleibenden Funde auf offenen Firmwareständen sind **nicht** als echte Kennfelder bestätigt.
- Keine allgemeingültige Präzisionsangabe.
- Für HC11-/8051-Images über 64 KiB gibt es keine validierten Code-Belege.
- Ursache des einmaligen GUI-Absturzes vom 01.11.2026 weiterhin unbekannt.
- Als „nicht validiert“ geführte Steuergerätefamilien bleiben es ([ECU-Unterstützung](ECU_SUPPORT.md)).
- 1.19.1 ändert nichts an Prüfsummenprüfung und Flash-Vorprüfung; ein Fund ist keine Freigabe zum Flashen.

---

## English

More reliable map recognition: fewer false finds from program code, text and pointer tables, corrected
assignments, no previously exact map lost.

### Map recognition

- **Architecture check:** TriCore, C16x, ARM (Cortex-M) and AVR count as detected only when two independent signs
  agree; otherwise "unknown".
- **No code evidence on foreign architectures:** fixed on three MED17 files (C16x evidence at 0x12600) and on a
  rusEFI ARM firmware.
- **Fewer false finds on text and pointer tables:** seven open firmware builds (development data): 1795 → 875 finds,
  provably wrong 921 → 0.
- **Two MSD80 maps restored:** 0x4FB18 and 0x5604C (lost in 1.19.0); MSD80 I8A0S 84 → 86 of 99 exact (development
  data).
- **Wrong HC11 code evidence on ME7.5 06A906018CG fixed:** HC11/8051 only on images up to 64 KiB.
- **No regression** on 15 real comparison pairs and 14 synthetic cases.

### Stability and memory

- No global caches holding whole firmware files; memory stays constant over repeated scans.
- A2L cache keyed by content (SHA-256): no stale definitions in name transfer and version compare.
- Parallel access to the A2L cache secured.

### Windows

- Correct file version in the EXE and the installer (previously 0.0.0.0). This is **not** a digital signature; the
  EXE is still not Authenticode-signed.
- Build process secured (separate, tested compiler function; check for undefined names).
- CodeQL check fixed (a test file was skipped because a docstring line was read as an encoding declaration).

### Known limitations

- TriCore code recognition remains **experimental**; no independent, complete TriCore blind test.
- The 875 remaining finds on open firmware builds are **not** confirmed as real maps.
- No general precision figure.
- No validated code evidence for HC11/8051 images above 64 KiB.
- The cause of the one-off GUI crash of 1 Nov 2026 remains unknown.
- ECU families listed as "not validated" remain so ([ECU support](ECU_SUPPORT.md)).
- 1.19.1 does not change checksum verification or the flash preflight; a find is no approval to flash.
