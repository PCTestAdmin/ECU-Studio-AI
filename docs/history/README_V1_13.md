# ECU Studio AI 1.13

Windows-ZIP vollständig entpacken und ECU-Studio-AI-1.13.exe starten. Keine lokale Python-Installation nötig. Die bisherigen 1.12-Pakete bleiben erhalten.

## Verbesserungen

- 16 unveränderte Standard-XDFs offline: MS41 1429861 (24K/256K), MS42 0110C6 (32K/512K) und MS43 430037/430055/430056/430064/430066/430069 (64K/512K). Automatische Vorschläge benötigen passende Software/Dateigröße und mindestens zwölf verschiedene monotone Achsenpaare in mindestens vier Datenregionen.
- Neuer RomRaider-Import: Datei → RomRaider XML mit BIN koppeln. Interne ROM-ID und Dateigröße müssen exakt passen. Numerische 2D/3D-Tabellen, Vererbung, dynamische/statische Achsen, Ganzzahlen und IEEE-754-f32 werden unterstützt. Nichtlineare Formeln sind ohne geprüfte Umkehrfunktion schreibgeschützt. Schalter, Includes und unbekannte Layouts werden mit Grund ausgelassen. Die erste Skalierungsvariante ist die Anzeigevorgabe.
- Lokale RomRaider-Dateien neben der BIN (gleicher Dateistamm.xml oder ecu_defs.xml) bzw. unter ~/.ecu_studio_ai/external_definitions/ecu_defs.xml werden geprüft und zum Import angeboten. Kein automatischer Download. Subaru-XML und OEM-BINs sind nicht enthalten.
- Einsbasierte XDF-Kategorien verhindern, dass reine Achsen automatisch als Kennfelder erscheinen. Das feste MS43-Softwarefeld verhindert falsche Versionshinweise aus zufälligen numerischen Teilstrings.
- Neues Strukturmodell aus offenen rusEFI-Presets. Es priorisiert unbekannte Strukturvorschläge und erzeugt keine Funktionsnamen oder Verifikationen. Herkunft und Metriken: KI-Werkzeuge → Installiertes Strukturtraining; weitere Quellen unter Hilfe → Definitionsquellen und Lizenzen.

## Konkrete Abdeckung

| Bereich | Stand |
|---|---|
| MS43 430069 | Lokale reale Regression: 856 quellenbasierte Zuordnungen, davon 403 2D-Tabellen und 453 Kennlinien; Original unverändert |
| MS42 0110C6 | Separates öffentliches Firmware-Abbild und Teilausschnitt: 592 Zuordnungen, davon 248 2D und 344 Kennlinien |
| MS41 und fünf weitere MS43-Stände | Definitionen und Identitäts-/Negativtests vorhanden; eigener realer BIN-Regressionsnachweis fehlt |
| Denso/Subaru | Neuer RomRaider-Formatimport, mit öffentlicher XML und synthetischen ROM-IDs geprüft; kein realer Denso-BIN-Nachweis |
| Bosch, Continental, Delphi und weitere | Generischer lokaler XDF/A2L-Import; passende Definition nötig, keine mitgelieferten OEM-Pakete oder universelle automatische Erkennung |

Alle Community-Zuordnungen bleiben ungeprüft. Quellenübereinstimmung bestätigt keine Firmware-/Patchvariante unabhängig. Standard- und Extended-Load-Definitionen sind nicht austauschbar. Keine Checksum-Korrektur oder Flash-Freigabe.

## Training

64 Tabellen wurden aus zwölf unveränderten rusEFI-Quelldateien extrahiert. Nach Dynamikfilter, Form-Deduplikation und Entfernung ähnlicher Flächen bleiben 14 Trainingstabellen, vier Mazda-Validierungstabellen und acht zurückgehaltene Honda/Hyundai-Tabellen. Die Trennung erfolgt vor der Datenaugmentation; Quellgruppen überschneiden sich nicht.

Auf 320 aus acht Testtabellen abgeleiteten Beispielen: Balanced Accuracy 85,35 % gegenüber 52,54 % beim bisherigen synthetischen Modell, Precision 81,36 %, Recall 75 %. Negative Beispiele sind erzeugte Störungen und Fehlinterpretationen. Das ist keine allgemeine OEM-Erkennungsrate. Keine Benutzer-BIN oder Subaru-/Bosch-OEM-Firmware wurde trainiert. Kennfeldfunktionen benötigen weiterhin fachlich bestätigte Referenzen.

Reproduzieren: Trainingsabhängigkeiten installieren (`pip install -e .[train]`), dann `python -m ecu_studio.tools.train_calibration_ranker`. Für die exakt geprüften Versionen siehe requirements-lock-windows.txt. Corpus, Originalquellen, Lizenzen, Modellgewichte und Split-Bericht liegen bei. Die Inferenz benötigt kein scikit-learn. Der erneute Trainingslauf erzeugte ein byteidentisches Modell.

Details: [Prüfbericht](DETECTION_REPORT_V113.md), [Funktionsstand](FEATURE_MATRIX_V113.md), [Training](TRAINING_REPORT_V113.json), [QA](QA_REPORT_V113.json).

Quellen: [MS41](https://github.com/ms4x-net/ms41), [MS42](https://github.com/ms4x-net/ms42), [MS43](https://github.com/ms4x-net/ms43), [rusEFI](https://github.com/rusefi/rusefi), [RomRaider](https://github.com/RomRaider/SubaruDefs). Die öffentliche [WinOLS-Beschreibung](https://www.evc.de/en/product/ols/software/) liefert keinen vollständig reproduzierbaren Erkennungsalgorithmus; proprietärer Code wurde nicht übernommen.
