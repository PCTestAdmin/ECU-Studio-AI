# Nächste Generation der Kennfelderkennung – Entwicklungsbericht (nach 1.21.0-rc1)

Stand: 25.11.2026 (Qualitätsphase 2: § 7, Qualitätsphase 3: § 8, Qualitätsphase 4: § 9). Zweig `feat/post-rc1-recognition-nextgen` (Basis: `v1.21.0-rc1`, Commit `c27796c`), Draft-PR.
**Nichts davon ist veröffentlicht.** Die Zahlen stammen aus privaten A2L-/HEX-Referenzdaten eines Datengebers
(BMW-Linien, siehe [ENTWICKLUNG_1.21.0.md](ENTWICKLUNG_1.21.0.md) § 2). Die Daten bleiben lokal; öffentlich sind nur
zusammengefasste Zahlen. Kein Modelltraining. Alle Regeln wurden nur an den Entwicklungsdaten (58 Abbilder)
untersucht; der Holdout (105 Abbilder) dient nur noch als bekannte Regressionsprüfung und ist **keine unabhängige
Validierung**.

Leitsatz: Lieber wenige zuverlässig belegte Kennfelder als viele scheinbar erkannte mit falschen Angaben.

## 1. Bestandsaufnahme der Erkennung (Phase 1)

Code in `src/ecu_studio/core` (17 357 Zeilen) und `src/ecu_studio/recognition` (2 237 Zeilen). Ablauf von
`scoped_scan.scan_calibration_candidates` ohne Definition:

| Schritt | Modul | Beleg |
|---|---|---|
| Profil, Architektur, Datenbereiche | `identification`, `architecture`, `data_regions` | Struktur |
| Rasterscanner (`discover`, `u8`, `u32`, `s16`), parallel | `scanner`, `parallel` | Datenmuster |
| Achsen mit Anzahl | `axis_arrays` | Struktur |
| TriCore-Aufrufe der Interpolationsroutinen, Zeigertripel, verlagerte Kalibrierung | `tricore_refs` | Programmcode |
| Datensätze (Kopf, Achsen, Werte), Wertebreite, Byte-Reihenfolge, Vorzeichen | `structure_scan`, `axis_records` | Struktur / Programmcode |
| Zeilenabstand-Suche (glatte Flächen) | `structure_scan` (row-pitch) | Datenmuster |
| Widersprochene Datenmuster, Reihung, Überschneidungen | `scoped_scan`, `precision` | – |
| Kennlinien-Datensätze, Text- und Zeigertabellen | `curve_records`, `region_classes` | Struktur |
| Belegstufe, Datentyp-Zweifel („?“) | `confidence`, `type_readings` | – |
| Zwillinge, gemeinsame Achsen, Funktionsgraph (C16x) | `map_groups`, `axis_groups`, `function_graph` | Struktur / Programmcode |
| Namensübertragung, Softwarestand-Vergleich | `name_transfer`, `version_compare` | Struktur |
| A2L mit Umrechnung (LINEAR, lineares RAT_FUNC), EPK-Prüfung | `a2l` | Definition |
| Lernmodelle (nur Umsortierung, Modellsperre) | `recognition/*` | – |

Ergebnis rc1 auf den Entwicklungsdaten nach Belegstufe (alle 2D-Funde):

| Belegstufe | Funde | exakt | Verwechslung | teilweise | nicht bewertbar |
|---|---:|---:|---:|---:|---:|
| Code-Beleg | 18 300 | 18 253 (99,7 %) | 0 | 5 | 0 |
| Strukturbeleg | 15 036 | 13 227 (88 %) | 1 088 | 502 | 73 |
| Datenmuster-Vermutung | 8 283 | 578 (7 %) | 4 228 | 1 690 | 1 670 |

### Die drei größten Schwächen

1. **Datenmuster-Funde sind meist falsch.** 4 228 der 5 316 Verwechslungen (80 %) stammen aus glatten Flächen ohne
   Code- oder Strukturbeleg; 3 662 Verwechslungen überdecken mehrere A2L-Objekte (Folgen von Einzelwerten und
   Wertblöcken, die als eine Tabelle gelesen werden). Sie sind als „Datenmuster-Vermutung“ gekennzeichnet, aber
   zahlreich. 30 der 58 Entwicklungsabbilder sind reine Kalibrierabbilder ohne Programmcode: Dort gibt es keinen
   Codebeleg, der sie widerlegen könnte.
2. **Keine Funktionsebene, keine Herkunft der Umrechnung.** Erkannte Tabellen haben weder Funktion noch Umrechnung;
   bei Definitionen war nicht sichtbar, woher Faktor, Offset und Einheit stammen, und eine nicht unterstützte
   Umrechnung fiel nur als Notiz auf.
3. **Keine unabhängige Validierung.** Seit der ersten Holdout-Messung (Runde 1) gibt es keine neue, vorab
   eingefrorene Testgruppe realer Steuergeräte. Bekannte Fehlerquellen aus dem Holdout (MEVD17.2.3-Vollflashs,
   MSV90-Byte-Reihenfolge) lassen sich ohne Entwicklungsdaten derselben Linien nicht ursächlich beheben.

Weitere bekannte Grenzen (unverändert): unbelegte Datentypen (sichtbar mit „?“), Überschneidungen zwischen
Kandidaten (Filter), Achsen nur im Programmcode (nicht als Kandidat ausgegeben).

## 2. Paket A: weniger Fehlzuordnungen durch Codebelege

*(Ergebnisse: Abschnitt 5.)*

**Ursache (Entwicklungsdaten, Vollabbilder mit Programmcode):** Der Programmcode liest viele Kalibrierwerte direkt
über ein globales Basisregister (`ld.bu/ld.h/ld.w d,[a1]off` u. ä., Basis aus der Startinitialisierung). Jede solche
Adresse beginnt ein eigenes Objekt. Eine glatte Fläche, in der eine solche Adresse **echt innen** liegt, umfasst
mehrere Objekte. Probe an den rc1-Ergebnissen: 289 Zeilenabstand-Funde mit direkt geladener Adresse innen,
**keiner exakt**; auf MSD80 203 davon Verwechslungen, auf MEVD17.2 alle 77 nicht bewertbar.

**Regel:** `tricore_refs.direct_loads` sammelt diese Adressen (vektorisiert über die vorhandene lineare Zerlegung,
nur Befehle außerhalb datenartiger Blöcke, ohne die Startinitialisierung der Basisregister); `call_descriptors`
liefert sie als `loaded`. Die Zeilenabstand-Suche verwirft wie bisher bei Aufrufargumenten (`addressed`, 1.21.0)
jede Fläche mit einer solchen Adresse innen. Eine Adresse am Anfang behält die Fläche. Schalter `DIRECT_LOADS`
(Ablation), synthetische Tests `tests/test_direct_loads.py`.

Erste Fassung (verworfen): Die Adressen wirkten schon **in** der Zeilenabstand-Suche. Dann füllten andere glatte
Flächen das Budget wieder auf: +41 Verwechslungen auf MEVD, 207 der 251 neuen Lesarten an anderer Stelle. Die
übernommene Fassung entfernt widerlegte Flächen erst **nach** der Reihung (`scoped_scan.refuted_by_loads`,
Schalter `LOADED_REFUTES_PITCH`), ohne Nachrücken.

**Zweite Regel: ein Codebeleg wird nicht verdrängt.** Bis rc1 gab jeder belegte Kandidat eine Überschneidung ab, wenn
sein eigener Anfang in einer früher beginnenden glatten Fläche lag (glatte Flächen enthalten Folgen, die wie ein
Datensatzkopf aussehen). Ablation „Ausnahme ganz entfernt“: +24 exakte Tabellen, 0 verloren, −23 Verwechslungen, keine
unmarkierte falsche Lesart auf den Entwicklungsdaten – **aber** im mitgelieferten synthetischen Demoabbild
verdrängen dann zwei falsche Datensatzköpfe beide echten Tabellen (Test schlug fehl). Alle 24 Gewinne stammten von
Datensatzköpfen. Übernommen ist deshalb nur: Programmcode-Belege (Interpolationsaufruf, Codereferenz,
Zeigerdeskriptor) gewinnen immer (`precision.CODE_EVIDENCE_ALWAYS_WINS`); Datensatzköpfe behalten die Ausnahme. Auf
den Entwicklungsdaten ändert das **nichts messbar** (gleiches Ergebnis wie Paket A allein); die Regel sichert den
Grundsatz, dass der stärkere Beleg nicht dem schwächeren weicht (synthetische Tests in
`tests/test_precision_sources.py`, auch für die beibehaltene Ausnahme).

## 3. Paket B: Funktionsebene (Prototyp)

Modul `core/function_id.py`. Eine Funktion stammt **nur** aus

- einer Definition: A2L `FUNCTION` mit `DEF_CHARACTERISTIC` (neu gelesen, `MapDefinition.function` mit Quelle), oder
- Beziehungen zu Tabellen mit bekannter Funktion: gleiche gespeicherte Achse (Adresse, nicht Werte), gleiche
  Coderoutine (C16x-Funktionsgraph), direkter Nachbar im Speicher (kein anderes Objekt dazwischen, ≤ 16 Byte).

Werte und Wertebereiche benennen nie eine Funktion; ohne Beleg bleibt sie „Unbekannt“. Status:

| Status | Bedingung |
|---|---|
| Bestätigt | eigene Definition nennt die Funktion, Tabelle geprüft |
| Stark gestützt | eigene Definition, Zuordnung zur Datei ungeprüft; oder zwei unabhängige Beziehungsarten zu Tabellen derselben Funktion, keine zu einer anderen |
| Vermutet | eine Beziehungsart; oder mit einem übertragenen Namen übernommen (bleibt ungeprüft) |
| Unbekannt | kein Beleg, oder Beziehungen zu verschiedenen Funktionen (als Widerspruch aufgeführt) |

Nur „Bestätigt“ und „Stark gestützt“ dienen als Anker; eine Vermutung stützt nie eine andere. *Seit Qualitätsphase 2
(§ 7.2): Ein Nachbar stimmt nur bei beidseitigem Einschluss durch Tabellen derselben Funktion; „Stark gestützt“ braucht
zwei Belegfamilien. Die folgende Messung beschreibt den Stand von PR #30 vor dieser Änderung.* Jede Hypothese führt
ihre Belege mit Quelle. Anzeige: Detailansicht und neuer Abschnitt „Funktionszuordnung“ im Funktionsgraph.

**Messung (Entwicklungsdaten, eine Datei je A2L, 28 A2L):** Tabellen mit A2L-Funktion nach Adresse sortiert, jede
zweite behält ihre Funktion (Anker), die übrigen werden verdeckt und vorhergesagt; richtig = die vorhergesagte
Funktion ist eine der eigenen A2L-Funktionen. Zählt alle verknüpften Objekte (auch Einzelwerte).

| Linie | Stark gestützt richtig | Vermutet richtig | Unbekannt (offen gelassen) |
|---|---:|---:|---:|
| MEVD17.2-N55 | 943 von 943 | 92 300 von 92 433 (99,9 %) | 13 289 |
| MSD80-N53/N54 | 2 970 von 3 000 (99,0 %) | 53 580 von 56 680 (94,5 %) | 55 172 |

Ablation: nur Nachbarschaft 99,9 % / 94,5 % richtig; nur gemeinsame Achse 97,9 % / 98,2 % bei wenigen Fällen
(978 / 13 029). **Grenzen:** Die abwechselnde Aufteilung ist günstig (Anker liegen dicht); A2L-Dateien einer Linie
sind ähnlich, die Fälle also nicht unabhängig; gemessen nur an zwei BMW-Linien. Ohne Definition gibt es keine Anker:
Dann bleibt jede Funktion „Unbekannt“, und nur die strukturellen Gruppen (ohne Namen) sind sichtbar.

## 4. Paket C: Datentyp und Skalierung mit Herkunft

