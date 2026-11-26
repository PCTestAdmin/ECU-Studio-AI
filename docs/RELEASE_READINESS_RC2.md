# Release-Bereitschaft 1.21.0-rc2 (Entscheidungsvorlage)

Stand: 26.11.2026, nach dem rc2-Release-Fix (Zellbreite gespeicherter Achsen, Commit `edd926c`; vorher
Qualitätsphase 6, 25.11.2026). Grundlage: Draft-PR #30 (Zweig `feat/post-rc1-recognition-nextgen`),
[Entwicklungsbericht § 11–12](ENTWICKLUNG_NEXTGEN.md), [Schreibsicherheit](EDIT_SAFETY_REVIEW.md),
[Release-Notes-Entwurf](RELEASE_NOTES_1.21.0-rc2.md).

**Nichts davon ist veröffentlicht.** Kein Merge, kein Tag, kein Release, keine Änderung des Update-Kanals ohne
ausdrückliche Freigabe. Diese Seite sammelt, was für eine Entscheidung über eine öffentliche, experimentelle
Vorabversion 1.21.0-rc2 bekannt ist, und was nicht.

## 1. Versionsplan

| Schritt | Inhalt | Status |
|---|---|---|
| PR #30 bleibt Draft | Quellstand nach QP2–QP6 und dem rc2-Release-Fix; Version im Zweig weiter `1.21.0-rc1` | ✅ |
| Release-Commit (später, nur mit Freigabe) | `__version__` und `pyproject.toml` → `1.21.0-rc2` (PEP 440 `1.21.0rc2`, Windows-Dateiversion `1.21.0.2`); CHANGELOG-Überschrift `## 1.21.0-rc2 (<Datum>) – Release Candidate (experimentelle Vorabversion)`; Kopf der Release Notes mit Datum | 📋 vorbereitet, nicht ausgeführt |
| Probelauf `release-dry-run/1.21.0-rc2-fix` | baut, testet und paketiert alles für die Version im Quellstand **außer** Veröffentlichen (kein Tag, kein Release, keine Attestierung); Job `publish-plan` zeigt nur, was ein Tag veröffentlichen würde | siehe § 5 |
| Installer-QA `qa/1.21.0-rc2-fix` | frische GitHub-Windows-Runner (Server 2022/2025): Neuinstallation, Update von 1.20.1, Update von 1.20.0 (alter Updater), **Update von veröffentlichter 1.21.0-rc1 über deren Testkanal**, Kette rc2 → rc3, Reparatur, Rücksicherung, gesperrte Ordner, Deinstallation; Testversionen nur auf dem Runner | siehe § 5 |
| Tag `v1.21.0-rc2` | nur mit ausdrücklicher Freigabe; der Release-Workflow veröffentlicht einen RC nur als GitHub-Pre-Release, nie „Latest“, und prüft danach, dass kein anderes Release verändert wurde | ⛔ nicht freigegeben |
| Stabile 1.21.0 | nicht Gegenstand dieser Vorlage | ⛔ nicht freigegeben |

Der stabile Update-Kanal bietet nie eine Vorabversion an (seit 1.21.0-rc1, getestet im Modus NoOffer). Nutzer von
1.21.0-rc1 mit eingeschaltetem Testkanal bekämen rc2 nach einer Veröffentlichung angeboten; Nutzer von 1.20.1 nicht.

## 2. Signaturstatus (tatsächlich)

| Prüfung | Befund |
|---|---|
| Update-Signatur (Ed25519, `core/signing.py`) | **nicht aktiv**: Das Programm liefert keinen öffentlichen Schlüssel (`recognition/data/update_signing_key.pub` fehlt); `tools/sign_release.py` erzeugt dann keine `.sig`-Dateien. Die Assets von 1.21.0-rc1 sind Setup, ZIP und je eine `.sha256`-Datei, keine `.sig`. |
| Authenticode (Code-Signatur der EXE und des Setups) | **nicht vorhanden**: Der Build enthält keinen Signierschritt; Windows kann beim ersten Start warnen. |
| Prüfsummen | SHA-256 je Paket; der Updater prüft sie vor der Installation. Eine Prüfsumme ist **keine Signatur**: Sie erkennt beschädigte Downloads, belegt aber nicht, wer das Paket erstellt hat. |
| Build-Herkunft | GitHub-Attestierung, nur beim Tag-Release (`gh attestation verify`); im Probelauf nicht erzeugt. Belegt, aus welchem Workflow-Lauf ein Paket stammt; **keine** Authenticode- und **keine** Update-Signatur. |
| Schlüssel | keine erzeugt, keine im Repository, keine in Secrets hinterlegt (nur mit ausdrücklicher Freigabe). |

