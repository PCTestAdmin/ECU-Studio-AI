# Modellkarte – Konfidenz und Lernmodell

Stand: 01.11.2026 (ECU Studio AI 1.18.2 und Entwicklungszweig `feature/1.19-recognition`). Was die Prozentwerte an den Funden bedeuten, woher sie
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
Sie wurden nur an einem MSD80-Vollflash mit unvollständiger Community-XDF entwickelt (seit 1.19-Zweig zusätzlich
Datensatzköpfe und bedingte Sprünge: 84 von 99 exakt; bei 2D-Kennfeldern kein Code-Fund im Widerspruch zur XDF,
eine XDF-Kennlinie 1×6 liegt dort, wo der Code eine 6×6-Tabelle übergibt), Präzision dort nicht
messbar ([Bericht](ANALYSE_2026-11-01.md)). Eine Quote wird erst mit einer vollständigen Referenz eingetragen; bis
dahin zeigt die App für diese Klassen keine Prozentzahl.

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

## 2a. Reproduzierbares Training (Entwicklungszweig 1.19)

Das ausgelieferte Modell vom 19.10.2026 ist **nicht reproduzierbar**: Die Trainingsdatei (JSONL) und das Skript,
das sie erzeugt hat, liegen weder im Repository noch lokal vor; die Quellordner (Hyundai SIM2K, MSS54, TunerPro)
sind lokal leer oder ohne Herkunftsangabe. Deshalb gibt es jetzt einen festen Ablauf:

1. **Datensatz** – `python -m ecu_studio.tools.build_candidate_dataset MANIFEST.json DATA.jsonl`.
   Der Scan läuft **ohne mitgelieferte Definitionen** (die MS43-XDF würde sonst die Antworten verraten) und **ohne
   das ausgelieferte Modell** (sein Schwellwert würde die Kandidaten vorsortieren). Label wie bisher: Kandidat
   beginnt exakt an einem Referenzobjekt. `DATA.meta.json` hält je Paar SHA-256 von BIN und Referenz, Quelle,
   Lizenz, Rolle, Zahl der Kandidaten und Treffer sowie den SHA-256 der JSONL fest. Keine Firmwarebytes, keine Namen.
2. **Training** – `python -m ecu_studio.tools.train_candidate_model DATA.jsonl --log LOG.json [--seed N]`.
   - Trainiert wird nur auf Rollen aus `--roles` (Standard `training`) und nur mit **vollständiger** Referenz
     (bei Teil-Referenzen sind die Negativbeispiele unbekannt). Rolle `test` wird **nie** angepasst oder zur
     Auswahl genutzt, nur am Ende mit dem fertigen Modell gemessen („blind“).
   - Bewertung *leave-one-family-out*: Softwarestände einer Familie liegen nie auf beiden Seiten. Die Skalierung
     der Merkmale stammt je Durchgang nur aus den Trainingsfamilien.
   - Das ausgelieferte Modell wird auf denselben zurückgehaltenen Daten gemessen.
   - **Ersetzungsregel:** nur mit `--promote` **und** wenn die mittlere AUC um mindestens 0,01 steigt und die
     Präzision bei 80 % Trefferquote in keiner Familie um mehr als 2 Punkte sinkt. Sonst wird das neue Modell nur
     als Kandidat neben die Daten geschrieben.
   - Das Protokoll enthält Seed, Daten-Hash, NumPy-/scikit-learn-Version, alle Messwerte und die Gate-Entscheidung.

## 2b. Nachtraining am 01.11.2026: Modell **nicht** ersetzt

Lokal vorhanden waren nur zwei Paare mit vollständiger Referenz, beide Siemens C167: MS43 430069 (eigene Datei
des Nutzers, Definition ms4x-net, GPL-3.0) und MS42 0110C6 (Definition ms4x-net, GPL-3.0). **Korrektur
(Validierung 01.11.2026):** Die MS42-BIN stammt aus dem Repository ms4x-net/ms42; ihr Herkunftsvermerk
(`.qa/v113-research/ms42-provenance.json`) erlaubt nur eine Kompatibilitäts-Regression, **kein Training und keine
Weitergabe**. Der Lauf hätte sie nicht als *training* führen dürfen. Das Kandidatenmodell wurde nicht übernommen,
seine lokalen Artefakte sind gelöscht, und der Datensatzbau verlangt jetzt `training_allowed: true` je Paar. Weitere lokale Paare (ME9, ME9.2.1, MS45, MED17, MED9, ME7) haben **keine dokumentierte Herkunft** und
wurden deshalb nicht zum Training verwendet, nur zur lokalen Messung (siehe Entwicklungsbericht).

| Ausgelassene Familie | Kandidaten | Treffer | AUC neu | AUC ausgeliefert | Präzision @ 80 % neu | ausgeliefert |
|---|---:|---:|---:|---:|---:|---:|
| Siemens MS42 | 167 | 53 | 0,825 | 0,844 | 58,1 % | 53,1 % |
| Siemens MS43 | 61 | 13 | 0,883 | 0,893 | 40,7 % | 47,8 % |

Daten-SHA-256 `711107c0…`, Seed 0, NumPy 2.5.4, scikit-learn 1.9.1. **Gate nicht bestanden** (mittlere AUC 0,854
gegenüber 0,869). Der Vergleich begünstigt das ausgelieferte Modell, weil es MS4x-Daten schon gesehen hat; ein neues
Modell aus nur zwei verwandten Familien ist trotzdem nicht belegbar besser. Das ausgelieferte Modell bleibt.
Gradient Boosting erreichte auf MS43 AUC 0,962, aber mit 13 Treffern ist das keine belastbare Aussage.