Modul `core/type_status.py`. Je Eigenschaft (Wertebreite, Vorzeichen, Byte-Reihenfolge) ein Status mit Quelle:
**bestätigt** (Definition oder Nutzer), **abgeleitet** (Ladebefehle, Datensatzkopf, Datensatzaufbau, Mehrheit der
Datensätze; oder die Frage stellt sich nicht, weil kein Wert ein gesetztes oberstes Bit hat), **alternativ** (offene
Lesarten genannt), **unbestimmt** (nur Werteverlauf). Jede Eigenschaft mit „alternativ“ oder „unbestimmt“ trägt
weiterhin das „?“ der Liste (Test).

Skalierung: Faktor, Offset und Einheit mit Quelle (`MapDefinition.scaling_source`, z. B. „A2L COMPU_METHOD … (LINEAR)“).
Erkannte Tabellen haben nie eine belegte Umrechnung: Rohwerte. Nicht unterstützte A2L-Umrechnungen (TAB_VERB,
nichtlineares RAT_FUNC, Tabellen) bleiben ausdrücklich Rohwerte.

**Prüfung gegen Referenzwerte:** Die A2L-Grenzen (LowerLimit/UpperLimit) werden gelesen; `a2l.limit_violations`
zählt Zellen außerhalb. Die Prüfung kann nur widersprechen, nie bestätigen.

*(Messung über alle Entwicklungs-A2L: Abschnitt 5.)*

## 5. Ergebnisse

Vergleich immer gegen `v1.21.0-rc1` (gleiche Abbilder, gleiche Auswertung). „Exakt“ = Anfang, Form und Wertebreite
wie in der A2L; „Verwechslung“ = Fund überdeckt ein anderes oder mehrere A2L-Objekte.

**Entwicklungsdaten (58 Abbilder, 52 508 verifizierbare 2D-Kennfelder)**

| Linie | Abbild | exakt rc1 → neu | Verwechslung | teilweise | nicht bewertbar |
|---|---|---:|---:|---:|---:|
| MEVD17.2-N55 | Kalibrierung (9) | 4 837 → 4 837 | 925 → 925 | 375 → 375 | 0 → 0 |
| MEVD17.2-N55 | Vollabbild (9) | 6 741 → 6 741 | 1 009 → 1 009 | 200 → 200 | 571 → 494 |
| MSD80-N53/N54 | Kalibrierung (21) | 7 091 → 7 091 | 2 174 → 2 174 | 1 074 → 1 074 | 0 → 0 |
| MSD80-N53/N54 | Vollabbild (19) | 13 389 → 13 389 | 1 208 → 1 005 | 548 → 547 | 1 172 → 1 164 |
| **Summe** | 58 | **32 058 → 32 058** | **5 316 → 5 113** | 2 197 → 2 196 | 1 743 → 1 658 |

Exakte Treffer je Abbild: **0 verloren, 0 hinzugewonnen**. Datentyp der exakten Treffer unverändert (falsches
Vorzeichen 1 326, falsche Byte-Reihenfolge 20, davon **ohne „?“: 0 → 0**). Achsen 31 431 / 31 480 unverändert. Wirkung
nur auf Vollabbilder mit Programmcode; reine Kalibrierabbilder haben keinen Codebeleg.

**Holdout (105 Abbilder) – nur Regressionsprüfung, keine Validierung**, Paket A gegen rc1:

| Linie | Abbild | exakt | Verwechslung rc1 → neu |
|---|---|---:|---:|
| MSD80-N43 | Vollabbild (10) | 8 049 → 8 049 | 530 → 450 |
| MSV90-N52 | Vollabbild (16) | 8 502 → 8 502 | 561 → 439 |
| MEVD17.2.3 (B38, B38I12, B48) | Vollabbild (23) | unverändert | unverändert |
| ME9-N40, alle Kalibrierabbilder | (56) | unverändert | unverändert |
| **Summe** | 105 | **52 701 → 52 701** | **10 743 → 10 541** |

Holdout: 0 exakte Treffer verloren, keine neue unmarkierte falsche Lesart (Vorzeichen, Byte-Reihenfolge) in keiner
Linie. MEVD17.2.3-Vollabbilder: nicht bewertbar 1 657 → 1 640, Verwechslungen unverändert – die bekannte Fehlerquelle
dort ist nicht behoben.
Endstand (Paket A, Codebeleg-Vorrang, Datentyp-Status) auf dem Holdout identisch mit Paket A allein: 52 701 exakt,
10 541 Verwechslungen, 0 verloren.

**Regressionsgruppe** (MS42, MS43, MSD80 mit XDF, synthetische Strukturen und Negativkontrollen): exakte Treffer
unverändert (22 / 197 / 86); MSD80 1 139 → 1 131 Funde; synthetische Fälle und Negativkontrollen unverändert.

**Negativgruppe** (quelloffene Firmware ohne Bosch/Siemens-Kalibrierstruktur: FOME, rusEFI, Speeduino; 7 Abbilder):
549 → 549 Funde, alle als unklar/Datenmuster bzw. Strukturbeleg gekennzeichnet, **sicher falsch 0 → 0**, keine fremden
Codebelege.

**Datentyp-Status (Paket C)**, je ein Vollabbild ohne Definition, Gesamtstatus je Kandidat (schwächste Eigenschaft):

| Linie | Kandidaten | abgeleitet | alternativ | unbestimmt | bestätigt |
|---|---:|---:|---:|---:|---:|
| MEVD17.2-N55 | 3 135 | 2 658 | 331 | 146 | 0 |
| MSD80-N53/N54 | 2 107 | 1 736 | 219 | 152 | 0 |

„Bestätigt“ ist ohne Definition nicht möglich; alle Umrechnungen „Unbekannt: Rohwerte“, alle Funktionen „Unbekannt“
(keine Anker). Achsen und Kennlinien halten das andere Vorzeichen jetzt offen, wenn die Werte es nicht
entscheiden (vorher still entschieden). Diese 1D-Objekte bewertet der Benchmark nicht gegen die A2L; die Änderung fügt
nur „?“ hinzu und kann keine neue Behauptung erzeugen. Die 2D-Bewertung ist unverändert (13 318 → 13 316 exakte
Treffer mit „?“).

**A2L-Grenzen als Gegenprobe** (Paket C, Entwicklungs-A2L, nur unterstützte Umrechnungen): MEVD17.2 0 von 344 924
Zellen außerhalb, MSD80 17 745 von 467 220 (3,8 %). Ein umgedrehtes Vorzeichen fällt in 38 760 von 39 150 (MEVD)
bzw. 41 532 von 43 223 (MSD80) Fällen auf. Die Abweichungen bei MSD80 zeigen, dass die Grenzen nicht immer zu den
gespeicherten Werten passen; deshalb nur Hinweis, **kein** Beleg in der Erkennung.

**Funktionsebene (Paket B):** siehe Abschnitt 3.

**Leistung** (je ein Vollabbild MSD80 und MSV90, abwechselnd rc1 / neu, je Lauf ein frischer Prozess, 5 Zeitläufe ohne
Speichermessung; rc1 aus `git archive v1.21.0-rc1`):

| Abbild | rc1 Median (min–max) | neu Median (min–max) | Spitzenspeicher rc1 → neu |
|---|---:|---:|---:|
| MSD80-N53/N54 | 14,42 s (14,11–15,49) | 14,82 s (14,32–15,89) | 86,3 → 86,3 MB |
| MSV90-N52 | 14,91 s (14,67–15,36) | 15,19 s (14,83–15,56) | 86,3 → 86,3 MB |

Etwa +0,3 bis +0,4 s je Abbild (Zerlegung der direkten Ladebefehle); die Bereiche überlappen. Speicher: ein Lauf rc1,
zwei Läufe neu (der vierte Speicherlauf wurde von außen beendet, Windows-Status 0x40010004, und nicht wiederholt).

## Grenzen

- Keine neue unabhängige Validierung: Entwicklungs- und Holdoutdaten sind bekannt; der Holdout ist mehrfach
  ausgewertet und nur noch Regressionsprüfung.
- Paket A wirkt nur, wo TriCore-Programmcode im Abbild liegt; MEVD17.2.3-Vollabbilder und reine Kalibrierabbilder
  profitieren nicht.
- Die Funktionsebene braucht Anker aus einer Definition; ohne A2L bleibt jede Funktion „Unbekannt“. Gemessen nur an
  zwei BMW-Linien mit günstiger Aufteilung.
- Umrechnungen werden nicht aus den Werten erraten: Erkannte Tabellen bleiben Rohwerte.
- Datenmuster-Funde bleiben zahlreich und meist falsch (gekennzeichnet).
- Qualitätsphase 2 (§ 7): Die Funktionsebene ist bei sehr wenigen Ankern und verdeckten Speicherblöcken auf
  MEVD17.2 unzuverlässig (Präzision 63 %); ganz verdeckte Funktionen werden zwangsläufig falsch zugeordnet, nur seltener.
  Datenfluss nur TriCore. Gemeinsame Achsen bei MEVD17.2 nicht gefunden. Ob ein falsches 1D-Vorzeichen mit „?“ markiert
  war, ist nicht ausgewertet.

## 6. Unabhängige Daten

Suche am 21.11.2026 (öffentliche Quellen, nur allgemeine Suchbegriffe): keine rechtmäßig nutzbaren A2L-/HEX-Paare
realer Steuergeräte gefunden, nur quelloffene Werkzeuge (z. B. calibrationReader, AsamCalTool, a2llib) ohne
Referenzdaten realer Steuergeräte. Nichts heruntergeladen. Eine neue Testgruppe gibt es damit weiterhin nicht.

## 7. Qualitätsphase 2 (22.11.2026): Funktionsanalyse, Code-Datenfluss, Gegenbeispiele

Herkunft aller Zahlen dieses Abschnitts: **Entwicklungsdaten** (58 Abbilder, 28 A2L, davon 28 Vollabbilder mit
Programmcode), sofern nicht anders vermerkt. Der **bekannte Holdout** (105 Abbilder) dient nur als Regression. Eine
**neue unabhängige Testgruppe gibt es nicht** (§ 7.10). Werkzeuge: `tools/function_benchmark.py` (öffentlich, nur
Zählungen) und private Auswerteskripte, die nur Summen ausgeben.

### 7.1 Analyse der bisherigen Funktionsidentifikation

Die Messung in § 3 (jede zweite Tabelle nach Adresse als Anker) ist günstig: Fast jede verdeckte Tabelle hat einen
Anker derselben Funktion direkt daneben. Unter harten Aufteilungen zeigt sich die Schwäche: Wird eine Funktion ganz
verdeckt (ihr richtiger Name kommt unter den Ankern nicht vor), ist **jede** Zuordnung falsch. Mit den Regeln von
PR #30 waren das bei 50 % verdeckten Funktionen 19 212 (MEVD17.2) bzw. 86 108 (MSD80) falsche Zuordnungen, davon
98 % allein über den direkten Nachbarn; 390 davon sogar „Stark gestützt“ (MSD80). Ursache: Funktionsgrenzen liegen
zwischen benachbarten Tabellen. Ein Nachbar teilt die A2L-Funktion auf MSD80 nur in 62 % der Paare (138 988 von
225 672), eine gemeinsame gespeicherte Achse auf MEVD17.2 nur in 50 %.

### 7.2 Harte Aufteilungen (Test A, B) und Regeländerung

Aufteilungen (deterministisch, Schlüssel-Hash, drei Salze summiert): `table` (zufällige Tabellen als Anker, Anteil
50/25/10/5/1/0 %), `block` (ganze 4-KiB-Speicherblöcke verdeckt), `function` (ganze Funktionen verdeckt). Gezählt
werden richtig / falsch / unbekannt über alle auswertbaren verdeckten Tabellen (mit A2L-Funktion). Kein Ergebnis
erreicht 100 %.

**Regel (umgesetzt):** Ein Nachbar stimmt nur noch, wenn die Tabelle auf **beiden** Seiten von Ankern derselben
Funktion eingeschlossen ist (`NEIGHBOUR_BOTH_SIDES`). „Ergebnis fließt in die andere Tabelle“ stimmt nicht mehr
(Schutzregel, § 7.4). Geprüft und **nicht** übernommen: gemeinsame Achse erst ab zwei Ankern (kein messbarer Nutzen,
verliert „Stark gestützt“-Treffer).

