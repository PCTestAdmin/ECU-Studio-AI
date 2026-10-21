# Dokumentation

| Dokument | Inhalt |
|---|---|
| [ECU_SUPPORT.md](ECU_SUPPORT.md) | Welche Steuergeräte mit welchen Referenzen gemessen sind – Trefferquote, Präzision, was nicht validiert ist |
| [RELEASE.md](RELEASE.md) | Neue Version veröffentlichen: Version, CHANGELOG, Tag, automatischer Build und Update-Verteilung |
| [MODELLKARTE.md](MODELLKARTE.md) | Lernmodell für Datenmuster-Funde: Trainingsdaten, Prüfung, Grenzen |
| [OPEN_SOURCE_VERGLEICH.md](OPEN_SOURCE_VERGLEICH.md) | Vergleich quelloffener ECU-Werkzeuge: welche Ideen übernommen, welche verworfen wurden |
| [../CHANGELOG.md](../CHANGELOG.md) | Änderungen je Version |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) · [../SECURITY.md](../SECURITY.md) | Mitmachen, Sicherheitslücken melden |
| [../examples/README.md](../examples/README.md) | Synthetische Beispieldateien und Vorlagen |

## Aufbau des Quellcodes

| Ordner | Inhalt |
|---|---|
| `src/ecu_studio/core` | Datenmodell und Formate (XDF, A2L, RomRaider, HEX/S19), Kennfelderkennung (`structure_scan`, `axis_records`, `axis_arrays`, `cpu_refs`), Prüfungen (`preflight`, `checksum_audit`, `checksum_search`), Updates (`updates`) |
| `src/ecu_studio/recognition` | Definitionskatalog, mitgelieferte XDFs, Lernmodell- und Kalibrierdaten |
| `src/ecu_studio/ui` | PySide6-Oberfläche, Dialoge, Update-Fenster |
| `src/ecu_studio/tools` | Kommandozeilenwerkzeuge: Benchmarks, Kalibrierung, Checksummen-Suche, Paketbau, Release-Notizen |
| `packaging` | Windows-Paket: Startprogramm (C#), Python-Einstieg, Updater, Installer-Skript, gesperrte Abhängigkeiten |
| `tests` | pytest-Suite (CI unter Python 3.11 und 3.12) |

## Häufige Befehle

```bat
python -m pytest -q                                                    :: alle Tests
python -m ecu_studio.tools.benchmark_suite MANIFEST.json               :: Erkennung gegen Referenzen messen
python -m ecu_studio.tools.structure_benchmark BIN XDF|A2L             :: ein Paar messen
python -m ecu_studio.tools.calibrate_confidence --pair BIN REF         :: Trefferquoten neu kalibrieren
python -m ecu_studio.tools.checksum_search BIN --at 0x7FFE             :: Prüfsummen-Layout suchen
build_exe_windows.bat                                                  :: Windows-Paket (ZIP + Installer) bauen
```
