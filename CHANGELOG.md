## Unveröffentlicht (18.10.2026)

- Neue rasterfreie Strukturerkennung (`core/structure_scan.py`): Spaltenzahl und Zeilenzahl werden aus der Datenwiederholung abgeleitet statt aus festen Rastern (8×8, 16×16 …); 8/16 Bit, Little/Big Endian, robuste Ausreißer-Prüfung.
- C16x-Code-Referenzen (Seite+Offset-Ladebefehle) als exakte Start-Hinweise; trennt lückenlos gepackte Kennfelder. Auf MS43 nachgewiesen, auf MS42 ohne Wirkung (andere Adressierung).
- Blind gemessen gegen XDF-Referenzen (`tools/structure_benchmark.py`, nur Geometrie): MS43 430069 Trefferquote 4,5 % → 47 %, exakte Layouts 1 → 88; MS42 0110C6 13 % → 56 %, exakt 5 → 24. Präzision MS43 71 % → 70 %, MS42 72 % → 58 %.
- Bekannte Grenzen: monotone Ebenen ohne Zeilenumbruch-Sprung (z. B. MAF-Raster) und doppelte Spaltenzahl bei gleich großen Nachbarzeilen; Laufzeit 4–8 s statt ~1 s. `structure_limit=0` stellt das bisherige Verhalten her.
- Weiterhin keine Funktionsnamen oder Einheiten aus Rohdaten; Kandidaten bleiben „Unbekannt“ und ungeprüft.
- Achsen-Erkennung (`core/axis_arrays.py`): Stützstellen-Arrays mit vorangestellter Anzahl (8-Bit-Anzahl + 8-Bit-Werte, 16-Bit-LE-Anzahl + 16-Bit-Werte), nur in Ketten benachbarter Arrays. Gegen XDF: MS43 98 % gefunden bei 97 % Präzision, MS42 98,5 % bei 97 %. Achsen erscheinen als 1×n-Kandidaten.
- Achsen-Zuordnung über den Code (MS43: Y-Achse, X-Achse, dann Kennfeld werden nacheinander geladen): Größe und Rohachswerte verankerter Kennfelder kommen aus den Achsen; Kennlinien (eine Achse) werden als 1×n erkannt. Code-Verweise nur noch aus direkt benachbarten Seite/Offset-Befehlen.
- Neuer Stand MS43 (2D ≥ 4×4): Trefferquote 47 % → 68 %, exakte Layouts 88 → 197, Präzision 70 % → 77 %; 1D (Achsen/Kennlinien) 615 exakt bei 96,5 % Präzision. MS42: 2D unverändert 56 %, Präzision 58 % → 70 %; 1D 398 exakt bei 97 %. Benchmark bewertet 2D und 1D getrennt.
- Kennfelder mit zwei vom Code geladenen Achsen passieren die Oberflächen-Glattheitsprüfung auch flach/grob (die Achsen belegen die Form).
- Dateien ohne bekanntes Profil (`core/data_regions.py`): Code/Daten-Trennung über den Anteil kleiner Nachbardifferenzen je Block (128/256 Byte). Kandidaten, die nur auf Glätte beruhen, müssen überwiegend in Datenblöcken liegen. Simuliert durch Scan der ganzen MS42/MS43-Datei ohne Kalibrierfenster: 2D-Präzision MS42 38 % → 61 %, MS43 69 % → 74 %, ohne Verlust an Trefferquote. Für Carrera/RS 235/ARAP/Clio gibt es keine Referenz; dort ungemessen.
- Unbekannte Dateien: Zeilenabstand-Suche nur noch in Datenbereichen (1-MB-ME7: 45 s → 17–25 s). Vorzeichen-Ansichten `s8`/`s16` (Bosch-ME7-Zündkennfelder). Bosch ME7 (Volvo, öffentliche XDFs) als dritte Referenzfamilie: Trefferquote 5–10 % → 48–66 %, exakte Layouts weiterhin selten (2–6) – nächste Baustelle.
- Bosch ME7: Lookup-Aufrufe (`MOV R12/R13` = Kennfeld, `MOV R14/R15` = Achsdaten mit Anzahl-Präfix) liefern Start, Spaltenzahl und X-Achse; die Zeilenzahl kommt aus der Folgeachse oder der Datenanpassung (glattere Lesart gewinnt). 103–123 Kennfelder je Datei werden so im Code gefunden. Gegen die (unvollständigen) XDFs: Trefferquote 48–66 % → 54–71 %, exakte Layouts 2–6 → je 6. MS43/MS42 unverändert. Über den Code gefundene Achsen erscheinen auch ohne Kette als Achsen-Kandidaten (auch mit Vorzeichen).
- Oberfläche: Farbskala kalt→heiß für Heatmap (mit Werten, Achsen, Legende), Tabelle (Zellen eingefärbt, Nachkommastellen nach Skalierung) und 3D (gefüllte Fläche); eigene Liniensymbole in der Werkzeugleiste; überarbeitetes Hell/Dunkel-Theme. `tools/screenshot.py` rendert die Oberfläche offscreen.
- Repository: historische Berichte nach `docs/history/`, neue README, `.gitignore`/`.gitattributes` (keine Firmware, keine Build-Artefakte), GitHub-Actions-Workflow für pytest.