Richtig / falsch (Rest: „Unbekannt“) von *n* auswertbaren verdeckten Tabellen; „PR #30“ = Achse + Nachbar wie bisher,
„neu“ = neue Regeln mit Beziehungen aus dem Programmcode (Vollabbilder, je Linie alle A2L, drei Salze summiert):

| Aufteilung | MSD80 *n* | MSD80 PR #30 | MSD80 neu | MEVD17.2 *n* | MEVD17.2 PR #30 | MEVD17.2 neu |
|---|---:|---:|---:|---:|---:|---:|
| abwechselnd 50 % | 114 852 | 56 554 / 3 132 | 66 346 / 2 802 | 106 665 | 93 243 / 133 | 93 137 / 101 |
| Tabellen 50 % | 345 437 | 154 315 / 55 295 | 82 366 / 2 953 | 319 862 | 218 752 / 10 610 | 74 306 / 170 |
| Tabellen 10 % | 620 573 | 111 149 / 36 697 | 62 863 / 2 370 | 576 002 | 102 888 / 7 753 | 10 482 / 983 |
| Tabellen 1 % | 682 329 | 52 128 / 4 511 | 46 407 / 447 | 633 539 | 12 347 / 1 421 | 991 / 591 |
| Tabellen 0 % | 689 130 | 0 / 0 | 0 / 0 | 640 008 | 0 / 0 | 0 / 0 |
| Speicherblöcke 50 % | 390 707 | 22 206 / 1 069 | 24 083 / 1 195 | 335 385 | 1 020 / 470 | 847 / 506 |
| ganze Funktionen 50 % | 365 444 | 0 / 86 108 | 0 / 7 857 | 265 996 | 0 / 19 212 | 0 / 779 |

„Stark gestützt“ und falsch: MSD80 Funktionen 50 % 390 → 20, Tabellen 50 % 153 → 29; MEVD17.2 0 → 0. Richtig und
„Stark gestützt“ (MSD80, Tabellen 50 %): 8 276 → 5 103. Wirkung der Anker: ohne Anker wird nichts benannt (0 falsch);
mit wenigen Ankern fällt die Abdeckung stark.

**Bilanz:** Falsche Zuordnungen sinken um 90–99 %, die Abdeckung fällt bei dichten Ankern etwa auf die Hälfte (MSD80)
bzw. ein Drittel (MEVD17.2). **Schwächen, offen gelassen:** Bei MEVD17.2 mit sehr wenigen Ankern (1 %) ist die neue
Präzision schlechter (62,6 % statt 89,7 %; falsch 1 421 → 591), ebenso bei verdeckten Speicherblöcken (62,6 % statt
68,5 %). Verdeckte Funktionen bleiben die schwerste Lage: Jede Zuordnung ist dort falsch, weil der richtige Name
nirgends vorkommt.

**Wann die Ebene „Unbekannt“ sagen muss:** keine Beziehung zu einem Anker; nur ein einseitiger Nachbar; Beziehungen
zu verschiedenen Funktionen (Widerspruch); nur „gleiche Eingangsgröße“ oder „Ergebnis fließt in die andere Tabelle“;
keine Definition im Projekt (dann gar keine Anker).

### 7.3 Datenfluss (TriCore, Paket B)

Schichten: Dekodierung (`tricore_flow.decode`, 16-/32-Bit-Formen für Kopien, Adressrechnung, Laden, Speichern,
Konstanten) → Datenflussmodell (`code_flow`, prozessorunabhängig) → Tabellenverweise (Interpolationsaufrufe aus
`tricore_refs`) → Aufrufe mit Eingängen (d4 = X, d5 = Y) und Ergebnis (d2) → Beziehungen → Semantik (nur über
Definitionen). Fenster: 32 Befehle zurück, 24 vor; Abbruch mit Grund bei Sprungziel, Routinenanfang, nicht
dekodiertem Befehl, Aufruf dazwischen, Wert aus dem Stapel, Zeiger aus dem Speicher, verändertem Adressregister,
erschöpftem Fenster. PowerPC und C16x: keine Datenflussanalyse (nicht behauptet).

Prüfung gegen die A2L (je ein Vollabbild MEVD17.2 und MSD80; MEASUREMENT-Adressen, AXIS_DESCR-Eingangsgröße,
FUNCTION IN/OUT/LOC):

| | MEVD17.2 | MSD80 |
|---|---:|---:|
| X-Eingang (d4) als RAM-Adresse aufgelöst | 351 (alle Messgrößen; 313 = A2L-Eingangsgröße X) | 395 (394 Messgrößen; 379 = X) |
| Y-Eingang (d5) aufgelöst | 277 (244 = Y) | 271 (255 = Y) |
| Aufrufe mit gespeichertem Ergebnis | 223 von 644 | 311 von 1 031 |
| Speicherziel ist Messgröße / davon in der eigenen Funktion (OUT/LOC) | 245 von 271 / 239 von 245 | 282 von 314 / 259 von 280 |

Beziehungen über alle 28 Vollabbilder (Paare mit gleicher / anderer A2L-Funktion):

| Beziehung | MEVD17.2 | MSD80 | stimmt ab? |
|---|---:|---:|---|
| gleiche aufrufende Routine | 6 294 / 312 | 22 759 / 2 129 | ja (Programmcode) |
| Ergebnis in derselben Variablen | 326 / 0 | 974 / 0 | ja (Programmcode) |
| Ergebnis fließt in die andere Tabelle | 73 / 25 | 55 / 42 | **nein** (66 %, Schutzregel) |
| gleiche Eingangsgröße | 1 441 / 1 211 | 4 666 / 7 625 | **nein**: gemeinsamer Betriebspunkt, keine Funktion |

Mehrere Beziehungen aus dem Programmcode zählen als **eine** Belegfamilie; „Stark gestützt“ braucht zwei Familien
(Achse, Speicherlage, Programmcode).

### 7.4 Funktionsgruppen ohne A2L (Test E) und Oberfläche

Gruppen aus Beziehungen, ohne Funktionsnamen gebildet, danach gegen die A2L-Funktionen geprüft (rein = alle
Mitglieder mit A2L-Funktion teilen eine; nur Gruppen mit mindestens zwei solchen Mitgliedern). Die Abstimmungsregeln
ändern die Gruppen nicht.

| Beziehungen | MSD80 Gruppen (rein) | MSD80 Mitglieder in reinen Gruppen | MEVD17.2 Gruppen (rein) | MEVD17.2 Mitglieder in reinen Gruppen |
|---|---:|---:|---:|---:|
| nur Struktur (Achse) | 4 005 (3 501, 87 %) | 26 613 von 30 140 | 483 (397, 82 %) | 1 932 von 3 513 |
| Struktur + Programmcode | 4 658 (4 035, 87 %) | 30 199 von 36 279 | 1 074 (943, 88 %) | 4 200 von 6 154 |
| nur Programmcode | 1 848 (1 663, 90 %) | 7 067 von 9 003 | 591 (546, 92 %) | 2 268 von 2 641 |

Ohne A2L heißen alle Gruppen „Unbekannte Funktionsgruppe N“; es werden keine Namen vergeben.

Funktionsgraph (kein Redesign, neue Abschnitte): „Beziehungen aus dem Programmcode“ je Art mit Beleg, Quell- und
Zieladresse, Verfahren und offenem Punkt (Tooltip); „Nicht eindeutig bestimmt“ mit den Abbruchgründen;
„Funktionsgruppen ohne Namen“ (`Unbekannte Funktionsgruppe N`, „Programmcode“ oder „nur Struktur“, bekannte
Funktionen nur aus Definitionen, Widersprüche genannt); „Funktionszuordnung“ wie bisher. Ohne Definition wird keine
Funktion benannt (GUI-Test).

### 7.5 Andere Softwarestände und Familien (Test C, D)

Funktionen wandern nur mit übertragenen Namen (Namensübertragung, Status „Vermutet“, nie Anker). Aufeinanderfolgende
Vollabbilder einer Linie mit **verschiedener** A2L; Ähnlichkeit: Anteil gleicher Bytes (Stichprobe jedes
64. Byte) 1 … 100 % (Median MEVD17.2 53 %, MSD80 24 %), Anteil unverschobener Tabellen 0 … 100 % (Median 4 % / 13 %). Prüfung gegen die A2L des Ziels:

| Test | Paare | übertragen | richtig | falsch | nicht prüfbar |
|---|---:|---:|---:|---:|---:|
| C: MEVD17.2, andere Stände | 8 | 9 560 | 9 539 | 13 | 8 |
| C: MSD80, andere Stände | 18 | 16 183 | 16 114 | 13 | 56 |
| D: MEVD17.2 ↔ MSD80 (vorher) | 2 | 138 | 0 | **24** | 114 |
| D: MEVD17.2 ↔ MSD80 (neu) | 2 | 0 | 0 | 0 | 0 |

**Regel (umgesetzt):** Decken die gemeinsamen Anker weniger als 0,5 % der Fenster ab, sind die Dateien keine
Schwesterstände; es wird nichts übertragen und der Grund genannt (`MIN_ANCHOR_SHARE`). Schwesterstände: 1,8 … 80 %;
andere Familien 0,03 / 0,04 %. Kosten: zwei schwach verwandte MSD80-Paare (0,01 / 0,05 %) verlieren 44 richtige
Zuordnungen (0 falsche, 257 nicht prüfbare). Ein MSD80-Paar ist byte-gleich (gleiche Software, andere A2L) und schönt
Test C um 1 341 richtige; ohne dieses Paar bleiben 14 773 richtig, 13 falsch.

### 7.6 Direktlade-Regel: Gegenbeispiele (Paket C)

Gemessen (Vollabbilder, eine Datei je A2L): MSD80 lädt 93 680 Adressen direkt; 83 916 sind Objektanfänge, 28 liegen
**innerhalb** eines A2L-Objekts. 20 von 21 373 echten Tabellen (0,09 %) haben einen solchen Ladebefehl innen – das
Gegenbeispiel „Ladebefehl in ein gültiges Objekt“ existiert. Nur 4 davon werden auch am Anfang geladen; eine Schutzregel
„nicht widerlegen, wenn der Anfang geladen wird“ würde höchstens 4 retten und betrifft keinen heutigen Fund – nicht
umgesetzt. MEVD17.2: alle 10 078 direkten Ladebefehle liegen außerhalb der A2L-Objekte. Die Regel wirkt nur auf reine
Datenmuster-Funde; kein exakter Fund hatte einen Ladebefehl innen (0 verloren, Entwicklung und Holdout).

Synthetische Gegenbeispiele (Tests `test_rank_counterexamples.py`): schwaches Muster verdrängt keinen Codebeleg;
Ladebefehle am Anfang oder in Code-/Datensatz-Objekten entfernen nichts; Reihenfolge der Kandidaten und der
Ladeadressen ändert das Ergebnis nicht. **Gefundener Fehler:** Bei exaktem Gleichstand (u16/s16 mit gleichen Werten)
entschied die Eingabereihenfolge. Behoben: Typ und Form entscheiden, vorzeichenlos zuerst (wie `preferred_sign`).
Eine verworfene Alternative mit eigenem Beleg wird beim Gewinner genannt. Hinweis: Eine Zwischenfassung (alphabetisch,
s16 zuerst) senkte im Holdout den Anteil richtiger Typen bei MSV90-Kalibrierabbildern (0,677 → 0,674); die endgültige
Fassung ergibt 0,681. Der Holdout war damit am Erkennen beteiligt; die Regel selbst stammt aus den Entwicklungsdaten.

### 7.7 Datentyp-Status

