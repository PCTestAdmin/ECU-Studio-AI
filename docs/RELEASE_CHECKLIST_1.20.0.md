# Release-Checkliste 1.20.0

Stand: 11.11.2026 – **veröffentlicht**.

- PR #19, #20, #21 und #22 sind in `main` gemergt; PR #22 als `5dedb77`.
- Tag `v1.20.0` (annotiert) zeigt auf `5dedb774d52dfa919967418a5eda42821a30bc8c`.
- Release: [ECU Studio AI v1.20.0](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/tag/v1.20.0). Prüfung der veröffentlichten Dateien: A7.

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

**Entscheidung (11.11.2026):** Für 1.20.0 als bekannte Einschränkung akzeptiert und in den Release Notes
beschrieben. Eine pauschale Regel `Type: filesandordirs; Name: "{app}\_internal"` unter `[UninstallDelete]` wird
**nicht** verwendet: Sie löscht auch Dateien, die ein Benutzer selbst in `_internal` abgelegt hat, und hilft
bestehenden Installationen nicht.

**Sicherer Fix für 1.20.1 (Plan):**

1. **Deinstallation nach Inventar.** Jede Installation enthält `RUNTIME_INVENTORY.json`: alle ausgelieferten Dateien
   mit SHA-256. Das In-App-Update ersetzt sie durch das Inventar der neuen Version (`packaging/updater.ps1`, Schritt 5
   nutzt es schon, um Benutzerdateien zu erkennen). Der Deinstaller des 1.20.1-Installers
   (`[Code]`, `CurUninstallStepChanged`, Schritt `usUninstall`) entfernt zusätzlich genau die Dateien, die
   - im Inventar stehen,
   - innerhalb von `{app}` liegen (keine absoluten Pfade, kein `..`) und
   - denselben SHA-256 wie im Inventar haben.

   Danach entfernt er nur leere Ordner. Nicht gelistete oder veränderte Dateien bleiben stehen und werden im
   Deinstallationsprotokoll genannt.
2. **Installer-Installationen per Installer aktualisieren.** Ist `unins000.exe` vorhanden, lädt das In-App-Update
   den geprüften `ECU-Studio-AI-<version>-setup.exe` (SHA-256 aus dem Release, wie beim ZIP) und führt ihn still mit
   `/DIR` auf den bestehenden Ordner aus. Inno Setup kennt dann alle Dateien, und „Apps & Features“ zeigt die richtige
   Version. Portable ZIP-Installationen behalten den bisherigen Weg; Sicherung und Wiederherstellen bleiben erhalten.
3. **Grenze:** Ein Deinstaller aus 1.19.1 oder 1.20.0 bleibt unverändert. Wer mit einem solchen Deinstaller
   deinstalliert, kann den Ordner `%LOCALAPPDATA%\Programs\ECU-Studio-AI` danach löschen (Benutzerdaten liegen
   außerhalb). Einen aktuellen Deinstaller erhält eine Installation, sobald sie einmal den Installer ab 1.20.1
   ausführt oder über Punkt 2 aktualisiert wird. Das Update 1.20.0 → 1.20.1 läuft noch mit dem Update-Code von
   1.20.0, Punkt 2 wirkt also erst bei Updates, die eine Version ab 1.20.1 ausführt.
4. **Nachweis vor dem Release:** Installer-QA-Modus `InApp` (Branch `qa/1.20.0-rc2`, `.github/qa/installer_test.ps1`)
   auf Windows Server 2022 und 2025, erweitert um
   - eine eigene Datei in `_internal` (muss bleiben),
   - eine veränderte ausgelieferte Datei (muss bleiben) und
   - die Erwartung „keine weiteren Rückstände“.

**Behebung (1.20.1, umgesetzt, noch nicht veröffentlicht):** Branch `fix/1.20.1-uninstall-update`.

- Punkt 1 und 2 wie geplant umgesetzt:
  - `packaging/uninstall_cleanup.ps1` arbeitet nach Inventar und SHA-256. Pfade außerhalb des Programmordners,
    Verknüpfungen, Junctions und ein unlesbares Inventar führen dazu, dass nichts gelöscht wird.
  - Der Installer ruft das Skript bei der Deinstallation auf und nach einem Update im Modus „veraltet“: nur
    unveränderte Dateien, die die neue Version nicht mehr ausliefert. Das Skript läuft aus einer temporären Kopie,
    weil es selbst im Inventar steht.
  - Das In-App-Update einer Installer-Installation führt den geprüften Installer aus, mit Sicherung und
    Zurücksetzen.
  - `DisplayVersion` in „Apps & Features“ wird vom Updater und beim Programmstart nachgeführt.