## 1.11.0 (17.10.2026)

- Smart Map Transfer mit bestätigten Definitionen, physikalischem Delta/Prozent, Konflikten, Zellvorschau, manueller Auswahl/Freigabe und atomarem Undo.
- CSV Log-to-Map mit Kanal-/Einheitenzuordnung, transparenten Soll/Ist-Regeln, bilinearer Belegungs-Heatmap, Editor-Zellnavigation und HTML-Bericht.
- Mehrere Kennfeldtabs, Schichten, Interpolation über physikalische Achsen, Glättung, disjunkte Auswahl, deklarative Rezepte und sichere Mehrprojekt-CLI.
- Virtueller Kennfeldkatalog, Favoriten/Gruppen, Dezimaleditor, Bitmasken-/Rohwertsuche, ZIP-BIN/ORI-Import und suchbarer Projektindex.
- Originalbackups, Recovery-Dateien, vorherige Projektstände, Hashintegrität, fsync/atomare Writes und Schutz der Originalpfade einschließlich Hardlinks.
- Veraltete Batch-Vorschauen gesperrt; Snapshot-Teilrestore verändert keine Stride-Lücken mehr; fehlender FORMATS-Import im Flächeneditor korrigiert.
- Vektorisierte Stride-Dekodierung und effizient angeordnete notwendige Scannerprüfungen. Vorher/Nachher auf gleichem synthetischen Korpus geprüft; reproduzierbare Größenbenchmarks.
- Schema-2-Migration mit Erhalt bestehender Datensätze; Provenienz-/Lineage-Gates für Training. MOD-Werte dürfen nicht unter ORI-Hash bestätigt werden. Modellkandidaten bleiben inaktiv.
- Strenge exakte Holdout-Metriken mit Herkunftsprüfung, real/synthetisch-Trennung, Leakage-Prüfung und optionalem Family-Holdout. Keine neuen realen Modellgewichte oder geprüften Multi-ECU-Labels erfunden.
- Windows-Regressionen, Qt-Integration, EXE-Build und Prüfung der paketierten Anwendung; siehe README_V1_11.md und QA_REPORT_V111.json.

## 1.10.0 (16.10.2026)
- Tatsächlich neues 24-Baum-ExtraTrees-Modell auf 4.000 synthetischen Oberflächen trainiert; portables JSON ohne Pickle, Inferenz mit NumPy.
- 1.000 Beispiele zur Validierung und 1.000 disjunkte synthetische Prozessbeispiele als Holdout. Alle Zahlen beziehen sich nur auf künstliche Strukturen.
- Modell als zusätzlicher Kandidaten-Hinweis im bisherigen Präzisions-Ranking integriert, niemals als bestätigter Kennfeldname, Achse oder Fahrzeugtyp.
- Kandidaten mit niedrigem Strukturwert leicht nachrangig behandelt, aber NICHT entfernt (keine validierte reale False-Negative-Rate).
- Bugfix: doppeltes Normalisieren bei der OOD/Unbekannt-Prüfung des semantischen ML-Modells entfernt.
- Zusätzlich zu einem Einzel-Firmware-Holdout erfolgt bei verifizierten Familienmodellen jetzt eine Leave-One-Firmware-Out-Prüfung. Mindestwerte sind Freigabebedingung.
- Kein neues semantisches ML-Modell freigegeben: unverändert 0 unabhängig geprüfte Trainingslabels für neue ECU-/TCU-Familien.
- Keine Drittanbieter-BINs eingebunden oder verteilt. Windows-GUI weiterhin nicht auf echter Windows-Maschine getestet.

