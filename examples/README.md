# Beispiele

Alle Dateien sind **synthetisch** (aus Skripten erzeugt) und enthalten keine echte Steuergeräte-Firmware.
Sie dienen zum Ausprobieren der Oberfläche, als Testdaten und als Vorlagen für die Kommandozeilenwerkzeuge.

| Ordner | Inhalt | Erzeugt durch |
|---|---|---|
| [`demo/`](demo) | Demo-BINs mit Kennfeldern (`demo_synthetic.bin`, `demo_multi_map.bin` + passende A2L), eine geänderte Fassung für den ORI/MOD-Vergleich, Definitions-CSV, XDF-Beispiel mit Schrittweiten | `make_demo.py`, `generate_multi_map.py` |
| [`checksum/`](checksum) | Datei mit gültiger Prüfsumme, geänderte Fassung und das zugehörige, an die Original-SHA-256 gebundene Checksummenprofil | – |
| [`memory/`](memory) | Intel-HEX- und S-Record-Beispiel für den Speicherabbild-Import (mit Lücken) | `make_memory_examples.py` |
| [`holdout/`](holdout) | Synthetisches TCU-Abbild mit Referenz für `python -m ecu_studio.tools.firmware_holdout` | – |
| [`templates/`](templates) | Vorlagen: Benchmark-Manifest (`tools/benchmark_suite`), Auswertungs- und Herkunftsmanifeste, Identitätsschema | – |

Schnell ausprobieren: ECU Studio AI starten → **Datei → BIN öffnen …** → `examples/demo/demo_multi_map.bin`, danach
**Datei → A2L / textuelles DAMOS koppeln …** mit `examples/demo/demo_multi_map.a2l` (ECU-Anker `0x800000`).
