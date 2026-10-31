# Modellkarte – Konfidenz und Lernmodell

Stand: 31.10.2026 (ECU Studio AI 1.17.0 und nächstes Update). Was die Prozentwerte an den Funden bedeuten, woher sie
kommen und wo ihre Grenzen liegen.

## 1. Gemessene Trefferquote je Beweisart

Jeder automatische Fund gehört zu einer **Evidenzklasse**, zum Beispiel Code-Verweis mit Achsen, Kopf-Datensatz,
Achsen-Array oder Datenmuster (`core/confidence.py`). Für jede Klasse wurde gemessen, welcher Anteil der Funde exakt
am Start eines Referenzobjekts beginnt (`tools/calibrate_confidence.py`, Daten in
`recognition/data/confidence_calibration.json`, gemessen am 21.10.2026).

| Evidenzklasse | Funde | Trefferquote | gemessen an |
|---|---:|---:|---|
| `code:2d:axes2` – Code-Verweis + zwei Achsen | 227 | 100 % | MS43 |
| `code:2d:axis1` – Code-Verweis + eine Achse (Kennfeld) | 12 | 100 % | MS43 |
| `code:1d:axis1` – Code-Verweis + Achse (Kennlinie) | 159 | 98,7 % | MS43 |
| `code:2d:noaxes` – Code-Verweis ohne Achsen | 35 | 97,1 % | MS42, MS43 |
| `header:nxny:shape` – Kopf-Datensatz, Form belegt | 435 | 97,7 % | MS42, MS43, unbekannte Images |
| `curve:record` – Kennlinien-Datensatz | 543 | 92,3 % | unbekannte Images |
| `axis:record` – Achse aus Kopf-Datensatz | 2461 | 90,7 % | MS42, MS43, unbekannte Images |
| `header:nxny` – Kopf-Datensatz | 510 | 82,2 % | MS42, MS43, unbekannte Images |
| `axis:count` – Achsen-Array mit Anzahl-Präfix | 2538 | 57,0 % | MS42, MS43, unbekannte Images |
| `pitch` – nur Zeilenabstand (Datenmuster) | 1135 | 23,2 % | MS42, MS43, unbekannte Images |
| `raster` – altes Raster | 80 | 15,0 % | MS42, MS43, unbekannte Images |

Aus der Quote folgt die angezeigte Stufe: **gesichert** ab 90 %, **wahrscheinlich** ab 60 %, sonst **Vermutung**.
Eine Klasse mit weniger als 20 gemessenen Funden gilt als **nicht kalibriert** und bekommt keine Prozentzahl.

**Noch nicht kalibriert** sind die TriCore-Klassen des nächsten Updates: `code:call:2d`/`code:call:1d` (Kennfeld,
Achsen und Zelltyp aus einem Interpolationsaufruf) und `code:call-pre:2d` (Achsen aus vorangehenden Achsensuchen).
Sie wurden nur an einem MSD80-Vollflash mit unvollständiger Community-XDF entwickelt: dort 0 Widersprüche zur
Referenz, aber keine Präzision messbar ([Bericht](ANALYSE_2026-10-30.md)). Eine Quote wird erst mit einer
vollständigen Referenz eingetragen.

## 2. Lernmodell für Datenmuster-Funde (seit 1.16)

Nur Funde, die **allein** auf Datenmustern beruhen (`pitch`, `raster`), bewertet zusätzlich ein Lernmodell
(`core/candidate_model.py`, Daten `recognition/data/candidate_model.json`, trainiert am 19.10.2026). Code- und
achsenbelegte Funde behalten ihre gemessene Klassenquote.

- **Modell:** logistische Regression über 20 Strukturmerkmale (Größe, Zellbreite, Glätte in Zeilen und Spalten,
  Wiederholung, Wertebereich, Ränder, Ausrichtung …), als JSON gespeichert (kein Pickle).
- **Daten:** 2684 Kandidaten, davon 328 Treffer, aus Siemens MS43 430069 und MS42 0110C6, Hyundai SIM2K ×4,
  BMW MSS54 ×12 (Teilabbilder) und TunerPro-Paaren (Porsche/Peugeot/Renault ×6), jeweils mit Definition.
  Das Modell enthält keine Firmwarebytes.
- **Prüfung:** Jede Familie wurde beim Training ausgelassen und danach an ihr gemessen (*family-out*):

| Ausgelassene Familie | Kandidaten | Basisquote | Präzision bei 80 % Trefferquote | AUC |
|---|---:|---:|---:|---:|
| Hyundai SIM2K | 1385 | 13,6 % | **34,2 %** | 0,83 |
| BMW MSS54 | 925 | 7,1 % | **32,1 %** | 0,91 |
| alte 8-Bit-Motronic | 146 | 4,8 % | **35,3 %** | 0,92 |
| Siemens MS4x | 228 | 28,9 % | **49,5 %** | 0,84 |

- **Angezeigte Quote:** Für jeden Score gilt die *family-out* gemessene Trefferquote seines Score-Bereichs (zehn
  Bereiche, 0,4 % bis 37,9 %). Das ist ein Messwert auf diesen Familien, keine Garantie für neue Familien.
- **Aussortieren:** Funde unter Score 0,042 werden verworfen. Diese Bereiche trafen *family-out* nur 0,4–0,7 %
  (etwa 2 von 543). Auf MS43/MS42 stieg die Präzision dadurch von 76 auf 80 % bzw. von 67 auf 72 %; die exakten
  Treffer blieben unverändert (197 bzw. 22).

