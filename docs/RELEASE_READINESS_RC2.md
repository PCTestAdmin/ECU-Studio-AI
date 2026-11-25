# Release-Bereitschaft 1.21.0-rc2 (Entscheidungsvorlage)

Stand: 25.11.2026, nach Qualitätsphase 6. Grundlage: Draft-PR #30 (Zweig `feat/post-rc1-recognition-nextgen`),
[Entwicklungsbericht § 11](ENTWICKLUNG_NEXTGEN.md), [Schreibsicherheit](EDIT_SAFETY_REVIEW.md),
[Release-Notes-Entwurf](RELEASE_NOTES_1.21.0-rc2.md).

**Nichts davon ist veröffentlicht.** Kein Merge, kein Tag, kein Release, keine Änderung des Update-Kanals ohne
ausdrückliche Freigabe. Diese Seite sammelt, was für eine Entscheidung über eine öffentliche, experimentelle
Vorabversion 1.21.0-rc2 bekannt ist, und was nicht.

## 1. Versionsplan

| Schritt | Inhalt | Status |
|---|---|---|
| PR #30 bleibt Draft | Quellstand nach QP2–QP6; Version im Zweig weiter `1.21.0-rc1` | ✅ |
| Release-Commit (später, nur mit Freigabe) | `__version__` und `pyproject.toml` → `1.21.0-rc2` (PEP 440 `1.21.0rc2`, Windows-Dateiversion `1.21.0.2`); CHANGELOG-Überschrift `## 1.21.0-rc2 (<Datum>) – Release Candidate (Vorabversion)`; Kopf der Release Notes mit Datum | 📋 vorbereitet, nicht ausgeführt |
| Probelauf `release-dry-run/1.21.0-rc2` | baut, testet und paketiert alles für die Version im Quellstand **außer** Veröffentlichen (kein Tag, kein Release, keine Attestierung); Job `publish-plan` zeigt nur, was ein Tag veröffentlichen würde | siehe § 5 |
| Installer-QA `qa/1.21.0-rc2` | frische GitHub-Windows-Runner (Server 2022/2025): Neuinstallation, Update von 1.20.1, Update von 1.20.0 (alter Updater), **Update von veröffentlichter 1.21.0-rc1 über deren Testkanal**, Kette rc2 → rc3, Reparatur, Rücksicherung, gesperrte Ordner, Deinstallation; Testversionen nur auf dem Runner | siehe § 5 |
| Tag `v1.21.0-rc2` | nur mit ausdrücklicher Freigabe; der Release-Workflow veröffentlicht einen RC nur als GitHub-Pre-Release, nie „Latest“, und prüft danach, dass kein anderes Release verändert wurde | ⛔ nicht freigegeben |
| Stabile 1.21.0 | nicht Gegenstand dieser Vorlage | ⛔ nicht freigegeben |

Der stabile Update-Kanal bietet nie eine Vorabversion an (seit 1.21.0-rc1, getestet im Modus NoOffer). Nutzer von
1.21.0-rc1 mit eingeschaltetem Testkanal bekämen rc2 nach einer Veröffentlichung angeboten; Nutzer von 1.20.1 nicht.

## 2. Signaturstatus (tatsächlich)

| Prüfung | Befund |
|---|---|
| Update-Signatur (Ed25519, `core/signing.py`) | **nicht aktiv**: Das Programm liefert keinen öffentlichen Schlüssel (`recognition/data/update_signing_key.pub` fehlt); `tools/sign_release.py` erzeugt dann keine `.sig`-Dateien. Die Assets von 1.21.0-rc1 sind Setup, ZIP und je eine `.sha256`-Datei, keine `.sig`. |
| Authenticode (Code-Signatur der EXE und des Setups) | **nicht vorhanden**: Der Build enthält keinen Signierschritt; Windows kann beim ersten Start warnen. |
| Prüfsummen | SHA-256 je Paket; der Updater prüft sie vor der Installation. |
| Build-Herkunft | GitHub-Attestierung beim Tag-Release (`gh attestation verify`); keine Signatur im Sinne einer Code-Signatur. |

Die Release Notes sagen deshalb „**nicht signiert** (weder Authenticode noch Update-Signatur)“. Eine Signatur
einzuführen ist ein eigenes Vorhaben (Schlüssel bzw. Zertifikat, [Anleitung](RELEASE.md)), nicht Teil von rc2.

## 3. Code-Review PR #30 (nach QP6)

Umfang: 8 Commits gegen `main` (QP1–QP6), 75 Dateien, rund 10 000 hinzugefügte Zeilen in Code, Tests und Dokumentation. Geprüft: Schreibwege,
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
| M1 | Die Schreibprüfung nimmt **2 Byte je Achsstützstelle** an (`AXIS_POINT_BYTES`), weil Kennfelder den Zelltyp ihrer Achsen nicht tragen. Bei 32-Bit-/Float-Achsen (z. B. MG1/EDC17-Definitionen) wird ein Schreiben in die obere Hälfte der Achse nicht als Achskonflikt erkannt; bei 8-Bit-Achsen ist der Bereich zu groß (sichere Richtung). Ebenso vergleicht die Kopiensuche 2 Byte je Punkt. | keine Regression (rc1 prüfte gar nicht); gemessene Linien nutzen 16-Bit-Achsen. Empfehlung vor 1.21.0 stabil: Achszelltyp aus der Definition mitführen (`A2LLinkResult.axis_objects`). |
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

Einzelheiten mit Datensatz und Validierungsstatus: [Entwicklungsbericht § 11](ENTWICKLUNG_NEXTGEN.md). Alle
gewerteten Läufe vom sauberen Commit mit Vorprüfung; Quellbaum während jedes Laufs unverändert.

| Prüfung | Ergebnis |
|---|---|
| pytest vollständig, isoliertes Profil (`52a4f83`) | 1 513 bestanden, 22 übersprungen, 0 Fehler |
| GUI-Smoke, dreimal | je 10 Prüfungen bestanden, keine Fehlerausgabe |
| i18n | 2 568 Texte, 0 ohne Übersetzung |
| Entwicklungsdaten (58 Abbilder) | 2D exakt rc1 32 058 → neu 35 276, Verwechslungen 5 316 → 4 117; gegen QP5 unverändert; `52a4f83` byte-identisch mit `5c9e262` |
| Holdout (105 Abbilder, nur Regression) | 2D exakt rc1 52 701 → 56 688, gegen QP5 unverändert, 0 verloren; unmarkiert falsche Breiten B38I12 3 → 0 |
| Regressionsgruppe (15) / Negativbestand (7) | unverändert / 549 Funde, 0 sicher falsch |
| Laufzeit und Speicher der Erkennung | kein messbarer Unterschied zu rc1 und QP5 |
| Schreibprüfung je Zelle, MEVD17.2 (rund 20 000 Kennfelder) | Median 60–64 ms |
| Registry, produktive Installation, Tags, Releases | unverändert (nur gelesen) |

## 5. Isolierter Testbuild und Installer-QA

Lokal wird nichts installiert. Testbuild und Installer-Prüfungen laufen auf frischen GitHub-Windows-Runnern in zwei
Zweigen, die nie gemergt, getaggt oder veröffentlicht werden: `release-dry-run/1.21.0-rc2` (Release-Workflow ohne
Veröffentlichung) und `qa/1.21.0-rc2` (Installer-QA). Ergebnisse: Abschnitt wird nach den Läufen ergänzt.

## 6. Antwort und Blocker

Wird nach den Läufen aus § 5 ergänzt.
