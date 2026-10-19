# Modellkarte – ECU Studio AI v1.5

## Was wurde tatsächlich trainiert?

- Modell: PCA/SVD-basierter 80-Merkmale-Strukturembedding mit 12 Projektionskomponenten.
- Daten: 67 nicht triviale reale Rohwertoberflächen aus einer 512-KiB-Siemens-MS43-Datei mit Softwarekennung 430069. Die Zuordnung der Beispielbereiche stammt aus einer öffentlichen, bisher nicht unabhängig validierten MS4X-XDF-Metadatenvorschau. Die ORIGINAL-BIN wird NICHT ausgeliefert.
- Aus 81 importierten Kennfeld-Hinweisen wurden 67 Trainingsproben angenommen. 11 waren inhaltsarm, drei hatten für dieses Modell ungeeignete Dimensionen.
- Trainiert sind **strukturelle Ähnlichkeiten, keine ECU-Funktionen**. Die in den Daten vorhandenen XDF-Namen dienen ausschließlich als Namen der nächstgelegenen Referenzoberfläche, NICHT als erkannte Funktion der Zielstelle.
- Speicherformat: JSON (kein Pickle), 80-dimensionale Normierung, PCA-Komponenten, relative Referenzcodes, Namen/Offsets, Quelle und Trainingsbericht.
- Training auf bereitgestelltem realem Abbild; keine Erzeugung künstlicher positiver Kennfeldlabels.

## Aussagekraft

- 67 Trainingsbeispiele stammen aus **einem** Softwarestand. Es gibt keinen Test auf unabhängigen Firmwareständen. Deshalb wird **keine** Kennfeld-Funktionsgenauigkeit, Generalisierbarkeit oder kalibrierte Wahrscheinlichkeit behauptet.
- Die P90-Kennzahl der Leave-One-Out-Nachbardistanzen auf derselben Firmware ist KEIN validierter Fehler- oder OOD-Wahrscheinlichkeitswert.
- Auf GS20, MD1, MG1 oder einem anderen Softwarestand wird dieses Modell nicht als benennendes Modell eingesetzt. Bei unpassender Familien-/Softwarekennung erfolgt **Abstention**.
- Es werden weder automatische Änderungen vorgenommen noch Checksummen oder Flashbarkeit bestätigt.

## Sicheres überwacht trainiertes Modell (noch nicht verfügbar)

`python -m ecu_studio.tools.safe_learning train-safe ...` verlangt für **eine Familie** mindestens zwei Funktionsklassen, pro Klasse zwölf unabhängig bestätigte Kennfelder aus mindestens vier Firmwareständen. Firmwaregruppen dürfen sich in Train/Test nicht überschneiden. Erst bei ausreichender klassenspezifischer Präzision, Trefferquote und Holdout-Qualität erfolgt eine Modellausgabe. In der mitgelieferten Datenbank gibt es **0** solche fachlich bestätigten Karten – daher wurde **kein** sicheres Funktionsklassifikationsmodell vorgetäuscht.

## Sichere Nachtrainingsstrategie

1. Richtige, softwarestandspezifische BIN+XDF/A2L-Paare mit SHA-256 und Quellenachweis importieren; bei MD1/MG1 sind exakte ECU-Adresssegmente nötig.
2. Unbekannte/mehrdeutige Treffer aus `ACTIVE_LEARNING_REVIEW_QUEUE.json` anhand unabhängiger Referenzen prüfen.
3. Ausschließlich fachlich bestätigte Beispiele in den Trainingskatalog freigeben; nie automatisch XDF-Import oder ML-Vorschläge als Ground Truth markieren.
4. Train/Test nach realen Firmware-Hashes getrennt halten, Fehler nach Klasse und ECU-Familie erfassen und das Modell bei Qualitätsabfall verwerfen.
5. Keine automatische Tuning-Bearbeitung, kein Flash ohne separate Prüfungen.

## Ergänzung v1.10 – synthetisch trainierter Struktur-Rejector

Das neue Modell `structure_rejector_v110.json` wurde auf geometrisch simulierten Oberflächen mit positiven und harten negativen Beispielen trainiert. Es ist **kein** semantischer ECU-Kennfeldklassifizierer, kennt keine Hardware-/Softwarestände und erreicht derzeit **0 echte Firmware-Holdouts**. Deshalb werden seine Scores nicht als echte Kennfeldwahrscheinlichkeiten angegeben. Das Modell kann vorhandene Strukturkandidaten geringfügig umsortieren und zeigt ihnen einen ergänzenden, ausdrücklich ungeprüften KI-Strukturwert an. Ein niedriger Wert entfernt keine sonst plausiblen Kennfelder. Die separate Release-Sperre für überwacht trainierte, geprüfte Typmodelle bleibt aktiv.
