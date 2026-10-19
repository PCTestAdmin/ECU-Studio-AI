# ECU Studio AI 1.9 – neues ECU-/TCU-Daten- und Testsystem

Basis ist das vollständige Windows-Python-Projekt **1.8.0**. Die Oberfläche und alle bisherigen Funktionen bleiben enthalten.

## Gefundene zusätzliche Datenquellen (nicht im ZIP kopiert)

- Subaru 5EAT, **Hitachi M32R** und **Denso SH705x**: öffentlich dokumentierte Firmware- und Definitionsbestände, siehe `new_ecu_tcu_sources.json`. Die originalen Subaru-ROMs stehen **ausdrücklich nicht** unter der MIT-Lizenz des Definitionsprojekts.
- Volvo **Bosch ME7**: öffentlich indexierte Original-BINs; Herkunft laut Anbieter nicht für alle Dateien verifizierbar.
- Hyundai N **Continental SIM2K**: Softwarestand-Verzeichnisse mit BIN-/XDF-Material; Paarung und Rechte jeweils prüfen.
- Volkswagen/Audi **DQ250-MQB**: wichtige Formatinformation, aber kein belastbar geprüftes neues Trainingspaar.
- Ein zusätzlicher Realbyte-Probelauf auf drei publizierten **Holden/68HC11-Bankfragmenten**: Nachvollziehbare Git-Blob-IDs und Ergebnisse in `REAL_PUBLIC_FIRMWARE_SCREEN_V19.json`. Dieser Probelauf ist nur eine separate Vorfilter-Analyse, **keine** reale Messung der Trefferquote von ECU Studio.

## Neuer TCU-Suchmodus

Unter `Werkzeuge → TCU · 1D-Wortpaar-Kandidaten suchen (experimentell)` wird ein optionaler, begrenzter Suchlauf angeboten. Er erkennt einige streng steigende 16-Bit-(X,Y)-Kurven mit Endmarker, einschließlich Big-/Little-Endian. Die Ausgabe ist grundsätzlich **ungeprüft**; die Y-Werte liegen als interleaved u16 vor und werden über Strides gelesen. Erkennung von Schaltpunkten, Drehmoment- oder Druckkennfeldern wird **nicht** behauptet.

Headless-Beispiel:

```powershell
python -m ecu_studio.tools.firmware_holdout tcu-curves --bin "C:\\Meine Dateien\\Getriebe.ori" --out tcu_vorschlaege.json
```

## Neues Firmware-Holdout-Tool

Ein manifestgetriebener Benchmark prüft getrennte Train-/Test-Firmwares, SHA-256, Quellenrechte und XDF- bzw. explizite JSON-Referenzdefinitionen. Ausgegeben werden **räumliche Überdeckung / Recall-Proxy**, nicht semantische Genauigkeit. Es werden **keine** externen Dateien automatisch zu bestätigten Trainingslabels erklärt.

```powershell
python -m ecu_studio.tools.firmware_holdout eval --manifest benchmark_manifest.json --out ergebnis.json
python -m ecu_studio.tools.firmware_holdout sources --out neue_quellen.json
```

- Eine Vorlage liegt unter `examples/NEW_ECU_TCU_HOLDOUT_MANIFEST.template.json`.
- `definition` kann eine XDF oder JSON-Liste von `MapDefinition`-Objekten sein.
- Mit 5EAT-RomRaider-XML ist der Import **noch nicht** kompatibel; dafür müssen vorher korrekt konvertierte und geprüfte Definitionen vorliegen. Für A2L mit segmentierter ECU-Speicherabbildung ist weiterhin der separate Projektimport zuständig.
- Positionsgenauigkeit ist bei einem Paarformat von mehrdeutigen Strides und überlappenden 1D-Kurven begrenzt. Deshalb beweist auch eine hohe Deckungsquote nicht, dass die Funktion richtig erkannt ist.

## Was wurde an der KI wirklich trainiert?

**Keine neuen semantischen Modellgewichte.** Die Quellenlage liefert öffentlich referenzierbare Firmware, aber noch keine hier lokal vollständig zugänglichen, unabhängig bestätigten Firmware-/Definitionspaare zur fairen Trainings-/Testaufteilung. Neue, ungeprüfte Firmware ist ausdrücklich **kein** Trainingslabel. Das vorhandene MS43-PCA-Strukturmodell bleibt unverändert.

Statt erfundener Trainingsresultate enthält v1.9 einen realdatenbasierten Risiko-Befund, einen neuen TCU-Strukturscanner, Schutz vor überlappenden Doppelbewertungen und einen reproduzierbaren Holdout-Benchmark. Damit können später konkrete Verbesserungen an neuen ECU-/TCU-Daten gemessen werden, bevor neue Gewichte produktiv eingebaut werden.

## Sicherer Betrieb

Das Projekt lädt und flasht keine ECU/TCU. Originaldateien bleiben unverändert. Alle Vorschläge müssen manuell abgeglichen werden. Vor tatsächlichem Fahrzeugbetrieb sind individuelle ECU-Checksummen-/Flash- und Betriebsprüfungen erforderlich. Ein bestandenes Programmsuite-Testergebnis ist **keine** Flash-Freigabe.

## Tests des v1.9-Pakets

- **168 Tests bestanden, 4 übersprungen.** Zu den übersprungenen Tests gehören GUI-Prüfungen, weil PySide6 in der Testumgebung nicht verfügbar ist.
- Reproduzierbares synthetisches Holdout in `examples/holdout_synthetic_tcu_manifest.json`: **2 von 2** künstlich gesetzten interleavten 1D-Kurven räumlich gefunden, ohne überzählige Treffer in diesem Testbild. Das ist **keine** bekannte Genauigkeit auf realen Subaru-5EAT-Dateien.
- Auf neu gefundenen echten Holden-Bankfragmenten wurde nur ein externer, vereinfachter Vorfilter getestet; siehe `REAL_PUBLIC_FIRMWARE_SCREEN_V19.json`. Eine exakte End-to-End-Gegenüberstellung von v1.8 und v1.9 auf diesen Firmwarebytes war in der verfügbaren Umgebung nicht möglich.
- Die Windows-Oberfläche wurde statisch kompiliert, aber mangels PySide6 nicht live gestartet. `test_v19_windows.bat` führt die lokalen Prüfungen auf Windows aus.
