# ECU Studio AI 1.20.0 – Release Notes (ENTWURF)

> **Entwurf, nicht veröffentlicht.** Version, Tag und GitHub-Release folgen erst nach ausdrücklicher Freigabe.
> Bis dahin trägt der Quellcode weiter die Version 1.19.1. Inhalt: [PR #19](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/19)
> (Checksummen & Integrität), [PR #20](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/20) (Definitionseditor) und
> [PR #21](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/21) (Testisolation). Prüfnachweise:
> [Release-Checkliste 1.20.0](RELEASE_CHECKLIST_1.20.0.md). Details und Grenzen: [Checksummen und Integrität](CHECKSUMMEN.md).

---

## Deutsch

1.20.0 bringt die **erste validierte Ausbaustufe** eines gemeinsamen Checksummen- und Integritätssystems. Es prüft,
was nachgewiesen ist, und sagt deutlich, was nicht geprüft ist. **Keine untersuchte Originaldatei erreicht bisher
eine vollständige Checksummenabdeckung.** ECU Studio AI erteilt keine Flashfreigabe. Eine Datei ist nach einer
Korrektur nicht automatisch flashbereit.

### Checksummen & Integrität

- **Fünf Status je Datei:** gültig, ungültig, unvollständig, nicht unterstützt, unbekannt. Ein zufällig passendes
  Verfahren macht eine Datei nie „gültig“.
- **Prüfung im Hintergrund** mit Fortschritt und Abbrechen. Detailbericht mit JSON-Export, Anzeige in Statusleiste,
  Exportdialog und Flash-Vorprüfung.
- **Getrennte Prüfstufen:**
  1. Profil-Prüffelder
  2. bekannte Prüfsummen
  3. Checksummenabdeckung
  4. Signaturen (immer „nicht geprüft“)
  5. Preflight
  6. Flashfreigabe (immer „keine“)

  Ein passendes Teilprofil oder eine unvollständige Prüfung ergibt nie einen sauberen Preflight.
- **Sichere Korrektur:**
  - Vorschau mit jedem Byte und ausdrückliche Bestätigung.
  - Unabhängige Nachprüfung vor dem Schreiben, Undo in der Sitzung.
  - Korrigierte **Kopie** mit Änderungsprotokoll (`.korrektur.json`) und `.bak`.
  - Kopie und Protokoll bleiben auch bei Schreib-, Lese- oder Speicherplatzfehlern konsistent; das Original bleibt
    unverändert.
- **Korrektur nur bei ausreichendem Beleg:** für Bosch-Multipoint nur, wenn eine der beiden Bedingungen gilt:
  - Das Steuergerät ist eindeutig als ME7, ME9 oder MED9 identifiziert.
  - Die Datei belegt das Verfahren stark: mindestens 32 am Original bestätigte Tabelleneinträge, davon mindestens
    16 in einer Tabelle.

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

### Weitere Korrekturen

- **Definitionseditor beim Dateiwechsel:** Nach dem Öffnen einer anderen Firmware zeigt der Editor keine Werte der
  vorherigen Datei mehr. Name, Adresse, Größe, Skalierung und Hinweise werden geleert, und Bearbeitungsfunktionen
  sind ohne Kennfeldauswahl deaktiviert. Ein Scan, der für eine andere geöffnete Datei gestartet wurde, gelangt nicht
  mehr in die aktuelle Datei.
- **Einstellungen der installierten Version geschützt:** Testläufe und der Oberflächentest des Builds schreiben nicht
  mehr in die Einstellungen (Registry) einer installierten ECU-Studio-Version.
- **Selbsttest der EXE** prüft jetzt auch das Checksummensystem.

### Bekannte Einschränkungen

- Keine untersuchte Originaldatei erreicht „gültig“. ME7-, EDC16- und EDC17-Dateien bleiben „unvollständig“.
- Die ME9-Referenz wird noch nicht als ME9 identifiziert. Ihre Korrektur stützt sich auf die Tabellenbelege der
  Datei (Bedingung B).
- EDC17CP09: 3 von 11 Strukturen unbestätigt. EDC16/EDC17-Korrekturen bleiben gesperrt.
- Die Referenzdateien wurden nur lokal gemessen. Außer bei MS43 fehlt eine dokumentierte Herkunft. Eine
  unabhängige Bestätigung mit weiteren rechtmäßigen Originalen steht aus.
- Die EXE ist weiterhin nicht Authenticode-signiert.

---

## English

1.20.0 brings the **first validated stage** of a unified checksum and integrity system. It checks what has been
proven and states clearly what has not been checked. **No original file examined so far reaches complete checksum
coverage.** ECU Studio AI never approves a file for flashing. A corrected file is not automatically ready to flash.

### Checksums & integrity

- **Five states per file:** valid, invalid, incomplete, unsupported, unknown. A method that matches by chance never
  makes a file "valid".
- **Background check** with progress and cancel. Detailed report with JSON export, shown in the status bar, export
  dialog and flash pre-check.
- **Separate check stages:**
  1. profile check fields
  2. known checksums
  3. checksum coverage
  4. signatures (always "not checked")
  5. pre-check
  6. flash approval (always "none")

  A matching partial profile or an incomplete check never results in a clean pre-check.
- **Safe correction:**
  - Preview of every byte and explicit confirmation.
  - Independent re-check before writing, undo in the session.
  - Corrected **copy** with a change log (`.korrektur.json`) and `.bak`.
  - Copy and log stay consistent even on write, read or disk-space errors; the original stays unchanged.
- **Correction only with sufficient evidence:** for Bosch multipoint only if one of two conditions holds:
  - The ECU is unambiguously identified as ME7, ME9 or MED9.
  - The file proves the method strongly: at least 32 table entries confirmed on the original, at least 16 of them in
    one table.

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

### Other fixes

- **Definition editor on file switch:** after opening another firmware the editor no longer shows values of the
  previous file. Name, address, size, scaling and hints are cleared, and editing functions are disabled without a
  selected map. A scan started for another opened file no longer reaches the current one.
- **Settings of the installed version protected:** test runs and the build's interface test no longer write into the
  settings (registry) of an installed ECU Studio version.
- **EXE self-test** now also checks the checksum system.

### Known limitations

- No original file examined reaches "valid". ME7, EDC16 and EDC17 files stay "incomplete".
- The ME9 reference is not yet identified as ME9. Its correction relies on the file's table evidence (condition B).
- EDC17CP09: 3 of 11 structures unconfirmed. EDC16/EDC17 corrections stay locked.
- The reference files were measured locally only. Apart from MS43 their origin is not documented. Independent
  confirmation with further lawfully obtained originals is still outstanding.
- The EXE is still not Authenticode-signed.