---

# v1.8 – 2026-10-16

- Klickbare Kennfeld-Heatmap und neue 2D-Kurvenschnitte (Zeile/Spalte, originale vs. bearbeitete Werte) mit Sprung in editierbare Einzelzellen.
- Verbesserte 3D-Oberfläche mit ORI/MOD-Drahtgitter-Vergleich, Dreh-/Neigungs- und Zoomsteuerung.
- Hashgebundener Import geprüfter, expliziter Prüfbereichs-Profile; lesende CRC32/Summationsprüfung für definierte Bereiche. `unknown` bei fehlendem Profil, `mismatch` bei Differenz; **keine ECU-universelle Checksum-Garantie und keine Reparatur**.
- Integrierter Kalibrierungs-Audit bei BIN-Export: Deltaübersicht, Zelländerungen, ungeprüfte Kennfelder, Dateihash und Bytes außerhalb von Tabellen. JSON-Bericht und CLI.
- Automatische Kennfeldgruppen mit nachvollziehbaren Kriterien, nie automatisches Hochstufen struktureller Kandidaten zu bestätigten ECU-Funktionen; interaktiver Baum und CSV-Export.
- Synthetischer Checksum-Test und sechs neue Regressionstests. **160 bestanden, 4 übersprungen**; Qt-GUI/Windows-EXE mangels PySide6 und Windows in dieser Umgebung nicht live getestet.

---

# v1.7 – 2026-10-16

- GUI-Blocker behoben: `require_image()` liefert wieder booleschen Erfolgswert.
- Read-only ORI/MOD-Kennfeld- und Zellvergleich (strided und endian-korrekt), Einzelzell-/Summen-CSV, Diff-Dialog mit Sprungfunktion.
- Neue Hash-genaue Fahrzeug-/ECU-Identitätsdatenbank mit atomarem, belegpflichtigem JSON-Massenimport und Konfliktsperre; zusätzliche vorsichtige Bosch-Text-Familienhinweise.
- Präzisionssuche ergänzt um konservative Nachbarachsen-Hinweise (ohne automatische Kennfeld-/Einheitenfreigabe).
- Transparentes Datenbank-Abdeckungsfenster für Audi / Mercedes-Benz / BMW / Opel / Lamborghini und read-only CLI-Workflows.
- Neues synthetisches ORI/MOD-Beispiel und neue Regressionstests. Keine neuen echten Hersteller-Firmware-Trainingspaare.

---

# v1.6 – 2026-10-16

- Präzisions-Postfilter für 2D-Struktur, Endian-Ambiguität und überlappende Kandidaten; unbekannte Funktion immer unbekannt.
- Strengere MS43-Strukturmodell-Abstention bei generischen linearen Ebenen/Rauschflächen.
- Familiengebundene supervisierte Prognose, OOD-Gate und Oberflächen-Duplikatsperre über Firmware-Holdouts.
- Markenübergreifende Referenzverwaltung (7 Links/Hinweise für Audi, BMW, Opel, Mercedes und Lamborghini), vier konkrete per Git-Blob gepinnte XDF-Pfade; keine Drittanbieter-BINs enthalten.
- Windows-GUI-Quellenanzeige, Offline-SQLite-Index, CLI und synthetischer Reproduktionsbenchmark.
- 146 Tests bestanden, drei übersprungen. Windows-Laufzeit nicht ausgeführt.
- **Kein weiteres supervised Training erfolgt:** unabhängig verifizierte Kennfeldlabels weiterhin 0, MS43-Modell aus v1.5 unverändert.

---

# v1.5 – 2026-10-16

- Reales PCA/SVD-Strukturmodell aus 67 MS43-Rohwertoberflächen trainiert und als JSON in Paket integriert. Externe Ausgangsdefinitionen unbestätigt; **keine** automatischen Funktionsnamen als sicher behauptet.
- Aktive Prüfqueue und Erklärungssuche für unsichere, unbekannte Tabellen.
- Familienregister für MD1/MG1/EDC17/EDC16/EDC15/ME-MED/SIMOS/SID/DCM/Denso/GS20/ZF.
- Explizite XDF/A2L-Datenaufnahme mit Firmware-SHA, manuell geprüfter Identität und bei A2L obligatorischen Speichersegmenten.
- Familienbezogenes supervised Training mit Klasse-/Firmware-Holdout und Mindestpräzision/-trefferquote; verweigert derzeit Freigabe wegen 0 unabhängiger Labels.
- Training/Status/Prüfqueue zusätzlich in der GUI; Schutz vor alten, ungeprüft familienübergreifenden ML-Klassifizierungen.
- 143 Python-Tests bestanden. Windows-Qt nicht live validiert.

