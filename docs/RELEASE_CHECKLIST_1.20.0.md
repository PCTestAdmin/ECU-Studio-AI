# Release-Checkliste 1.20.0

Stand: 08.11.2026.

- PR #19, #20 und #21 sind in `main` gemergt.
- Version 1.20.0 ist auf dem Branch `release/1.20.0-preparation` vorbereitet; der PR wird erst nach Freigabe gemergt.
- Tag, GitHub-Release und Veröffentlichung erfolgen erst nach ausdrücklicher Freigabe.

Release-Text: [RELEASE_NOTES_1.20.0.md](RELEASE_NOTES_1.20.0.md).

## A. Qualitätssicherung

### A1. Merge nach `main`

Reihenfolge #21 → #20 → #19, normale Merge-Commits, kein Force-Push, keine umgeschriebene Historie.

| Schritt | Commit | CI auf `main` (Tests 3.11/3.12, CodeQL) |
|---|---|---|
| PR #21 (Testisolation) | `83643be` | grün |
| PR #20 (Definitionseditor) | `eddcccd` | grün |
| PR #19 mit `main` aktualisiert, Konflikt in `load_state` aufgelöst | `ece47f6` | PR-CI grün |
| PR #19 (Checksummen & Integrität) | `2ee14d9` | grün |

Die Konfliktlösung entspricht der im Release-Kandidaten `qa/1.20.0-rc` geprüften: `main_window.py` ist byteidentisch
(Blob `d18d2cb`). Der Baum von `main` nach dem Merge ist mit dem geprüften Kandidaten identisch, ohne die drei
QA-Dateien des QA-Branchs.

### A2. Tests und Benchmarks (lokal, Stand `main` 2ee14d9 bzw. Release-Branch)

| Prüfung | Ergebnis |
|---|---|
| [x] pytest mit lokalen Opt-in-Referenzen | 1026 bestanden, 6 übersprungen, 0 fehlgeschlagen |
| [x] pytest im offiziellen Build (`build_release.ps1`, Version 1.20.0) | 988 bestanden, 19 übersprungen, 0 fehlgeschlagen |
| [x] CI Python 3.11 und 3.12, CodeQL | grün auf `main` und auf dem Kandidaten |
| [x] Checksummen-Tests mit Referenzen | 158 bestanden |
| [x] Bosch-Multipoint | 199 von 199 Herstellerwerten (70 + 63 + 66) mit beiden Implementierungen identisch |
| [x] EDC16 / EDC17 | unverändert: EDC16C31/C35 je 1/1 Bereich; EDC17CP09 8 bestätigt, 3 unbestätigt; Signaturen nie „gültig“; Korrektur gesperrt |
| [x] Belastungsprüfung Checksummen (sechs Referenzen) | Details unter der Tabelle |
| [x] Kennfelderkennung, 15 reale Vergleichspaare | 0 Abweichungen zur Basis (exakte Kennfelder 2D 1454, 1D 3800; Datentyp 1250; Achsen 1215; Achsadressen 2406); Laufzeit 110 → 100 s, Spitzenspeicher 548 → 547 MB |
| [x] Kennfelderkennung, 14 synthetische Fälle | 0 Abweichungen (exakt 222, Fehlfunde 2D 155 unverändert) |
| [x] Negativ-Benchmark, sieben offene Firmwarestände | 875 Funde, sicher falsch 0; identisch zur Basis (ohne Zeit und Speicher) |
| [x] GUI-Smoke-Test | bestanden, mit echter MS43 (856 Kennfelder, Original unverändert) und Checksummenablauf im echten Fenster |
| [x] Definitionseditor, Einstellungsisolation, Übersetzungen | Tests bestanden (Teil der Suite) |
| [x] Firmware-Guard | `tree` für die drei PR-Stände und `main` OK; Commit-Hook bei jedem Commit OK |
| [x] Zurückgezogene Lerndaten | Installer-Manifest „sauber“ (lokal und CI) |
| [x] Einstellungen des Entwicklers | Registry-Export vor und nach Suite, GUI-Smoke und komplettem `build_release.ps1` byteidentisch |

Belastungsprüfung der Checksummen an sechs Referenzen:
- **Erkennung und Korrektur:** Jede Änderung in einem geprüften Bereich wird erkannt. Multipoint bietet Vorschau,
  unabhängige Nachprüfung und eine korrigierte Kopie mit Protokoll. Das Original bleibt unverändert. EDC16/EDC17
  verweigern die Korrektur.
- **Abgeschnittene Dateien:** in 8 Längen nie „gültig“, nie ein Fehler, keine Korrektur.
- **Zufallsdaten:** 60 Zufalls- und Zufallstabellen-Dateien, 0 Korrekturangebote.
- **Abbrechen:** ändert nichts.
- **Schreibfehler:** Es bleibt nichts zurück.
- **Simulierter Lesefehler:** Die vorherige Kopie und das Protokoll werden wiederhergestellt.
- **Speicher:** Zuwachs höchstens 3,6 KiB nach 30 Prüfungen.

