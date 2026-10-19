# ECU Studio AI v1.10 – Reales zusätzliches KI-Training mit klarer Gültigkeitsgrenze

Diese Version basiert auf **v1.9**. Es wurde ein **neues strukturelles Lernmodell** tatsächlich trainiert und in der präziseren Kandidatenbewertung aktiviert. Das ist **kein** trainiertes Modell zur zuverlässigen Identifikation von Funktionen wie Drehmoment, Einspritzung, Schaltkennlinie oder Ladedruck in fremden Firmwareständen.

## Was tatsächlich trainiert wurde

- Modell: `src/ecu_studio/recognition/data/structure_rejector_v110.json` (24 kleine ExtraTrees, keine Pickles/ausführbaren Modelle).
- Trainingsmenge: 4.000 eigenständig erzeugte 2D-Rohwertoberflächen: 2.000 mit nichtlinearen, kalibrierungsähnlichen Strukturen und 2.000 negative Beispiele (Rauschen, Zähler, wiederholte Achsen, abrupte Stufen, einzelne Ausreißer usw.).
- Validierung: 1.000 separat generierte Samples (500 je Klasse); Schwelle wurde ausschließlich anhand der negativen Validierungsfälle bestimmt.
- Synthetischer Holdout: 1.000 weitere separat generierte Samples mit bisher nicht im Training verwendeten Generatorvarianten. Train und Holdout sind **nicht** voneinander kopierte Zellen oder Oberflächen.
- Das Modell lässt sich unter Windows mit NumPy ausführen; `scikit-learn` wird **nur zum erneuten ExtraTrees-Training** benötigt.
- Metriken: `TRAINING_REPORT_V110.json` enthält alle Anzahlen und Kennzahlen und macht kenntlich, dass **0 reale Firmware-Holdouts und 0 geprüfte Typ-Labels** vorliegen.

**Wichtig:** Ein synthetischer Test misst ausschließlich, wie gut das Modell künstliche Oberflächen von künstlichen Gegenbeispielen trennt. Die Zahlen sind **keine ECU-/TCU-Kennfeld-Trefferrate** und keine validierte Eignung zum automatischen Ausschließen echter Kennfelder. Darum ergänzt das Modell nur eine vorsichtige Rankingwertung und einen Hinweistext; es bestätigt nichts, vergibt keine Funktionsnamen und verwirft keine Kandidaten allein durch den neuen KI-Score.

## Zusätzlich verbesserte Qualitätssicherung

- Die bestehende semantische Klassifikation benutzt nun die OOD-Normierung **genau einmal**. Das korrigiert einen Fehler, durch den bereits normalisierte Merkmale nochmals umgerechnet wurden.
- Überwachte Modelle aus fachlich geprüften Kennfeldern müssen nun zusätzlich zu der vorherigen Split-Prüfung alle unabhängigen Firmwaregruppen einmal vollständig als Testgruppe auslassen (`Leave-One-Firmware-Out`). Eine gute zufällige Firmwareauswahl genügt nicht mehr.
- Die bisherige MS43-PCA-Strukturvorlage bleibt unberührt. Es wird **keine** durch XDF-Namen fingierte Typ-Freigabe erstellt.

## Training lokal erneut ausführen

Unter Windows mit Python 3.11 oder 3.12 nach dem Entpacken:

```bat
py -m pip install -e ".[train]"
set PYTHONPATH=%CD%\src
py -m ecu_studio.recognition.train_structure_rejector --out src\ecu_studio\recognition\data\structure_rejector_v110.json --report TRAINING_REPORT_V110.json
```

Oder `train_structure_windows.bat` verwenden. Die Daten entstehen deterministisch im Generator. Es werden keine echten ECU-Firmwares heruntergeladen. Alternativ `--algorithm linear` ohne scikit-learn (wesentlich schwächere Modellqualität auf diesen Tests). Die Ausgabedatei kann mit `StructureRejector.load()` auf Schäden überprüft werden.

Weitere Tests: `test_v110_windows.bat`. Sie enthalten die bestehenden Regressionstests und die neuen v1.10-Testfälle.

## Was für echtes ECU-/TCU-Kennfeldtraining noch fehlt

- Genehmigt nutzbare, vollständige und exakt aufeinander bezogene `.bin`/`.ori` + XDF/A2L-Kombinationen verschiedener Firmwarestände.
- Unabhängig überprüfte Kennfeldadressen, Typen, Achsen, Faktoren, Funktionen (bei TCUs einschließlich Layout der Schaltkurven).
- Ein firmwaregruppengetrennter Blindtest mit echten bislang ungesehenen Images. Dabei Definition-Recall, lokationsbasierte Präzision und semantische Klassengenauigkeit getrennt messen.

Öffentlich auffindbare ROMs wurden **nicht** ungeprüft in die Trainingsdaten übernommen. Verfügbare Community-Definitionen beweisen ihre Adressen und Funktionen für neue Dateien nicht automatisch.

**Sicherheit:** Die neue Strukturwertung ist keine Checksummen- oder Flashfreigabe. Originaldateien und Exportfreigaben unverändert separat kontrollieren. GUI wurde in dieser Linux-Umgebung ohne PySide6 **nicht** auf Windows live getestet.