„Wertgleich ist nicht datentypgleich“: Haben die Werte kein gesetztes oberstes Bit, ergeben beide Lesarten dieselben
Zahlen; das ist jetzt „wertgleich“ (kein Typbeleg), nicht mehr „abgeleitet“. Neu „codebelegt“ (Ladebefehle der
Routine; gewinnt auch bei gleichen Werten), Widersprüche werden genannt (Ladebefehle uneinig, Byte-Reihenfolge offen,
Konflikt Erkennung/Definition aus der Fusion). **Fehler behoben:** Namensübertragung, XDF-Vorschau und
Referenzsignaturen galten als „bestätigt“ (jetzt „abgeleitet“, Umrechnung Rohwert), manuell gewählte Rohdaten ebenso
(jetzt „unbestimmt“). Das „?“ bleibt bei allem außer bestätigt/codebelegt.

### 7.8 Kennlinien und Achsen (1D)

Exakt = Kandidat am Anfang eines 1D-Referenzobjekts mit gleicher Zellenzahl und Breite. Vorzeichen nur auswertbar,
wenn ein Wert das oberste Bit setzt; Byte-Reihenfolge nur, wenn die Lesarten sich unterscheiden.

| | MEVD17.2 | MSD80 |
|---|---:|---:|
| 1D-Kandidaten / exakt | 43 919 / 39 798 | 67 124 / 63 175 |
| davon Kennlinienwerte / Achsen | 7 549 / 32 249 | 12 330 / 50 836 |
| falsche Breite / falsche Länge | 623 / 26 | 910 / 43 |
| Vorzeichen richtig / falsch / nicht auswertbar | 7 967 / 1 219 / 30 612 | 10 496 / 2 382 / 50 297 |
| Byte-Reihenfolge richtig / falsch / nicht auswertbar | 34 957 / 414 / 1 718 | 52 914 / 332 / 2 511 |
| gemeinsame Achsen (≥ 2 Nutzer) gefunden / einmal / verfehlt | 0 / 94 / 1 372 | 2 238 / 338 / 10 418 |
| feste Achsen (nicht gespeichert) | 362, nicht auswertbar | 0 |

rc1, PR #30 und neu sind identisch (0 verloren, 0 gewonnen). Nicht auswertbar: ob ein falsches Vorzeichen mit „?“
markiert war (die 1D-Auswertung speichert die Markierung nicht).

### 7.9 Erkennung: Vergleich rc1 / PR #30 / neu

| | rc1 | PR #30 | neu |
|---|---:|---:|---:|
| Entwicklung: exakt (von 52 508) | 32 058 | 32 058 | 32 058 |
| Entwicklung: Verwechslungen | 5 316 | 5 113 | 5 113 |
| Holdout (Regression): exakt (von 91 370) | 52 701 | 52 701 | 52 701 |
| Holdout: Verwechslungen | 10 743 | 10 541 | 10 541 |
| Holdout MSV90 Kalibrierung: Typ richtig | 0,677 | 0,677 | 0,681 |
| Negativsatz, Regressionssatz | – | unverändert | unverändert |

0 exakte Kennfelder verloren gegenüber rc1 und PR #30 (je Abbild).

### 7.10 Neue Daten

Erneute Suche (22.11.2026, nur allgemeine Begriffe, keine privaten Daten übertragen): keine rechtmäßig nutzbaren
A2L-/HEX-Paare für EDC16/17, MED17, MEVD17.2.3, MD1/MG1, MSD80/81, MSV90, Simos/SID oder Getriebesteuergeräte. Gefunden
nur Werkzeuge (asap2Go calibrationReader MIT, pyA2L LGPL, a2lfile MIT/Apache, Atlas AGPL) und eine Sammlung von
ME7-Abbildern, deren Code MIT-lizenziert ist, deren Firmware aber laut Beschreibung keine überprüfbare Herkunft hat –
**ungeeignet**, nichts heruntergeladen. Kein bekannter Datensatz wurde als neuer Holdout ausgegeben. Lücke bleibt.

### 7.11 Leistung, Speicher, Qt-Abbau

Wiederholter Lauf (22.11.2026, ohne Fremdlast): je Version 5 Zeitläufe und 2 Speicherläufe abwechselnd, jeder in
eigenem Prozess; alle 14 Läufe regulär beendet (der Speicherlauf der Vorrunde war von außen mit 0x40010004 beendet
worden).

| Abbild | rc1 Median (min–max, σ) | neu Median (min–max, σ) | Spitzenspeicher rc1 → neu | exakt rc1 = neu |
|---|---:|---:|---:|---:|
| MSD80-N53/N54 | 14,31 s (13,87–14,68, 0,29) | 14,64 s (14,11–15,03, 0,33) | 87,5 / 87,2 → 86,3 / 86,3 MB | 620 |
| MSV90-N52 | 15,03 s (14,41–15,13, 0,30) | 15,20 s (14,98–15,89, 0,40) | 86,3 / 86,3 → 86,3 / 86,3 MB | 526 |