## 3. Grenzen

- Die Klassenquoten stammen überwiegend aus Siemens-C167-Images (MS42/MS43) und unbekannten Images. Für andere
  Familien sind sie ein Richtwert.
- Weder Klassenquoten noch Lernmodell erkennen **Funktionen**: Namen, Einheiten und Bedeutung kommen nur aus
  Definitionen oder eigener Prüfung.
- Neue Familien brauchen eigene, rechtmäßig nutzbare Referenzpaare. Dann lassen sich die Quoten neu kalibrieren
  (`tools/calibrate_confidence.py`) und das Modell nachtrainieren (`tools/train_candidate_model.py`).

---

# Frühere Modelle (Historie)

## Strukturembedding v1.5

### Was wurde tatsächlich trainiert?

- Modell: PCA/SVD-basierter 80-Merkmale-Strukturembedding mit 12 Projektionskomponenten.
- Daten: 67 nicht triviale reale Rohwertoberflächen aus einer 512-KiB-Siemens-MS43-Datei mit Softwarekennung 430069. Die Zuordnung der Beispielbereiche stammt aus einer öffentlichen, bisher nicht unabhängig validierten MS4X-XDF-Metadatenvorschau. Die ORIGINAL-BIN wird NICHT ausgeliefert.
- Aus 81 importierten Kennfeld-Hinweisen wurden 67 Trainingsproben angenommen. 11 waren inhaltsarm, drei hatten für dieses Modell ungeeignete Dimensionen.
- Trainiert sind **strukturelle Ähnlichkeiten, keine ECU-Funktionen**. Die in den Daten vorhandenen XDF-Namen dienen ausschließlich als Namen der nächstgelegenen Referenzoberfläche, NICHT als erkannte Funktion der Zielstelle.
- Speicherformat: JSON (kein Pickle), 80-dimensionale Normierung, PCA-Komponenten, relative Referenzcodes, Namen/Offsets, Quelle und Trainingsbericht.
- Training auf bereitgestelltem realem Abbild; keine Erzeugung künstlicher positiver Kennfeldlabels.

### Aussagekraft

- 67 Trainingsbeispiele stammen aus **einem** Softwarestand. Es gibt keinen Test auf unabhängigen Firmwareständen. Deshalb wird **keine** Kennfeld-Funktionsgenauigkeit, Generalisierbarkeit oder kalibrierte Wahrscheinlichkeit behauptet.
- Die P90-Kennzahl der Leave-One-Out-Nachbardistanzen auf derselben Firmware ist KEIN validierter Fehler- oder OOD-Wahrscheinlichkeitswert.
- Auf GS20, MD1, MG1 oder einem anderen Softwarestand wird dieses Modell nicht als benennendes Modell eingesetzt. Bei unpassender Familien-/Softwarekennung erfolgt **Abstention**.
- Es werden weder automatische Änderungen vorgenommen noch Checksummen oder Flashbarkeit bestätigt.

### Sicheres überwacht trainiertes Modell (noch nicht verfügbar)

`python -m ecu_studio.tools.safe_learning train-safe ...` verlangt für **eine Familie** mindestens zwei Funktionsklassen, pro Klasse zwölf unabhängig bestätigte Kennfelder aus mindestens vier Firmwareständen. Firmwaregruppen dürfen sich in Train/Test nicht überschneiden. Erst bei ausreichender klassenspezifischer Präzision, Trefferquote und Holdout-Qualität erfolgt eine Modellausgabe. In der mitgelieferten Datenbank gibt es **0** solche fachlich bestätigten Karten – daher wurde **kein** sicheres Funktionsklassifikationsmodell vorgetäuscht.

### Sichere Nachtrainingsstrategie

1. Richtige, softwarestandspezifische BIN+XDF/A2L-Paare mit SHA-256 und Quellenachweis importieren; bei MD1/MG1 sind exakte ECU-Adresssegmente nötig.
2. Unbekannte/mehrdeutige Treffer aus der Prüfliste (früher `docs/history/ACTIVE_LEARNING_REVIEW_QUEUE.json`, bis v1.15.0 in der Git-Historie) anhand unabhängiger Referenzen prüfen.
3. Ausschließlich fachlich bestätigte Beispiele in den Trainingskatalog freigeben; nie automatisch XDF-Import oder ML-Vorschläge als Ground Truth markieren.
4. Train/Test nach realen Firmware-Hashes getrennt halten, Fehler nach Klasse und ECU-Familie erfassen und das Modell bei Qualitätsabfall verwerfen.
5. Keine automatische Tuning-Bearbeitung, kein Flash ohne separate Prüfungen.

## Synthetisch trainierter Struktur-Rejector (v1.10)

Das Modell `structure_rejector_v110.json` wurde auf geometrisch simulierten Oberflächen mit positiven und harten negativen Beispielen trainiert. Es ist **kein** semantischer ECU-Kennfeldklassifizierer, kennt keine Hardware-/Softwarestände und erreicht derzeit **0 echte Firmware-Holdouts**. Deshalb werden seine Scores nicht als echte Kennfeldwahrscheinlichkeiten angegeben. Das Modell kann vorhandene Strukturkandidaten geringfügig umsortieren und zeigt ihnen einen ergänzenden, ausdrücklich ungeprüften KI-Strukturwert an. Ein niedriger Wert entfernt keine sonst plausiblen Kennfelder. Die separate Release-Sperre für überwacht trainierte, geprüfte Typmodelle bleibt aktiv.
