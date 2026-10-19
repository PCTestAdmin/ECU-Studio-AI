# ECU Studio AI 1.11 – implementierter Entwicklungsstand

Weiterentwicklung der gelieferten v1.10 vom 17.10.2026. Die Anwendung ist tatsächlich erweitert. **Der Master-Auftrag ist noch nicht vollständig abgenommen: Eine bessere Erkennungsgenauigkeit auf unabhängigen realen ECU-/TCU-Firmwarefamilien ist nicht belegt.**

## Installation und Windows-Build

Portable Ausgabe: `dist/ECU-Studio-AI-1.11/ECU-Studio-AI-1.11.exe`. Den **gesamten Ordner einschließlich `_internal`** zusammenhalten. Kein Python/Internet zum Ausführen erforderlich. Der lokale Build ist nicht digital signiert.

Quellcode starten: `start_windows.bat`. Getestet: CPython 3.13.2 x64 / Windows 11. Grundlegende Python-Anforderung bleibt >=3.10; andere Kombinationen wurden hier nicht erneut geprüft.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1
```

Das Skript installiert `requirements-lock-windows.txt`, führt Regressionstests und GUI-Integration aus, baut die EXE und prüft die **paketierte Anwendung selbst** mit `--smoke-test`. Die Abhängigkeiten sind festgehalten; bitidentische Builds auf verschiedenen Rechnern werden nicht behauptet. Tests ohne Paketierung: `test_next_windows.bat`.

## Kennfeldbearbeitung

Kennfeld doppelt anklicken oder `Strg+Enter`: Mehrere schließbare Kennfeldtabs bleiben gleichzeitig offen. Jeder enthält Tabelle, ORI/MOD-Kurve, Heatmap, 3D und überlagerte Zeilenschnitte („Schichten“). Alle Tabs teilen denselben Byte-Overlay und Undo/Redo.

Zellen markieren und **Auswahl bearbeiten** wählen: addieren, Prozentänderung, setzen, linear X/Y oder bilinear interpolieren, 3×3 glätten. Interpolation verwendet vollständige physikalische Achsen, ansonsten Zellindizes. Glättung mittelt Nachbarzellen nach Index aus einem unveränderten Ausgangssnapshot. Alle Zielwerte werden vorab auf Rohwertgrenzen geprüft; Übernahme als ein Undo-Schritt.

**Achsen / Log-Kanäle** bearbeitet Definition und physikalische Stützstellen, nicht Achsbytes in der Firmware. Nichtlineare XDF-Formeln bleiben ohne geprüfte Inverse schreibgeschützt. Definitions-/Notizänderungen haben Projektbackups, jedoch keinen Byte-Undo.

Kontextmenü: Favoriten und eigene Gruppen. Der virtuelle Katalog filtert Namen, Typen, Gruppen und Hex-/Dezimaladressen. **Ansicht → Hex-Editor: Dezimalwerte** schaltet Anzeige/Eingabe um. Mustersuche: `01 02 ??`, `bits:1010???? ????????`, `u16le:1500`, `s16be:-20`. Rohwertsuchen finden auch unaligned Vorkommen.

## AI Smart Map Transfer

1. Zielprojekt mit passenden Definitionen öffnen; **Werkzeuge → AI Smart Map Transfer**.
2. Gespeichertes Quellprojekt mit ORI/MOD-Änderungen laden.
3. Familie, Hardwarekennungen, Softwarestände und Prüfnachweis dokumentieren und Kompatibilität fachlich bestätigen. Erkannte Familien dürfen der Angabe nicht widersprechen.
4. **Änderungen vergleichen**, Kennfelder auswählen und die Zellvorschau prüfen.
5. Ausgewählte Kennfelder ausdrücklich übernehmen. JSON-Vorschau, Freigabe-Audit und Undo sind verfügbar.

Die Zuordnung erfolgt über eindeutige Namen/Funktionen bestätigter Definitionen, unabhängig von Adressen. Physikalisches Delta oder relative Änderung wird mit Zielskalierung und Zielbytefolge neu kodiert. Fehlende/abweichende Achsen, Dimensionen, Einheiten, nichtlineare Formeln, Überlappungen und Überläufe sperren die jeweiligen Kennfelder. Eine spätere Zieländerung macht die Vorschau ungültig. Änderungen außerhalb gewählter Kennfelder werden nicht kopiert.

**Verschobene Quelltabellen suchen** findet eindeutige identische Byteoberflächen als **ungeprüfte** Zieldefinitionen. Die bestehende Referenz-/Ähnlichkeitssuche bleibt verfügbar. Keine automatische Bestätigung der Semantik, kein Resampling unterschiedlicher Achsen. Manuell eingetragene Hardwarekennungen sind kein automatisch aus der Firmware gewonnener Hardwarebeweis.

## AI Log-to-Map Analyzer

**Werkzeuge → AI Log-to-Map Analyzer**: CSV öffnen, Kanalzuordnung und Quell-Einheiten prüfen, analysieren. Unterstützt sind einfache Tabellen mit Komma/Semikolon/Tab, UTF-8/Windows-1252 und bis zu 50 Vorspannzeilen, sofern bekannte Kanalnamen erkannt werden. Keine vorgetäuschte Unterstützung proprietärer Loggerformate.

Messgrößen: Drehzahl, Last, Ladedruck Soll/Ist, Lambda Soll/Ist, Zündwinkel, Ansaugluft-/Kühlmitteltemperatur und numerische Zeit. Unterstützte Druck-, Temperatur- und Zeiteinheiten werden umgerechnet. Fehlwerte werden gezählt und aus den betreffenden Berechnungen ausgeschlossen. Unbekannte Einheiten werden abgelehnt. Unterschiedliche deklarierte absolute/relative Druckbezüge werden nicht verglichen; bei beidseitig unbekanntem Bezug erscheint ein Hinweis.

Die Diagnose ist **regelbasiert**, keine neu trainierte Ursachen-KI. Sie meldet Abweichungen mit angegebenen Schwellen (Standard: 150 mbar und 0,05 Lambda). Kalibrierung, Sensorik, Regelung und Betriebszustand sind mögliche Prüfrichtungen, keine bewiesenen Ursachen. Keine automatischen Tuningwerte.

Für die Heatmap eine bestätigte Kennfelddefinition mit vollständigen monotonen X/Y-Achsen, Eingangssignalen und Einheiten auswählen. Auf-/absteigende Achsen sind unterstützt; Punkte außerhalb werden separat gezählt. Bilineare Gewichtung zeigt **Messpunktbelegung**, keine Verweildauer oder bewiesene tatsächliche ECU-Kennfeldwahl. Zellklick navigiert in den Editor. HTML-Export enthält Messwerte, Abweichungen und Heatmap.

## Projekte, Wiederherstellung und Automatisierung

Projektformat 1 bleibt lesbar; neue Metadaten sind optional. Originalbackup: `.ecustudio-originals/<SHA256>.bin`. Vorherige Projektdatei: `<projekt>.ecustudio.bak`. Alle zwei Minuten bei ungespeicherter Arbeit entsteht `<name>.recovery.ecustudio`, bei unbenannten Dateien unter `~/.ecu_studio_ai/recovery/`.

Recovery-Dateien normal als Projekt öffnen. Fehlt die Quelle, wird das hashgeprüfte Originalbackup verwendet. Existiert die Quelle mit abweichendem Hash, stoppt das Laden. Für den Transport Projekt **und** `.ecustudio-originals` gemeinsam kopieren. Hashintegrität ist Beschädigungserkennung, keine digitale Signatur. Atomare Writes synchronisieren die temporäre Datei vor dem Replace; keine Garantie gegen jeden Hardware-/Stromausfall.

Die feste Grenze von 200 Versionsständen entfällt; praktische Grenze: 256 MiB Projektgröße. Byte-Audit einschließlich Undo/Redo wird gespeichert. Der Undo-Stack selbst wird nach dem Wiederöffnen nicht rekonstruiert. Snapshot-Teilrestore berücksichtigt tatsächliche Zellbytes, keine Stride-Lücken.

Auch nach Undo auf null geänderte Bytes enthält die Sitzung neue Audit-Ereignisse. Diese bleiben speicherbedürftig, damit der Bearbeitungsverlauf nicht unbemerkt verloren geht.

**Datei → Projektdatenbank durchsuchen** (`Strg+Umschalt+D`) indexiert/sucht Projektmetadaten und Kennfeldnamen. Lokaler Index: `~/.ecu_studio_ai/projects.sqlite3`. Dateiprojekte bleiben maßgeblich. ZIP-Import liest ausgewählte BIN/ORI-Einträge begrenzt in den Speicher, ohne Pfade zu extrahieren.

Rezepte sind hashgebundene JSON-Operationen, kein ausführbarer Python-Code. GUI: **Bearbeitungsrezept ausführen** mit Bytevorschau. CLI:

```powershell
.\.venv\Scripts\python.exe -m ecu_studio.tools.next_workflows batch-recipe batch.json --report preview.json
.\.venv\Scripts\python.exe -m ecu_studio.tools.next_workflows batch-recipe batch.json --commit --report result.json
```

`batch.json`: `{"schema":1,"jobs":[{"project":"a.ecustudio","recipe":"recipe.json","output":"a-new.ecustudio"}]}`. Alle Jobs werden vor dem ersten Write geplant. Ausgaben müssen neu sein; Quellen bleiben erhalten. Jeder Projektwrite ist atomar. Bei Datenträgerfehlern können bereits fertig geschriebene **neue Ausgaben** verbleiben; keine Mehrdatei-Transaktion.

CLI-Transfer: `python -m ecu_studio.tools.next_workflows transfer --help`. Erst Vorschau; Schreiben erfordert deren exakten SHA-256-Freigabetoken, Kennfeldauswahl und neuen Projektpfad.

`core/plugins.py` bietet eine getestete Registry für vertrauenswürdige Import-/Prüffunktionen. Keine automatische Codeausführung aus Projekten/ZIPs. Pluginimporte sind ungeprüft; Prüfergebnisse dürfen keine Flashfreigabe setzen. Noch kein GUI-Pluginmanager.

## KI, Daten und Grenzen

Vorhandene JSON-Modellgewichte/Herkunftsdateien bleiben enthalten. **Keine neuen Gewichte werden als verbesserte reale Erkennung aktiviert.** Die Datenbank enthält 81 unbestätigte MS43-Definitionen sowie öffentliche Hinweise, keine verifizierte Multi-ECU-Trainingsbasis. Details: `DATABASE_REPORT_V111.json`, `TRAINING_STATUS_V111.json`.

Semantisches Training verlangt jetzt auch geprüfte Nutzungsrechte und unabhängige Firmware-Verwandtschaftsgruppen. ORI/MOD derselben Gruppe bleiben in derselben Faltung. Schema 2 ergänzt Herkunft/Hardware, ohne Bestätigungen bei unverändertem Reimport zu löschen. Geänderte MOD-Werte können nicht unter dem ORI-Hash als Referenz bestätigt werden.

KI-Dialog: `examples/training_provenance.template.json` nach tatsächlicher Prüfung ausfüllen/importieren. Hintergrundtraining erzeugt **inaktive** Kandidaten unter `~/.ecu_studio_ai/candidate-models/`; aktive Nutzergewichte werden nicht ersetzt.

`recognition/evaluation.py` prüft Firmware-/Definitionshashes, Rechte, bestätigte Labels und getrennte reale/synthetische Herkunft. Nahezu identische Images, gleiche Gruppen und wiederverwendete Blöcke über Splits werden abgelehnt. Exakte Layouttreffer statt bloßer Überdeckung; Familienauswertung und optional Family-Holdout. Precision/F1/Fehlalarme pro MiB sind nur bei explizit vollständiger Ground Truth bekannt. Vorlage: `examples/evaluation_manifest.template.json`.

Gepaarte API: `evaluate(manifest, {'baseline': callable, 'candidate': callable})`. `promotion_gate` verlangt mindestens drei unabhängige reale Gruppen und eine Verbesserung ohne zusätzliche Fehlalarme; es aktiviert nichts. GUI/CLI evaluiert standardmäßig den aktuellen Detektor. Historische v1.9-Überdeckungs-Proxys sind keine neue exakte Genauigkeitsmessung.

Quellenprüfung am 17.10.2026: [MS4X MS43](https://github.com/ms4x-net/ms43) unterscheidet GPL-3.0 für Definitionen/Dokumentation von OEM-Firmware zur Erhaltung/Reparatur. Das belegt keine pauschalen Trainingsrechte an ROMs oder unabhängig bestätigte Labels. Keine Firmware-/Ground-Truth-Übernahme daraus. Bestehende GPL-Attribution bleibt erhalten.

## Nachweise und offene Abnahme

`next-tests.xml`, `baseline-tests.xml`; `qa-artifacts/source-gui/` und `qa-artifacts/exe-gui/` mit isolierter Windows-Qt-Integration/Screenshots; `PERFORMANCE_V111.md` und Performance-JSONs; `baseline-detections.json`/`next-detections.json` für den identischen synthetischen Vergleichskorpus. GUI-Prüfung erfolgte per Windows-Offscreen-Rendering, nicht am Fahrzeug.

Offen: echte unabhängige Holdouts, neue fachlich geprüfte Referenzen für die gewünschten Familien, validierte fahrzeugspezifische Checksummen, weitere Loggeradapter, Transfer-Resampling und praktische Tunerabnahme. Generische Scanner behalten ihre Suchgrenzen: 16-Bit bis 8 MiB, zusätzliche Datentypen bis 2 MiB, ggf. auf bekannte Datenfenster beschränkt. Keine behauptete Vollsuche jedes Bytes einer 16-MiB-Datei. Memory Mapping wurde nicht eingeführt: Ladezeiten waren gegenüber der Analyse klein; immutable In-Memory-Originale wurden beibehalten.

Keine Flashfreigabe durch Softwaretests, Referenztreffer, Strukturwerte oder Transfer. Emissions-, Diagnose-, Wegfahrsperren- und Sicherheitsabschaltungen wurden nicht implementiert.