### A3. Build 1.20.0 (offizieller Prozess `build_release.ps1` + Inno Setup)

| Prüfung | Ergebnis |
|---|---|
| [x] Lokaler Build | Exit 0; EXE-Selbsttest und `--smoke-test` bestanden; ZIP = Installer (1310 Dateien, gleiche Hashes) |
| [x] CI-Build (`installer-qa.yml`, Lauf 42509901293) | erfolgreich; Release-Notes-Prüfung wie `release.yml` (Tag `v1.20.0` = Paketversion, CHANGELOG-Abschnitt vorhanden) |
| [x] Version | EXE-Dateiversion 1.20.0.0, Produktversion 1.20.0; Installer 1.20.0; `VERSION.txt` 1.20.0; Fenstertitel „ECU Studio AI v1.20.0“ |
| [x] Lokal gegen CI | Programmcode (`_internal/app`, 214 Dateien) identisch; Unterschied nur in eingebetteter Python-Laufzeit und Starter-Build |
| [x] Inhalt | 0 private Referenz-Hashes und -Namen; einzige firmwareähnliche Endung: 16 mitgelieferte öffentliche XDF-Definitionen; keine zurückgezogenen Modelle |
| [x] Signatur | EXE nicht Authenticode-signiert (bekannt) |

SHA-256 des CI-Kandidaten. Dieses Paket wurde auf den Testsystemen installiert und über die Staging-Quelle aktualisiert:

```
99ed545e531bd69390c1db158e1297daae0f042711f37fc0dbe13c90cac45add  ECU-Studio-AI-1.20.0-windows-x64.zip
79dbd1b48b6060f3bf9c65d56d87b632913e9b908fadacb3fc27ea78a0446a48  ECU-Studio-AI-1.20.0-setup.exe
```

SHA-256 des lokalen Builds (gleicher Programmcode, andere Python-Laufzeit):

```
4aab41c12da2b7e5b981d82fe625a9fc36a983cde2ba374de931c35f26558943  ECU-Studio-AI-1.20.0-windows-x64.zip
dabf2c28e289cf63006109ab200d33645e83d4996ef0d25692df339c9824b298  ECU-Studio-AI-1.20.0-setup.exe
```

Die Pakete der Veröffentlichung baut `release.yml` neu; ihre Hashes werden andere sein.

### A4. Windows-Installer und Updates auf frischen, isolierten Systemen

GitHub-gehostete Runner `windows-2022` und `windows-2025`, ein frisches System je Job. Workflow `installer-qa.yml` auf
`qa/1.20.0-rc2`, Lauf 42509901293. Keine Tags, kein Release, nur Leserechte. Die private Installation (1.16.3) auf dem
Entwicklungsrechner wurde nicht berührt.

| Prüfung | Windows Server 2022 | Windows Server 2025 |
|---|---|---|
| Frische Installation: 72 Prüfungen (Start über Startmenü und Desktop, Icon, Taskleiste, Selbsttest, GUI-Smoke, Kennfelderkennung, Checksummen, Neustart, Deinstallation, Neuinstallation, keine Rückstände) | ✅ 72/72 | ✅ 72/72 |
| Update per Installer von 1.19.1: 45 Prüfungen (alle Dateien per SHA-256, Projekt und Einstellungen aus 1.19.1, portable Kopie unverändert) | ✅ 45/45 | ✅ 45/45 |
| **Echtes In-App-Update aus der laufenden 1.19.1** (Details unter der Tabelle) | ✅ 46/47 | ✅ 46/47 |
| davon: Deinstallation nach In-App-Update ohne Rückstände | ❌ eine Datei bleibt (siehe A5) | ❌ eine Datei bleibt |

Ablauf des In-App-Updates, Schritt für Schritt geprüft:
1. 1.19.1 per veröffentlichtem Installer installieren, Projekt und Einstellungen anlegen.
2. Start über das Startmenü.
3. Per Maus (UI Automation) „Einstellungen → Jetzt nach Updates suchen“. Der Dialog zeigt „Version 1.20.0 ist
   verfügbar“ sowie „Installiert: 1.19.1 · Neu: 1.20.0“.
4. „Jetzt aktualisieren“: Download und SHA-256-Prüfung durch das Programm.
5. „Update bereit“ → Ja. Das Programm schließt sich, der Updater installiert und führt den Selbsttest aus.
6. Neustart als „ECU Studio AI v1.20.0“ mit Programmicon und Taskleisten-Identität.
7. Prüfung danach:
   - alle 1314 Dateien per SHA-256;
   - Sicherung der 1.19.1 vorhanden;
   - Selbsttest und GUI-Smoke-Test;
   - Projekt und Einstellungen aus 1.19.1 geöffnet;
   - Benutzerdateien unverändert.

