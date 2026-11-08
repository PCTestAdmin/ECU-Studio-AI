# Release-Checkliste 1.20.0

Stand: 08.11.2026. **Kein Schritt in Abschnitt B ist ausgeführt.** Merge, Versionsänderung, Tag und Veröffentlichung
erfolgen erst nach ausdrücklicher Freigabe. Release-Text: [RELEASE_NOTES_1.20.0.md](RELEASE_NOTES_1.20.0.md).

## A. Qualitätssicherung des Release-Kandidaten

Release-Kandidat: Branch `qa/1.20.0-rc` = PR #19 (`feature/1.20-checksum-system`) + PR #20
(`fix/definition-editor-stale-state`) + PR #21 (`fix/test-settings-isolation`) + QA-Workflow
`.github/workflows/installer-qa.yml`. Die Version im Quellcode bleibt 1.19.1.

### A1. Tests und Benchmarks (lokal, 08.11.2026)

| Prüfung | Ergebnis |
|---|---|
| [x] pytest, Release-Kandidat, ohne lokale Referenzen | 977 bestanden, 19 übersprungen, 0 fehlgeschlagen (vor PR #21); im lokalen Build mit PR #21: 980 bestanden, 19 übersprungen |
| [x] pytest, Release-Kandidat, mit lokalen Opt-in-Referenzen | 1018 bestanden, 6 übersprungen (optionale Daten bzw. gebauter `dist`-Ordner), 0 fehlgeschlagen |
| [x] Checksummen-Tests mit Referenzen | 109 bestanden; Bosch-Multipoint 199/199 Herstellerwerte mit beiden Implementierungen |
| [x] EDC16 / EDC17 | unverändert: EDC16C31/C35 je 1/1 Bereich; EDC17CP09 8 bestätigt, 3 unbestätigt, Signaturblöcke erkannt, nie „gültig“; Korrektur gesperrt |
| [x] Sicherheitsregeln PR #19 | Preflight-Matrix, Multipoint-Gate mit Grenzwerten (31/32 Einträge, 15/16 je Tabelle, abgeleiteter Eintrag), 8 Fehlerinjektionen beim Export |
| [x] Kennfelderkennung, 15 reale Vergleichspaare | 0 Abweichungen gegenüber der Basis (außer Zeit und Speicher) |
| [x] Kennfelderkennung, 14 synthetische Fälle | 0 Abweichungen |
| [x] Negativ-Benchmark, sieben offene Firmwarestände | 875 Funde, sicher falsch 0; identisch zur Basis inklusive Versions-Stabilität (ohne Zeit und Speicher) |
| [x] Speicher und wiederholte Scans | Spitzenspeicher je Datei im Benchmark gemessen (z. B. MED17 2 MiB: 28,9 MB); Tests für konstante Speichernutzung über wiederholte Scans und wiederholte Checksummenprüfungen bestanden |
| [x] GUI-Smoke-Test | bestanden, inklusive Checksummenprüfung im echten Fenster |
| [x] Übersetzungen | Englisch-Tests der Oberfläche bestanden (Teil der Suite) |
| [x] Firmware-Guard | `tree HEAD` und `staged` OK |
| [x] Zurückgezogene Lerndaten | Installer-Manifest „sauber“ (lokal und CI) |
| [x] Private Referenzen im Paket | 0 von 8 geprüften Referenz-Hashes und -Namen in ZIP und Installer; einzige firmwareähnliche Endung: 16 mitgelieferte öffentliche XDF-Definitionen |
| [x] Einstellungen des Entwicklers | Registry-Export vor und nach Testsuite, GUI-Smoke und komplettem `build_release.ps1` identisch (PR #21) |

### A2. Build (offizieller Prozess `build_release.ps1` + Inno Setup)

| Prüfung | Ergebnis |
|---|---|
| [x] Lokaler Build | Exit 0; EXE-Selbsttest und `--smoke-test` bestanden; ZIP = Installer (1310 Dateien, gleiche Hashes) |
| [x] CI-Build (GitHub Actions, `installer-qa.yml`) | erfolgreich; diese Pakete wurden auf den Testsystemen installiert |
| [x] Lokal gegen CI | Programmcode (`_internal/app`) identisch; Unterschied nur in der eingebetteten Python-Laufzeit (CI 3.13.17, lokal 3.13.2) |
| [x] Version | 1.19.1, unverändert (Erhöhung nicht freigegeben) |

### A3. Windows-Installer auf frischen, isolierten Systemen

GitHub-gehostete Runner `windows-2022` und `windows-2025`, je ein frisches System pro Job, Workflow
`installer-qa.yml` auf `qa/1.20.0-rc` (Lauf 42502195031). Keine Tags, kein Release, nur Leserechte. Die private
Installation (1.16.3) auf dem Entwicklungsrechner wurde nicht berührt.

| Prüfung | Windows Server 2022 | Windows Server 2025 |
|---|---|---|
| Installation auf sauberem System, ohne Python im PATH | ✅ | ✅ |
| Start über Startmenü (echtes Fenster, Versionstitel) | ✅ | ✅ |
| Start über Desktopverknüpfung | ✅ | ✅ |
| Programmicon (Fenster 16/32 px) und Taskleisten-Identität (AppUserModelID, Relaunch-Befehl) | ✅ | ✅ |
| EXE-Selbsttest und GUI-Smoke-Test der installierten EXE | ✅ | ✅ |
| Testdatei öffnen, automatische Kennfelderkennung | ✅ | ✅ |
| Checksummenprüfung, Korrekturvorschau, korrigierte Kopie mit Änderungsprotokoll | ✅ | ✅ |
| Projekt speichern, Programmneustart, Projekt und Einstellungen wieder da | ✅ | ✅ |
| Deinstallation: Programmordner, Verknüpfungen, Eintrag „Apps & Features“ entfernt | ✅ | ✅ |
| Keine unerwarteten Dateien oder Einträge zurück (Vorher/Nachher-Vergleich) | ✅ | ✅ |
| Erneute Installation, danach erneut Deinstallation ohne Rückstände | ✅ | ✅ |
| Update vom veröffentlichten 1.19.1-Installer auf den Kandidaten (alle 1314 Dateien per SHA-256 geprüft) | ✅ | ✅ |
| Update über den In-App-Updater von 1.19.1 | ✅ | ✅ |
| Projekt und Einstellungen aus 1.19.1 nach dem Update erhalten und lesbar | ✅ | ✅ |
| Private Benutzerdaten nach Update und Deinstallation erhalten | ✅ | ✅ |
| Separate portable ECU-Studio-Kopie unverändert | ✅ | ✅ |

Benutzerdaten (`%USERPROFILE%\.ecu_studio_ai`, Registry `HKCU\Software\ECU Studio`) bleiben nach der
Deinstallation bewusst erhalten; so steht es in `packaging/installer.iss`.

### A4. GitHub

| Prüfung | Ergebnis |
|---|---|
| [x] PR #19 | CI grün, mergebar |
| [x] PR #20 | CI grün, mergebar; Textkonflikt mit #19 in `load_state` bekannt und im Kandidaten aufgelöst |
| [x] PR #21 | CI grün, mergebar |

## B. Freigabe und Veröffentlichung (erst nach Freigabe)

1. [ ] Freigabe für den Merge von PR #19, PR #20 und PR #21 nach `main`. Reihenfolge: #21, #20, #19. Der
   Textkonflikt in `load_state` zwischen #19 und #20 wird wie im Release-Kandidaten aufgelöst: beide Zeilen behalten,
   `clear_map_editor()` danach.
2. [ ] Nach dem Merge: CI auf `main` grün (Tests 3.11/3.12, CodeQL).
3. [ ] Freigabe der Versionsnummer: `src/ecu_studio/__init__.py` → `__version__ = "1.20.0"`.
4. [ ] `CHANGELOG.md`: Den Abschnitt „Unveröffentlicht – geplant als 1.20.0 (Entwurf)“ in `## 1.20.0 (Datum)`
   umbenennen. Der Release-Workflow liest genau diesen Abschnitt (`tools/release_notes.py`). Die englische Fassung
   aus [RELEASE_NOTES_1.20.0.md](RELEASE_NOTES_1.20.0.md) übernehmen; dort „ENTWURF“ entfernen.
5. [ ] `ROADMAP.md` und die Roadmap-Grafiken: 1.20.0 als veröffentlicht eintragen.
6. [ ] Freigabe für Tag und Release: `git tag v1.20.0` und `git push origin v1.20.0`. Der Workflow `release.yml`
   baut, testet, prüft das Update von 1.19.1 auf Windows Server 2022 und 2025 und veröffentlicht erst danach.
7. [ ] Nach der Veröffentlichung: Download-Hashes gegen die `.sha256`-Dateien prüfen, `gh attestation verify`.
8. [ ] QA-Branch `qa/1.20.0-rc` löschen. Er wird nie gemergt; der QA-Workflow liegt nur dort.

## C. Was ausdrücklich nicht im Release-Text stehen darf

- dass alle ECU-Checksummen automatisch korrigiert werden;
- dass ME7, ME9, EDC16 oder EDC17 vollständig unterstützt seien;
- dass Dateien nach der Korrektur flashbereit seien;
- dass digitale Herstellersignaturen verifiziert würden;
- dass eine Flashfreigabe vorliege.