- Unit-Tests: `tests/test_uninstall_inventory.py`. Sie decken unter anderem ab:
  - veränderte ausgelieferte Dateien bleiben;
  - Pfade außerhalb des Programmordners werden nie entfernt;
  - Junctions und symbolische Links werden nicht verfolgt;
  - ein falscher SHA-256 und ein fehlgeschlagener Installer setzen zurück.
- Installer-QA auf frischen Runnern Windows Server 2022 und 2025 (Branch `qa/1.20.1-a5`, Kandidat als QA-Version
  1.20.1 und Folgeversion 1.20.2 gebaut, nichts veröffentlicht). Alle Jobs grün:

  | Modus | Ablauf | Ergebnis je System |
  |---|---|---|
  | Fresh | Installation, Benutzerdatei, Deinstallation, zweiter Durchgang | 78/78 ([Lauf 43061015894](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/runs/43061015894)) |
  | Update | Installer v1.19.1 → Installer Kandidat | 51/51, keine veralteten Dateien, nach Deinstallation bleibt genau die Benutzerdatei |
  | InApp | v1.20.0 aktualisiert sich mit seinem eigenen Updater | 60/60. Die gemessene Grenze: Der alte Deinstaller lässt genau die neuen Dateien zurück |
  | Repair | wie InApp, danach Installer des Kandidaten, Deinstallation | 24/24, bleibt nur die Benutzerdatei |
  | Chain | v1.19.1 → Kandidat → 1.20.2 über die Oberfläche (Installer-Weg) | 68/68, `DisplayVersion` 1.20.2, Deinstallation lässt nur die Benutzerdatei |
  | Heal | v1.20.0 → Kandidat mit dem Updater von 1.20.0 (ZIP-Weg), danach Kandidat → 1.20.2 (Installer-Weg) | 22/22 ([Lauf 43062362942](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/runs/43062362942)), keine Rückstände, bleibt nur die Benutzerdatei |
  | Rollback | falscher SHA-256, falsche erwartete Version, Installer-Update, Wiederherstellen | 37/37, Ordner nach Fehlern bytegleich, `DisplayVersion` zurückgesetzt |

  Lauf 43062362942 wiederholt alle Modi zusätzlich mit Heal: 14 von 14 Jobs grün.
- Nicht auf den Runnern geprüft, nur in Unit-Tests: eine veränderte ausgelieferte Datei bei der echten Deinstallation.
- Grenze wie in Punkt 3: Alte Installationen erhalten den neuen Deinstaller erst mit einem Installer-Lauf ab 1.20.1
  oder dem ersten Update, das 1.20.1 selbst ausführt. Bis dahin hilft das manuelle Löschen des Programmordners.

### A7. Prüfung der veröffentlichten Dateien (11.11.2026)

Die SHA-256-Werte des Release-Kandidaten gelten nicht für das Release. Alle Werte hier stammen aus den
veröffentlichten Dateien.

| Prüfung | Ergebnis |
|---|---|
| [x] Release-Workflow | [Lauf 43048590191](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/runs/43048590191) erfolgreich. Build mit 987 bestandenen und 20 übersprungenen Tests. Prüfung auf zurückgezogene Lerndaten (ZIP und Installer): „sauber“. Update von v1.19.1 auf windows-2022 und windows-2025 bestanden, ebenso Oberflächentest, Wiederherstellen und Installer-Installation mit Deinstallation |
| [x] GitHub-Release | öffentlich, kein Entwurf, keine Vorabversion, „Latest“. Titel „ECU Studio AI v1.20.0“. Release-Text auf Deutsch und Englisch |
| [x] `ECU-Studio-AI-1.20.0-windows-x64.zip` | SHA-256 `69cd922f211545c25f246c94bec5a472e41ac316b69ef0b96cba1e12ad5ec23b`. Stimmt mit der `.sha256`-Datei und dem GitHub-Digest überein (unabhängiger Download über die öffentlichen Links) |
| [x] `ECU-Studio-AI-1.20.0-setup.exe` | SHA-256 `05a1751dfc9945f2555e8f227a8e004e9e9d0835917ae2a6b8ae181c65ab6ca8`. Stimmt mit der `.sha256`-Datei und dem GitHub-Digest überein |
| [x] Build-Herkunft | `gh attestation verify` für ZIP und Installer gültig. Workflow `release.yml@refs/tags/v1.20.0`, Quell-Commit `5dedb774…`, Lauf 43048590191 |
| [x] Version | `VERSION.txt` 1.20.0. EXE-Dateiversion 1.20.0.0, Produktversion 1.20.0. Installer-Version 1.20.0 |
| [x] Inhalt | Inventar: 1313 Einträge, 0 Abweichungen. 0 Treffer gegen die privaten Referenz-Hashes. Nur öffentliche XDF-Definitionen. Programmcode identisch mit dem geprüften Release-Kandidaten (214 Dateien). Gegenüber 1.19.1 ist genau eine Datei neu (`integrity.py`) |
| [x] Signaturen | keine Authenticode-Signatur (bekannt). Kein Update-Signaturschlüssel eingerichtet, daher keine `.sig`-Dateien (wie bei 1.19.1) |
| [x] Update-Erkennung 1.19.1 | Der Update-Code von 1.19.1 erkennt gegen die echte GitHub-API 1.20.0 als verfügbar. Er lädt das ZIP und prüft es (SHA-256 wie oben) |
| [x] Installer-QA mit den veröffentlichten Dateien | [Lauf 43050701572](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/runs/43050701572), Branch `qa/1.20.0-release`, gleiche SHA-256. Ergebnisse auf Server 2022 und 2025: Fresh 72/72, Update 45/45, InApp 46/47. Einzige Abweichung: A5, genau `_internal\app\ecu_studio\core\integrity.py` |

