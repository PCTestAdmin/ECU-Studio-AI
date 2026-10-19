# ECU Studio AI

Kalibrier-Workbench für Motor- und Getriebesteuergeräte: BIN-Dateien öffnen, Kennfelder finden,
mit XDF/A2L-Definitionen koppeln, als Tabelle, Heatmap und 3D-Fläche ansehen und nachvollziehbar
bearbeiten. Die Originaldatei wird nie überschrieben; jede Änderung bleibt im Audit sichtbar.

![Heatmap mit Farbskala](docs/images/dark-heatmap.png)

| Kennfeldtabelle (hell) | 3D-Ansicht (dunkel) |
|---|---|
| ![Tabelle](docs/images/light-table.png) | ![3D](docs/images/dark-3d.png) |

*Screenshots mit der synthetischen Demo-Datei `examples/demo_multi_map.bin`.*

## Funktionen

- **Kennfeldsuche ohne Definition** – findet Tabellen, Kennlinien und Achsen direkt in den Rohdaten:
  - Zeilenabstand aus der Datenwiederholung statt fester Raster (8/16 Bit, mit/ohne Vorzeichen, LE/BE)
  - Stützstellen-Arrays mit Anzahl-Präfix (Achsen) und Code-Verweise (C16x: Seite+Offset-Ladebefehle)
  - Achsen, die der Code vor einem Kennfeld lädt, legen dessen Größe und Rohachsen fest
    (Siemens MS43: Y/X/Kennfeld-Ladefolge; Bosch ME7: Lookup-Aufruf mit Kennfeld- und Achsenzeiger)
  - Code/Daten-Trennung für Dateien ohne bekanntes Steuergeräteprofil
- **Kalibrierte Konfidenz** – jede automatische Fundstelle zeigt die gemessene Trefferquote ihrer
  Evidenzklasse (z. B. Code-Verweis + Achsen 100 %, nur Datenglätte 30 %) als gesichert / wahrscheinlich / Vermutung
- **Flash-Preflight** – vor dem Export: unveränderte Zwillings-/Überwachungskopien, Änderungen im Programmcode,
  zerstörte Achsen, ungewöhnliche Sprünge, Checksummenstatus – als Ampel mit Begründung
- **Funktionsgraph** – welche Kennfelder dieselbe Code-Routine liest oder dieselben Achsen nutzt
- **Signal-Tracing** – RAM-Eingänge jedes Kennfeldzugriffs; gleiche Variable = gleiche physikalische Größe,
  direkt als Logger-Liste nutzbar
- **Achsen-Semantik** – Vorschläge für Größe und Skalierung von Stützstellen (Drehzahl, Temperatur, Last …)
- **Weitere Prozessoren** – C16x (Siemens MS4x, Bosch ME7) vollständig; 68HC11 und 8051 mit automatischer
  Speicherbasis als bestätigende Evidenz
- **Definitionen koppeln** – TunerPro XDF, A2L/DAMOS, RomRaider-XML, CSV; mitgelieferte
  Standard-XDFs für Siemens MS41/MS42/MS43
- **Ansichten** – Hex-Editor, 2D-Rohdaten, Kennfeldtabelle, Heatmap, 3D-Fläche, ORI/MOD-Kurven, Speicheratlas
- **Bearbeiten** – Batch mit Vorschau, Undo/Redo, Projektstände, Patch-Export, Änderungsprotokoll
- **Hell/Dunkel** – umschaltbar unter *Ansicht*

Alle automatischen Funde sind **Geometrie-Hypothesen**: Name, Einheit und Funktion eines Kennfelds
kommen nur aus einer passenden Definition oder deiner Prüfung.

## Erkennungsgüte

Blind gemessen gegen öffentliche XDF-Definitionen (`python -m ecu_studio.tools.structure_benchmark BIN XDF`),
2D-Kennfelder ab 4×4:

| Datei | gefunden | exakt (Start, Größe, Breite) | Präzision |
|---|---|---|---|
| Siemens MS43 430069 | 67 % (vorher 4,5 %) | 197 von 379 (vorher 1) | 76 % |
| Siemens MS42 0110C6 | 55 % (vorher 13 %) | 22 von 213 (vorher 5) | 67 % |
| Bosch ME7 (Volvo, 3 Stände) | 54–71 % (vorher 5–10 %) | je 6 (vorher 0) | nicht belastbar* |

Achsen/Kennlinien: MS43 610 exakt (96,5 % Präzision), MS42 398 exakt (97 %). Scan-Dauer 5–25 s je Datei.
\* Die ME7-XDFs definieren nur einen kleinen Teil der Kennfelder. Details: [CHANGELOG](CHANGELOG.md).

## Installation (Windows)

Voraussetzung: Python 3.10–3.12 mit dem Launcher `py`.

```bat
start_windows.bat
```

Legt beim ersten Start `.venv` an, installiert die Abhängigkeiten und startet die Oberfläche.
Manuell:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python -m ecu_studio.main
```

Eigenständige EXE: `build_exe_windows.bat` (PyInstaller).

## Entwicklung

```bat
python -m pytest -q
python -m ecu_studio.tools.structure_benchmark <bin> <xdf-oder-csv>
python -m ecu_studio.tools.screenshot <bin> <ausgabeordner>
```

| Ordner | Inhalt |
|---|---|
| `src/ecu_studio/core` | Datenmodell, Formate, Kennfeldsuche (`structure_scan`, `axis_arrays`, `data_regions`) |
| `src/ecu_studio/recognition` | Definitionskatalog, mitgelieferte XDFs, Modelle |
| `src/ecu_studio/ui` | PySide6-Oberfläche, Theme, Icons |
| `src/ecu_studio/tools` | Kommandozeilenwerkzeuge (Benchmarks, Audits, Screenshots) |
| `tests` | pytest-Suite |
| `examples` | synthetische Demo-Dateien (keine echte Firmware) |
| `docs/history` | Berichte und Notizen früherer Versionen |

## Wichtige Hinweise

- **Keine Checksummen-Korrektur, nicht flash-validiert.** Geänderte Dateien vor dem Flashen mit einem
  geeigneten Werkzeug prüfen. Eingriffe in Steuergeräte können Typgenehmigung, Abgasverhalten und
  Versicherungsschutz betreffen.
- **Keine Steuergeräte-Firmware im Repository.** Eigene Reads gehören nicht in `examples/`; `.gitignore`
  schließt `*.bin` außerhalb von `examples/` aus.
- **Lizenz:** GPL-3.0, siehe [LICENSE](LICENSE).
- **Fremddaten:** Die mitgelieferten MS4x-XDFs (MS4x Dev Team) und Open-ECU-Presets (rusEFI) stehen unter
  GPL-3.0; Herkunft und Prüfsummen in `src/ecu_studio/recognition/data/definitions/NOTICE.txt` und
  `src/ecu_studio/recognition/data/training/NOTICE.txt`.