Die Release Notes sagen deshalb „**nicht signiert** (weder Authenticode noch Update-Signatur)“. Eine Signatur
einzuführen ist ein eigenes Vorhaben (Schlüssel bzw. Zertifikat, [Anleitung](RELEASE.md)), nicht Teil von rc2.

## 3. Code-Review PR #30 (nach QP6)

Umfang: 12 Commits gegen `main` (QP1–QP6 und rc2-Release-Fix), 86 Dateien, rund 11 500 hinzugefügte Zeilen in Code, Tests und Dokumentation. Geprüft: Schreibwege,
Datenschutz, Nebenläufigkeit, Update-Kanal und Netzwerk, Laufzeit, Dokumentation gegen Code.

### Kritisch

Keine offenen.

### Hoch

| # | Befund | Stand |
|---|---|---|
| H1 | **Kosten der neuen Schreibprüfung**: je Zellbearbeitung wurden alle Achsobjekte neu gebaut; Kopienliste und „Achse im Wertebereich“ waren quadratisch. Synthetisch 613 ms je Zelle bei 3 000 Kennfeldern; bei echten MEVD17.2-Definitionen (rund 20 000 Kennfelder) spürbare Verzögerung je Eingabe. | **behoben** (QP6): Kopienliste begrenzt, nur Nutzer der Achse geprüft, nur Achsen nahe dem Schreibbereich gebaut, billige Vorprüfung vor der exakten Länge. Gleichheit mit der vollständigen Prüfung per Brute-Force-Test. Messwerte § 4. |
| H2 | **Keine unabhängige Validierung.** Alle Gütezahlen stammen aus Referenzdaten eines Datengebers (TriCore: MEVD17.2, MSD80; Holdout seit der ersten Messung nur Regression). | offen, **nicht behebbar ohne neue Daten**; in Notes und Bericht offen benannt. Kein Blocker für eine ausdrücklich experimentelle Vorabversion, aber Blocker für jede Gütebehauptung und für 1.21.0 stabil. |

### Mittel

| # | Befund | Einordnung |
|---|---|---|
| M1 | Die Schreibprüfung nahm **2 Byte je Achsstützstelle** an (`AXIS_POINT_BYTES`), weil Kennfelder den Zelltyp ihrer Achsen nicht trugen. Bei 32-Bit-/Float-Achsen war die obere Hälfte ungeschützt; bei 8-Bit-Achsen war der Bereich zu groß (bis in die eigenen Werte); die Kopiensuche verglich 2 Byte je Punkt. | **behoben** (rc2-Release-Fix, `edd926c`): Achstyp als eigenes Merkmal je Kennfeld aus A2L, XDF und Erkennern; unbekannte Breite mit 4 Byte je Punkt geschützt; Widersprüche angezeigt, gemeinsame Achse dann abgelehnt; Klärung an die Breite gebunden. 39 synthetische Tests, Brute-Force-Gleichheit, Erkennung byte-identisch, Kosten unverändert ([EDIT_SAFETY_REVIEW § 4a](EDIT_SAFETY_REVIEW.md), [Entwicklungsbericht § 12](ENTWICKLUNG_NEXTGEN.md)). |
| M2 | **Rückgängig/Wiederholen und das Laden eines Projekts** umgehen die Schreibprüfung bewusst (sie stellen frühere Bytes wieder her). | gewollt, dokumentiert ([EDIT_SAFETY_REVIEW](EDIT_SAFETY_REVIEW.md)). |
| M3 | **Ablehnung bei unbekannter Achsidentität sperrt auch richtige gemeinsame Achsen** (Entwicklungsdaten: 861 richtige stehen auf „unbekannt“). | gewollt (Entscheidung 3/4); Freigabe nur über technische Klärung mit allen Angaben. |
| M4 | **Gemeinsame Achsen bei MEVD17.2**: 0 von 1 466 gefunden; Ursache: die Nutzertabellen werden nicht erkannt (9 433 nicht gefunden), nicht die Verknüpfung. | offen; in Notes als Einschränkung. |
| M5 | **Unmarkiert falsche Datentypen**: 48 Vorzeichen (MSD80-Achsen) und 41 Breiten (Entwicklungsdaten) bleiben ohne „?“; die Werte trennen die Lesarten nicht (Klassen mit Tausenden richtiger Fälle gleicher Form). | offen; keine Regel ohne Fehlmarkierung möglich; in Notes als Einschränkung. |

