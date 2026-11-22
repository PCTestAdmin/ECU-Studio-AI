# Nächste Generation der Kennfelderkennung – Entwicklungsbericht (nach 1.21.0-rc1)

Stand: 21.11.2026. Zweig `feat/post-rc1-recognition-nextgen` (Basis: `v1.21.0-rc1`, Commit `c27796c`), Draft-PR.
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

Nur „Bestätigt“ und „Stark gestützt“ dienen als Anker; eine Vermutung stützt nie eine andere. Jede Hypothese führt
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

## 6. Unabhängige Daten

Suche am 21.11.2026 (öffentliche Quellen, nur allgemeine Suchbegriffe): keine rechtmäßig nutzbaren A2L-/HEX-Paare
realer Steuergeräte gefunden, nur quelloffene Werkzeuge (z. B. calibrationReader, AsamCalTool, a2llib) ohne
Referenzdaten realer Steuergeräte. Nichts heruntergeladen. Eine neue Testgruppe gibt es damit weiterhin nicht.
