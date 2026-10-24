# Quellcodevergleich und isolierte Detektorversuche, 24.10.2026

Ausgangspunkt: veröffentlichtes ECU Studio AI 1.17.0, `main` bei `62d98e1`.
Die Ausgangssuite besteht mit **591 bestandenen und 7 übersprungenen Tests**. Keine Firmware,
externen Definitionen oder fremden Binärprogramme werden mit dieser Entwicklungsrunde veröffentlicht.
Es wird kein Release erstellt und kein neuer Detektor automatisch in der App eingeschaltet.

## Untersuchte Quellen

Die Repositories wurden direkt von GitHub als flache, auf Analysequellcode begrenzte Checkouts gelesen.
Die folgenden Commit-IDs fixieren den tatsächlich untersuchten Stand, nicht einen beweglichen Branch.
Es wurden keine fremden Installationsskripte, Anwendungen oder Buildsysteme ausgeführt.

| Projekt und Quellstand | Lizenznachweis | Sprache / hier relevante Familien | Gelesene Implementierungen und Prüfungen |
|---|---|---|---|
| [ZedSuite `77d75fb`](https://github.com/LeZed97/ZedSuite/tree/77d75fb9e28df04379fd6d1912197947f1cce0c0) | `LICENSE`, `NOTICE`: GPL-3.0; Marken separat ausgeschlossen | Rust / TypeScript; VAG EDC15P, EDC15VM, EDC16U1/U31/U34 | `src-tauri/src/detector/ecu/bosch/edc15p/layout.rs`, `edc16u31/mod.rs`, `edc16u31/signatures.rs`, `ecu_identifier.rs`; eingebettete Rust-Tests |
| [BimmerStein `d3e2921`](https://github.com/CAATZ/bimmerstein-bin-analyzer/tree/d3e292169680cc56707c3b60337dddcad090c622) | `LICENSE`, `NOTICE`: GPL-3.0-or-later | TypeScript; generische Datenmuster und konkrete MS41-C166-Analyse | `packages/engine/src/axes.ts`, `structural.ts`, `family/ms41/{analyzer,header,frame,c166,consumers,runtime-axes,runtime-grids}.ts`, entsprechende Engine-Tests; `packages/eval/src/{metrics,exact-gates}.ts`, `fixtures/README.md` |
| [UniversalPatcher `f7da5f9`](https://github.com/joukoy/UniversalPatcher/tree/f7da5f99930e7fdaaef0b4a094e36d723762d6be) | `LICENSE` und `Source/LICENSE`: GPL-3.0 | C#; konfigurationsabhängige GM-/PCM-Strukturen | `Source/tableSearch.cs`, `Source/AutoDetect.cs`, Such-/Segmentkonfiguration; keine ECU-weite Trefferquote selbst reproduziert |
| [tune-editor `e8f7ed2`](https://github.com/TheFlashBold/tune-editor/tree/e8f7ed22814c5e4f2698dd5cdfcd54162eb7638f) | `LICENSE`: GPL-3.0 | TypeScript; u. a. Simos, MED17, MS4x und DSG-Definitionszuordnung | `src/lib/{binUtils,a2lParser,xdfParser}.ts`; im gelesenen Dateibaum kein entsprechender Blindscanner-Benchmark gefunden |
| [RomRaider `dafe0c3`](https://github.com/RomRaider/RomRaider/tree/dafe0c36c1a68efadbeedb2825f3855463fdbc35) | `license.txt` GPL-2.0; Kopf von `DOMRomUnmarshaller.java` erlaubt ausdrücklich GPL-2.0 **oder später** | Java; definitionsgesteuerte ROM-/Tabellenfamilien | `src/main/java/com/romraider/xml/DOMRomUnmarshaller.java`, `maps/{Table,Table1D,Table2D,Table3D,Rom}.java`, XML-/Skalierungs-Tests |
| [xdfkit `a8f9853`](https://github.com/nyetlabs/xdfkit/tree/a8f985358bc3167b60552ddeba96fa65a4c29a1a) | `COPYING.LESSER`, `COPYING`, README: LGPL-3.0-or-later | Go; Formatverarbeitung und ME7-/M3-Definitionsprüfung | `lint/{lint,record}.go`, `a2l/read.go`, zugehörige Tests; keine familienübergreifende Blindsuche |
| [ECUxPlot `134f539`](https://github.com/nyetwurk/ecuxplot/tree/134f5392bde646938b66f5f41fe04f09e0034e92) | `gpl-3.0.txt`; eigene Drittkomponentenhinweise | Java; Messprotokolle | `src/org/nyet/ecuxplot/ECUxDataset.java`: Logger-/CSV-Erkennung und Datenauswertung. Für die gesuchte Kennfeld-Blinderkennung nicht ausgewählt |

## Algorithmischer Direktvergleich

| Projekt | Erkennungsansatz aus Code | Bei ECU Studio AI vorhanden? | Zusätzliches Potenzial | Testbarkeit hier |
|---|---|---|---|---|
| ZedSuite | Familien-Templates mit Dimensionen, Achsen-/Wertebereichen; Header-/Signaturanker, Selektor- und Nachbarschaftsregeln, Codeblock-Layouts | Kopfdatensätze, Achsen, Ketten und Konfiguration teilweise; konkrete U-Familienregeln nicht | Hoch für genau diese U-Varianten; Übertragbarkeit auf C31/C35 unbewiesen | Strukturmechanik synthetisch; passende echte U-Familienpaare fehlen |
| BimmerStein | Monotone Achsen nur erste Stufe; Paarzeiger auf Count-Achsen, exakte Datensatzgrenzen, MS41-Busabbildung und begrenzte C166-Datenflussanalyse | Count-Achsen, direkte C16x-Verweise und Denso-Zeigerdeskriptoren vorhanden; MS41-spezifische Laufzeit-Achszustände nicht | Hoch: echte Adress-/Dimensionsbeziehungen statt allein glatter Flächen | Teilformat synthetisch; passende MS41-Firmware fehlt |
| UniversalPatcher | Konfigurierte Muster mit Platzhaltern/Variablen, Such- und Zielsegmenten, Zeigerdereferenzierung; gemeinsame Musterpräfixe sparen Vergleiche | Muster, Regionen, Speicherabbildung und direkte Referenzen bereits teilweise | Mittel für konkrete neue Deskriptoren; kein universeller Geometriebeweis | Suchmechanik testbar; kein belegter Zusatznutzen gegenüber vorhandenen Scannern |
| tune-editor | EPK/CAS/Kennungen und bekannte Kalibrierbereiche; A2L-Layouts und XDF-Metadaten bestimmen Adressen/Achsen | EPK-Prüfung, Speichersegmente, RECORD_LAYOUT und Achsverweise vorhanden | Gering für Blindsuche; nützlich als Import-/Identitätsgegenprüfung | Definitionsmechanik bereits geprüft; keine Blindscanner-Gleichsetzung |
| RomRaider | ROM-ID, Definitionserbung, Speicheradressierung, Datentypen und Tabellenaufbau aus Definition | Vorhandener RomRaider-Importer mit Identitätsprüfung | Gering für neue unbekannte Kennfelder | Formatmechanik testbar; kein zusätzlicher Blinddetektor gefunden |
| xdfkit | Definierte Achsen gegen Rohbytes prüfen; Count-Header, vorzeichenabhängige Monotonie, Ausrichtung jedes einzelnen 16-Bit-Felds, gemischte Achsbreiten | Packed-Header und referenzierte Inline-Datensätze teilweise | Mittel: Padding-/Achsbreitenfehler vermeiden | Gut synthetisch; echte passende ME7-Paare fehlen |

**ZedSuite-Methode → vorhandener Mechanismus → Unterschied:**

- EDC16U31-Dimensionsheader und Achsenprüfung → `axis_records` → bereits weitgehend vorhanden;
  die semantischen Templates und kalibrierten Wertebereiche gelten jedoch nur für die untersuchten Varianten.
- Vollständiger Selektor-/Tabellenverbund → `axis_records._chained`, `axis_groups` → unser Scanner kennt Ketten,
  aber die Gruppenanzeige entdeckt keine unbekannten Tabellen. Ein Selektor kann weitere Evidenz liefern,
  wenn sein konkretes Format belegt ist.
- EDC15P-Codeblock-Signatur → `profiles`, `data_regions` → eine belegte dynamische Segmentgrenze wäre nützlich.
  Feste Standardadressen als Fallback sind für unbekannte Familien kein Nachweis.
- Konkrete U31-Abstände und Gruppengrößen → kein gleichwertiger C31/C35-Decoder → nicht ohne passende
  Referenzen übertragen. Auch der gelesene Code enthält feste Referenz-/Diagnoseadressen und spezifische
  Suchzonen; daraus wird keine allgemeine Adressliste übernommen.

Bei ZedSuite wurden im U31-Modul drei Tests zur Template-Konfiguration gelesen, außerdem Layout- und
Identitätstests. Sie ersetzen keinen auf unseren Dateien ausgeführten Referenzbenchmark. Eigene reale
Bench-Aussagen des Projekts werden hier nicht als unabhängig nachgemessene Qualität verwendet.

BimmerStein hat im jetzigen Stand messbare Qualitätsdefinitionen, exakte Gates und Negativtests im Repository.
Das geht über die ältere Beschreibung in `OPEN_SOURCE_VERGLEICH.md` hinaus. Die Tests der Laufzeit-Grids
prüfen unter anderem widersprüchliche Zweige, unbekannte Instruktionen, Schreibzugriffe auf Achszustände und
gemeinsame Achsen. Die Evaluation unterscheidet vollständigen Typ-/Layouttreffer und Achspaarbindung.
Die dortigen MS41-Firmwaredateien sind ausdrücklich lokal, die Strukturreferenzen teilweise öffentlich.
Ohne diese Firmware können wir deren reale Ergebnisse nicht reproduzieren. Die fremde Metrik ordnet zudem
1:1 nach Überdeckung zu; unsere bisherigen IoU-Zahlen sind damit nicht unmittelbar austauschbar.

## Auswahl und Reihenfolge

| Rang | Verfahren | Neuheit / Nutzen | Fehlalarm-/Wartungsrisiko | Entscheidung |
|---|---|---|---|---|
| 1 | BimmerStein-inspirierte Achszeiger-Header plus exakte Nachfolgergrenzen | Achsadresse, Dimension und Tabellenbreite gemeinsam begründbar; geteilte Achsen möglich | Mittel; Adressrahmen, überlappende Lesarten und zufällige Zeiger müssen geklärt sein | Eigenständiger begrenzter Prototyp implementiert |
| 2 | xdfkit-inspirierte Ausrichtung pro Feld bei adressierten Count-Datensätzen | Ergänzt gemischte 8-/16-Bit-Achsen und Padding; konkrete Fehlerklasse statt neuer Flächensuche | Mittel; mehrere Lesarten werden abgelehnt, Codeanker allein ist noch keine vollständige Disassemblierung | Als zweiter, separat messbarer Prototyp implementiert |
| 3 | ZedSuite-Selektor-/Gruppen-Konsistenz | Potenziell zusätzliche Strukturbelege für kopflose Nachbartabellen | Hoch ohne passende Varianten-/Selektorreferenz; Spezialregeln und semantische Fehlbehauptungen vermeiden | Nicht implementiert, bis passende Daten vorhanden sind |

BimmerSteins vollständige rückwärts gerichtete Analyse gestagter Achszustände ist der interessanteste
weiterführende Ansatz. Sie ist nicht mit einem simplen C16x-Muster gleichzusetzen: notwendig wären korrekte
Instruktionsgrenzen, Aufrufverträge, Überschreibungsregeln, Begrenzung von Schleifen und Konsens aller relevanten
Vorgängerpfade. Ohne passende MS41-Testdatei wird dieser größere Decoder nicht spekulativ nachgebaut.

Keine bloßen monotonen Läufe, glatten Nachbarflächen oder Mehrheitsabstimmungen werden produktiv ergänzt.
Konfidenz wird nicht durch die Zahl ähnlicher Beweise hochgesetzt. Ein Byte-/Wort-Vorzeichen wird ohne Beleg
nicht als fachlich sicher dargestellt. Es gibt keine neue Abhängigkeit oder GUI-Funktion.

## Tatsächlich implementierter Code

- `core/experimental_detectors.py`: `scan_pointer_chains` erkennt direkte u16LE-Dateizeiger in Dateien bis
  64 KiB; beide Count-Achsen liegen vor dem Header und überlappen sich nicht. Mindestens drei exakt verkettete
  Header sind erforderlich. Ein eindeutiger Folgeheader fixiert die Wertebreite. Die letzte Tabelle wird
  mangels Folgegrenze nicht ausgegeben. Dies ist **nicht** BimmerSteins vollständiger MS41-Decoder und enthält
  weder dessen Bus-XOR-Abbildung noch dessen gelockerte Plateau-Achsen oder heuristische Kachelung.
- `scan_aligned_records` untersucht vorhandene C16x-Adressanker. Byte-Counts, getrennte 8-/16-Bit-Achsen,
  erlaubtes Alignment-Padding und ein exakt anschließender adressierter Datensatz müssen zusammenpassen.
  Mehrdeutige Lesarten werden verworfen. Rein gepackte einheitliche Layouts bleiben beim bisherigen Decoder.
- `combine_conservatively` erhält bestehende Kandidaten unverändert. Doppelte Vorschläge und Überschneidungen
  werden gezählt; konkurrierende experimentelle Vorschläge werden ausgeschlossen. Keine Erhöhung von
  Verifikation, Konfidenz oder kalibrierter Trefferquote.
- `tools/benchmark_suite.py` erhält einen optionalen Detektoraufruf. Referenzen werden ausschließlich im
  Scoring gelesen; Detektoren erhalten eine separate `BinaryImage` ohne Dateipfad. Schreibende oder als
  verifiziert deklarierte Versuchsergebnisse werden abgewiesen. Der optionale Speicherlauf kontrolliert
  außerdem Ergebnisdeterminismus und räumt den Tracer bei Fehlern auf.
- `tools/detector_benchmark.py` verwendet den vorhandenen gesperrten Manifest-/Validierungsworkflow und
  denselben Benchmark für Baseline, isolierten Versuch und konservative Kombination. Herkunft, Quellcommit,
  Eingabehash, Vollständigkeit, Datenrolle, neue/verlorene exakte Layouts, Konfliktzahlen, Laufzeit und
  Python-Allokationspeak stehen in JSON und Markdown. Es werden nur fest registrierte interne Experimente
  ausgeführt, keine beliebigen Module aus einem Manifest geladen.
- Produktiver Korrektheitsfix in `axis_arrays.axis_at`: negative oder typfalsche Header werden vor der
  Byte-Indizierung abgewiesen. Reproduzierbarer Altfehler: Der letzte Dateibytewert konnte als Count und der
  Dateianfang als Achse einer vermeintlichen negativen Adresse gelesen werden. Der Regressionstest verhindert
  diese künstliche Dateiumwicklung. Für gültige Adressen wird keine Erkennungssteigerung behauptet.

**Lizenz und Herkunft:** Die neuen Python-Verfahren sind eigenständige Implementierungen der beschriebenen
Strukturideen. Es wurden keine fremden Funktionen, Signaturtabellen, Namen, Referenzdatensätze, Logos oder
Codeblöcke übernommen. Deshalb gibt es keine neu eingebettete Fremdkomponente. Die Projektlizenz bleibt
GPL-3.0-only. Bei einer späteren direkten Übernahme wären die jeweiligen Copyright-/Lizenztexte und bei
ZedSuite die getrennten Markenbedingungen zu erhalten. RomRaiders hier gelesenes GPL-2.0-or-later lässt
insbesondere eine GPL-3-Nutzung zu; ein bloßes GPL-2.0-only dürfte nicht pauschal gleichbehandelt werden.

## Reproduzieren und Metriken

```text
python -m ecu_studio.tools.detector_benchmark .qa/local-manifest.json --out .qa/compare.json --markdown .qa/compare.md --memory
python -m pytest -q tests/test_experimental_detectors.py tests/test_detector_benchmark.py tests/test_axis_arrays.py
```

Das Manifest folgt [REFERENCE_VALIDATION.md](REFERENCE_VALIDATION.md). Reale Firmware bleibt lokal und wird
im neuen CI-Messworkflow abgelehnt. Synthetische Tests sind kein unabhängiger realer Qualitätsnachweis.
Auch bei deklarierter Vollständigkeit kann der Code die Qualität oder Rechte einer Referenz nicht selbst beweisen.

Die historische exakte 2D-Metrik prüft Start, Zellbreite und Dimensionen auch in transponierter Orientierung;
sie beweist **nicht** automatisch Vorzeichen, Endianness, Einheiten oder fachliche Achsrollen. Separate
Typ-/Achskennzahlen bleiben im Bericht. IoU-Präzision/-Recall sind von exakten Treffern zu unterscheiden.
Die 2D-Referenz umfasst wie bisher Tabellen ab 4 × 4; Kennlinien werden separat bewertet.
Speicher bedeutet einen separaten `tracemalloc`-Peak von Python-Allokationen, nicht den gesamten Prozess-RSS.
Laufzeiten vergleichen identische Eingaben und Aufrufbedingungen, sind aber keine Hardware-unabhängigen Zusagen.

Die vollständigen lokalen Berichte enthalten keine Eingabepfade oder Firmwarebytes. Öffentliche Ergebnisse
werden auf Hashbindungen und Summen reduziert; insbesondere keine komplette Referenz oder Fehlfundadressliste
in Git oder Actions-Artefakten. Algorithmus-URLs sind öffentliche Quellnachweise, keine privaten Eingabepfade.

## Noch nicht nachgewiesen

| ECU | Bisher dokumentiert exakt | Neuer Detektor exakt | Kombiniert exakt | Präzision vorher/nachher | Ergebnis |
|---|---:|---|---|---|---|
| EDC17CP09 | 463/703 | nicht gemessen | nicht gemessen | nicht gemessen | Passende Referenzdaten fehlen |
| EDC16C35 | 283/387 | nicht gemessen | nicht gemessen | nicht gemessen | Passende Referenzdaten fehlen |
| EDC16C31 | 272/364 | nicht gemessen | nicht gemessen | nicht gemessen | Passende Referenzdaten fehlen |
| MSD85 | 279/1026 | nicht gemessen | nicht gemessen | nicht gemessen | Passende Referenzdaten fehlen |
| MSD80 | 217–224/864 | nicht gemessen | nicht gemessen | nicht gemessen | Passende Referenzdaten fehlen |

Die Ausgangswerte sind aus der bestehenden Unterstützungsmatrix verifiziert, keine neuen Messungen.
Benötigt werden die passenden vollständigen Original-/Definitionspaare mit erlaubter Nutzung, beiden Hashes,
HW-/SW-Kennungen und Speichersegmenten. Zusätzlich fehlen MS41-Originale mit vollständiger passender Definition,
VAG EDC16U1/U31/U34 für den ZedSuite-Vergleich und ME7-Referenzen für gemischte/aligned Datensätze.
Die lokale EDC17C69-Datei ohne passende vollständige Definition ersetzt diese Paare nicht.

## Gemessener Methodenvergleich

Der vollständige Vergleich bei `2921684` umfasst 14 hashgebundene Paare: vier synthetische Strukturdateien,
acht synthetische Negativkontrollen und zwei reale MS4x-Kontrollen. Beide realen Paare bleiben `training`;
**unabhängige reale Testpaare: 0**. Die MS43-Datei stammt aus dem lokalen Benutzerbestand, die passende
430069-Definition aus dem vorhandenen öffentlichen Referenzbestand. Ein OEM-Originalstatus dieser lokalen
Datei wird nicht zusätzlich behauptet. Diese Messung ersetzt keine unabhängige Freigabe.

| Paar / Verfahren | Baseline exakt | Isoliert exakt | Kombiniert exakt | IoU-Präzision vorher / kombiniert | Neue / verlorene exakte Layouts |
|---|---:|---:|---:|---|---|
| MS42 0110C6 / Zeigerketten | 22/213 | nicht anwendbar (>64 KiB) | 22/213 | 72,0 % / 72,0 % | 0 / 0 |
| MS42 0110C6 / ausgerichtete Records | 22/213 | 0 | 22/213 | 72,0 % / 72,0 % | 0 / 0 |
| MS43 430069 lokal / Zeigerketten | 197/367 | nicht anwendbar (>64 KiB) | 197/367 | 78,7 % / 78,7 % | 0 / 0 |
| MS43 430069 lokal / ausgerichtete Records | 197/367 | 0 | 197/367 | 78,7 % / 78,7 % | 0 / 0 |
| Synthetische Zeigerkette u8 | 0/4 | 3/4 | 0/4 | 0 % / 0 % | 0 / 0 |
| Synthetische Zeigerkette u16 | 0/4 | 3/4 | 3/4 | keine Kandidaten / 100 % | 3 / 0 |
| Synthetische gemischte Achsen | 0/4 | 3/4 | 3/4 | 100 % / 100 % | 3 / 0 |
| Synthetische gepaddete Achsen | 2/4 | 1/4 | 3/4 | 100 % / 100 % | 1 / 0 |

Die Zeigerketten werden in den realen großen Dateien bewusst nicht ausgeführt; die Nullzeile im vollständigen
JSON ist anhand von `applicable=false` als außerhalb ihres Formats erkennbar. Das ist kein Ergebnis des
vollständigen fremden Scanners und kein Beleg seiner Unterlegenheit. Auch eine 64-KiB-MS43-Teildatei wäre
nicht automatisch das untersuchte MS41-Direktadressformat.

Der u8-Synthetikfall zeigt eine bewusst erhaltene Grenze: Der Einzelversuch findet drei korrekte Strukturen,
aber ein überlappender bestehender Fehlkandidat blockiert die Kombination. Er wird nicht still ersetzt.
Das Konfliktprotokoll erklärt den Ausschluss. Für eine spätere Ersetzung wäre eine gesondert geprüfte
Evidenzregel erforderlich; ein höherer Score oder die Mehrheit von Scannern reicht nicht.

Beide Prototypen liefern **0 eigene Funde auf allen acht gemessenen Negativdateien**. Die Kombination
behält auf Zahlenrampen allerdings den vorhandenen Fehlfund der Baseline und deren 1024 Achshypothesen.
Dies wird nicht als behobene Fehlalarmklasse ausgegeben. Die automatisierten Tests ergänzen abgeschnittene
Dateien, falsche Zeigerrichtung/-reihenfolge, signierte Wortachsen, widersprüchliche Breiten, Abbruch,
Ressourcenbudgets und konkurrierende Layouts. Synthetische Werte ersetzen keine OEM-Referenz.

Lokale Einzelzeiten aus demselben Methodenlauf: MS42 Baseline 2,13 s, Zeigerkombination 2,09 s,
Record-Kombination 2,04 s; MS43 3,60 / 3,83 / 3,53 s. Diese Schwankungen begründen keinen
Geschwindigkeitsgewinn. Python-Allokationspeaks der Kombinationen bleiben dort bei 13,9 bzw. 18,3 MiB.
Sehr kleine isolierte Läufe runden im bisherigen Berichtsformat auf 0,00 s / 0,0 MiB; das bedeutet nicht,
dass sie keine Zeit oder Speicher benötigen. Die gemessene Ausführungsumgebung ist Windows x64,
CPython 3.13, sequenzieller Scanneraufruf ohne explizite Freischaltung des Prozesspools.

**Integrationsentscheidung:** Keiner der beiden neuen Erkennungsprototypen wird in `scoped_scan` aktiviert.
Die Mechanik zeigt synthetischen Nutzen, aber der reale Erkennungsgewinn ist hier nicht nachgewiesen.
Die Ergebnisse gehören nicht in die kalibrierten Konfidenzen oder die ECU-Unterstützungsmatrix.

## Aus dem Vergleich abgeleitete produktive Korrekturen

Neben dem negativen Achszeiger wurde ein vorhandenes Leistungsproblem tatsächlich reproduziert:
64 KiB wiederholte Zahlenrampen benötigen vor der Optimierung 33,21 s und einen Python-Allokationspeak
von 95,9 MiB. Ein instrumentierter Profillauf zählt 72127 Aufrufe von `surface_evidence`; der Großteil
der Zeit entfällt auf `scan_axis_records` und seine wiederholten Oberflächen-/Subword-Prüfungen.
Die instrumentierten 171 s werden ausdrücklich **nicht** mit normalen Laufzeiten verglichen.

`axis_records.scan_axis_records` verwendet jetzt einen auf **einen Scan und 512 Einträge** begrenzten Cache
für exakt gleiche Wertebytes, Geometrie, Datentyp und Byte-Reihenfolge. Es werden weder ähnliche Werte
zusammengelegt noch Adressen, Achsen, Schwellen oder Resultatlimits geändert. Die privaten Bytes bleiben
nicht in einem globalen Cache. `evidence_cache_size=0` erlaubt eine kontrollierte Gegenprobe ohne Cache.
Die Tests vergleichen sämtliche Definitionsfelder für beide Byte-Reihenfolgen und u8/u16/s16 sowie
Wiederholungsmuster; nach einem anderen Bild darf keine alte Bewertung weiterverwendet werden.

Diese Optimierung ist eine eigenständige Folge der Messung, keine direkte Übernahme eines fremden
Erkennungsalgorithmus. Sie soll identische Resultate mit weniger wiederholter Arbeit liefern; der vorhandene
Fehlfund auf Rampen wird dadurch nicht entfernt.

Eine separate Gegenprobe verwendet einen frischen Checkout des veröffentlichten Tags `v1.17.0`
(`62d98e1`) und den optimierten Stand `f5cccfd`, je drei vollständige sequenzielle Scans derselben
64-KiB-Rampendatei ohne Profiler oder Tracemalloc:

| Messung | 1.17.0 | Optimiert |
|---|---|---|
| Laufzeiten, Sekunden | 36,005 / 35,965 / 35,867 | 8,750 / 8,790 / 8,714 |
| Median, Sekunden | 35,965 | 8,750 |
| Gesamte Kandidaten / davon 2D | 1025 / 1 | 1025 / 1 |
| Hash aller Definitionsfelder | identisch in allen sechs Läufen | identisch in allen sechs Läufen |

Auf **diesem synthetischen Problemfall** ist der komplette Scan damit etwa 4,1-mal schneller, bei exakt
gleichen Ergebnissen. Das ist kein allgemeiner ECU-Performancefaktor und keine zusätzliche Erkennungsqualität.
Die Gegenprobe der beiden realen Paare zeigt keinerlei Änderung an den gemessenen Qualitätskennzahlen
oder exakten Layoutschlüsseln: 22/213 und 197/367. Einzelzeiten MS42 2,29 → 2,09 s, MS43 3,75 → 3,72 s;
daraus wird kein belastbarer Laufzeitgewinn bei realer Firmware abgeleitet.

Die gezielten Cache-/Experiment-/Achsprüfungen bestehen mit 43 Tests. Die abschließenden vollständigen
Regressionstests und die erneute Methodenmessung am optimierten Stand ergänzen diesen Zwischenstand.