---

# Version 1.4 – Öffentliche Datenbank befüllt

- 14 konkrete und SHA-gepinnte XDF-Quellen (MS41, MS42, MS43, GS20).
- 118 echte, lizenz- und quellengebundene Kennfeld-Metadatensätze aus MS41/MS42/MS43.
- Separate SQLite mit 81 auf die echte MS43-BIN-SHA bezogenen, **nicht** fachlich bestätigten XDF-Vorschaudefinitionen; BIN selbst nicht mitgeliefert.
- Erststart-Seed aller vorhandenen SQLite-Kataloge idempotent und ohne Überschreiben bestehender Daten.
- Windows-Menü: öffentlicher Quellenkatalog, SHA-gepinnter XDF-Download und manuelle MS43-Offline-Vorschau.
- CLI: öffentliche Quellen auflisten, softwaregebundenen Original-XDF-Import auslösen, separate Offline-Vorschau indexieren.
- Lizenzhinweise und Originalquellen dokumentiert; keine fremden Daten als validierte Trainingsbeispiele markiert.
- 137 Tests bestanden, GUI nicht live auf Windows getestet.

---

# v1.3 – Erkennungsarchitektur in drei Ebenen

- Neu: opt-in SQLite-Definitionsdatenbank mit ECU-/Quellenhash, Familienzuordnung und rückverfolgbarer Herkunft.
- Neu: erneut geladene byteidentische Definitionen, nach Nutzerfreigabe.
- Neu: manuelle Fachprüfung pro Map, erforderlich für Referenztransfer und ML-Training.
- Neu: Batchimport für hunderte bis tausende lokale BIN/XDF-Paare aus JSON-Paarlisten.
- Neu: Referenzbasierte Suche für verschobene und moderat veränderte, zusammenhängende Map-Matrizen derselben ECU-Familie.
- Neu: Einzigartigkeitsprüfung mit zweitbestem Treffer und Mehrdeutigkeitsabstinenz.
- Neu: rein lokal trainierbares, versioniertes JSON-ML-Modell mit Firmware-getrenntem Holdout und klassenspezifischem Recall.
- Neu: NumPy-ML-Features aus Oberflächen, Gradienten und Statistiken; Score- und Qualitätsabstinenz.
- Neu: Qt-Menüaktionen und Hintergrundworker für Matching sowie Batchimport.
- Neu: CLI `python -m ecu_studio.tools.recognition_v13` für Index, Batch, Training und Erkennungsberichte.
- Schutz: Nach Veränderung einer bereits bestätigten Definition fällt der Bestätigungsstatus zurück.
- Tests: 132 bestanden, einschließlich echtem Upload-Dateiprofil, verschobenem Map-Fund, doppeltem/mehrdeutigem Fund und ML-Firmware-Holdout mit synthetischen Daten.

Nicht geändert: XDF/A2L-Parser enthalten weiterhin einen dokumentierten Teilumfang; keine 100-%-Semantik unbekannter Firmware. Keine neuen Checksummen-/Flash-Funktionen.

## 1.9.0 (16.10.2026)
- Neuer opt-in 1D-TCU-(X,Y)-Kurvenscanner; Strides, BE/LE, Terminator, keine Typfreigabe.
- Firmware-Holdout-Benchmark mit SHA-256, Split-Leakage-Prüfung, ein-zu-eins zugeordneten Kennfeldpositionen und transparenter räumlicher Deckungsmetrik.
- Quellenkatalog für Subaru 5EAT (Hitachi/Denso), Volvo ME7, Hyundai SIM2K, VAG DQ250.
- Realdaten-Vorfilterdiagnose an drei publizierten Holden-68HC11-Bankfragmenten, keine Labels und keine ROM-Weitergabe.
- Weitere registrierte ECU/TCU-Familien, ausdrücklich ohne neue automatische Typidentifikation.
- Neues Windows-Werkzeugmenü für 1D-Getriebekurven.
- Keine neuen KI-Funktionslabels oder semantischen Trainingsgewichte: es fehlen geprüfte, rechtmäßig verwendbare Trainings-/Holdout-Paare.