### Niedrig

| # | Befund | Einordnung |
|---|---|---|
| N1 | Tester-Assistent: Abbruch ist kooperativ; das Schließen wartet auf den nächsten Prüfpunkt der Analyse. | getestet (Abbruch, Schließen während der Analyse). |
| N2 | `run_provenance` ruft `git` auf; im installierten Programm ohne Git bleibt der Commit leer. | nur für Entwickler-Benchmarks; kein Programmpfad. |
| N3 | Die Breitenregel „Doppellücke“ und die Mindestpunktzahl verwaister Achsen stammen aus Holdout-Befunden; an den Entwicklungsdaten wirkungslos. | als holdout-abgeleitet dokumentiert; Gegenbeispieltests synthetisch. |
| N4 | Tester-Assistent: Kam das Analyseergebnis an, während der Hintergrund-Thread noch endete, blieb das Fenster auf der Analyseseite (Seitenwechsel während des Laufs gesperrt); „Weiter“ funktionierte danach. Gefunden im rc2-Probelauf (ein Testfehler unter Python 3.12). | **behoben** (`1713b31`): Der Lauf gilt bis zur Behandlung des Thread-Endes im Fenster; die Ergebnisseite öffnet von dort. Deterministischer Test. Keine Auswirkung auf Messwerte oder Export. |

### Ohne Befund geprüft

- **Netzwerk und Update-Kanal:** PR #30 ändert weder `core/updates.py` noch Netzwerkcode; neue Module
  (`tester_core`, `tester_assistant`, `run_provenance`) enthalten keinen Netzwerkzugriff.
- **Datenschutz:** Der Tester-Export enthält nur Zählwerte (gerundet ab 100), wird nur nach Vorschau, Häkchen und
  Dateiwahl geschrieben, überschreibt nie und wird vor dem Schreiben gegen ein festes Schema geprüft. Keine
  privaten Pfade, Hashes, Adressen oder Firmwaredaten im Repository (Firmware-Guard, Prüfung des Diffs).
- **Schreibwege:** Jeder Schreibweg der Oberfläche (Zelle, Hex, Fläche, Stapel, Rezept, Übertragung,
  Wiederherstellung, Checksummenkorrektur) trägt eine Freigabe; `BinaryImage.commit` prüft unmittelbar vor dem
  Schreiben erneut ([Tabelle](EDIT_SAFETY_REVIEW.md)).
- **Benchmarks:** gewertete Läufe nur von einem sauberen Commit mit geprüftem Importpfad; Herkunft im Ergebnis.

## 4. Tests und Messungen

Einzelheiten mit Datensatz und Validierungsstatus: [Entwicklungsbericht § 11–12](ENTWICKLUNG_NEXTGEN.md). Alle
gewerteten Läufe vom sauberen Commit mit Vorprüfung; Quellbaum während jedes Laufs unverändert. Die Zeilen unten
sind **am 26.11.2026 nach dem Release-Fix neu gemessen** (Commit `edd926c`), nicht aus QP6 übernommen. Der
spätere Commit `1713b31` ändert nur `ui/tester_assistant.py` (N4), keinen Erkennungs- oder Schreibcode; Tests,
GUI-Smoke und i18n wurden danach wiederholt.

