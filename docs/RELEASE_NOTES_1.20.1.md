# ECU Studio AI 1.20.1 – Release Notes

**Veröffentlicht am 12.11.2026. Released on 12 Nov 2026.**

Inhalt: [PR #24](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/24) (Deinstallation und Update, A5),
[PR #25](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/25) (Release-Workflow),
[PR #26](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/26) (ME7-Prüfsummen, nur Prüfung) und
[PR #27](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/27) (Signaturstatus). Nachweise zu A5:
[Release-Checkliste 1.20.0, A5](RELEASE_CHECKLIST_1.20.0.md#a5-befund-rückstand-nach-in-app-update-und-deinstallation).
Details und Grenzen der Prüfungen: [Checksummen und Integrität](CHECKSUMMEN.md).

---

## Deutsch

1.20.1 behebt Rückstände nach Deinstallationen, die auf ein In-App-Update folgen (A5). Außerdem prüft die Version
weitere ME7-Prüfsummen, aber **nur als Prüfung, ohne Korrektur**. **Keine untersuchte Originaldatei erreicht eine
vollständige Checksummenabdeckung.** ECU Studio AI erteilt weiterhin keine Flashfreigabe.

### Fehlerbehebungen

- **A5 – Deinstallation nach einem In-App-Update:** Der Deinstaller entfernt zusätzlich genau die Programmdateien,
  die alle drei Bedingungen erfüllen:
  - laut `RUNTIME_INVENTORY.json` ausgeliefert;
  - innerhalb des Programmordners;
  - unverändert (SHA-256).

  Eigene, unbekannte und veränderte Dateien bleiben stehen, ebenso Verknüpfungen und Junctions. Sie werden im
  Deinstallationsprotokoll genannt. Es gibt keine pauschale Löschregel.
- **Update-Sicherung beim Deinstallieren:** Bis 1.20.0 löschte der Deinstaller die Ordner `ECU-Studio-AI.backup`
  und `ECU-Studio-AI.update-staging` neben dem Programmordner vollständig. Dort kann aber die einzige Kopie einer
  veränderten oder eigenen Datei liegen. Ab 1.20.1 wird jede Datei einzeln geprüft. Entfernt werden nur:
  - unveränderte Programmdateien laut Inventar des Ordners;
  - byte-gleiche Kopien (SHA-256) von Dateien im Programmordner;
  - Deinstallationsprogramm und -protokoll dieser Anwendung.

  Alles andere bleibt samt Ordner erhalten und wird im Deinstallationsprotokoll genannt.
- **Update über den geprüften Installer:**
  - Installationen mit Installer laden bei „Jetzt nach Updates suchen“ den Installer
    `ECU-Studio-AI-<version>-setup.exe`. Die SHA-256-Prüfsumme wird gegen das Release geprüft.
  - Der Installer läuft mit Sicherung und setzt bei einem Fehler automatisch zurück.
  - Portable ZIP-Kopien aktualisieren sich wie bisher.
- **Versionsanzeige in Windows:** „Apps & Features“ zeigt nach einem Update ab 1.20.1 die tatsächlich installierte
  Version.

### Neue Funktionen

- **Weitere ME7-Prüfsummen, nur Prüfung:** ROMSYS (Startup, Parameterseite, Programmseiten), CRC-Tabelle,
  Hauptdaten-Prüfsumme, Hauptdaten-CRC32 und Hauptprogramm-Prüfsumme.
  - Eigene Umsetzung nach dem quelloffenen ME7Sum.
  - An einem ME7.5-Original gemessen: 8 von 8 gespeicherten Werten reproduziert. **Nicht unabhängig validiert.**
  - Keine Korrektur. Der Status bleibt höchstens „Unvollständige Prüfung“.
  - Die Hintergrund-Prüfsummen hat schon 1.20.0 als Multipoint-Einträge geprüft; sie werden nicht doppelt gezählt.
- **Erweiterte Integritätsstatus:** Die Liste „nicht geprüft“ folgt dem, was in der Datei tatsächlich nachgewiesen
  ist. Auf ME7.5 bleiben zum Beispiel Hauptdaten-CRC32 und indirekte CRC-Blöcke ausdrücklich offen.
- **Architektur für die Signaturprüfung:** Herstellersignaturen in der Firmware haben sechs getrennte Status: gültig,
  ungültig, Struktur erkannt, erwartet, nicht unterstützt, unbekannt.
  - „Gültig“ und „ungültig“ gibt es nur nach einer echten kryptographischen Prüfung (Ed25519 oder
    RSA-PKCS#1 v1.5 mit SHA-256) mit einem Schlüssel aus einem ausdrücklich angegebenen Vertrauensspeicher. Ein
    Schlüssel aus der Datei selbst zählt nie.
  - OEM-Signaturen werden getrennt von Authenticode und GitHub-Attestations geführt.
  - Signaturen werden nur geprüft, nie erzeugt, verändert oder entfernt.
  - Für keine Steuergerätefamilie liegt bisher ein vertrauenswürdiger OEM-Schlüssel vor. Die Anzeige echter Dateien
    ändert sich deshalb nicht.

### Verbesserungen

- **Schutz vor widersprüchlichen Checksummenkorrekturen:** Die Korrekturvorschau rechnet das Ergebnis vorab
  vollständig nach.
  - Würde eine Korrektur eine bisher stimmende Prüfsumme eines anderen Verfahrens falsch machen, wird sie mit
    Begründung verweigert.
  - Bleiben nicht korrigierbare Prüfsummen falsch, warnt die Vorschau. Die Datei bleibt dann „Unterstützt und
    ungültig“.
  - Die Vorschau dauert dadurch etwa doppelt so lang (zum Beispiel ME7.5: 139 → 305 ms).
- **Sichererer Release-Workflow:**
  - Titel immer „ECU Studio AI vX.Y.Z“, Release-Text auf Deutsch und Englisch.
  - Versionsprüfung von EXE, ZIP und Installer.
  - Installer-, Update- und Deinstallationstest auf Windows Server 2022 und 2025.
  - Assets und SHA-256-Werte werden vor und nach dem Veröffentlichen geprüft, dazu ein Herkunftsnachweis.
  - Firmware-Guard und Modellsperre; Probeläufe veröffentlichen nie.
- **Tests und Validierung:**
  - neue Tests für das Inventar beim Deinstallieren, die ME7-Prüfungen (mit einer zweiten, einfachen
    Implementierung), die Signaturzustände (nur synthetische Schlüssel) und den Release-Workflow;
  - die Kennfelderkennung ist gegenüber 1.20.0 unverändert: 15 reale Vergleichspaare, 14 synthetische Fälle und der
    Negativ-Benchmark ohne Unterschied.

### Bekannte Einschränkungen

- **Übergang bei alten In-App-Updates:** Das Update von 1.20.0 auf 1.20.1 über „Jetzt nach Updates suchen“ führt
  noch der Updater von 1.20.0 aus.
  - Dieser alte Weg behält den Deinstaller von 1.20.0. Er kennt drei neue Dateien nicht und lässt sie nach einer
    Deinstallation im Programmordner `%LOCALAPPDATA%\Programs\ECU-Studio-AI` zurück:
    - `_internal\app\ecu_studio\core\firmware_signatures.py`
    - `_internal\app\ecu_studio\core\me7_checksums.py`
    - `_internal\uninstall_cleanup.ps1`
  - **Empfohlen: Reparaturinstallation.** Führe `ECU-Studio-AI-1.20.1-setup.exe` aus diesem Release einmal über die
    bestehende Installation aus. Danach entfernt die Deinstallation alle Programmdateien. Projekte, Einstellungen und
    eigene Dateien bleiben erhalten. Auch das nächste Update durch 1.20.1 oder neuer behebt den Übergang.
  - Schon deinstalliert? Dann denselben Installer einmal ausführen und danach erneut deinstallieren. Die drei Dateien
    werden dabei als unveränderte Programmdateien erkannt und entfernt.
  - Lösche den Programmordner bitte nicht als Ganzes von Hand. Dort können eigene oder veränderte Dateien liegen.
- **Keine vollständige Checksummenabdeckung:** Keine untersuchte Originaldatei erreicht „gültig“. ME7, EDC16 und
  EDC17 bleiben „unvollständig“. Eine erfolgreiche Teilprüfung bestätigt nicht die Unversehrtheit der ganzen Datei.
- **Neue ME7-Verfahren nicht unabhängig validiert:** Gemessen an nur einem Original mit undokumentierter Herkunft.
  Die Hauptdaten-CRC32 kam auf keinem Original vor und ist ungeprüft; indirekte CRC-Blöcke werden nicht unterstützt.
- **EDC17CP09:** Weiterhin sind 3 von 11 Strukturen unbestätigt. EDC16- und EDC17-Korrekturen bleiben gesperrt.
- **Keine verifizierten OEM-Signaturen:** Für keine Familie ist eine Herstellersignatur kryptografisch geprüft.
- **Keine automatische Flashfreigabe:** Auch eine korrigierte Datei ist nicht automatisch flashbereit.
- **Keine Authenticode-Signatur:** Die EXE ist nicht code-signiert; Windows kann beim ersten Start warnen.
- Die **TriCore-Codeerkennung** (Architekturprüfung der Kennfelderkennung) ist weiterhin **experimentell**.

---

## English

1.20.1 fixes files left behind by an uninstall that follows an in-app update (A5). It also checks further ME7
checksums, but **as checks only, without correction**. **No original file examined so far reaches complete checksum
coverage.** ECU Studio AI still never approves a file for flashing.

### Bug fixes

- **A5 – uninstall after an in-app update:** the uninstaller also removes exactly the program files that meet all
  three conditions:
  - shipped according to `RUNTIME_INVENTORY.json`;
  - inside the program folder;
  - unchanged (SHA-256).

  The user's own, unknown and changed files stay, and so do links and junctions. They are listed in the uninstall
  log. There is no blanket delete rule.
- **Update backup on uninstall:** up to 1.20.0 the uninstaller deleted the folders `ECU-Studio-AI.backup` and
  `ECU-Studio-AI.update-staging` next to the program folder completely. They can hold the only copy of a changed or
  own file, though. From 1.20.1 every file there is checked on its own. Only these are removed:
  - unchanged program files according to the folder's inventory;
  - byte-identical copies (SHA-256) of files in the program folder;
  - this application's uninstaller and uninstall log.

  Everything else stays, together with its folder, and is listed in the uninstall log.
- **Update through the verified installer:**
  - Installations made with the installer download the installer `ECU-Studio-AI-<version>-setup.exe` on "Check for
    updates now". Its SHA-256 checksum is verified against the release.
  - The installer runs with a backup and rolls back automatically on failure.
  - Portable ZIP copies update as before.
- **Version shown in Windows:** after an update from 1.20.1 on, "Apps & Features" shows the version that is actually
  installed.

### New features

- **Further ME7 checksums, check only:** ROMSYS (startup, parameter page, program pages), CRC table, main data
  checksum, main data CRC32 and main program checksum.
  - Own implementation following the open-source ME7Sum.
  - Measured on one ME7.5 original: 8 of 8 stored values reproduced. **Not independently validated.**
  - No correction. The status stays "incomplete check" at best.
  - The background checksums were already checked by 1.20.0 as multipoint entries; they are not counted twice.
- **Extended integrity states:** the "not checked" list follows what is actually present in the file. On ME7.5, for
  example, the main data CRC32 and indirect CRC blocks stay explicitly open.
- **Architecture for signature verification:** manufacturer signatures in the firmware have six separate states:
  valid, invalid, structure detected, expected, unsupported, unknown.
  - "Valid" and "invalid" only result from a real cryptographic check (Ed25519 or RSA-PKCS#1 v1.5 with SHA-256) with
    a key from an explicitly given trust store. A key taken from the file itself never counts.
  - OEM signatures are kept separate from Authenticode and GitHub attestations.
  - Signatures are only checked, never created, changed or removed.
  - No trusted OEM key is available for any ECU family yet, so nothing changes in how real files are shown.

### Improvements

- **Protection against conflicting checksum corrections:** the correction preview fully recomputes the result in
  advance.
  - If a correction would break a checksum of another method that currently matches, it is refused with a reason.
  - If checksums that cannot be corrected stay wrong, the preview warns. The file then stays "supported and
    invalid".
  - The preview therefore takes about twice as long (for example ME7.5: 139 → 305 ms).
- **Safer release workflow:**
  - The title is always "ECU Studio AI vX.Y.Z", the release text is in German and English.
  - Version check of EXE, ZIP and installer.
  - Installer, update and uninstall test on Windows Server 2022 and 2025.
  - Assets and SHA-256 values are checked before and after publishing, plus a build provenance attestation.
  - Firmware guard and model lock; dry runs never publish.
- **Tests and validation:**
  - new tests for the uninstall inventory, the ME7 checks (with a second, simple implementation), the signature
    states (synthetic keys only) and the release workflow;
  - map detection is unchanged from 1.20.0: 15 real comparison pairs, 14 synthetic cases and the negative benchmark
    show no difference.

### Known limitations

- **Transition for old in-app updates:** the update from 1.20.0 to 1.20.1 via "Check for updates now" is still
  carried out by the 1.20.0 updater.
  - This old path keeps the 1.20.0 uninstaller. It does not know three new files and leaves them behind in the
    program folder `%LOCALAPPDATA%\Programs\ECU-Studio-AI` after an uninstall:
    - `_internal\app\ecu_studio\core\firmware_signatures.py`
    - `_internal\app\ecu_studio\core\me7_checksums.py`
    - `_internal\uninstall_cleanup.ps1`
  - **Recommended: repair installation.** Run `ECU-Studio-AI-1.20.1-setup.exe` from this release once over the
    existing installation. After that, uninstalling removes all program files. Projects, settings and your own files
    are kept. The next update carried out by 1.20.1 or later also completes the transition.
  - Already uninstalled? Run the same installer once and uninstall again. The three files are then recognised as
    unchanged program files and removed.
  - Please do not delete the program folder as a whole by hand. It may contain your own or changed files.
- **No complete checksum coverage:** no original file examined reaches "valid". ME7, EDC16 and EDC17 stay
  "incomplete". A successful partial check does not confirm that the whole file is intact.
- **New ME7 methods not independently validated:** measured on a single original of undocumented origin. The main
  data CRC32 did not occur on any original and is unverified; indirect CRC blocks are not supported.
- **EDC17CP09:** 3 of 11 structures are still unconfirmed. EDC16 and EDC17 corrections stay locked.
- **No verified OEM signatures:** no manufacturer signature is cryptographically verified for any family.
- **No automatic flash approval:** even a corrected file is not automatically ready to flash.
- **No Authenticode signature:** the EXE is not code-signed; Windows may warn on first start.
- **TriCore code detection** (architecture check of the map detection) is still **experimental**.
