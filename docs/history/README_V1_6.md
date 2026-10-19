# ECU Studio AI v1.6 – Präzisionssuche & markenübergreifendes Quellenverzeichnis

**Erweitert die hochgeladene v1.5 direkt. Windows-Quellcodepaket mit lokaler Qt-Oberfläche, SQLite-Datenbank und vorhandenem 67-Sample-MS43-Strukturmodell.**

## Neu in Version 1.6

- Neuer Postfilter `core/precision.py`: normierte horizontale/vertikale Sprünge, Ausreißerkanten, Dynamik beider Achsen, Prüfung alternativer Byte-Reihenfolge und starke Überlappungsunterdrückung. Bereits die bisherigen 8/16/32-Bit-Scanner erzeugen die Kandidaten; der neue Filter verwirft typische Fehldeutungen vor der Anzeige.
- Scanner-Rückgabe aus `scan_calibration_candidates` bleibt konsequent `Unbekannt` / `verified=False`. Eine visuell passende Kurve ist **kein** Beweis der ECU-Kennfeldfunktion.
- Das vorhandene MS43-Strukturmodell wird weiterverwendet, allerdings mit zusätzlicher **Abstention** für verrauschte, eindimensionale oder generisch lineare Flächen. Keine fremden Firmwarestände als sicher erkannt.
- Training/ML-Inferenz: Familienbindung, OOD-Distanz-Prüfung, pro-Klasse-Holdout-Schwellen, Sperre bei familienübergreifend identischen Trainingsoberflächen. Alte nicht familiengebundene Modelle geben keine Klassen frei.
- Neues offline eingebautes **ECU-Quellenverzeichnis** für Audi, Mercedes-Benz, BMW, Opel und Lamborghini. Sieben Einträge, davon vier individuelle XDF-Quellen mit dokumentiertem Git-Blob-SHA-1. Kein automatischer Download, kein Bundling lizenzunklarer Fremddateien, keine automatische Zuordnung von XDF zu einer BIN.
- GUI-Menü **Werkzeuge → ECU · Quellen Audi / Mercedes / BMW / Opel / Lamborghini …** und CLI `source-discovery`.

## Laufzeit auf Windows

1. ZIP entpacken.
2. Windows mit Python 3.10+ und Internetzugang für die erstmalige Installation öffnen.
3. `start_windows.bat` ausführen. Dies installiert die lokalen Python-Abhängigkeiten in `.venv` und öffnet ECU Studio.
4. Für ein ausführbares Paket optional `build_exe_windows.bat` ausführen. **Die ZIP enthält kein bereits unter Windows getestetes EXE.**

Die bisherigen Projekte, BIN-Dateien, lokalen Kataloge und Definitionen werden nicht automatisch geändert. Die im ZIP enthaltene SQLite-Datei ist eine **Beispiel-/Quellendatenbank**; vorhandene lokale `~/.ecu_studio_ai/recognition-v1.sqlite3` nicht ohne Backup überschreiben.

## Quellenindex & Import

```powershell
python -m ecu_studio.tools.safe_learning source-discovery --db recognition_public_index.sqlite3 --out ECU_QUELLEN.json
python -m ecu_studio.tools.safe_learning source-discovery --brand Audi --db recognition_public_index.sqlite3
python -m ecu_studio.tools.safe_learning train-status --db recognition_public_index.sqlite3
python -m ecu_studio.tools.precision_benchmark --out PRECISION_BENCHMARK.json
```

Die Original-XDFs werden nur als verlinkte Quellen dokumentiert. BMW B58/MG1, Audi/VAG Simos, Opel Altformat-XDFs sind nicht ohne exakt passende Binärdaten, Softwarekennung, rechtmäßige Nutzung und sorgfältige manuelle Prüfung trainierbar. Für **Mercedes** ist kein geprüftes BIN-/Definitionspaar hinterlegt; für **Lamborghini** nur ein technischer Plattformhinweis (nicht ein XDF-Trainingsdatensatz). Weitere XDF/A2L-BIN-Paare lassen sich wie bisher über `safe_learning intake-pair` mit Hash, Segmenten und manueller Prüfung aufnehmen. **Ein bloßer GitHub-Download darf nie einen Datensatz automatisch verifizieren.**

## KI-Trainingsstand (wichtig)

- Mitgeliefert: unverändertes bestehendes MS43-Modell, auf **67 realen Rohdatenflächen aus genau einer Firmware** basierend. Die XDF-Labels sind noch nicht unabhängig bestätigt.
- Neu hinzugekommene fachlich verifizierte ECU-Kennfeldbeispiele: **0**. Neues supervised Modell: **keines**. Erzielte Erkennungsgenauigkeit für Audi, Mercedes, BMW-MG1, Opel, Lamborghini: **nicht messbar**.
- Die strengere Nachbearbeitung ist eine **Softwareverbesserung der Strukturfilterung**, keine Behauptung erfolgreichen neuen Supervised-Trainings. Erst bei echten, bestätigten BIN+Definition-Paaren aus getrennten Softwareständen werden neue Klassifikatoren freigegeben.

## Reproduzierbare Tests

`146 passed, 3 skipped` (Python/pytest) sowie Python-Syntaxprüfung. Im mitgelieferten *synthetischen* Zwei-Map-Test blieben beide Ankeradressen erhalten; 5 Vor-Kandidaten wurden zu 2 Kandidaten. In einem weiteren synthetischen Mehrkartenbeispiel blieben 7 zuvor definierte Testadressen erhalten und die Gesamtzahl sank von 28 auf 14. Diese Zahlen sind **keine** Benchmarks für echte ECU-Hersteller. `PRECISION_BENCHMARK.json` enthält die reproduzierbaren Angaben.

**Nicht durchgeführt:** Windows-Qt-Livetest, unabhängiger Firmware-Holdout, Herstellerübergreifender Kennfeld-Benchmark, Prüfstand oder Flash-/Checksum-Freigabe. Die Anwendung verändert im automatischen Lern-/Erkennungsdurchlauf keine Steuergerätedatei.

## Dateien

- `src/ecu_studio/core/precision.py` – Strukturprüfung
- `src/ecu_studio/recognition/source_registry.py` und `data/brand_sources.json` – geprüfte Quellenidentitäten, konservative Statusverwaltung
- `recognition_public_index.sqlite3` – vorhandene Datenbank plus Quellenhinweise
- `PRECISION_BENCHMARK.json`, `DISCOVERY_SOURCE_REPORT.json`, `QA_REPORT.json` – Inspektionsberichte
- `src/ecu_studio/recognition/data/ms43_430069_structure_model.json` – unverändertes bestehendes Strukturmodell

Die gesamten bisherigen v1.5-Quellen, Tests, Beispiel-Dateien, Windows-Skripte und Datenbanktabellen bleiben erhalten.
