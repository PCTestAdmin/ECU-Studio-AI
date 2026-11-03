# Modellkarte – Konfidenz und Lernmodell

Stand: 03.11.2026 (ECU Studio AI 1.18.2 und Entwicklungszweig `feature/1.19-recognition`). Was die Prozentwerte an den Funden bedeuten, woher sie
kommen und wo ihre Grenzen liegen.

> **03.11.2026 – Lernmodell für Datenmuster im 1.19-Zweig deaktiviert.** Die Nutzungsberechtigung seiner
> Trainingsdaten ist nicht nachweisbar (§ 2d). Die Datei bleibt zur Nachvollziehbarkeit unverändert im Repository,
> wird aber im Scan nicht mehr angewendet. Abschnitte 2–2b′ beschreiben das Modell, wie es bis 1.18.2 lief.

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

## 2. Lernmodell für Datenmuster-Funde (1.15.0 bis 1.18.2; im 1.19-Zweig deaktiviert, § 2d)

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

## 2d. Herkunftsprüfung aller gelernten Daten und Deaktivierung (03.11.2026)

**Geprüfte Artefakte** in `recognition/data/` (nur vorhandene Vermerke, Git-Historie und öffentliche
Repository-Metadaten; nichts heruntergeladen):

| Artefakt | Wirkung im Scan | Trainings-/Messdaten | Nachweis | Status 1.19 |
|---|---|---|---|---|
| `candidate_model.json` (19.10.2026) | verwirft Datenmuster-Funde unter Score 0,042, ersetzt deren Quote | MS43 430069; MS42 0110C6; Hyundai SIM2K ×4; BMW MSS54 ×12; TunerPro Porsche/Peugeot/Renault ×6 | **nicht nachweisbar** (siehe unten) | **deaktiviert** |
| `structure_rejector_v110.json` | Strukturprüfung | nur synthetisch erzeugte Flächen | erzeugt im Projekt | aktiv |
| `calibration_ranker_v113.json` | Reihung von Strukturvorschlägen | rusEFI, Commit `cf2988a6`, 12 Quelldateien, mitgeliefert in `training/sources` | GPL-3.0, Quellen und Lizenz beiliegend | aktiv |
| `ms43_430069_structure_model.json` | Formähnlichkeit nur für genau diesen Softwarestand, kein Funktionsnachweis, enthält sich bei Unsicherheit | vom Nutzer bereitgestellter MS43-430069-Fullread + XDF (GPL-3.0) | Bereitstellung durch den Nutzer dokumentiert, **ausdrückliche Trainingsfreigabe nicht** | aktiv – Bestätigung offen |
| `confidence_calibration.json` (21.10.2026) | angezeigte Quote je Evidenzklasse | **Messung**, kein Training: MS43, MS42, ME9, ME9.2.1, MS45, EDC17CP09 (A2L), SIM2K, MSS54 | Messwerte (Zählungen); MS42-Vermerk erlaubt Regression | aktiv – Bewertung offen |
| `ms41_ms42_samples.tsv`, `ms43_430069_3d_sample.tsv` | Beispiel-Metadaten | aus ms4x-net-XDF (GPL-3.0), keine Firmwarewerte | GPL-3.0 | aktiv |

**Quellen des Lernmodells im Einzelnen:**

- **MS42 0110C6:** Herkunftsvermerk der BIN „read-only compatibility regression, not training or redistribution“ –
  **ausdrückliches Trainingsverbot.**
- **Hyundai SIM2K ×4:** Die erste Fassung der Modelldatei (19.10.2026, Commit `3995ed7`) nannte
  `naamons/HyundaiN-TuningLib (GPL-3.0)`. Das Repository steht laut GitHub unter GPL-3.0, die Lizenz deckt aber die
  Definitionen (XDF/XML); ob die verwendeten BIN-Dateien daraus stammen und unter dieser Lizenz stehen, ist nicht
  belegt. Die lokalen SIM2K-Daten haben keine Ursprungsangabe.
- **BMW MSS54 ×12 (Teilabbilder):** Erste Fassung nannte `saildot4k/MSS54-XDFs`; das Repository hat **keine Lizenz**.
- **TunerPro Porsche/Peugeot/Renault ×6:** keine Quelle angegeben.
- **MS43 430069:** vom Nutzer bereitgestellt; ausdrückliche Trainingsfreigabe nicht dokumentiert.
- Am 31.10.2026 (Commit `8267e83`) wurden die Quellenangaben aus der Modelldatei entfernt („Statements about where
  non-bundled reference and training files came from are removed“). Diese Historie bleibt hier festgehalten.