| Prüfung | Ergebnis |
|---|---|
| pytest vollständig, isoliertes Profil (`1713b31`) | 1 553 bestanden, 22 übersprungen, 0 Fehler (QP6: 1 513; neu 39 Tests der Achszellbreite und 1 Test des Tester-Assistenten, § 5.1) |
| Übersprungen (22), jeweils begründet | private Referenzdaten nicht eingebunden (Tests, die nur lokal mit Datengeber-Dateien laufen), Oberflächen-Zeitmessung und Paketprüfung nur mit `ECU_STUDIO_GUI_TESTS` bzw. gebautem Paket, symbolische Links ohne Windows-Recht, Registry-Tests nur auf CI-Runnern |
| GUI-Smoke, dreimal | je 10 Prüfungen bestanden, keine Fehlerausgabe |
| i18n | 2 592 Texte, 0 ohne Übersetzung (25 neue) |
| Firmware-Guard (Arbeitsbaum) | OK |
| Entwicklungsdaten (58 Abbilder) | alle 58 Ergebnisdateien **byte-identisch** mit QP6 (`52a4f83`): 2D exakt 35 276, Verwechslungen 4 117; 1D exakt MEVD17.2 50 829, MSD80 75 008 |
| Holdout (105 Abbilder, nur Regression) | alle 105 Ergebnisdateien byte-identisch mit QP6 (`5c9e262`): 2D exakt 56 688; 1D je Linie unverändert |
| Regressionsgruppe (15) / Negativbestand (7) | 15 von 15 unverändert / 549 Funde, 0 sicher falsch, gleich QP6 |
| Funktionsidentifikation (Prototyp), beide Konfigurationen | Ergebnisdateien byte-identisch mit QP6 |
| Herkunft aller gewerteten Läufe | Commit `edd926c`, Quellbaum unverändert (`source_changed: false`) |
| Laufzeit und Speicher der Erkennung | unverändert (gleiche Läufe, gleiche Ergebnisse; Laufzeiten im üblichen Rauschen) |
| Schreibprüfung je Zelle, MEVD17.2 (3 Definitionen, rund 19 500–20 900 Kennfelder, je 20 Stichproben) | Median 60–74 ms; unmittelbar davor derselbe Messlauf mit dem Stand vor dem Fix (`c51fe2b`): 57–72 ms. Kein messbarer Unterschied. Gemeldete Konflikte beim Schreiben 2/2/5 → 0 (Fehlmeldungen der 2-Byte-Annahme bei 8-Bit-Achsen, § 4a der Schreibsicherheit) |
| Registry, produktive Installation, Tags, Releases | unverändert (nur gelesen; Registry byte-identisch mit der Sicherung vom Beginn) |

## 5. Isolierter Testbuild und Installer-QA

Lokal wird nichts installiert. Testbuild und Installer-Prüfungen laufen auf frischen GitHub-Windows-Runnern in
Zweigen, die nie gemergt, getaggt oder veröffentlicht werden. Für den Stand **nach dem Release-Fix** wurden beide
Läufe neu gestartet, auf neuen Zweigen (die Zweige vom 25.11. bleiben unverändert stehen). Jeder Zweig liegt auf
dem Stand von PR #30; der Probelauf trägt zusätzlich nur die Release-Einträge (Version, CHANGELOG-Überschrift, Kopf
der Notes), die QA nur ihre Testskripte unter `.github/`.

### 5.1 Läufe nach dem Release-Fix (26.11.2026)

**Erste Runde** (`release-dry-run/1.21.0-rc2-fix`, `qa/1.21.0-rc2-fix`, Stand `1965d55`): Release-Workflow
erfolgreich, Installer-QA 20 von 20 Läufen (1 160 Prüfungen, 0 fehlgeschlagen) – aber der Test-Workflow des
Probelaufzweigs schlug unter Python 3.12 mit **einem Fehler** fehl (`test_analysis_runs_in_background_and_matches_the_command_line`,
1 551 bestanden). Ursache war ein echter Wettlauf im Tester-Assistenten (Befund N4, § 3): Das Ergebnis der Analyse
kam im Fenster an, während der Hintergrund-Thread noch endete; der Seitenwechsel wurde abgelehnt, die Ergebnisseite
öffnete nicht von selbst. Behoben in `1713b31` mit einem Test, der diese Reihenfolge erzwingt (vorher rot, nachher
grün). Weil sich damit das ausgelieferte Programm ändert, wurden Probelauf und QA vollständig wiederholt:

