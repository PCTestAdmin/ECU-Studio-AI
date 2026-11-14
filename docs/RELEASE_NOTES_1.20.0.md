# ECU Studio AI 1.20.0 – Release Notes

**Veröffentlicht am 11.11.2026. Released on 11 Nov 2026.**

Inhalt: [PR #19](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/19) (Checksummen & Integrität),
[PR #20](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/20) (Definitionseditor) und
[PR #21](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/21) (Testisolation). Prüfnachweise:
[Release-Checkliste 1.20.0](RELEASE_CHECKLIST_1.20.0.md). Details und Grenzen: [Checksummen und Integrität](CHECKSUMMEN.md).

---

## Deutsch

1.20.0 bringt die **erste validierte Ausbaustufe** eines gemeinsamen Checksummen- und Integritätssystems. Es prüft,
was nachgewiesen ist, und sagt deutlich, was nicht geprüft ist. **Keine untersuchte Originaldatei erreicht bisher
eine vollständige Checksummenabdeckung.** ECU Studio AI erteilt keine Flashfreigabe. Eine Datei ist nach einer
Korrektur nicht automatisch flashbereit.

### Neu

- **Zentrales Checksummen- und Integritätssystem** mit fünf Status je Datei: gültig, ungültig, unvollständig, nicht
  unterstützt, unbekannt. Ein zufällig passendes Verfahren macht eine Datei nie „gültig“.
- **Automatische Prüfung ausgewählter Checksummen:**
  - Läuft nach dem Öffnen und nach Bearbeitungen im Hintergrund, mit Fortschritt und Abbrechen.
  - Geprüft werden nur die in der Tabelle unten genannten Verfahren.
  - Detailbericht mit JSON-Export; Anzeige in Statusleiste, Exportdialog und Flash-Vorprüfung.
- **Korrekturvorschau für validierte Verfahren:** Jedes geänderte Byte wird gezeigt, und die Korrektur verlangt eine
  ausdrückliche Bestätigung. Erlaubt ist sie nur für Bosch-Multipoint und für ein geprüftes, an die Datei gebundenes
  Profil, und nur unter den Bedingungen unten.
- **Sichere korrigierte Kopien:**
  - Geschrieben wird immer eine **Kopie** mit Änderungsprotokoll (`.korrektur.json`) und `.bak`; das Original bleibt
    unverändert.
  - Kopie und Protokoll bleiben auch bei Schreib-, Lese- oder Speicherplatzfehlern konsistent.
  - Undo in der Sitzung.
- **Unabhängige Nachprüfung** der korrigierten Daten vor dem Schreiben.
- **Erweiterter Preflight** mit getrennten Prüfstufen:
  1. Profil-Prüffelder
  2. bekannte Prüfsummen
  3. Checksummenabdeckung
  4. Signaturen (immer „nicht geprüft“)
  5. Preflight
  6. Flashfreigabe (immer „keine“)

  Ein passendes Teilprofil oder eine unvollständige Prüfung ergibt nie einen sauberen Preflight.

**Korrektur nur bei ausreichendem Beleg:** Für Bosch-Multipoint muss eine der beiden Bedingungen gelten:
- Das Steuergerät ist eindeutig als ME7, ME9 oder MED9 identifiziert.
- Die Datei belegt das Verfahren stark: mindestens 32 am Original bestätigte Tabelleneinträge, davon mindestens 16 in
  einer Tabelle.

Diese Schwellen sind eine **Sicherheitsentscheidung** von ECU Studio AI, keine Eigenschaft der Steuergeräte.

### Was geprüft wird – und was nicht

| Einordnung | Verfahren | Prüfung | Korrektur |
|---|---|---|---|
| **Unterstützt** (unabhängig belegt) | Bosch-Multipoint-Prüfsummentabellen (ME7.x, ME9, MED9): 199 von 199 Herstellerwerten in drei Originalen reproduziert, mit zwei Implementierungen | ja | ja, mit Vorschau und unter den Bedingungen oben |
| **Unterstützt** (vom Nutzer belegt) | Geprüftes, an den SHA-256 der Datei gebundenes Checksummenprofil | nur die deklarierten Prüffelder | ja |
| **Teilweise geprüft** | Bosch MED17/EDC17-Blöcke (EDC17CP09: 8 von 11 Strukturen am Original bestätigt, 3 unbestätigt) | ja | gesperrt ohne signierten OEM-Nachweis |
| **Teilweise geprüft** | Bosch EDC16-Bereiche (EDC16C31, EDC16C35: je 1 Bereich) | ja | gesperrt ohne signierten OEM-Nachweis |
| **Nicht unterstützt** | weitere ME7-Prüfsummen (ROMSYS, CRC-Tabellen, Haupt- und Programmprüfsummen) | nein, Datei bleibt „unvollständig“ | nein |
| **Nicht unterstützt** | Siemens/Continental (z. B. MS43, MSD80, Simos, SID), Bosch MG1/MD1 und alle übrigen Familien | nein | nein |
| **Nie** | Digitale Herstellersignaturen | werden nur als erwartet/erkannt ausgewiesen, nie verifiziert | werden nie verändert |

**Bedeutet ausdrücklich nicht:**
- Nicht alle ECU-Checksummen werden automatisch korrigiert.
- ME7, ME9, EDC16 und EDC17 sind nicht vollständig unterstützt.
- Eine korrigierte Datei ist nicht automatisch flashbereit.
- Digitale Signaturen werden nicht verifiziert.
- Es gibt keine Flashfreigabe.

### Behobene Fehler

- **Definitionseditor:** Nach dem Öffnen einer anderen Firmware zeigt der Editor keine Werte der vorherigen Datei
  mehr. Name, Adresse, Größe, Skalierung und Hinweise werden geleert. Bearbeitungsfunktionen sind ohne
  Kennfeldauswahl deaktiviert.
- **Scan-Ergebnisse beim Dateiwechsel:** Ein Kennfeldscan oder eine Erkennung, die für eine andere Datei gestartet
  wurde, gelangt nicht mehr in die aktuell geöffnete Datei.
- **Isolation der Test-Einstellungen:** Testläufe und der Oberflächentest des Builds schreiben nicht mehr in die
  Einstellungen (Registry) einer installierten ECU-Studio-Version.
- **Selbsttest der EXE** prüft jetzt auch das Checksummensystem.

### Bekannte Einschränkungen

- **Keine vollständige Checksummenabdeckung:** Keine untersuchte Originaldatei erreicht „gültig“. ME7-, EDC16- und
  EDC17-Dateien bleiben „unvollständig“.
- **Teilprüfung ist keine Integritätsbestätigung:** Checksummen werden nicht für alle Steuergeräte vollständig
  geprüft. Eine erfolgreiche Teilprüfung (zum Beispiel alle Multipoint-Tabellen stimmen) bestätigt nicht, dass die
  ganze Datei unversehrt ist.
- **Keine Flashfreigabe:** Auch eine korrigierte Datei ist nicht automatisch flashbereit.
- **Signaturen werden nicht kryptografisch geprüft.** Sie werden nur als erwartet oder erkannt ausgewiesen und nie
  verändert.
- **Fehlende ME7-Prüfungen:** ROMSYS, CRC-Tabellen sowie Haupt- und Programmprüfsummen werden nicht geprüft.
- **EDC17CP09:** 3 von 11 Strukturen sind unbestätigt. EDC16- und EDC17-Korrekturen bleiben gesperrt.
- **Weitere Familien nur eingeschränkt:** Siemens/Continental, Bosch MG1/MD1 und alle übrigen Familien haben keine
  Checksummenprüfung.
- Die ME9-Referenz wird noch nicht als ME9 identifiziert. Ihre Korrektur stützt sich auf die Tabellenbelege der Datei.
- Die Referenzdateien wurden nur lokal gemessen. Außer bei MS43 fehlt eine dokumentierte Herkunft. Eine
  unabhängige Bestätigung mit weiteren rechtmäßigen Originalen steht aus.
- Die **TriCore-Codeerkennung** (Architekturprüfung der Kennfelderkennung) ist weiterhin **experimentell**.
- **Keine Authenticode-Signatur:** Die EXE ist nicht code-signiert; Windows kann beim ersten Start warnen.
- **Deinstallation nach einem In-App-Update:** Wurde eine Installation über „Jetzt nach Updates suchen“ aktualisiert,
  bleiben nach der Deinstallation Programmdateien zurück, die erst mit der neuen Version hinzukamen. Beim Update von
  1.19.1 auf 1.20.0 ist das genau eine Datei (`_internal\app\ecu_studio\core\integrity.py`). Benutzerdaten in
  deinem Profil sind nicht betroffen. *Redaktionell korrigiert am 14.11.2026:* Bitte lösche den Ordner
  `%LOCALAPPDATA%\Programs\ECU-Studio-AI` nicht als Ganzes von Hand, denn er kann eigene oder veränderte Dateien
  enthalten. Abhilfe: Führe den Installer ab Version 1.20.1 einmal über die Installation aus und deinstalliere danach
  erneut. Alternativ kannst du nur die eine oben genannte Datei löschen.

---

## English

1.20.0 brings the **first validated stage** of a unified checksum and integrity system. It checks what has been
proven and states clearly what has not been checked. **No original file examined so far reaches complete checksum
coverage.** ECU Studio AI never approves a file for flashing. A corrected file is not automatically ready to flash.

### New

- **Central checksum and integrity system** with five states per file: valid, invalid, incomplete, unsupported,
  unknown. A method that matches by chance never makes a file "valid".
- **Automatic check of selected checksums:**
  - Runs in the background after opening a file and after edits, with progress and cancel.
  - Only the methods listed in the table below are checked.
  - Detailed report with JSON export; shown in the status bar, the export dialog and the flash pre-check.
- **Correction preview for validated methods:** Every changed byte is shown, and the correction needs explicit
  confirmation. It is allowed only for Bosch multipoint and for a reviewed profile bound to the file, and only under the
  conditions below.
- **Safe corrected copies:**
  - Always a **copy** with a change log (`.korrektur.json`) and `.bak`; the original stays unchanged.
  - Copy and log stay consistent even on write, read or disk-space errors.
  - Undo in the session.
- **Independent re-check** of the corrected data before writing.
- **Extended pre-check** with separate check stages:
  1. profile check fields
  2. known checksums
  3. checksum coverage
  4. signatures (always "not checked")
  5. pre-check
  6. flash approval (always "none")

  A matching partial profile or an incomplete check never results in a clean pre-check.

**Correction only with sufficient evidence:** for Bosch multipoint one of two conditions must hold:
- The ECU is unambiguously identified as ME7, ME9 or MED9.
- The file proves the method strongly: at least 32 table entries confirmed on the original, at least 16 of them in one
  table.

These thresholds are a **safety decision** of ECU Studio AI, not a property of the ECUs.

### What is checked – and what is not

| Category | Method | Check | Correction |
|---|---|---|---|
| **Supported** (independently proven) | Bosch multipoint checksum tables (ME7.x, ME9, MED9): 199 of 199 manufacturer values reproduced in three originals, with two implementations | yes | yes, with preview and under the conditions above |
| **Supported** (proven by the user) | Reviewed checksum profile bound to the file's SHA-256 | declared check fields only | yes |
| **Partially checked** | Bosch MED17/EDC17 blocks (EDC17CP09: 8 of 11 structures confirmed on the original, 3 unconfirmed) | yes | locked without a signed OEM proof |
| **Partially checked** | Bosch EDC16 ranges (EDC16C31, EDC16C35: one range each) | yes | locked without a signed OEM proof |
| **Not supported** | further ME7 checksums (ROMSYS, CRC tables, main and program checksums) | no, the file stays "incomplete" | no |
| **Not supported** | Siemens/Continental (e.g. MS43, MSD80, Simos, SID), Bosch MG1/MD1 and all other families | no | no |
| **Never** | Digital manufacturer signatures | only reported as expected/detected, never verified | never changed |

**Explicitly not:**
- Not all ECU checksums are corrected automatically.
- ME7, ME9, EDC16 and EDC17 are not fully supported.
- A corrected file is not automatically ready to flash.
- Digital signatures are not verified.
- There is no flash approval.

### Fixes

- **Definition editor:** after opening another firmware the editor no longer shows values of the previous file. Name,
  address, size, scaling and hints are cleared. Editing functions are disabled without a selected map.
- **Scan results on file switch:** a map scan or recognition started for another file no longer reaches the file that
  is open now.
- **Test settings isolation:** test runs and the build's interface test no longer write into the settings (registry)
  of an installed ECU Studio version.
- **EXE self-test** now also checks the checksum system.

### Known limitations

- **No complete checksum coverage:** no original file examined reaches "valid". ME7, EDC16 and EDC17 files stay
  "incomplete".
- **A partial check is no integrity confirmation:** checksums are not fully checked for every ECU. A successful
  partial check (for example, all multipoint tables match) does not confirm that the whole file is intact.
- **No flash approval:** a corrected file is not automatically ready to flash either.
- **Signatures are not checked cryptographically.** They are only reported as expected or detected and never changed.
- **Missing ME7 checks:** ROMSYS, CRC tables and main and program checksums are not checked.
- **EDC17CP09:** 3 of 11 structures are unconfirmed. EDC16 and EDC17 corrections stay locked.
- **Further families only limited:** Siemens/Continental, Bosch MG1/MD1 and all other families have no checksum check.
- The ME9 reference is not yet identified as ME9. Its correction relies on the file's table evidence.
- The reference files were measured locally only. Apart from MS43 their origin is not documented. Independent
  confirmation with further lawfully obtained originals is still outstanding.
- **TriCore code recognition** (architecture check of the map recognition) is still **experimental**.
- **No Authenticode signature:** the EXE is not code-signed; Windows may warn on first start.
- **Uninstall after an in-app update:** if an installation was updated via "Check for updates now", program files
  that were added by the new version remain after uninstalling. For the update from 1.19.1 to 1.20.0 this is exactly
  one file (`_internal\app\ecu_studio\core\integrity.py`). User data in your profile is not affected. *Editorial
  correction of 14 Nov 2026:* please do not delete the folder `%LOCALAPPDATA%\Programs\ECU-Studio-AI` as a whole by
  hand, because it can contain your own or changed files. Remedy: run the installer of version 1.20.1 or later once
  over the installation, then uninstall again. Alternatively, delete only the one file named above.