**Folge:** Die Nutzungsberechtigung ist nicht nachweisbar. `core/candidate_model.py` wendet seit diesem Stand nur
noch ein Modell an, das `training_data_cleared: true` trägt; das setzt nur der Trainer, und nur für Zeilen aus Paaren
mit `training_allowed: true`. Das mitgelieferte Modell trägt die Markierung nicht und wird nicht angewendet. Der
Scanbericht und die Scanmeldung nennen den Grund.

**Gemessene Wirkung der Deaktivierung** (15 reale Paare, `benchmark_suite`, gleicher Rechner, gegen den Stand mit
Modell):

| Paar (vollständige Referenz) | exakt 2D | Präzision 2D mit → ohne Modell | Falschfunde | Recall 2D |
|---|---|---|---|---|
| MS43 430069 | 197 = 197 | 79 % → 75 % | 65 → 83 | 66 % → 67 % |
| MS42 0110C6 | 22 = 22 | 72 % → 66 % | 40 → 58 | 50 % → 55 % |
| ME9 770115XE | 98 = 98 | 62 % → 42 % | 81 → 190 | 56 % → 59 % |
| ME9.2.1 725D601B | 170 = 170 | 72 % → 64 % | 94 → 145 | 54 % → 56 % |
| MS45 4520D30S | 30 = 30 | 66 % → 38 % | 42 → 150 | 18 % → 20 % |

Exakte Kennfelder, Datentypen, Achsen, Achsadressen und Kennlinien sind auf allen 15 Paaren **unverändert**. Es
erscheinen mehr ungeprüfte Datenmuster-Funde (Teil-Referenzen: MSD80 1116 → 1246, MED17 je +41 bis +58); sie tragen
die gemessene Klassenquote (`pitch` 23 %, `raster` 15 %, Stufe „Vermutung“). In der synthetischen Negativkontrolle
„Rampen“ steigen die Falschfunde von 1 auf 10, die übrigen Negativkontrollen bleiben bei 0.

**Neues Modell aus freigegebenen Daten: nicht möglich.** Es gibt lokal keinen freigegebenen Datensatz mit
vollständiger Referenz: rusEFI-Abbilder (GPL-3.0) liegen ohne Definition vor, der rusEFI-Tabellenkorpus enthält
keine Firmware-Abbilder, Speeduino steht teilweise unter CC BY-NC, MS43 hat keine dokumentierte Trainingsfreigabe.
Die bereits freigegebenen Modelle (Struktur-Rejector, Kalibrier-Ranker) wirken schon im Scan und können das
Lernmodell ohne neue Abstimmung nicht ersetzen; eine Abstimmung an Daten ohne Freigabe wäre wieder Training an
diesen Daten.

**Bereits veröffentlicht:** Das Modell ist in allen zehn Releases 1.15.0 bis 1.18.2 enthalten und dort aktiv
(1.15.0–1.17.0 Datei-Stand `c86891f`, 1.18.0–1.18.2 `62eb523`, nur die Quellenangaben unterscheiden sich), jeweils
im Quellcode und im Windows-Paket. Nachgeprüft an den veröffentlichten ZIP-Dateien 1.15.0 (`c86891f`) und 1.18.2
(`62eb523`); der Installer wird aus demselben Programmordner gebaut (`packaging/*.iss`), wurde aber nicht entpackt.
Offene Fragen (nicht eigenmächtig entschieden, ältere Releases
unverändert):

1. Dürfen die Releases 1.15.0–1.18.2 mit diesem Modell weiter zum Download stehen, oder braucht es einen Hinweis bzw.
   eine korrigierte Fassung?
2. Soll die Modelldatei in 1.19.0 trotz Deaktivierung mitgeliefert werden (Nachvollziehbarkeit) oder aus dem Paket
   entfernt werden (sie enthält keine Firmwarebytes, nur 20 Gewichte und Statistiken)?
3. Ist die Trainingsnutzung des MS43-430069-Fullreads (eigene Datei) ausdrücklich freigegeben? Davon hängen das
   MS43-Strukturmodell und ein künftiges Modell ab.
4. Dürfen die Quoten in `confidence_calibration.json` (Messung, kein Training, aber an Dateien ohne geklärte
   Herkunft) weiter angezeigt werden?

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