### A6. GitHub

| Prüfung | Ergebnis |
|---|---|
| [x] PR #19, #20, #21 | gemergt; vor jedem Merge: offen, mergebar, CI grün, keine neuen Commits, keine offenen Review-Kommentare, Firmware-Guard OK |
| [x] PR #22 (Release-Vorbereitung) | am 11.11.2026 nach erneuter Prüfung gemergt (`5dedb77`): offen, mergebar, CI grün, keine Reviews oder Kommentare, nur geprüfte Commits von PCTestAdmin, Firmware-Guard OK |
| [x] CI auf `main` nach dem Merge | Tests 43047459244, CodeQL 43047459931: erfolgreich |

## B. Freigabe und Veröffentlichung

1. [x] Merge von PR #21, #20 und #19 nach `main` (A1).
2. [x] CI auf `main` grün.
3. [x] Version 1.20.0 (`pyproject.toml`, `src/ecu_studio/__init__.py`): im Release-Vorbereitungs-PR.
4. [x] `CHANGELOG.md`: Abschnitt `## 1.20.0 (11.11.2026)` (Datum am Veröffentlichungstag angepasst);
   `tools/release_notes.py v1.20.0` prüft ihn.
5. [x] **Freigabe:** PR #22 nach `main` gemergt (11.11.2026, `5dedb77`).
6. [x] `ROADMAP.md` und Roadmap-Grafiken: 1.20.0 als veröffentlicht eingetragen (nach der Veröffentlichung).
7. [x] **Freigabe für Tag und Release:** [Lauf 43048590191](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/runs/43048590191) erfolgreich (build, update-test
   windows-2022 und windows-2025, publish). `git tag v1.20.0` und `git push origin v1.20.0`. Der Workflow `release.yml`
   baut, testet und prüft das Update von 1.19.1 auf Windows Server 2022 und 2025. Erst danach veröffentlicht er.
8. [x] Nach der Veröffentlichung (A7):
   - Download-Hashes gegen die `.sha256`-Dateien geprüft; `gh attestation verify` ausgeführt.
   - Titel „ECU Studio AI v1.20.0“. Englischer Teil aus [RELEASE_NOTES_1.20.0.md](RELEASE_NOTES_1.20.0.md) und
     absolute Links im Release-Text ergänzt.
9. [x] Branches aufgeräumt.
   - Gelöscht sind die Branches der gemergten PRs #14 bis #22. Der Head jedes Branches ist per Commit-Abstammung
     in `main` enthalten.
   - `qa/1.20.0-rc` (letzter Commit `fca95a8`) ist gelöscht. Er ist vollständig ersetzt: Der Produktcode ist in
     `main`, die QA-Werkzeuge liegen in neuerer Form in `qa/1.20.0-rc2`.
   - `qa/1.20.0-release` (`f63ac99`, nur für A7) ist nach der Dokumentation gelöscht.
   - **`qa/1.20.0-rc2` (`507aea3`) bleibt.** Der Installer-QA-Workflow mit dem Modus `InApp` liegt nur dort und
     wird für den Nachweis des A5-Fixes in 1.20.1 gebraucht.

## C. Was ausdrücklich nicht im Release-Text stehen darf

- dass alle ECU-Checksummen automatisch korrigiert werden;
- dass ME7, ME9, EDC16 oder EDC17 vollständig unterstützt seien;
- dass Dateien nach der Korrektur flashbereit seien;
- dass digitale Herstellersignaturen verifiziert würden;
- dass eine Flashfreigabe vorliege.
