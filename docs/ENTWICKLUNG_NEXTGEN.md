# Nächste Generation der Kennfelderkennung – Entwicklungsbericht (nach 1.21.0-rc1)

Stand: 22.11.2026 (Qualitätsphase 2: § 7). Zweig `feat/post-rc1-recognition-nextgen` (Basis: `v1.21.0-rc1`, Commit `c27796c`), Draft-PR.
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