**Recherche neuer Trainingsdaten (Stand 21.10. und 01.11.2026):** Rechtmäßig nutzbare Paare aus Originalfirmware und
vollständiger Definition für Bosch MD1/MG1/MED17.x/EDC17, Continental Simos/SID oder Delphi gibt es nicht; die
öffentlichen Uploads Dritter haben keine Lizenz (§ 69c UrhG) und werden nicht verwendet. Offene Quellen mit
vollständiger Referenz sind Open-Source-Steuergeräte: rusEFI (GPL-3.0, bereits im Kalibrier-Ranker), Speeduino
(Definition GPL-2.0, Abstimmungen CC BY-NC 4.0 – „nicht kommerziell“, für ein mitgeliefertes Modell rechtlich
zu klären). Diese Daten beschreiben keine OEM-Steuergeräte; ihr Nutzen für Bosch/Siemens ist unbelegt.

## 2b′. Überprüfung der Modellentscheidung (Validierung 01.11.2026)

Nachgerechnet mit denselben Daten und Familien-Auslassung (Bootstrap, 2000 Ziehungen):

| Ausgelassene Familie | AUC-Differenz neu − ausgeliefert | 95-%-Intervall | Brier neu | Brier ausgeliefert | Basisrate | mittlerer Score neu / ausgeliefert |
|---|---:|---|---:|---:|---:|---|
| Siemens MS42 | −0,019 | [−0,069; +0,027] | 0,148 | 0,157 | 0,32 | 0,33 / 0,40 |
| Siemens MS43 | −0,010 | [−0,092; +0,070] | 0,170 | 0,125 | 0,21 | 0,42 / 0,33 |

- **Entscheidung bestätigt, aber aus Datenmangel:** Beide Intervalle enthalten 0 – keines der Modelle ist
  nachweisbar besser. Weil die Beweislast beim neuen Modell liegt, bleibt das ausgelieferte.
- **Unbekannte Familien sind damit nicht bewertet:** MS42 und MS43 sind Schwesterfamilien (Siemens C167, ähnlicher
  Datensatzaufbau). Die Auslassung einer Familie misst hier die Übertragung auf einen nahen Verwandten, nicht auf
  Bosch, TriCore oder PowerPC.
- **Kalibrierung:** Der mittlere Score liegt bei beiden Modellen in der Nähe der Basisrate, aber mit Abweichungen bis
  0,21 (neu, MS43). Die App zeigt deshalb nicht den Score, sondern die familienweise gemessene Trefferquote des
  Score-Bereichs (`heldout_rate_table`).
- **Datenüberschneidung:** keine identischen Merkmalszeilen zwischen den Familien. Das ausgelieferte Modell hat MS4x
  bereits im Training gesehen; der Vergleich begünstigt es.
- **Klassenverteilung:** 228 Kandidaten, 66 Treffer (MS42 32 %, MS43 21 %); das Training gewichtet die Klassen aus.
- **Herkunft des ausgelieferten Modells (offen):** Es wurde am 19.10.2026 unter anderem mit MS42 0110C6 (Vermerk:
  kein Training) und mit Hyundai-SIM2K-, MSS54- und TunerPro-Paaren ohne dokumentierte Herkunft trainiert; diese
  Quellen sind lokal nicht mehr vorhanden. Das Modell enthält keine Firmwarebytes, nur 20 Gewichte. Ob es
  ausgeliefert bleiben soll oder die Datenmuster-Bewertung ohne Modell laufen soll, entscheidet der Nutzer.

### Verifiziertes Nutzerfeedback (Konzept, nicht umgesetzt)

Die Prüfliste speichert Bestätigungen und Ablehnungen im Projekt. Daraus ließen sich später Trainingsbeispiele
gewinnen, aber **nur kontrolliert**:

1. **Kein automatisches Lernen.** Entscheidungen bleiben im Projekt. Ein Export in einen Datensatz geschieht nur auf
   ausdrücklichen Befehl und nur für Dateien, die der Nutzer für Training freigibt (`training_allowed`).
2. **Gruppierung nach Firmware:** Alle Beispiele einer Originaldatei (SHA-256 im Prüfprotokoll) bilden eine Gruppe
   und liegen nie auf beiden Seiten einer Auswertung.
3. **Verzerrung beachten:** Bestätigt und abgelehnt wird nur, was die Erkennung angeboten hat. Feedback ergänzt
   daher Referenzen mit vollständiger Definition, ersetzt sie aber nicht. Nicht entschiedene Funde sind keine
   Negativbeispiele.
4. **Gleiche Ersetzungsregel:** Ein Modell mit Feedback ersetzt das ausgelieferte nur über das bestehende Gate,
   gemessen an Familien, die nicht im Feedback vorkommen.

## 2c. Code- und Strukturbelege sind kein Lernmodell

Funde aus Programmcode (TriCore-Interpolationsaufrufe), Kopf-Datensätzen und Achsen-Arrays werden **nicht** vom
Lernmodell bewertet; sie bilden Ebene 2 der Erkennung (`core/fusion.py`). Das Lernmodell bewertet nur Ebene 3
(Datenmuster). Ein Datentyp wird nur dann als belegt angezeigt, wenn die Ladebefehle der Interpolationsroutine
ihn festlegen; sonst stehen die anderen möglichen Lesarten am Fund (`dtype_alternatives`).

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