Etwa +0,2 bis +0,3 s je Abbild (direkte Ladebefehle, seit PR #30); die Bereiche überlappen. Die Datenflussanalyse
läuft nicht im Scan, nur beim Öffnen des Funktionsgraphen: 2,9–3,7 s und 60–64 MB Spitzenspeicher (tracemalloc, nur
Python-Objekte) je Vollabbild. Grenzen: nur zwei Abbilder, ein Rechner, ein Tag; Streuung zwischen Tagen bisher bis 7 %.

**Qt-Abbau:** Ursache der „QLabel already deleted“-Meldungen: `QTimer.singleShot(0, self.methode)` ohne Kontextobjekt
und die Rückrufe der Checksummenprüfung liefen nach dem Löschen des Hauptfensters (Testende) noch auf gelöschten
Kindfenstern. Behoben: verzögerte Aufrufe mit Fenster als Kontext (Qt verwirft sie), Rückrufe prüfen, ob das Fenster
noch existiert. Test reproduziert den Fehler mit dem alten Stand (4 Meldungen) und besteht mit dem neuen. Drei
vollständige Testläufe: je Exit-Code 0, 0 Meldungen (1 328–1 329 bestanden, 22 übersprungen). Die bestehende
Fensterbereinigung des Testlaufs bleibt.

## 8. Qualitätsphase 3 (24.11.2026): Zuverlässige Funktionsidentifikation und Achsenerkennung

Herkunft aller Zahlen: **Entwicklungsdaten** (58 Abbilder; Funktionsebene: die 28 Vollabbilder mit Programmcode,
MEVD17.2 9, MSD80 19), drei Salze summiert, sofern nicht anders vermerkt. Jede Regel wurde an **einer** Linie
entworfen und an der **anderen** gegengeprüft; beide Linien stehen getrennt da. Der bekannte Holdout dient nur als
Regression (§ 8.6). Es gibt **keine neue unabhängige Testgruppe** (§ 8.8). Wahrscheinlichkeiten werden nicht
angegeben, nur Zählungen.

Einordnung: **PR #30** = Stand vor dieser Phase (Commit `fad6fd2`); **neu** = dieser Stand; **entwicklungsgeprüft**
= an Entwicklungsdaten gemessen, nicht unabhängig validiert.

### 8.1 Funktionsidentifikation: Enthaltung statt falscher Namen

**Analyse (PR #30, Entwicklungsdaten):** Die meisten falschen Namen entstehen, wenn eine Tabelle nur **eine**
Belegfamilie hat (fast immer: gemeinsame gespeicherte Achse) und der richtige Name unter den Ankern fehlt oder fern
liegt. Bei MEVD17.2 mit 1 % Ankern gingen 579 von 591 falschen Namen allein auf die Achse zurück. Die
Zuverlässigkeit einer Beziehungsart ist **linienabhängig**: Unter Ankerpaaren nennt eine gemeinsame Achse bei
MEVD17.2 nur in 47–62 % dieselbe Funktion, bei MSD80 in rund 90 %.

**Regel (umgesetzt, `LOCAL_CHECK = 'single'`):** Beruht ein Funktionsvorschlag auf nur einer Belegfamilie (wäre
„Vermutet“), muss die Funktion unter den je zwei nächstgelegenen Ankern links und rechts (nach Adresse) vorkommen.
Sonst bleibt die Tabelle „Funktion unbekannt“; die zurückgehaltene Funktion steht mit Grund („Speicherlage spricht
dagegen“) und fehlendem Beleg in der Detailansicht. Vorschläge aus zwei unabhängigen Belegfamilien („Stark gestützt“)
prüft die Regel nicht. Grundlage: Die Kalibrierung ist nach Softwaremodulen abgelegt; ein ferner Name ohne zweiten
Beleg ist eher eine gemeinsame Größe als eine gemeinsame Funktion.

**Weitere Regeln:** Eine Achse, deren Nutzer sich über die Punktzahl uneinig sind, stimmt nicht ab und wird als
Widerspruch genannt. Ein übernommener Name wird nie „bestätigt“; widersprechen Name und Beziehungen, bleibt die
Funktion unbekannt. Hypothesen dienen nie als Anker (keine Ketten).

**Geprüft und nicht übernommen (Schalter bleiben für Ablationen):**

| Variante | Ergebnis (Entwicklungsdaten) |
|---|---|
| gemeinsame Quelle (Achse, Routine, Ergebnisvariable) stimmt erst ab 10 % übereinstimmender Anker (`HUB_MIN_SHARE`) | an MEVD17.2 entworfen; an MSD80 schädlich: 1 % Anker 14 373 → 617 richtige Namen |
| Selbstprüfung je Beziehungsart an den Ankern derselben Datei (`SELF_CHECK`) | nahezu wirkungslos; wo sie greift, kostet sie mehr richtige als falsche Namen (MEVD17.2, 10 % Anker, ein Salz: −906 richtig, −34 falsch) |
| Speicherlage-Prüfung für jeden Vorschlag (`LOCAL_CHECK = True`) | gleiche falsche Namen wie die umgesetzte Regel, auf MSD80 weniger richtige |

**Präzision-Abdeckung (Entwicklungsdaten, drei Salze summiert; richtig / falsch, Präzision = richtig unter benannten).**
Abdeckung = richtig unter allen auswertbaren verdeckten Tabellen (*n*); viele haben gar keine Beziehung zu einem Anker.

| Aufteilung | MEVD17.2 *n* | MEVD17.2 PR #30 | MEVD17.2 neu | MSD80 *n* | MSD80 PR #30 | MSD80 neu |
|---|---:|---:|---:|---:|---:|---:|
| Anker 50 % | 319 862 | 74 306 / 170 (99,8 %) | 74 306 / 92 (99,9 %) | 345 437 | 82 366 / 2 953 (96,5 %) | 73 938 / 2 486 (96,7 %) |
| Anker 25 % | 480 168 | 32 607 / 320 (99,0 %) | 32 607 / 79 (99,8 %) | 517 371 | 74 252 / 2 618 (96,6 %) | 63 851 / 1 641 (97,5 %) |
| Anker 10 % | 576 002 | 10 482 / 983 (91,4 %) | 10 474 / 288 (97,3 %) | 620 573 | 62 863 / 2 370 (96,4 %) | 52 101 / 1 143 (97,9 %) |
| Anker 5 % | 608 214 | 4 987 / 1 232 (80,2 %) | 4 985 / 494 (91,0 %) | 654 822 | 56 321 / 1 681 (97,1 %) | 45 404 / 969 (97,9 %) |
| Anker 1 % | 633 539 | 991 / 591 (62,6 %) | 991 / 393 (71,6 %) | 682 329 | 46 407 / 447 (99,0 %) | 35 987 / 339 (99,1 %) |
| Speicherblöcke 50 % (räumlich getrennt) | 335 385 | 847 / 506 (62,6 %) | 812 / 127 (86,5 %) | 390 707 | 24 083 / 1 195 (95,3 %) | 14 813 / 152 (99,0 %) |
| Speicherblöcke 10 % | 577 507 | 355 / 331 (51,7 %) | 351 / 28 (92,6 %) | 612 124 | 5 941 / 692 (89,6 %) | 2 486 / 14 (99,4 %) |
| ganze Funktionen 50 % (verdeckt) | 265 996 | 0 / 779 | 0 / 497 | 365 444 | 0 / 7 857 | 0 / 5 713 |

- **„Stark gestützt“ und falsch:** unverändert (MEVD17.2 0; MSD80 29 / 7 / 3 / 3 / 0 bei 50 / 25 / 10 / 5 / 1 %, 20 bei
  verdeckten Funktionen) – die Regel betrifft nur „Vermutet“. **„Vermutet“ und falsch:** MEVD17.2 10 % 983 → 288,
  MSD80 10 % 2 367 → 1 140.
- **Korrekt zurückgehalten** (Funktion unter den Ankern nicht vorhanden, Tabelle blieb unbekannt): steigt leicht, z. B.
  verdeckte Funktionen MSD80 357 587 → 359 731 von 365 444.
- **Abdeckungsverlust:** MEVD17.2 praktisch keiner (höchstens 35 richtige Namen je Aufteilung); MSD80 10 % (Anker
  50 %) bis 22 % (Anker 1 %) der richtigen Namen bei Tabellenaufteilungen, 38–58 % bei Speicherblöcken. Auf MSD80 stützen ferne Achsen häufiger die richtige Funktion
  als auf MEVD17.2; die Regel kann das nicht unterscheiden.
- **Andere Softwarestände und fremde Familien** (Namensübertragung, unverändert gegenüber PR #30): gleiche Linie
  25 653 richtig / 26 falsch von 25 743 übertragenen Namen; fremde Familie 0 Übertragungen. Übertragene Namen sind
  nie Anker und nie „bestätigt“.
- **Völlig unbekannte Funktionen:** Bei 0 % Ankern wird nichts benannt (0 falsch). Bei verdeckten Funktionen ist jeder
  Name falsch; die Regel senkt sie um 36 % (MEVD17.2) bzw. 27 % (MSD80), beseitigt sie aber nicht.

**Hauptgründe für „Funktion unbekannt“:** keine Beziehung zu einem Kennfeld mit bekannter Funktion;
Speicherlage spricht gegen den einzigen Beleg; Belege führen zu verschiedenen Funktionen; Achse mit uneinigen Nutzern;
nur „gleiche Eingangsgröße“ oder „Ergebnis fließt in die andere Tabelle“ (stimmen nicht ab).

### 8.2 Gemeinsame Achsen

**Modell (neu, `core/axis_refs.py`):** Kennfeld → Achsenreferenz → gespeichertes Achsenobjekt. Jede Achse mit mehr als
einem Punkt hat eine Referenz mit Status **gespeichert** (Adresse belegt durch Definition, Programmcode oder eigenen
Datensatzkopf), **fest** (Definition nennt Punkte ohne Adresse, z. B. A2L `FIX_AXIS`) oder **ungeklärt** (keine Quelle
nennt die Adresse; sie wird nicht aus Werten geraten). Gemeinsam heißt: **gleiche Speicheradresse**. Gleiche Werte an
verschiedenen Adressen bleiben zwei Objekte. TriCore-Adressen derselben Bytes (gecacht 0x8…/ungecacht 0xA…) werden als
Aliase eines Objekts geführt. Widersprüche je Objekt: verschiedene Punktzahlen, verschiedene Achsnamen,
verschiedene Zelltypen in Definitionen, Achse im Wertebereich eines Nutzers. Ein widersprüchliches Objekt ist kein
Funktionsbeleg. A2L `AXIS_DESCR`/`AXIS_PTS`/`COM_AXIS`/`FIX_AXIS`/`RECORD_LAYOUT` werden wie bisher beim Verknüpfen
gelesen; `axis_refs` ordnet sie nur ein. Aliasing (gleiche Achse unter zwei A2L-Adressen) kam in den Daten nicht vor.

**Messung (Entwicklungsdaten; rc1, PR #30 und neu identisch):**

| | MEVD17.2 | MSD80 |
|---|---:|---:|
| gemeinsame Referenzachsen (≥ 2 Nutzer) | 1 466 | 12 994 |
| gefunden (≥ 2 Funde nutzen sie) / nur ein Fund / verfehlt | 0 / 94 / 1 372 | 2 238 / 338 / 10 418 |
| falsch zusammengelegte Achsen / falsch zugeordnete Kennfelder | 0 / 0 | 0 / 0 |
| Achsadresse der Funde richtig / falsch | 31 302 / 36 | 54 388 / 203 |
| Achsadresse nicht prüfbar (keine Referenztabelle an der Stelle) | 2 439 | 1 153 |
| feste Achsen (nicht gespeichert, nicht auswertbar) | 362 | 0 |
| Achs-Zelltyp | nicht auswertbar (nicht im Export) | nicht auswertbar |

**Ursachen:** Verfehlt werden gemeinsame Achsen, weil ihre **Nutzer** nicht gefunden werden, nicht weil Achsen falsch
verbunden würden (0 falsche Zusammenlegungen). MEVD17.2: Die Nutzer gemeinsamer Achsen werden im Programmcode kaum
statisch adressiert – Ghidra fand für 1 252 gesuchte Adressen (beide Segmente) nur 29 statische Verweise; die
Adressen entstehen zur Laufzeit. *(Korrektur Qualitätsphase 4, § 9.4: weitgehend widerlegt. Gesucht wurde nach
Datenstarts; der Code adressiert aber die Datensatzköpfe, und die meisten davon statisch.)* MSD80: 1 162 Tabellenaufrufe haben zwei oder mehr Achsen-Vorabsuchen auf demselben
Pfad, ergeben aber keinen verwertbaren Achsdeskriptor (leere, doppelte oder nicht als Achse lesbare Vorabsuchen).
**Nicht umgesetzt:** Achsen über gleiche Werte zusammenlegen (verboten, kein Speicherbeleg).

### 8.3 Datenfluss (TriCore)

Keine neue Datenflussregel. Für Achsen hilft der begrenzte Datenfluss nicht: Bei MEVD17.2 fehlt die statische
Adresse der Nutzer (siehe 8.2), bei MSD80 scheitern die Vorabsuchen vor der Datenflussstufe. Eine Erweiterung lohnt
erst mit einer Adressrechnung über Basisregister und Indizes (Laufzeitadressen); das ist nicht begonnen.
Laufzeit und Speicher der Funktionsebene: `identify()` auf allen Referenzobjekten eines Vollabbilds (10 000–20 000
Tabellen, unter Parallellast gemessen) PR #30 0,5 / 3,1 / 5,9 s, neu 0,6 / 3,5 / 6,2 s; Spitzenspeicher unverändert
(29 / 152 / 210 MB).

### 8.4 Technische Gruppe, Hypothese, bestätigte Funktion; Oberfläche

Getrennt dargestellt: technische Gruppe („Unbekannte Funktionsgruppe N“, nur Struktur/Programmcode), Hypothese
(„Vermutet“, „Stark gestützt“ – immer „nicht bestätigt“) und bestätigte Funktion (eigene geprüfte Definition).

- **Detailansicht:** Achsen mit Status, Adresse, Punktzahl und Quelle; gemeinsame Achse mit den anderen Nutzern;
  Widersprüche des Achsobjekts; Funktionsstatus mit Belegen, „Funktion unbekannt“ mit Grund, zurückgehaltene
  Funktionen, Widersprüche, fehlender Beleg.
- **Funktionsgraph:** Abschnitt „Achsenreferenzen: N gespeichert · N fest · N ungeklärt“ mit widersprüchlichen
  Achsobjekten und ungeklärten Referenzen; Abschnitte „Widersprüchlich (Funktion unbekannt)“ und „Zurückgehalten
  (Funktion unbekannt, Belege reichen nicht)“; jeder nicht bestätigte Name trägt „(Status, nicht bestätigt)“.
- **Filter** (in der bestehenden Belegauswahl, kein Umbau): „Gemeinsame Achse“, „Achsenreferenz ungeklärt“,
  „Funktion unbekannt“, „Funktion vermutet“, „Widersprüchliche Funktionsbelege“.

### 8.5 Kennlinien und Achsen (1D): „?“ statt falscher Sicherheit

Ausgewertet wird jetzt auch, ob ein falscher Typ mit „?“ markiert war. Unterschieden: **technisch falscher Typ**
(Breite, Vorzeichen, Byte-Reihenfolge widersprechen der Definition), **falsche sichtbare Rohinterpretation** und
**nicht bestimmbarer Typ** (beide Lesarten ergeben dieselben Zahlen: „nicht auswertbar“, z. B. Vorzeichen ohne
gesetztes oberstes Bit; MEVD17.2 20 367, MSD80 32 893 exakte Funde mit technisch anderem, aber wertgleichem Typ).

**Befund (PR #30):** Falsche Vorzeichen waren fast immer markiert, falsche Byte-Reihenfolge und falsche Breite **nie**.
Ursachen: (a) Die 16-Bit-Achsen von Datensätzen außerhalb der Byte-Reihenfolge-Abstimmung (flache Werte, die am
nächsten Kopf enden) behielten die zuerst probierte Lesart (big), obwohl die Mehrheit des Abbilds little ist und beide
Lesarten steigen – alle falschen Byte-Reihenfolgen exakter 1D-Funde (MEVD17.2 414, MSD80 332). (b) Die Werte einer
Kennlinie `n, X[n], W[n]` wurden als 16 Bit gelesen, auch wenn kein Datensatz direkt dahinter beginnt; dann sind
8-Bit-Werte gleich möglich – 603 von 631 bzw. 877 von 877 falschen Breiten (an MEVD17.2 entworfen, an MSD80 geprüft).

**Regeln (umgesetzt, nur Markierung, keine Typänderung):** (a) `ENDIAN_AXES_OPEN`: solche Achsen tragen „Byte-
Reihenfolge nicht belegt (gegen die Mehrheit der Datensätze gelesen, beide Lesarten steigen)“. (b) `CURVE_WIDTH_OPEN`:
Kennlinienwerte ohne Datensatzkopf direkt hinter den 16-Bit-Werten tragen „Wertebreite offen“. Werte, Adressen,
Formen, Typen und Achsen aller Funde sind in allen 58 Entwicklungsabbildern unverändert.

| exakte 1D-Funde, falsch und mit „?“ markiert | rc1 | PR #30 | neu |
|---|---:|---:|---:|
| Vorzeichen falsch: markiert / unmarkiert – MEVD17.2 | 0 / 1 219 | 1 210 / 9 | 1 210 / 9 |
| Vorzeichen falsch: markiert / unmarkiert – MSD80 | 0 / 2 382 | 2 334 / 48 | 2 334 / 48 |
| Byte-Reihenfolge falsch: markiert / unmarkiert – MEVD17.2 | 0 / 414 | 0 / 414 | 414 / 0 |
| Byte-Reihenfolge falsch: markiert / unmarkiert – MSD80 | 0 / 332 | 0 / 332 | 332 / 0 |
| Breite falsch: markiert / unmarkiert – MEVD17.2 | 0 / 623 | 0 / 623 | 573 / 50 |
| Breite falsch: markiert / unmarkiert – MSD80 | 0 / 910 | 0 / 910 | 875 / 35 |
| exakte 1D-Funde mit irgendeinem „?“ – MEVD17.2 / MSD80 | 0 / 16 | 2 123 / 3 089 | 3 555 / 4 073 |

Preis: Auch richtige Lesarten erhalten ein „?“, wo die Werte es nicht entscheiden (z. B. 1 682 bzw. 962 richtige
16-Bit-Kennlinien ohne Kopf dahinter). Ein „?“ ist eine offene Frage, kein Fehler. **Gemessen, nicht umgesetzt:**
Beginnt direkt hinter 8-Bit-Werten ein Datensatz (und nicht hinter 16-Bit-Werten), waren 16 Bit in allen Fällen falsch
(MEVD17.2 160, MSD80 281, 0 richtig); ein Umstellen auf 8 Bit wäre eine Typänderung und bleibt für die nächste Runde.

### 8.6 Erkennung: Vergleich rc1 / PR #30 / neu

Entwicklungsdaten (58 Abbilder) und Holdout (105 Abbilder, nur Regression):

| | rc1 | PR #30 | neu |
|---|---:|---:|---:|
| Entwicklung: exakt (von 52 508) | 32 058 | 32 058 | 32 058 |
| Entwicklung: Verwechslungen | 5 316 | 5 113 | 5 113 |
| Entwicklung: teilweise / unklar / nicht bewertbar | 2 197 / 305 / 1 743 | 2 196 / 305 / 1 658 | 2 196 / 305 / 1 658 |
| Entwicklung: Datentyp richtig unter exakten | 95,8 % | 95,8 % | 95,8 % |
| Holdout: exakt (von 91 370) / Verwechslungen | 52 701 / 10 743 | 52 701 / 10 541 | 52 701 / 10 541 |
| 1D exakt (Entwicklung) MEVD17.2 / MSD80 | 39 798 / 63 175 | 39 798 / 63 175 | 39 798 / 63 175 |
| Codebeziehungen, Funktionsgruppen | – | wie § 7 | unverändert (kein Code geändert) |

Alle Funde (Lage, Form, Typ, Byte-Reihenfolge, Achsadressen und -werte) sind zwischen PR #30 und neu in allen 58
Entwicklungs- und 105 Holdout-Abbildern identisch; geändert haben sich nur die „?“-Markierungen. 0 exakte Kennfelder
verloren. Holdout, nur Regression: falsche Byte-Reihenfolgen exakter 1D-Funde jetzt zu 92 % markiert (3 930 von 4 268),
falsche Breiten zu 90 % (1 735 von 1 934); 0 falsche Achsenzusammenlegungen. Die Markierungszahl von PR #30 auf dem
Holdout wurde nicht gemessen (älterer Export ohne Markierung).

Laufzeit und Speicher (Vollabbilder, je Version 3 Zeitläufe und 2 Speicherläufe abwechselnd, ohne Fremdlast,
24.11.2026):

| Abbild | rc1 Median (min–max) | PR #30 | neu | Spitzenspeicher rc1 / PR #30 / neu |
|---|---:|---:|---:|---:|
| MSD80-N53/N54 | 13,72 s (13,61–14,03) | 14,34 s (14,07–14,76) | 14,01 s (13,83–14,08) | 87,2 / 87,2 / 87,2 MB |
| MSV90-N52 | 14,63 s (14,47–14,77) | 14,64 s (14,45–14,69) | 14,64 s (14,46–14,98) | 86,3 / 86,3 / 86,3 MB |

Die Unterschiede liegen in der Streuung; ein Rechner, ein Tag, zwei Abbilder.

### 8.7 Lokales Testverfahren für Tester (`tools/tester_report.py`)

Für neue Daten ohne Datenweitergabe: Ein Tester misst lokal mit eigener Datei und eigener Definition (Erkennung,
Achsenreferenzen, Funktionsidentifikation unter Ankeraufteilungen). Das Werkzeug zeigt zuerst den **vollständigen**
Export als Vorschau und schreibt nichts. Gespeichert wird nur mit einem Zustimmungscode, der an genau diesen Inhalt
gebunden ist (geänderter Inhalt → neue Vorschau). Der Export enthält nur Zählwerte, Programmversion und die vom Tester
eingetragene Linie – keine Namen, Adressen, Dateinamen, Größen, Hashes, Pfade oder Zeitstempel; eine Prüfung weist
Felder dieser Art und alle Listen zurück. Nichts wird gesendet; die Weitergabe entscheidet der Tester.

### 8.8 Neue Daten

Gezielte Suche (24.11.2026, andere Begriffe als zuvor: Forschungsdatensätze, Demo-Steuergeräte, offene
Steuergeräte-Projekte; keine privaten Daten übertragen): Gefunden wurden eine Sammlung von Original-Abbildern mit
A2L-/XDF-Definitionen ohne Herkunfts- oder Rechteangabe (eine MIT-Lizenzangabe des Sammlers ersetzt kein
Nutzungsrecht an Herstellersoftware) und ein Forschungsprojekt mit einem Getriebesteuergeräte-Abbild ohne
Rechteangabe und nur synthetischer A2L. **Beide ungeeignet, nichts heruntergeladen.** Offene Projekte (rusEFI/FOME)
liefern keine A2L/HEX-Paare. Die Lücke bleibt; das Testverfahren in § 8.7 ist der Weg zu neuen Messwerten.

### 8.9 Softwarequalität

| Prüfung | Ergebnis (24.11.2026) |
|---|---|
| pytest vollständig, lokal Python 3.13, je Lauf eigenes isoliertes Testprofil | Endstand: 2 Läufe je 1 353 bestanden, 22 übersprungen, Exit-Code 0, 0 Qt-Meldungen „QLabel already deleted“. Zwei frühere Läufe ebenfalls grün, aber nicht gewertet: einer vor dem letzten neuen Test (1 352), bei einem wurde während des Laufs Quelltext geändert. |
| übersprungene Tests (22) | 15 benötigen private, nie gebündelte Daten (lokale Referenz-Originale 9, eigene Abbilder/Proben 3, private Abbilder 3); 2 optionale Vergleichsdateien (eine lokale, eine öffentliche) nicht eingerichtet; 2 starten die echte Anwendung bzw. messen Zeiten nur mit `ECU_STUDIO_GUI_TESTS=1`; 2 schreiben Wegwerf-Registry-Schlüssel und laufen nur auf CI-Runnern; 1 braucht das Recht für symbolische Links |
| CI (Python 3.11 / 3.12), CodeQL | nach dem Push im PR #30 (Ergebnis dort) |
| GUI-Smoke (isoliertes Profil, ohne Bildschirm) | bestanden, 10 Prüfungen, 0 QLabel-Meldungen |
| i18n | 2 400 Texte, 0 ohne Übersetzung |
| Firmware-Guard, Modellsperre, zurückgezogene Modelle | Guard über Commit-/Push-Hooks, nicht umgangen; Modellsperre und zurückgezogene Modelle in der Testsuite grün |
| Negativkontrollen (FOME, rusEFI, Speeduino) | 549 Funde, 0 sicher falsch; identisch mit PR #30 |
| Regressionsgruppe (MS42/MS43/MSD80-XDF, synthetische Strukturen und Negativabbilder) | identisch mit PR #30 |
| Registry | nur gelesen; Export vor und nach den Prüfungen verglichen, keine Wiederherstellung |
| geschützte Arbeitskopie, Releases, Tags | unverändert |

### 8.10 Grenzen

- Alle Zahlen stammen aus zwei Linien eines Datengebers (MEVD17.2, MSD80, TriCore); andere Familien sind nicht gemessen.
- Die Speicherlage-Regel setzt modulweise abgelegte Kalibrierung voraus; wo das nicht gilt, kostet sie Abdeckung.
- Bei sehr wenigen Ankern (1 %) bleibt MEVD17.2 schwach (71,6 % Präzision); MSD80 verliert dort am meisten
  Abdeckung (22 % der richtigen Namen).
- Verdeckte Funktionen bleiben die schwerste Lage: Jeder Name ist dort falsch.
- Gemeinsame Achsen bei MEVD17.2 werden weiter nicht gefunden; die Ursache liegt in der Erkennung der Nutzer.

## 9. Qualitätsphase 4 (25.11.2026): Open-Source-Vergleich, Adressauflösung, Achsen

Herkunft aller Zahlen: **Entwicklungsdaten** (58 Abbilder), sofern nicht anders vermerkt; der bekannte Holdout
(105 Abbilder) nur als Regression. Einordnung: **PR #30 vor QP4** = Commit `0110130`; **neu** = dieser Stand;
alles **entwicklungsgemessen, nicht unabhängig validiert**. Die A2L dient nur der Auswertung, nie als Eingang.

### 9.1 Open-Source-Vergleich

Fünf Projekte wurden im Quelltext gelesen (nicht ausgeführt), mit Commit, Datei und Zeile:
[OPEN_SOURCE_RECOGNITION_RESEARCH.md](OPEN_SOURCE_RECOGNITION_RESEARCH.md). Das Ergebnis:

- Neu für uns waren zwei Ideen: Achsen mit gleichen Stützstellen (PPD Maps) und die Auflösung von Achsenzuständen
  über mehrere Pfade (BimmerStein MS41). Beide sind als eigene Umsetzung eingebaut (§ 9.2, § 9.3).
- Die Rollenfindung über gültige Aufrufe, der Typ aus Ladebefehlen und die Breite nur aus exakten Lücken
  (Denso-Werkzeug) bestätigen bereits vorhandene Regeln.
- Kennfeldnamen aus Wertebereichen und Familienvorlagen (ZedSuite) sind verworfen.
- Es wurde kein Code übernommen.

Die wirksamste Regel dieser Phase (§ 9.7) stammt nicht aus den Projekten. Sie ergab sich aus der Pflicht, jeden
verlorenen exakten Treffer zu erklären.

### 9.2 Code-belegte Achsen (`tricore_refs.CODE_AXES`, P1 und P2)

**Befund:** Bisher galt eine Achse nur als Achse, wenn ihre Stützstellen streng steigen. Liest eine erkannte
Interpolationsroutine einen Kopf als Achse, sagt aber schon der Code, dass dort eine Achse liegt. Wiederholte
Stützstellen am Ende („900, 900, 900“) und nicht bedatete Achsen (alle gleich) sind dann ebenfalls Achsen.

**Regel:** Eine solche Lesart wird nur angenommen, wenn die Breite (Vorabsuche) bzw. der Datensatzaufbau
(Datensatzroutine) feststeht. Beides muss dieselbe Routine an mindestens 5 streng lesbaren Aufrufen zeigen, zu
mindestens 90 % einheitlich. Die Werte wählen die Breite nie. Der Fund trägt in der Detailansicht den Hinweis
„Achsen nur durch den Programmcode belegt …, Stützstellen nicht streng steigend: wiederholte Stützstellen / alle
Stützstellen gleich (nicht bedatet)“.

| Entwicklungsdaten, 2D exakt | PR #30 vor QP4 | nur Code-Achsen | neu (alle Regeln) |
|---|---:|---:|---:|
| MEVD17.2 Vollabbilder (9 894 verifizierbar) | 6 741 | 8 508 | 8 508 |
| MSD80 Vollabbilder (15 613) | 13 389 | 14 723 | 14 790 |
| Kalibrierabbilder beider Linien (27 001) | 11 928 | 11 928 | 11 928 |
| Summe (52 508) | 32 058 | 35 159 | 35 226 |
| verlorene exakte Kennfelder | – | 0 | 0 |
| Verwechslungen | 5 113 | 5 124 | 4 478 |

Die neuen Funde sind überwiegend nicht bedatete Kennfelder (Nullen) mit nicht bedateten Achsen. Ihre Lage, Form und
Achsen sind aber richtig. Die 11 zusätzlichen Verwechslungen der Code-Achsen allein kommen alle aus reinen
Datenmuster-Funden, deren Lage sich durch die belegten Kennfelder verschiebt, keine aus einem Codeaufruf. Den
Rückgang auf 4 478 bewirkt § 9.7.

### 9.3 Vorabsuchen derselben Routine (`tricore_refs.PRE_FUNCTION`, P2)

**Analyse der MSD80-Vorabsuchen** (19 Vollabbilder, 19 347 Tabellenaufrufe nach Vorabsuchen, je Aufrufpfad
gezählt; vorher = PR #30 vor QP4, nachher = neu):

| Klasse (Pfad des Aufrufs) | Aufrufe | vorher Deskriptor | nachher mit Deskriptor: Achsen richtig / teilweise / keine Referenztabelle | nachher offen |
|---|---:|---:|---:|---:|
| zwei streng lesbare Achsen | 6 353 | 4 721 | 4 128 / 36 (+ 369 falsch, unverändert) / 290 | 1 530 |
| beide Achsen nicht streng lesbar | 8 857 | 0 | 8 435 / 209 / 5 | 208 |
| eine Achse nicht streng lesbar | 1 164 | 0 | 330 / 4 / 3 | 827 |
| letzte zwei Vorabsuchen gleich | 415 | 0 | 90 / 0 / 12 | 313 |
| keine Vorabsuche auf dem Pfad | 1 215 | 0 | 502 / 0 / 5 | 708 |
| nur eine Vorabsuche auf dem Pfad | 1 343 | 0 | 407 / 0 / 36 | 900 |

„Vorher Deskriptor“ der ersten Zeile umfasst auch 182 Deskriptoren über einen anderen Weg; 1 632 Aufrufe fielen
später weg (Formkonflikt, Breite, Überlappung). „Teilweise“ heißt: eine der beiden Achsen weicht von der Referenz ab
(meist eine wertgleiche Kopie, siehe § 9.5). Ein Deskriptor wird erst zum Fund, wenn die Zellbreite die Lücke exakt
füllt. Die Zählung je Aufrufpfad stammt aus einem Prüfskript, das die Routinenrollen ohne gelernte Registerrollen
bestimmt; die Klassen sind daher Näherungen.

Die Zählung oben gilt je Aufrufpfad und ist deshalb nicht direkt mit den 1 162 Aufrufen aus § 8.2 vergleichbar. Die
größte Klasse („beide Achsen nicht streng lesbar“, 8 857) löst fast vollständig § 9.2 (208 offen); bei „eine Achse
nicht streng lesbar“ bleiben 827 von 1 164 offen.

**Prototyp „Aufrufer“ (verworfen):** Zuerst geprüft wurde, ob die Vorabsuchen bei Aufrufen ohne zwei Vorabsuchen
im **Aufrufer** der Routine liegen (Gedanke aus BimmerStein). Auf zwei Abbildern ergab das 0 Auflösungen bei 160
Aufrufen. Die Aufrufer enthalten keine weiteren Vorabsuchen.

**Regel (umgesetzt):** Für einen Tabellenaufruf, den kein Pfad benennt, zählen die Vorabsuchen derselben Routine vor
dem Aufruf, nach Adresse geordnet, Wiederholungen zusammengefasst. Genau zwei verschiedene Achsen ergeben X (früher)
und Y (später). Alles andere bleibt offen: eine Achse, drei Achsen, ein Rücksprung zu einer früheren Achse oder ein
`ret` dazwischen. Die Regel gilt nur für Daten, die kein anderer Aufruf benennt; eine Pfad-Lesart wird nie
überstimmt. Messung beim Entwurf (zwei MSD80-Abbilder): 22 neue Tabellen mit genau zwei Achsen, alle 22 mit den
Referenzachsen. Mit mehr als zwei Achsen wären es 2 von 25 mit einer falschen Achse gewesen, deshalb nur genau zwei.

**Ergebnis:** Allein +50 exakte Kennfelder (nur MSD80; MEVD17.2 unverändert), 0 verloren, +7 Verwechslungen (reine
Datenmuster-Funde); zusammen mit § 9.2 +67. Die Achsen solcher Deskriptoren werden nur als Teil einer angenommenen
Tabelle verwendet, nie als eigene Achsenkandidaten. In einer früheren Fassung verdrängten sie bei MEVD17.2 16–18
Kennlinien-Datensätze je Abbild; das wurde vor der Endmessung behoben.

### 9.4 MEVD17.2: dynamische Adressen (P1)

Die Annahme der Aufgabe lautete, dass die Nutzer gemeinsamer Achsen bei MEVD17.2 erst zur Laufzeit adressiert
werden (§ 8.2: Ghidra fand 29 statische Verweise auf 1 252 Adressen). Diese Annahme ist **weitgehend widerlegt**:

- Ghidra hatte nach **Datenstarts** gesucht. Der Code nennt aber den **Datensatzkopf** (`n1, n2, X[n1], Y[n2], Z`;
  Kopf = erste Achse − 2).
- In einem Vollabbild werden rund 812 von 1 158 Kennfeldern und 705 von 1 359 Kennlinien über ihren Kopf statisch
  adressiert (`movh.a`/`lea`, globale Basisregister).

Warum diese Köpfe bisher keinen Fund ergaben (ein Abbild, Zählungen):

- 192 Kennfeldköpfe, an Datensatzroutinen übergeben, scheiterten an streng steigenden Achsen, fast immer wegen
  wiederholter Stützstellen. **Behoben durch § 9.2:** MEVD17.2 +1 767 exakte Kennfelder, falsche Achsadressen
  unverändert 36.
- Rund 613 Kennlinien je Abbild gehen an Routinen, die als Vorabsuche eingestuft sind. Sie werden nicht als
  Kennlinie benannt: **offen**, nächster Schritt.
- Rund 238 Kennfelder und 458 Kennlinien werden nur über Lade- und Speicherbefehle angesprochen, nicht über einen
  Interpolationsaufruf: **offen**.

**Echte Laufzeitadressen** sind selten. Zwei Prototypen ohne Nutzen:

- **Flash-Zeigertabellen:** 0 Treffer.
- **„Basisregister mit genau einer Definition in der Routine“:** 4 aufgelöste Adressen auf zwei Abbildern;
  verworfen.

Kennzahlen P1 (MEVD17.2, Entwicklungsdaten, PR #30 vor QP4 → neu):

| Kennzahl | Wert |
|---|---|
| zusätzlich aufgelöste Ausdrücke | keine echten Laufzeitadressen; die Köpfe waren bereits statisch aufgelöst |
| zusätzliche exakte Kennfelder | +1 767 (§ 9.2) |
| richtige / falsche Achsadressen | 31 302 → 35 658 / 36 → 36 |
| neue Verwechslungen | Vollabbilder 1 009 → 1 005 (mit § 9.7) |
| gemeinsame Achsen gefunden | 0 → 0 (von 1 466) |
| ungelöst mit Grund | Kennlinien an Vorabsuche-Routinen (~613 je Abbild), Lade-/Speicherzugriffe (~696 je Abbild) |

Gemeinsame Achsen bleiben bei MEVD17.2 unauffindbar. Die Kennfelder tragen ihre Achsen im eigenen Datensatz.
Gemeinsame Achsen sind dort eigene Achsobjekte (A2L `AXIS_PTS`), deren Nutzer über die oben offenen Wege
angesprochen werden.

### 9.5 Achsen: gefundene und falsche Zuordnungen (P2)

| MSD80, Entwicklungsdaten | PR #30 vor QP4 | neu |
|---|---:|---:|
| gemeinsame Referenzachsen gefunden / nur einmal / verfehlt (von 12 994) | 2 238 / 338 / 10 418 | 2 701 / 493 / 9 800 |
| Achsadresse der Funde richtig / falsch | 54 388 / 203 | 58 830 / 249 |
| falsch zusammengelegte Achsobjekte (betroffene Kennfelder) | 0 (0) | 34 (42) |

Analyse der falschen Achsen:

- **46 neue falsche Achsadressen,** alle auf neu gefundenen Tabellen; keine bisherige Tabelle wurde schlechter.
  Bei 38 davon sind die Bytes unserer Achse gleich denen der Referenzachse (wertgleiche Kopie an anderer Adresse).
  28 sind nicht bedatete Achsen.
- **Falsche Zusammenlegungen:** Achsobjekte, deren Stützstellen alle gleich sind, waren in 20 von 124 Fällen falsch
  zusammengelegt (16 %); Achsen mit echten Werten nur in 14 von 2 599 (0,5 %).
- **Maßnahme (Markierung, keine Änderung):** Ein gemeinsames Achsobjekt, dessen Nutzer alle gleiche Stützstellen
  lesen, trägt „nicht bedatet (alle Stützstellen gleich): gemeinsam nur über die Speicheradresse; wertgleiche Kopien
  an anderen Adressen sind möglich“ (`axis_refs.AxisObject.unapplied`, Detailansicht, Funktionsgraph).

Damit gilt die Aussage „0 falsche Zusammenlegungen“ aus § 8 nicht mehr: Die 34 Fälle sind die Kehrseite der
zusätzlich gefundenen Achsen. Der größere Teil betrifft nicht bedatete Achsen und ist markiert.

### 9.6 Kennlinien und Achsen (1D): Fehlerklassen (P3)

Klassifiziert wurden die 85 unmarkierten falschen Breiten aus § 8.5 (Entwicklungsdaten):

| Klasse | Anzahl | Maßnahme |
|---|---:|---|
| 8-Bit-Achse als 16-Bit-Datensatzachse gelesen; die Bytes steigen auch einzeln | 53 | „?“: Breite offen (neu) |
| 8-Bit-Kennlinie als s16 gelesen (nur das Vorzeichen markiert); hinter den 8-Bit-Werten beginnt eine Achse | 18 | nicht markierbar ohne hohen Preis (siehe unten) |
| 8-Bit-Kennlinie; hinter der 16-Bit-Lesart liegt zufällig ein Datensatzkopf | 10 | „?“ nur, wenn auch hinter den 8-Bit-Werten ein Datensatzkopf beginnt |
| in einem Wertblock | 4 | keine |

**Preis der Markierung:**

- Die Achsenregel markierte 39 falsche Breiten und 0 richtige.
- Eine Kennlinienregel, die auch bloße Anzahl-Achsen hinter den 8-Bit-Werten gelten ließ, markierte 18 falsche,
  aber 311 richtige Breiten. Deshalb zählt nur ein Datensatzkopf.

| exakte 1D-Funde | PR #30 vor QP4 | neu |
|---|---:|---:|
| unmarkierte falsche Breiten / falsche Vorzeichen – MEVD17.2 | 50 / 9 | 32 / 9 |
| unmarkierte falsche Breiten / falsche Vorzeichen – MSD80 | 35 / 48 | 14 / 48 |
| richtige Breiten mit „?“ – MEVD17.2 / MSD80 | 1 654 / 1 024 | 1 780 / 1 144 |

Die neue Breitenregel allein markiert keine richtige Breite zusätzlich (Ablation § 9.9: 1 654 / 1 024 unverändert).
Die höhere Zahl im Endstand kommt von den 4 553 zusätzlich gefundenen Kennlinien und Achsen aus § 9.7, die nach der
Regel aus § 8.5 markiert werden.

**Die 57 unmarkierten falschen Vorzeichen:**

- **48 MSD80-Achsen:** Nur vorzeichenlos gelesen steigen sie; die Definition nennt sie vorzeichenbehaftet, dann
  stiegen sie nicht. Hier widerspricht die Definition der Monotonie einer Interpolationsachse. Unsere Lesart ist
  strukturell belegt und bleibt ohne „?“.
- **9 MEVD17.2-Achsen:** Folgefehler der Byte-Reihenfolge, die bereits mit „?“ markiert ist.

**Statusbegriffe:** Die Status Bestätigt / Codebelegt / Abgeleitet / Alternativ / Wertgleich / Unbestimmt bleiben
unverändert (`type_status`).

**8-Bit-Experiment (`curve_records.CURVE_U8_BY_HEAD`, Standard aus, Typänderung):** Beginnt direkt hinter den
8-Bit-Werten ein Datensatzkopf und keiner hinter den 16-Bit-Werten, werden die Werte als 8 Bit gelesen. Gemessen
gegen den Stand ohne § 9.7:

| 8-Bit-Experiment, Entwicklungsdaten | MEVD17.2 | MSD80 |
|---|---:|---:|
| positive Beispiele: Breite jetzt richtig (exakte 1D-Funde) | +382 | +590 |
| negative Beispiele: bisher richtige Breite jetzt falsch (verlorene exakte Treffer) | 0 | 0 |
| falsche Breiten gesamt | 618 → 236 | 910 → 394 |
| unmarkierte falsche Breiten | 32 → 32 | 14 → 14 |

Das Experiment bleibt **aus**: Es ändert den Datentyp, und die Regel ist nur an diesen Daten entworfen. Es ist der
Kandidat für die nächste Phase, sobald eine Linie außerhalb der Entwicklungsdaten es prüfen kann. Eingeschaltet
trägt jeder so gelesene Fund „Wertebreite 1 Byte … (Experiment; ungeprüft)“ und ein „?“ bei der Breite; er ist nie
bestätigt.

### 9.7 Kennlinien-Datensätze widerlegen Datenmuster-Funde (`scoped_scan.CURVE_HEADS_REFUTE_PITCH`)

**Befund:** Mit § 9.2 und § 9.3 gingen 102 exakte 1D-Funde verloren (MEVD17.2 37, MSD80 65). 72 davon überdeckte ein
reiner Datenmuster-Fund (Zeilenabstand, keine Referenztabelle an seinem Start). Die neuen Kennfelder hatten solche
Funde verschoben. Kennlinien-Datensätze (`n, X[n], W[n]` in einer Datensatzkette) füllen seit rc1 nur Lücken und
verloren deshalb gegen jede Fläche.

**Regel:** Liegt der Kopf eines verketteten Kennlinien-Datensatzes echt innerhalb eines reinen Datenmuster-Fundes,
ist der Fund keine einzelne Tabelle und wird verworfen. Das ist dieselbe Begründung wie bei Kennfeld-Datensatzköpfen
(`PITCH_NO_RECORDS`, seit 1.21.0). Die Regel wirkt nach der Rangfolge als reine Entfernung, damit kein schwächerer
Fund nachrückt. Belegte Funde (Programmcode, Datensatzkopf) sind nie betroffen.

| Entwicklungsdaten | ohne Regel (QP4 sonst) | mit Regel | nur diese Regel gegen PR #30 vor QP4 |
|---|---:|---:|---:|
| exakte 2D-Kennfelder | 35 226 | 35 226 (0 verloren) | 32 058 → 32 058 |
| Verwechslungen | 5 138 | 4 478 | 5 113 → 4 469 |
| exakte 1D-Funde MEVD17.2 / MSD80 | 43 420 / 64 805 | 44 801 / 68 044 | 39 798 / 63 175 → 41 160 / 66 366 |
| verlorene exakte 1D-Funde | – | 0 | 0 |
| unmarkierte falsche Breiten / Vorzeichen | unverändert | unverändert | unverändert |

Die Regel wirkt auch auf reinen Kalibrierabbildern ohne Programmcode (MSD80 2 174 → 1 849, MEVD17.2 925 → 810
Verwechslungen). Neu gefundene 1D-Objekte mit falscher Breite (MEVD17.2 +44, MSD80 +78) tragen alle ein „?“.
19 neue 1D-Funde liegen innerhalb eines anderen Referenzobjekts (MSD80), 147 außerhalb aller (nicht bewertbar).

### 9.8 Testbericht für Tester (P4)

Überprüfung von `tools/tester_report.py`. Die Schwachstellen und ihre Behebung:

1. **Freitext:** Die Linie war ungeprüfter Freitext und hätte eine Softwarenummer oder einen Dateinamen tragen
   können. Jetzt erlaubt: nur 2–40 einfache Zeichen; abgewiesen werden Ziffernfolgen ab 6 Stellen, Hex-Adressen,
   Fahrgestellnummern, Pfade und die eigenen Dateinamen.
2. **Wiedererkennbarkeit:** Exakte Gesamtzahlen können zusammen mit Linie und Version einen Softwarestand
   kennzeichnen. Jetzt sind Werte ab 100 standardmäßig auf zwei Stellen gerundet; mit `--exakt` und Hinweis entfällt
   die Rundung. Die Vorschau warnt ausdrücklich vor kleinen Stichproben.
3. **Fehlermeldungen:** Sie konnten Pfade enthalten. Jetzt erscheint nur die Fehlerart; die volle Meldung zeigt
   `--details`, nur lokal. Protokollausgaben und Warnungen sind während der Messung abgeschaltet.
4. **Bedienung für Nicht-Programmierer:** Neu ist der geführte Ablauf `--assistent`: drei Fragen, Vorschau,
   Speichern nur nach „ja“, nie Überschreiben.
5. **Prüfung des Exports:** Sie weist jetzt auch unbekannte Felder, Bytes, Listen und gerundet erklärte, aber
   ungerundete Zahlen zurück.

Das Werkzeug enthält keinen Netzwerkcode. Jeder Bericht trägt „Keine unabhängige Validierung.“ Die Anleitungen:
[BETA_TESTER_GUIDE.md](BETA_TESTER_GUIDE.md) (englisch), [BETA_TESTER_ANLEITUNG.md](BETA_TESTER_ANLEITUNG.md)
(deutsch). Tests mit synthetischen und manipulierten Eingaben: leere, abgeschnittene und zufällige Datei, kaputte
CSV, fehlende Datei, private Linie, Überschreiben, gefälschter Export. Das Werkzeug ist nicht in rc1 enthalten;
Tester brauchen einen Testbuild dieses Zweigs.

### 9.9 Gesamtvergleich und Ablation

Entwicklungsdaten (58 Abbilder, 52 508 verifizierbare 2D-Kennfelder); „verloren“ je Abbild gegen PR #30 vor QP4:

| Stand | 2D exakt | Verwechslungen | 1D exakt MEVD17.2 / MSD80 | verloren 2D / 1D |
|---|---:|---:|---:|---:|
| rc1 (veröffentlicht) | 32 058 | 5 316 | 39 798 / 63 175 | – |
| PR #30 vor QP4 | 32 058 | 5 113 | 39 798 / 63 175 | – |
| nur Code-Achsen (§ 9.2) | 35 159 | 5 124 | 43 420 / 64 850 | 0 / 57 |
| nur Vorabsuchen derselben Routine und Breitenregel (§ 9.3, § 9.6) | 32 108 | 5 120 | 39 798 / 63 156 | 0 / 19 |
| nur Kennlinien-Regel (§ 9.7) | 32 058 | 4 469 | 41 160 / 66 366 | 0 / 0 |
| QP4 ohne Kennlinien-Regel | 35 226 | 5 138 | 43 420 / 64 805 | 0 / 102 |
| **neu (Kombination)** | **35 226** | **4 478** | **44 801 / 68 044** | **0 / 35** |
| neu ohne § 9.7, mit 8-Bit-Experiment | 35 226 | 5 138 | 43 802 / 65 395 | 0 / 102 |

**Die 35 verlorenen exakten 1D-Funde** (gewonnen: 9 907):

- **MEVD17.2, 18 Achsen:** Jede war in PR #30 nur die X-Achse einer falsch gelesenen Kennlinie; hinter ihr liegt
  laut Referenz eine weitere Achse (9) oder ein Kennfeld (9), keine Kennlinienwerte. Jetzt belegt dort ein neu
  gefundenes Kennfeld mit Codeaufruf die Stelle, und die falsche Kennlinie fällt samt Achse weg.
- **MSD80, 13 (7 Kennlinien, 6 Achsen):** von einem reinen Datenmuster-Fund überdeckt, der erst innerhalb des
  Datensatzes beginnt (der Kopf liegt davor, § 9.7 greift nicht).
- **MSD80, 4:** neben neuen Kennfeldern mit Codeaufruf, ohne Fund an der Stelle.

**Je Familie (Kriterien: 0 verlorene exakte 2D-Kennfelder, keine neue unmarkierte falsche Lesart, Verwechslungen
nicht höher):**

| Familie / Linie | Datenrolle | 2D exakt | Verwechslungen | Kriterien erfüllt |
|---|---|---:|---:|---|
| MEVD17.2-N55 | Entwicklung | 11 578 → 13 345 | 1 934 → 1 815 | ja |
| MSD80-N53/N54 | Entwicklung | 20 480 → 21 881 | 3 179 → 2 663 | ja |
| MSD80-N43 | Holdout (Regression) | 12 450 → 13 162 | 1 495 → 1 276 | ja |
| MSV90-N52 | Holdout (Regression) | 12 658 → 13 883 | 2 438 → 2 352 | ja |
| MEVD17.2.3 (B38, B38I12, B48) | Holdout (Regression) | 27 180 → 29 085 | 6 349 → 5 895 | ja, außer B38I12-Vollabbilder: Verwechslungen 583 → 585 |
| ME9-N40 | Holdout (Regression) | 413 → 413 | 259 → 221 | ja |
| Regressionsgruppe (15 Abbilder, u. a. MS42, MS43, synthetische) | Regression | nur MSD80-I8A0S verändert: 86 → 93 | – | ja |
| Negativbestand (7 Abbilder, rusEFI, FOME, Speeduino) | Negativkontrolle | 549 Funde, 0 sicher falsch (wie QP3) | – | ja |

Holdout gesamt (nur Regression, keine Validierung): exakt 52 701 → 56 543, 0 verloren, Verwechslungen
10 541 → 9 744. Die Regeln wurden nur an den Entwicklungsdaten entschieden; der Holdout bestätigt nichts, er zeigt
nur, dass nichts kaputtging.

### 9.10 Softwarequalität

| Prüfung | Ergebnis |
|---|---|
| pytest vollständig (Python 3.13, isoliertes Profil: `ECU_STUDIO_TEST_PROFILE=1`, Einstellungen und `LOCALAPPDATA` im Temp-Ordner) | 1 412 bestanden, 22 übersprungen, Exit-Code 0, 0 Qt-Meldungen („QLabel already deleted“) |
| neue Tests (nur synthetisch) | Code-Achsen und Vorabsuchen derselben Routine inkl. Gegenbeispiele (drei Achsen, `ret` dazwischen, zu wenige strenge Aufrufe); Kennlinien-Regel (Kopf am Start, Codebeleg bleibt, Schalter aus); Breitenmarkierung (positiv und negativ); nicht bedatete Achsobjekte; Testbericht mit manipulierten Eingaben |
| GUI-Smoke (isoliertes Profil, offscreen) | 10 Prüfungen bestanden, regulärer Qt-Abbau (Exit-Code 0) |
| i18n | 2 410 Texte, 0 ohne Übersetzung |
| Firmware-Guard (Arbeitsbaum, vor Commit und Push) | OK; keine Firmware, A2L, Hashes oder Kennfeldinhalte im Repository |
| Modellsperre | unverändert (Tests) |
| Registry | Schlüssel „ECU Studio“ identisch mit der Sicherung vom Beginn der Phase; nur gelesen |
| Geschützte Bereiche | Arbeitskopie `ECU-Studio-AI-v1.10` (`6e987c5`, 8 Änderungen), Tags, Releases, rc1 und Update-Kanal unverändert |
| CI (Python 3.11/3.12), CodeQL | siehe Checks von PR #30 |

Laufzeit und Speicher (Vollabbilder, je Version 3 Zeitläufe und 2 Speicherläufe abwechselnd, jeder in eigenem
Prozess, 25.11.2026):

| Abbild | rc1 Median (min–max) | PR #30 vor QP4 | neu | Spitzenspeicher rc1 / PR #30 / neu | exakt rc1 / PR #30 / neu |
|---|---:|---:|---:|---:|---:|
| MSD80-N53/N54 | 14,20 s (12,67–14,87) | 14,28 s (13,25–15,08) | 13,75 s (13,09–14,19) | 87,2 / 87,2 / 87,2 MB | 620 / 620 / 707 |
| MSV90-N52 | 14,32 s (14,22–14,78) | 14,62 s (13,95–15,23) | 14,37 s (13,88–14,73) | 86,3 / 86,3 / 86,3 MB | 526 / 526 / 599 |

Kein messbarer Mehraufwand; die Streuung war an diesem Tag größer als bei § 8 (σ bis 1,1 s). Das MSV90-Abbild
gehört zum Holdout und dient hier nur der Laufzeitmessung.

### 9.11 Grenzen

- Alle Zahlen stammen aus TriCore-Linien eines Datengebers. Andere Familien sind nicht gemessen; § 9.2 und § 9.3
  wirken nur auf TriCore-Code. § 9.7 wirkt auf jede Familie mit 16-Bit-Datensätzen, war aber in der
  Regressionsgruppe außerhalb von MSD80 ohne Wirkung.
- Code-belegte Achsen finden vor allem **nicht bedatete** Kennfelder. Ihr Nutzen für Anwender ist kleiner, als die
  Zahl der exakten Funde vermuten lässt.
- Wertgleiche Kopien nicht bedateter Achsen lassen sich ohne Definition nicht unterscheiden. Sie werden markiert,
  nicht aufgelöst; 34 Achsobjekte sind falsch zusammengelegt.
- MEVD17.2: Kennlinien an Vorabsuche-Routinen und reine Lade-/Speicherzugriffe bleiben offen; gemeinsame Achsen
  werden dort weiter nicht gefunden.
- Neue unabhängige Daten gibt es nicht. Der Testbericht ist der Weg dorthin, aber selbst keine Validierung.