**Zweite Runde** (`release-dry-run/1.21.0-rc2-fix2` → `f51cc19`, `qa/1.21.0-rc2-fix2` → `ce2fd94`, Stand `1713b31`):

| Lauf (26.11.2026) | Ergebnis |
|---|---|
| Versionen | Tag-Prüfung: `v1.21.0-rc2`, Kanal `prerelease`, Version `1.21.0-rc2`, Windows-Dateiversion `1.21.0.2`, PEP 440 `1.21.0rc2`; Version jeder gebauten Datei gleich dem Tag |
| Release-Wächter (Negativtest) | alle Negativfälle abgelehnt, RC nur als Pre-Release, stabiler Kanal ohne RC |
| Release-Notes-Prüfung | „ECU Studio AI v1.21.0-rc2 (Vorabversion / Pre-release)“, 164 Zeilen DE + EN, Kanal `prerelease` |
| Build mit Tests auf dem Runner (Python 3.13) | 1 555 bestanden, 20 übersprungen; EXE-Smoke-Test, Start ohne Python im Pfad |
| Pakete | `ECU-Studio-AI-1.21.0-rc2-setup.exe` und `…-windows-x64.zip` je mit `.sha256`; Prüfsummen nachgerechnet: stimmen. Keine `.sig`, keine Attestierung (Probelauf) |
| Signatur | „Kein Signaturschlüssel konfiguriert – Dateien bleiben unsigniert“ (wie § 2) |
| Update-Test Windows Server 2022 / 2025 | bestanden (Installer über das letzte Release, Apps & Features, Deinstallation lässt nur Benutzerdateien) |
| `publish-plan` (liest nur die Release-Liste) | „v1.21.0-rc2 würde mit `--prerelease --latest=false` veröffentlicht (Latest vorher: v1.20.1)“ |
| `publish` | **übersprungen** (kein Tag) |
| Installer-QA, 10 Modi × Windows Server 2022/2025 | **20 von 20 Läufen, 1 160 Einzelprüfungen, 0 fehlgeschlagen**: Neuinstallation (96), Update von 1.20.1 (55), kein Angebot im stabilen Kanal – NoOffer (80), Reparatur über 1.20.0 (30), Kette rc2 → rc3 (80), Heilung nach altem Updater (26), Rücksicherung (42), gesperrte Ordner (52), vorhandene Installation (49), Update der veröffentlichten rc1 über deren Testkanal – FromRc1 (70) |
| Tests 3.11 / 3.12 auf PR #30 (`1713b31`), Probelauf- und QA-Zweig | grün, je 1 553 bestanden, 22 übersprungen |
| CodeQL auf PR #30 (`1713b31`) | grün |
| `release.yml` | unverändert seit `v1.21.0-rc1`; `.github/` im PR unverändert gegenüber `main` |
| Tags und Releases danach | unverändert: kein `v1.21.0-rc2`, Latest weiter v1.20.1, rc1 weiter Pre-Release |

### 5.2 Läufe vor dem Release-Fix (25.11.2026, Stand QP6, nur zum Vergleich)