Die Update-Quelle war eine **Staging-Quelle nur auf dem Runner**:
- `api.github.com` und `github.com` zeigen per hosts-Datei auf einen lokalen HTTPS-Server.
- Eine Wegwerf-Test-CA wird danach gelöscht.

Der Code von 1.19.1 lief unverändert; das Serverprotokoll belegt den Abruf von Release-Info, `.sha256` und ZIP.
Es wurde kein GitHub-Release angelegt.

Benutzerdaten (`%USERPROFILE%\.ecu_studio_ai`, Registry `HKCU\Software\ECU Studio`) bleiben nach der
Deinstallation bewusst erhalten (`packaging/installer.iss`).

### A5. Befund: Rückstand nach In-App-Update und Deinstallation

**Befund:** Nach einem In-App-Update von 1.19.1 auf 1.20.0 und anschließender Deinstallation bleibt genau eine Datei
im Programmordner: `_internal\app\ecu_studio\core\integrity.py`.

**Ursache (belegt):**
- Der Inno-Setup-Deinstaller der 1.19.1-Installation kennt nur die Dateien, die er selbst installiert hat.
- Das In-App-Update tauscht den Ordner aus und übernimmt `unins000.exe/.dat`.
- Dateien, die erst mit der neuen Version hinzukommen, bleiben deshalb stehen. Die Rückstandsliste auf beiden
  Systemen entspricht exakt der Menge „neu in 1.20.0 gegenüber 1.19.1“.

**Einordnung:**
- Das Verhalten besteht seit Einführung des In-App-Updaters. Schon 1.19.1 brachte gegenüber 1.19.0 drei neue Dateien.
- Es ist keine Folge des 1.20.0-Codes.
- Nicht betroffen sind Funktion, Benutzerdaten und Sicherheit.
- Das Update per Installer ist nicht betroffen (45/45).

**Offene Entscheidung:** Ein Eintrag `Type: filesandordirs; Name: "{app}\_internal"` unter `[UninstallDelete]` in
`packaging/installer.iss` würde künftige Fälle für Installationen ab dem 1.20.0-Installer beheben. Für bestehende
1.19.1-Installationen hilft er nicht. Er löscht außerdem Dateien, die ein Benutzer selbst in `_internal` abgelegt hat.
Nicht umgesetzt; als bekannte Einschränkung dokumentiert.

### A6. GitHub

| Prüfung | Ergebnis |
|---|---|
| [x] PR #19, #20, #21 | gemergt; vor jedem Merge: offen, mergebar, CI grün, keine neuen Commits, keine offenen Review-Kommentare, Firmware-Guard OK |
| [x] Release-Vorbereitungs-PR | offen, nicht gemergt |

## B. Freigabe und Veröffentlichung

1. [x] Merge von PR #21, #20 und #19 nach `main` (A1).
2. [x] CI auf `main` grün.
3. [x] Version 1.20.0 (`pyproject.toml`, `src/ecu_studio/__init__.py`): im Release-Vorbereitungs-PR.
4. [x] `CHANGELOG.md`: Abschnitt `## 1.20.0 (11.11.2026)` (Datum am Veröffentlichungstag angepasst);
   `tools/release_notes.py v1.20.0` prüft ihn.
5. [ ] **Freigabe:** Release-Vorbereitungs-PR nach `main` mergen.
6. [ ] `ROADMAP.md` und Roadmap-Grafiken: 1.20.0 als veröffentlicht eintragen.
7. [ ] **Freigabe für Tag und Release:** `git tag v1.20.0` und `git push origin v1.20.0`. Der Workflow `release.yml`
   baut, testet und prüft das Update von 1.19.1 auf Windows Server 2022 und 2025. Erst danach veröffentlicht er.
8. [ ] Nach der Veröffentlichung:
   - Download-Hashes gegen die `.sha256`-Dateien prüfen und `gh attestation verify` ausführen.
   - Englischen Teil aus [RELEASE_NOTES_1.20.0.md](RELEASE_NOTES_1.20.0.md) und absolute Links im Release-Text
     ergänzen (wie bei 1.19.1).
9. [ ] QA-Branches `qa/1.20.0-rc` und `qa/1.20.0-rc2` löschen. Sie werden nie gemergt; der QA-Workflow liegt nur dort.

## C. Was ausdrücklich nicht im Release-Text stehen darf

- dass alle ECU-Checksummen automatisch korrigiert werden;
- dass ME7, ME9, EDC16 oder EDC17 vollständig unterstützt seien;
- dass Dateien nach der Korrektur flashbereit seien;
- dass digitale Herstellersignaturen verifiziert würden;
- dass eine Flashfreigabe vorliege.
