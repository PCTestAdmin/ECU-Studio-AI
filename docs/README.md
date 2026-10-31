# Dokumentation

| Dokument | Inhalt |
|---|---|
| [FIRMWARE_PROTECTION.md](FIRMWARE_PROTECTION.md) | Firmware-Schutz: lokale Ablage, Git-Hooks, Regeln, Ausnahmen, Prüfung vor dem Push, Restrisiken |
| [ANALYSE_2026-10-31.md](ANALYSE_2026-10-31.md) | Firmware-Schutz, Fehlerbehebungen bei Definition/XDF-Export, lokale Referenzsuche mit Benchmark, Aufgabenstand |
| [OPEN_SOURCE_DETECTION_BENCHMARK.md](OPEN_SOURCE_DETECTION_BENCHMARK.md) | Quellcodevergleich, isolierte Detektorversuche und reproduzierbare Qualitätsgrenzen |
| [ANALYSE_2026-10-30.md](ANALYSE_2026-10-30.md) | TriCore-Interpolationsaufrufe (MSD80): Recherche, Prozessornachweis, Stackslots, Achsensuche, Zelltyp, Messung, Grenzen |
| [DELCO_D98_RESEARCH.md](DELCO_D98_RESEARCH.md) | Delco „D98“ = Multec-S-Kalibrierkennung: Quellen, Rechte, fehlende Daten |
| [DELCO_D98_BENCHMARK.md](DELCO_D98_BENCHMARK.md) | Multec S: nur synthetische Negativkontrolle messbar |
| [ANALYSE_2026-10-24.md](ANALYSE_2026-10-24.md) | 1.17-Kandidat: Kennfeldpaket, Workflow, Messnachweise, Windows-Prüfung und offene Referenzdaten |
| [PROGRESS.md](PROGRESS.md) | Erkennung je Version und Meilenstein, inklusive TriCore-Stufen am MSD80-Vollflash |
| [ECU_SUPPORT.md](ECU_SUPPORT.md) | Welche Steuergeräte mit welchen Referenzen gemessen sind – Trefferquote, Präzision, was nicht validiert ist |
| [RELEASE.md](RELEASE.md) | Neue Version veröffentlichen: Version, CHANGELOG, Tag, automatischer Build und Update-Verteilung |
| [MAP_PACK.md](MAP_PACK.md) | Offenes Kennfeldpaket v2, Grenzen, Herkunft, Vorschau, Undo und Softwarestand-Abgleich |
| [REFERENCE_VALIDATION.md](REFERENCE_VALIDATION.md) | Hashgebundene lokale Referenzmessung mit Rollen, Fehlfundanalyse und Baseline-Vergleich |
| [MODELLKARTE.md](MODELLKARTE.md) | Gemessene Trefferquote je Beweisart, Lernmodell für Datenmuster-Funde, Grenzen |
| [OPEN_SOURCE_VERGLEICH.md](OPEN_SOURCE_VERGLEICH.md) | Vergleich quelloffener ECU-Werkzeuge: welche Ideen übernommen, welche verworfen wurden |
| [ANALYSE_2026-10-23.md](ANALYSE_2026-10-23.md) | Fehlfundanalyse, gemeinsame Achsen, Softwarestand-Abgleich, Projektbibliothek, verworfene Ansätze, Qualitätsmatrix |
| [../CHANGELOG.md](../CHANGELOG.md) | Änderungen je Version |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) · [../SECURITY.md](../SECURITY.md) | Mitmachen, Sicherheitslücken melden |
| [../examples/README.md](../examples/README.md) | Synthetische Beispieldateien und Vorlagen |

## Aufbau des Quellcodes

| Ordner | Inhalt |
|---|---|
| `src/ecu_studio/core` | Datenmodell und Formate (XDF, A2L, RomRaider, HEX/S19), Kennfelderkennung (`structure_scan`, `axis_records`, `axis_arrays`, `cpu_refs`, `tricore_refs` für TriCore-Interpolationsaufrufe), Prüfungen (`preflight`, `checksum_audit`, `checksum_search`), Updates (`updates`) |
| `src/ecu_studio/recognition` | Definitionskatalog, mitgelieferte XDFs, Lernmodell- und Kalibrierdaten |
| `src/ecu_studio/ui` | PySide6-Oberfläche, Dialoge, Update-Fenster |
| `src/ecu_studio/tools` | Kommandozeilenwerkzeuge: Benchmarks, Kalibrierung, Checksummen-Suche, Paketbau, Release-Notizen, Roadmap-Clips |
| `packaging` | Windows-Paket: Startprogramm (C#), Python-Einstieg, Updater, Installer-Skript, gesperrte Abhängigkeiten |
| `tests` | pytest-Suite (CI unter Python 3.11 und 3.12) |

## Häufige Befehle

```bat
python -m pytest -q                                                    :: alle Tests
python -m ecu_studio.tools.benchmark_suite MANIFEST.json               :: Erkennung gegen Referenzen messen
python -m ecu_studio.tools.benchmark_suite MANIFEST.json --baseline ALT.json  :: Vorher/Nachher mit Regressionsurteil
python -m ecu_studio.tools.miss_analysis MANIFEST.json                 :: Ursachen verfehlter Kennfelder
python -m ecu_studio.tools.structure_benchmark BIN XDF|A2L             :: ein Paar messen
python -m ecu_studio.tools.calibrate_confidence --pair BIN REF         :: Trefferquoten neu kalibrieren
python -m ecu_studio.tools.checksum_search BIN --at 0x7FFE             :: Prüfsummen-Layout suchen
python -m ecu_studio.tools.support_matrix RESULT.json                  :: Steuergeräte-Matrix der App aus Messungen
python -m ecu_studio.tools.feature_clips docs/clips                    :: Roadmap-Clips neu aufnehmen (synthetische Datei)
build_exe_windows.bat                                                  :: Windows-Paket (ZIP + Installer) bauen
```