| Lauf (25.11.2026) | Ergebnis |
|---|---|
| Release-Workflow, Probelauf | **erfolgreich**: Build mit Tests auf dem Runner (1 515 bestanden, 20 übersprungen), Release-Notes-Prüfung (Kanal `prerelease`), Paket `ECU-Studio-AI-1.21.0-rc2-setup.exe` und `…-windows-x64.zip` mit SHA-256, Update-Test auf Windows Server 2022 und 2025; Job `publish-plan`: „würde mit `--prerelease --latest=false` veröffentlicht (Latest vorher: v1.20.1)“; Job `publish` **übersprungen** |
| Signatur im Probelauf | Build meldet „Kein Signaturschlüssel konfiguriert – Dateien bleiben unsigniert“; keine `.sig`, kein Authenticode (wie § 2) |
| Installer-QA, 10 Modi × Windows Server 2022/2025 | **20 von 20 Läufen bestanden, 1 160 Einzelprüfungen, 0 fehlgeschlagen**: Neuinstallation (96), Update von 1.20.1 (55), kein Angebot einer Vorabversion im stabilen Kanal (80), Reparatur über 1.20.0 (30), Kette rc2 → rc3 über den Testkanal (80), Heilung nach Update durch den alten Updater (26), Rücksicherung (42), gesperrte Ordner (52), vorhandene Installation (49), **neu: Update der veröffentlichten 1.21.0-rc1 über deren Testkanal** (70: Download der rc1 geprüft, Testkanal im Menü eingeschaltet, Rückfrage nennt Risiken, Update über den geprüften Installer, kein ZIP, Sicherung = rc1, Projekt, BIN und private Datei des Benutzers unverändert, Deinstallation lässt Benutzerdaten stehen) |
| Tests (Python 3.11/3.12) und CodeQL auf PR #30, Probelauf- und QA-Zweig | grün |
| Tags und Releases danach | unverändert: kein `v1.21.0-rc2`, Latest weiter v1.20.1, rc1 weiter Pre-Release |

Die Testpakete bleiben Artefakte der Läufe (Aufbewahrungsfrist von GitHub); sie werden nicht veröffentlicht.

## 6. Antwort und Blocker

**Technisch:** bereit für eine öffentliche, ausdrücklich experimentelle Vorabversion. Der Schreibsicherheitsbefund
M1 ist behoben und synthetisch vollständig getestet; die Erkennung ist byte-identisch mit QP6; die Kosten der
Schreibprüfung sind unverändert. Der im Probelauf gefundene Fehler des Tester-Assistenten (N4) ist behoben, danach
wurden Probelauf und Installer-QA vollständig wiederholt: alles grün, Veröffentlichung nur als Pre-Release geplant,
Latest unberührt (§ 5.1).

**Fachlich:** nur mit den in den Notes genannten Einschränkungen. Alle Gütezahlen stammen aus den Daten eines
Datengebers (zwei TriCore-Linien), der Holdout ist bekannt; zwei Regeln sind holdout-abgeleitet; 41 Breiten- und
48 Vorzeichenfehler bleiben unmarkiert; gemeinsame Achsen bei MEVD17.2 werden nicht gefunden. Eine rc2 darf deshalb
keine Gütezahl als allgemeine Erkennungsleistung ausgeben (die Notes tun das nicht).

| Einordnung | Punkte |
|---|---|
| **Technisch blockierend für rc2** | keine. Einzige offene Voraussetzung ist die ausdrückliche Freigabe (Merge, Tag, Veröffentlichung). |
| **Akzeptierte Einschränkung für rc2** (in den Notes genannt) | keine unabhängige Validierung (H2); Daten eines Datengebers, Holdout bekannt; zwei holdout-abgeleitete Regeln; 41 Breiten- und 48 Vorzeichenfehler unmarkiert (M5); gemeinsame Achsen MEVD17.2 nicht gefunden (M4); unbekannte Identität sperrt auch richtige gemeinsame Achsen (M3); Achsen ohne Typangabe mit 4 Byte je Punkt geschützt (mögliche zusätzliche Rückfragen); nicht signiert (weder Authenticode noch Update-Signatur) |
| **Für 1.21.0 stabil erforderlich** | Rückmeldungen zu rc2 ausgewertet; belegte Blocker behoben; Schreibsicherheit und Installations-/Update-Wege erneut geprüft; unabhängige Validierung im Umfang der standardmäßig eingeschalteten Funktionen (sonst bleiben sie experimentell oder ausgeschaltet); Code-Signatur empfohlen; ausdrückliche Freigabe |
| **Für 1.22.0 geplant** | siehe [ROADMAP](../ROADMAP.md) „1.22.0 und später“: unabhängige Validierung, MEVD17.2.3/MSV90, weitere Familien, Checksummen, gemeinsame Achsen MEVD17.2, Signaturstrategie |
| Erledigt in dieser Runde | M1 Achszellbreite (`edd926c`), N4 Tester-Assistent (`1713b31`) |

Ohne Freigabe geschieht nichts davon: kein Merge, kein Tag, keine Veröffentlichung, keine Änderung des Update-Kanals.
