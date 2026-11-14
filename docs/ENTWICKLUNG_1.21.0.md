# Entwicklungsbericht 1.21.0 – Kennfelderkennung mit A2L-/HEX-Referenzdaten

Stand: 14.11.2026, **in Entwicklung, nicht veröffentlicht**. Ausgangspunkt `v1.20.1` (8cca756), Branch
`feat/1.21.0-map-detection`. Die Referenzdaten (HEX-Abbilder und A2L-Dateien) sind private Daten eines Datengebers.
Sie bleiben lokal. Firmwarebytes und A2L-Inhalte wurden an keinen externen Dienst übertragen; in der
Sitzung des KI-Entwicklungsassistenten erschienen nur Dateinamen, Zählwerte, Lage und Größe einzelner
Kandidaten (Strukturmetadaten) und einmal drei gekürzte Abbild-Hashes aus einem Prüfprotokoll (das Werkzeug gibt
sie seitdem nicht mehr aus). Dieser Bericht enthält nur zusammengefasste
Zählwerte: keine Kennfeldnamen, keine Adressen, keine Softwarestände, keine Hashes. Der Detailbericht mit
Hashes, Adressen und Beispielen bleibt lokal (`.qa`).

## 1. Kurzfassung

- **Daten:** 74 Referenzsätze, 163 Abbilder, 80 A2L aus acht Steuergerätelinien (Bosch ME9, MEVD17.2, MEVD17.2.3;
  Siemens MSD80, MSV90). Getrennt **vor** der Entwicklung: 58 Abbilder Entwicklung (2 Linien), 105 Holdout (6 Linien).
- **Holdout, erste Messung (Runde 1, unabhängig):** exakt gefundene verifizierbare 2D-Kennfelder
  **35 382 → 49 958** von 91 370 (Recall 0,387 → 0,547). Datentyp richtig unter den exakten Funden 80,5 % → 93,3 %,
  Achsen 99,8 % → 99,8 %. 113 vorher exakte Kennfelder gehen verloren, 14 689 kommen hinzu.
- **Runde 2 (§ 6a), nur an Entwicklungsdaten entwickelt:** Entwicklung 30 735 → 31 142 exakt, teilweise
  2 774 → 2 449. Zweite Holdout-Messung (nicht mehr unabhängig): 49 958 → 51 016 exakt, teilweise 4 837 → 4 074,
  Verwechslungen 15 518 → 15 459, Vorzeichenfehler 2 017 → 2 281. Eine neue unabhängige Testgruppe gibt es nicht.
- **Am stärksten:** TriCore-Vollflashs, deren Kalibrierung anders gelinkt ist oder über Zeigertripel angesprochen
  wird. MSV90 0,219 → 0,793, MSD80 N43 0,650 → 0,893 (Holdout).
- **Wiedererkennung über Versionen:** falsche Namensübertragungen auf dem Holdout 1 832 → 210 bei 0,7 % weniger
  richtigen.
- **Keine Regression** im Regressionssatz (15 Fälle). Alle Tests grün. Laufzeit insgesamt −2 % gegenüber 1.20.1
  (Runde 2), Spitzenspeicher gleich.
- **Offen:** mehr Verwechslungen auf MEVD17.2.3-Vollflashs; Byte-Reihenfolge der MSV90-Kalibrierabbilder (§ 9).
  Kein Modelltraining.

## 2. Referenzdaten (zusammengefasst)

| Linie | Rolle | Sätze | Abbilder (Kalibrierung / Vollflash) | A2L |
|---|---|---:|---|---:|
| ME9 (N40) | Test | 3 | 3 / 0 | 3 |
| MEVD17.2 (N55) | Entwicklung | 3 | 9 / 9 | 9 |
| MEVD17.2.3 (B38) | Test | 11 | 11 / 11 | 11 |
| MEVD17.2.3 (B38 I12) | Test | 4 | 4 / 4 | 4 |
| MEVD17.2.3 (B48) | Test | 8 | 8 / 8 | 8 |
| MSD80 (N43) | Test | 10 | 11 / 10 | 10 |
| MSD80 (N53/N54) | Entwicklung | 19 | 21 / 19 | 19 |
| MSV90 (N52) | Test | 16 | 19 / 16 | 16 |
| **Summe** | | **74** | **86 / 77 = 163** | **80** |

- **Zuordnung:** Jedes Abbild wurde aus seiner HEX-Datei erzeugt (Segmente, Lücken und Startadresse dokumentiert)
  und über EPK bzw. Kalibrierkennung seiner A2L zugeordnet. A2L-Adressen wurden über die Speichersegmente der A2L und
  die Lage des Abbilds in Dateioffsets übersetzt, nicht direkt als Offset gelesen. Bei ME9 deklariert die A2L keine
  EPK; dort ist die Lage über den Datenvergleich bestimmt.
- **Byte-Reihenfolge:** alle A2L `MSB_LAST` (Little Endian), außer ME9 (`MSB_FIRST`, PowerPC) und einer MSD80-A2L,
  die `MSB_FIRST` deklariert, obwohl das Steuergerät TriCore ist. Bewertet wurde jeweils mit der Angabe je Objekt.
- **Objekte:** zusammen gut 1,3 Mio. VALUE, 150 000 CURVE, 118 000 MAP und 147 000 VAL_BLK. Achsen: STD_AXIS,
  COM_AXIS (gemeinsame Achsen; bei MSD80/MSV90 die Mehrheit) und wenige FIX_AXIS (nur Bosch und ME9).
  Umrechnungen fast nur RAT_FUNC und TAB_VERB.
- **Bewertet** werden nur 2D-Kennfelder (MAP), deren gespeicherte Achsen im Abbild steigen („verifizierbar“).
  Kennlinien, Festwerte und Blöcke sind getrennt gezählt und nicht Teil der Trefferquote.
- **Auffälligkeiten:** ein Abbild war byte-gleich mit einem anderen und wurde übersprungen. Ein MSD80-Vollflash
  (Entwicklung) beginnt bei Adresse 0 und besteht aus neun Segmenten mit Lücken von zusammen 6,9 MB; die Erkennung
  findet dort keine Aufrufstellen.
  Die MEVD17.2.3-Vollflashs haben zwischen Programm- und Datenbereich eine Lücke von 6 MB; die Abbilder bilden sie
  mit Füllbytes nach. Keine Datei war unlesbar oder beschädigt.

## 3. Verfahren

- **Blind:** Die Erkennung bekommt nur die Bytes, keine A2L und keinen Dateinamen. Die A2L dient nur der Bewertung.
- **Trennung vor der Arbeit:** Entwicklung (58 Abbilder: MEVD17.2 N55, MSD80 N53/N54) und Holdout (105 Abbilder:
  alle anderen Linien) wurden nach Steuergerätelinien getrennt, bevor eine Zeile Code geändert wurde. Testlinien
  gingen nur in die Bestandsaufnahme (§ 2) und die Ausgangsmessung mit unverändertem 1.20.1 (§ 4) ein. Keine Regel
  wurde an ihnen entwickelt oder abgestimmt. Die Erkennung lief einmal auf dem Holdout, nach dem Einfrieren des
  Codes. Die Identifikation lief dort, nachdem ihr Code fertig war; danach wurde er nicht mehr geändert.
- **Klassen je Fund:** exakt (Start, Form und Zellbreite wie in der A2L), teilweise (überwiegend dasselbe Kennfeld,
  Start/Form/Breite abweichend), Verwechslung (überwiegend andere Objekte: Kennlinien, Festwerte, Blöcke),
  unklar (im beschriebenen Bereich, aber keinem Objekt zuordenbar), nicht bewertbar (außerhalb dessen, was die A2L
  beschreibt). Funde ohne A2L-Objekt gelten **nicht** automatisch als Fehlfund: die A2L beschreibt nicht jede
  Tabelle. Deshalb wird keine Präzision ausgewiesen.
- **Typ richtig:** Breite, Byte-Reihenfolge und Vorzeichen; das Vorzeichen zählt nur, wo die Bytes es entscheiden.
  **Achsen richtig:** Rohwerte der Achsen sind ein lineares Abbild der A2L-Achse.

## 4. Ausgangslage 1.20.1

Unverändertes 1.20.1, blind auf allen 163 Abbildern: 143 878 verifizierbare 2D-Kennfelder, davon 55 899 exakt
gefunden (Recall 0,389). Unter den exakten Funden war der Datentyp in 79,2 % richtig. Die Fehler waren falsche
Byte-Reihenfolge (7 099, Ursache: jeder Datensatz wählte seine Reihenfolge nach der glatteren Oberfläche) und
falsches Vorzeichen (4 529, Ursache: vorzeichenlos als Vorgabe). Achswerte waren bei 99,8 % der exakten Funde mit
Achsen richtig. Mit 1.20.1 nicht gefunden wurden vor allem:

- Kennfelder, die der TriCore-Code über eine verlagerte Kalibrierung, über Zeigertripel oder über getrennte
  Achssuchen anspricht (Vollflashs MSD80 N53/N54 und MSV90: Recall 0,34 bzw. 0,22),
- Datensätze mit gemischten Achsbreiten oder Byte-Werten mit Vorzeichen (Bosch),
- Kennfelder mit gemeinsamen Achsen, die ohne eigenen Kopf abgelegt sind (alle Linien; im reinen Kalibrierabbild
  ohne Code nicht auffindbar).

Wiedererkennung über Versionen (Namensübertragung zwischen aufeinanderfolgenden Softwareständen, ohne A2L des
Zielstands): auf den Entwicklungslinien 86,1 % der gemeinsamen Kennfelder richtig übertragen, 2 830 falsch.
Identifikation: MEVD17.2 (Entwicklung) 7 von 9 Ständen „mehrdeutig“, 2 als Plattform MED17; Siemens-Stände ohne
Software-Merkmal.

## 5. Änderungen

Alle Änderungen sind allgemeine Regeln; keine gilt für einzelne Dateien, Softwarestände oder diese Referenzdaten.
Jede Regel hat einen Schalter und einen synthetischen Test.

| Bereich | Regel | Schalter |
|---|---|---|
| A2L | Zeichenketten mit verdoppelten Anführungszeichen beenden das Objekt nicht mehr; VAL_BLK mit `NUMBER` bekommt seine Größe. Lexikon einmal normalisiert. | – |
| TriCore-Lage | Code, der die Kalibrierung außerhalb des Abbilds adressiert: die dichteste 64-KiB-Seite der Aufrufziele wird an jeder Seitenposition des Abbilds geprüft. Achsköpfe und Datensätze werden getrennt gezählt; eine Lage gilt nur, wenn ein Beleg eindeutig ist (≥ 20 Treffer, ≥ 3× der nächstbeste) und der andere dieselbe Lage bevorzugt. | `RELOCATE` |
| TriCore-Aufrufe | Unbelegte Achsen (Anzahlkopf, alle Stützstellen gleich) zählen bei der Rollenerkennung der Achssuch-Routinen mit, wenn die Routine auch echte Achsen liest (≥ 25 % der Aufrufe). | `BLANK_AXES` |
| TriCore-Zeigertripel | Arrays aus 12-Byte-Einträgen (Daten, X-Achse, Y-Achse) benennen Tabellen. Beide Achsen müssen lesbar sein, die Daten dürfen selbst keine Achse sein, ein Nachbareintrag muss 12 Byte entfernt liegen, mindestens 20 Einträge. | `POINTER_TRIPLES` |
| Zeilenabstand | Glatte Zeilenabstands-Läufe, in deren Innerem der Code ein Objekt einzeln adressiert, werden verworfen. | – |
| Datensätze | Achsbreiten 8/16 Bit gemischt; Werte auch s8; Wertebreite aus dem kleinsten Abstand zum nächsten Datensatzkopf (bis 3 Füllbytes); eine Byte-Reihenfolge je Abbild aus den Datensätzen mit 16-Bit-Zählern/Achsen; Lesarten, deren Kopf in Zählern/Achsen eines anderen Datensatzes beginnt, entfallen; Höchstzahl 1000 → 2000. | `BYTE_ORDER`, `NEXT_HEADER_WIDTH`, `NESTED_HEADERS` |
| Vorzeichen | Wo der Code es nicht festlegt: Lesart ohne Überlauf zwischen Nachbarzellen (Sprungsumme vorzeichenbehaftet ×4 kleiner); Gleichstand → vorzeichenlos. | `SIGN_BY_WRAPS` |
| Identifikation | EPK-Projekt verfeinert eine Plattformfamilie, wenn es genau eine Klartextfamilie nennt; Siemens-Datensatzname als Software-Merkmal. | – |
| Namensübertragung | Flache Blöcke nur bei übereinstimmenden Nachbarankern oder gleichen angrenzenden Bytes. | `FLAT_NEEDS_PLACE` |

Alle neuen Funde bleiben **ungeprüft** und tragen ihre Herkunft („TriCore-Zeigertripel + Achsen (ungeprüft)“ usw.).
Unsichere Fälle werden nicht als erkannt ausgegeben: mehrdeutige Lage → keine Verlagerung, widersprüchliche Achsen →
kein Fund, Vorzeichen-Gleichstand → vorzeichenlos mit Hinweis.

## 6. Ergebnisse

Exakt = verifizierbare 2D-Kennfelder mit richtigem Start, Form und Zellbreite. Typ und Achsen jeweils unter den
exakten Funden. Werte „1.20.1 → 1.21.0“.

### 6.1 Holdout (105 Abbilder, einmal nach dem Einfrieren gemessen)

| Linie | Abbild | n | verifizierbar | exakt | Recall | Typ richtig | Achsen richtig | teilweise | Verwechslung | unklar |
|---|---|---:|---:|---|---|---|---|---|---|---|
| ME9 N40 | Kalibrierung | 3 | 1 024 | 299 → 365 | 0,292 → 0,356 | 0,876 → 0,926 | 247/247 → 321/321 | 302 → 252 | 429 → 434 | 11 → 11 |
| MEVD17.2.3 B38 | Kalibrierung | 11 | 11 780 | 4 126 → 5 416 | 0,350 → 0,460 | 0,763 → 0,941 | 4 080/4 080 → 5 372/5 381 | 1 050 → 602 | 2 142 → 2 106 | 419 → 399 |
| MEVD17.2.3 B38 | Vollflash | 11 | 11 780 | 6 365 → 7 636 | 0,540 → 0,648 | 0,914 → 0,946 | 6 319/6 319 → 7 569/7 578 | 323 → 319 | 1 467 → 1 773 | 398 → 162 |
| MEVD17.2.3 B38 I12 | Kalibrierung | 4 | 3 099 | 1 001 → 1 355 | 0,323 → 0,437 | 0,774 → 0,920 | 984/984 → 1 342/1 342 | 314 → 187 | 766 → 768 | 270 → 265 |
| MEVD17.2.3 B38 I12 | Vollflash | 4 | 3 099 | 1 562 → 1 950 | 0,504 → 0,629 | 0,908 → 0,951 | 1 547/1 547 → 1 929/1 929 | 96 → 108 | 487 → 647 | 225 → 104 |
| MEVD17.2.3 B48 | Kalibrierung | 8 | 8 632 | 2 992 → 3 938 | 0,347 → 0,456 | 0,761 → 0,943 | 2 953/2 953 → 3 899/3 907 | 750 → 429 | 1 571 → 1 539 | 309 → 298 |
| MEVD17.2.3 B48 | Vollflash | 8 | 8 632 | 4 580 → 5 509 | 0,531 → 0,638 | 0,914 → 0,947 | 4 541/4 541 → 5 457/5 465 | 233 → 236 | 1 088 → 1 299 | 299 → 127 |
| MSD80 N43 | Kalibrierung | 11 | 10 253 | 3 313 → 3 870 | 0,323 → 0,377 | 0,688 → 0,899 | 3 185/3 199 → 3 744/3 756 | 835 → 720 | 1 845 → 1 811 | 75 → 75 |
| MSD80 N43 | Vollflash | 10 | 9 009 | 5 853 → 8 049 | 0,650 → 0,893 | 0,917 → 0,997 | 5 772/5 794 → 7 991/8 013 | 402 → 245 | 1 462 → 836 | 89 → 125 |
| MSV90 N52 | Kalibrierung | 19 | 13 340 | 2 946 → 3 368 | 0,221 → 0,252 | 0,586 → 0,645 | 2 580/2 590 → 3 008/3 016 | 1 758 → 1 546 | 3 262 → 3 308 | 42 → 42 |
| MSV90 N52 | Vollflash | 16 | 10 722 | 2 345 → 8 502 | 0,219 → 0,793 | 0,516 → 0,968 | 2 084/2 094 → 8 465/8 465 | 1 118 → 193 | 2 301 → 997 | 36 → 63 |
| **Summe** | | **105** | **91 370** | **35 382 → 49 958** | **0,387 → 0,547** | **0,805 → 0,933** | 34 292/34 348 → 49 097/49 173 | 7 181 → 4 837 | 16 820 → 15 518 | 2 173 → 1 671 |

- Verlorene exakte Kennfelder: **113** (gewonnen 14 689), in 49 von 105 Abbildern, höchstens 4 je Abbild. Ursachen:
  67 MSV90-Kennfelder (64 aus Datensatzköpfen) werden nicht mehr ausgegeben, 23 MEVD17.2.3-Datensätze beginnen
  jetzt ein Byte zu früh (teilweise statt exakt), Rest Einzelfälle. Die Ursachen wurden am Holdout nicht im Einzelnen
  untersucht, um ihn nicht zur Abstimmung zu benutzen.
- Vorzeichenfehler 2 639 → 2 017, Byte-Reihenfolge 4 270 → 1 336 (davon 1 046 in MSV90-Kalibrierabbildern, § 9).
- **Verwechslungen nehmen auf den MEVD17.2.3-Vollflashs zu** (zusammen 3 042 → 3 719): zusätzliche
  Datensatz-Lesarten, die ein Kennfeld überdecken, ohne es genau zu treffen. Insgesamt sinken Verwechslungen
  (16 820 → 15 518) und unklare Funde (2 173 → 1 671).
- „Nicht bewertbar“ (außerhalb der A2L) steigt 3 052 → 6 231, vor allem auf Vollflashs (Programmbereich).
  Ob das echte, nicht dokumentierte Tabellen oder Fehlfunde sind, lässt sich mit diesen Daten nicht sagen.

### 6.2 Entwicklung (58 Abbilder)

| Linie | Abbild | n | verifizierbar | exakt | Recall | Typ richtig | Verwechslung |
|---|---|---:|---:|---|---|---|---|
| MEVD17.2 N55 | Kalibrierung | 9 | 9 894 | 3 444 → 4 311 | 0,348 → 0,436 | 0,788 → 0,935 | 1 528 → 1 509 |
| MEVD17.2 N55 | Vollflash | 9 | 9 894 | 6 211 → 6 682 | 0,628 → 0,675 | 0,906 → 0,967 | 1 390 → 1 319 |
| MSD80 N53/N54 | Kalibrierung | 21 | 17 107 | 5 541 → 6 361 | 0,324 → 0,372 | 0,689 → 0,906 | 3 493 → 3 391 |
| MSD80 N53/N54 | Vollflash | 19 | 15 613 | 5 321 → 13 381 | 0,341 → 0,857 | 0,684 → 0,996 | 2 609 → 1 693 |
| **Summe** | | **58** | **52 508** | **20 517 → 30 735** | **0,391 → 0,585** | **0,770 → 0,963** | 9 020 → 7 912 |

Verloren 17, gewonnen 10 235. Vorzeichenfehler 1 890 → 1 128, Byte-Reihenfolge 2 829 → 21.

### 6.3 Wiedererkennung über Versionen

Namensübertragung zwischen aufeinanderfolgenden Softwareständen einer Linie (Quelle mit A2L, Ziel nur Bytes),
bewertet an der A2L des Ziels:

| Daten | Paare | gemeinsame Kennfelder | richtig übertragen | falsch übertragen |
|---|---:|---:|---|---|
| Entwicklung | 54 | 60 838 | 52 358 (86,1 %) → 51 763 (85,1 %) | 2 830 → 691 |
| Holdout | 94 | 97 943 | 89 473 (91,4 %) → 88 799 (90,7 %) | 1 832 → 210 |

Falsche Übertragungen sinken auf dem Holdout um 89 %; dafür werden 0,7 % der richtigen nicht mehr vorgeschlagen.
Übertragene Namen bleiben Vorschläge („transfer-proposed“, ungeprüft).

### 6.4 Identifikation (ohne A2L)

| Daten | 1.20.1 | 1.21.0 |
|---|---|---|
| MEVD17.2 (Entwicklung, 9 Stände, je Kalibrier- und Vollabbild) | 2 eindeutig (MED17), 7 mehrdeutig | 2 eindeutig (MED17), 7 eindeutig (MEVD17.2) |
| MEVD17.2.3 (Holdout, 46 Abbilder) | 46 eindeutig | 46 eindeutig |
| Siemens MSD80/MSV90 mit Software-Merkmal (Entwicklung 40, Holdout 56) | 0 / 0 | 36 / 56 |
| ME9 (Holdout, 3) | unbekannt | unbekannt |

Die Familie der Siemens-Stände bleibt „unbekannt“: Die Abbilder nennen sie nicht im Klartext, und ein
Datensatzname allein belegt keine Familie.

### 6.5 Regression, Negativfälle, Laufzeit und Speicher

- **Regressionssatz** (4 synthetische Strukturfälle, 8 synthetische Negativdateien, MS42, MS43, MSD80-Vollflash mit
  Community-XDF): exakte Kennfelder in allen 15 Fällen unverändert (MSD80 86 von 99, MS43 197, MS42 22).
  Negativdatei „Rampen“: 10 → 1 Fund. MS43: ein Kandidat mehr (Präzision 75 → 74 %). Die realen Paare früherer
  Berichte (15) und der Negativbestand offener Firmware (7) lagen lokal nicht mehr vor und konnten nicht wiederholt
  werden.
- **Tests:** 1144 bestanden, 21 übersprungen (fehlende lokale Daten, Rechte für Symlinks, nur CI), 0 fehlgeschlagen.
  Darin Firmware-Guard, Modellsperre und GUI-Tests. Die Benutzereinstellungen in der Registry waren vor und nach
  den Tests identisch. Firmware-Guard über den ganzen Baum: ohne Befund.
- **Laufzeit/Speicher** (je ein Abbild pro Linie und Abbildtyp, 15 Abbilder, nacheinander ohne Last): 151 → 161 s
  (+6 %). Am stärksten MSD80-N43-Vollflash 7,2 → 11,8 s und MSV90-Vollflash 12,3 → 15,3 s (dort findet die
  TriCore-Auswertung jetzt viele Tabellen mehr); Kalibrierabbilder unverändert oder schneller. Spitzenspeicher unverändert (höchstens 431 MB beim
  10-MB-Vollflash). Regressionssatz 29,8 → 31,0 s; die synthetische Rampen-Datei 8,0 → 10,6 s und 96 → 101 MB.

## 6a. Zweite Runde: Fehlzuordnungen, Datentypen, Laufzeit

Nach der ersten Holdout-Messung (§ 6.1) wurde weiterentwickelt, **nur an den Entwicklungsdaten** (58 Abbilder).
Der Holdout wurde nicht zur Abstimmung benutzt. Er wurde danach ein zweites Mal gemessen. Diese zweite Messung ist
**keine unabhängige Prüfung** mehr: Die Testlinien sind seit der ersten Messung bekannt. Sie zeigt nur, ob die
Änderungen dort schaden. Eine neue, unbenutzte Testgruppe gibt es nicht (§ 6a.7).

### 6a.1 Bestätigte Ursachen (Entwicklungsdaten)

- **Byte-Tabellen als 16-Bit gelesen:** Datensätze mit 16-Bit-Achsen und 8-Bit-Werten wurden als 16-Bit-Tabelle
  gelesen. Die 8-Bit-Lesart wird als zu flach verworfen; die 16-Bit-Lesart reicht dann doppelt so weit, bis in den
  nächsten Datensatz. Ergebnis: „teilweise“ (richtiger Start, falsche Breite) oder Verwechslung.
- **16-Bit-Lesarten auf ungeraden Adressen:** In keinem Abbild der acht Linien beginnt ein 16-Bit-A2L-Objekt auf
  einer ungeraden Adresse. Solche Lesarten sind Zufallstreffer aus Zählern und Achsen anderer Datensätze.
- **Mehrdeutige Stimmen zur Byte-Reihenfolge:** Datensätze mit 8-Bit-Zählern und 16-Bit-Achsen unter 256 steigen in
  beiden Reihenfolgen. Sie stellten 51–70 % der Gegenstimmen, änderten auf den Entwicklungsdaten aber die gewählte
  Reihenfolge nie (§ 6a.2).

### 6a.2 Neue Regeln und ihre Wirkung (Ablation, 27 Kalibrierabbilder der Entwicklung)

| Regel | Schalter | exakt | teilweise | Verwechslung | Vorzeichenfehler | Stand |
|---|---|---:|---:|---:|---:|---|
| Wertebreite aus der Datensatzgrenze: 16-Bit-Lesart ohne nachfolgenden Datensatz, 8-Bit-Lesart gleicher Form mit nachfolgendem Datensatz (Anzahl 3–32 + streng steigende Achse, bis 3 Füllbytes) → Byte-Tabelle | `WIDTH_BY_BOUNDARY` | +366 | −290 | +75 | +27 | an |
| 16-Bit-Felder nur auf der Adressparität des Abbilds (≥ 20 Datensätze mit 16-Bit-Zählern/Achsen, ≥ 4 : 1) | `ALIGNED_16` | ±0 | ±0 | −62 | ±0 | an |
| Nur entscheidende Stimmen zur Byte-Reihenfolge | `DECISIVE_VOTES` | ±0 | ±0 | ±0 | ±0 | **aus** |

`DECISIVE_VOTES` ist technisch begründet, hat auf den Entwicklungsdaten aber keine messbare Wirkung. Ihre einzige
erwartbare Wirkung beträfe die MSV90-Byte-Reihenfolge, die nur aus dem Holdout bekannt ist. Eingeschaltet wäre sie
eine am Holdout ausgerichtete Regel; sie bleibt deshalb aus, bis neue Entwicklungsdaten sie prüfen.

Die Breitenregel irrt in 18 Fällen (16-Bit-Tabellen 16×16, 12×12, 10×10, deren Bytes zufällig wie ein Datensatz
weitergehen). In 31 weiteren Fällen geht ein Kennfeld ganz verloren: Die falsch verkürzte Lesart hat eine schwächere
Oberfläche, eine früher beginnende Zeilenabstands-Lesart gewinnt die Überlappung und verdrängt auch benachbarte
Datensätze. Alle Lesarten dieser Regel sind als „Wertebreite nur aus dem Datensatzaufbau abgeleitet“ gekennzeichnet.

### 6a.3 Ergebnisse

| Daten | exakt 1.20.1 → 1.21 (Runde 1) → 1.21 (Runde 2) | teilweise | Verwechslung | Vorzeichenfehler | Byte-Reihenfolge falsch |
|---|---|---|---|---|---|
| Entwicklung (58) | 20 517 → 30 735 → **31 142** | 3 812 → 2 774 → 2 449 | 9 020 → 7 912 → 7 908 | 1 890 → 1 128 → 1 158 | 2 829 → 21 → 21 |
| Holdout (105), zweite Messung | 35 382 → 49 958 → **51 016** | 7 181 → 4 837 → 4 074 | 16 820 → 15 518 → 15 459 | 2 639 → 2 017 → 2 281 | 4 270 → 1 336 → 1 336 |

- Entwicklung Runde 1 → 2: 65 exakte Kennfelder verloren, 472 gewonnen. Holdout: 113 verloren, 1 171 gewonnen.
- Holdout je Linie (Runde 1 → 2, exakt): Kalibrierabbilder ME9 365 → 378, MEVD17.2.3 B38 5 416 → 5 734,
  B38 I12 1 355 → 1 447, B48 3 938 → 4 169, MSD80 N43 3 870 → 4 007, MSV90 3 368 → 3 531. Vollflashs nahezu gleich
  (MEVD17.2.3 +108, MSD80 N43 ±0, MSV90 −4): Dort lagen die Tabellen schon über den Code fest.
- **Datentyp richtig** unter den exakten Funden sinkt leicht (Holdout 93,3 % → 92,9 %): Die neuen Byte-Tabellen
  haben öfter ein Vorzeichen, das die Bytes zwar entscheiden, die Erkennung aber nicht kennt. Sie sind als
  ungeprüft markiert (§ 6a.5).
- **Nicht gelöst:** Verwechslungen auf MEVD17.2.3-Vollflashs (1.20.1 3 042 → Runde 1 3 719 → Runde 2 3 744) und die
  Byte-Reihenfolge der MSV90-Kalibrierabbilder (unverändert 1 046). Beide sind nur aus dem Holdout bekannt; eine
  Abhilfe ohne neue Entwicklungsdaten wäre eine Anpassung an die Testdaten.

### 6a.4 Nicht bewertbare Kandidaten

Kandidaten der Vollflashs außerhalb aller A2L-Objekte, automatisch eingeordnet (erste zutreffende Klasse):
nachweislich falsch (≥ 90 % Füllbytes, ≥ 80 % Text, vom eigenen Datenmaskenmodell als Code erkannt), plausibel
(der TriCore-Code bildet die Startadresse mit `movh.a` + `lea`; oder die ersten 64 Byte stehen im A2L-Datenbereich,
vermutlich eine inaktive Kopie), sonst nicht bewertbar. „Plausibel“ ist **nicht verifiziert**; bestätigt ist keiner.

| Daten | gesamt | nachweislich falsch | plausibel, nicht verifiziert | nicht bewertbar |
|---|---:|---:|---:|---:|
| Entwicklung (Stand Runde 1) | 3 248 | 66 (Füllbytes 44, Text 22) | 57 (Code-Bezug 36, Kopie 21) | 3 125 |
| Holdout (Diagnose, Runde 2) | 6 235 | 176 (Füllbytes 104, Text 48, Code 24) | 150 (Code-Bezug 122, Kopie 28) | 5 909 |

Stichprobe (fester Seed, je Linie 40): Entwicklung 78 von 80 nicht bewertbar, Holdout 182 von 200.

**Unabhängige Gegenprobe an einem Entwicklungsstand mit ELF-Symboltabelle** (Linkersymbole mit Adresse und Größe,
nicht aus der A2L): Von 1 087 Kandidaten des Vollflashs (Stand Runde 1) liegen 258 exakte Funde genau auf einem ELF-Objekt und 568
innerhalb eines größeren Objekts (Struktur). **Keiner der 136 nicht bewertbaren Kandidaten liegt in einem
ELF-Objekt.** Das spricht dort gegen echte, nur undokumentierte Tabellen, ist aber kein Beweis (nicht jeder Bereich
trägt Symbole) und gilt für einen einzelnen Stand.

Fazit: Der größte Teil lässt sich mit den vorhandenen Daten weder bestätigen noch widerlegen. Er bleibt als
„Datenmuster-Vermutung“ ungeprüft und wird nicht als sicher erkannt ausgegeben.

### 6a.5 Anzeige

- Datentyp mit „?“ und Grund (Tooltip, Detailansicht), wenn er nicht belegt ist: Vorzeichen offen (mit Alternative),
  nur aus der Glätte geschätzt (Datenmuster-Funde) oder Wertebreite nur aus dem Datensatzaufbau abgeleitet.
- Übertragene Namen: „Name übertragen (ungeprüft)“.
- Belegstärke (Code-Beleg / Strukturbeleg / Datenmuster-Vermutung) und Herkunft wurden schon angezeigt.
  Überlappende Kandidaten werden weiterhin vor der Ausgabe aufgelöst; es erscheint immer nur eine Lesart je Bereich.

### 6a.6 Laufzeit und Speicher

Zuerst ein reproduzierbares Profil (seriell, je Linie ein Kalibrier- und ein Vollabbild): Den größten Einzelanteil
auf TriCore-Vollflashs hat der Code-Durchlauf (`_walk`, 30–40 % der seriellen Zeit), danach die Datensatzsuche.
Geändert, jeweils mit Gleichheitsprüfung aller Durchlauf-Ergebnisse auf 77 TriCore-Abbildern (0 Unterschiede):

- Der Durchlauf besucht nur Befehle, die seinen Zustand ändern (≈ 40 % der Befehle). Sprungziele werden in
  Adressreihenfolge zusammengeführt. Der Befehlsstrom wird einmal je Abbild dekodiert, in kompakten Feldern
  (4 Byte je Befehl).
- Stack-Speicherbefehle werden zwischen den Durchläufen wiederverwendet; die Lagesuche verlagerter Kalibrierung prüft
  nur Bytes, die eine Anzahl sein können.

Leistungssatz, 15 Abbilder, nacheinander ohne Last, 1.20.1 → 1.21 Runde 1 → Runde 2:

| Linie | Abbild | Laufzeit (s) | Spitzenspeicher (MB) | exakt |
|---|---|---|---|---|
| ME9 | Kalibrierung | 4,8 → 5,0 → 5,1 | 19 → 19 → 19 | 101 → 123 → 127 |
| MEVD17.2 | Kalibrierung / Vollflash | 8,0 / 12,1 → 7,7 / 11,9 → 7,7 / 10,7 | 38 / 173 → gleich → gleich | 940 → 1 053 → 1 077 |
| MEVD17.2.3 (3 Linien) | Kalibrierung | 17,3 → 15,6 → 15,9 | 22 → 22 → 22 | 1 001 → 1 319 → 1 398 |
| MEVD17.2.3 (3 Linien) | Vollflash (10 MB) | 61,9 → 57,6 → 55,9 | 431 → 431 → 431 | 1 553 → 1 869 → 1 880 |
| MSD80 (2 Linien) | Kalibrierung | 16,4 → 15,7 → 15,8 | 45 → 45 → 45 | 528 → 601 → 621 |
| MSD80 (2 Linien) | Vollflash | 19,5 → 26,8 → 23,5 | 88 → 87 → 86 | 630 → 1 462 → 1 462 |
| MSV90 | Kalibrierung / Vollflash | 7,3 / 12,2 → 7,1 / 15,8 → 7,2 / 14,1 | 36 / 86 → gleich → gleich | 296 → 697 → 702 |
| **Summe** | | **159,5 → 163,1 → 155,9** | **431 → 431 → 431** | **5 049 → 7 124 → 7 267** |

Gegenüber 1.20.1 insgesamt 2 % schneller bei 44 % mehr exakten Funden. Langsamer bleiben die Siemens-Vollflashs
(MSD80 +21 %, MSV90 +16 %), wo die TriCore-Auswertung jetzt ein Vielfaches an Tabellen findet. Eine erste Fassung
des Befehlsstroms in Python-Listen brauchte auf 10-MB-Vollflashs 200 MB mehr Speicher; mit kompakten Feldern ist der
Spitzenspeicher wieder wie in 1.20.1. Regressionssatz: alle 15 Fälle unverändert, keine neuen Funde in den
synthetischen Negativdateien.

**Prüfungen Runde 2:** pytest 1 154 bestanden, 22 übersprungen, 0 fehlgeschlagen (inkl. GUI, Firmware-Guard,
Modellsperre; Registry-Einstellungen vorher/nachher identisch). GUI-Smoke 10/10, Übersetzungsprüfung 2 256 Texte
ohne Lücke, Firmware-Guard über den ganzen Baum ohne Befund.

### 6a.7 Referenzdaten, die fehlen

- **Neue unabhängige Testgruppe:** Keine. Alle lokal vorhandenen Referenzsätze mit A2L sind bereits Entwicklung
  oder Holdout. Die Ergebnisse dieser Runde sind deshalb nicht unabhängig bestätigt.
- **Reale Paare früherer Berichte (15) und Negativbestand offener Firmware (7):** In den zulässigen lokalen
  Verzeichnissen nicht vorhanden. Wiederholbar sind nur der Regressionssatz (synthetische Fälle, synthetische
  Negativdateien, MS42, MS43, MSD80 mit Community-XDF).
- Für die offenen Punkte (MSV90-Byte-Reihenfolge, MEVD17.2.3-Vollflashs) fehlen Entwicklungsdaten derselben Linien.

## 7. Ghidra und REA (nur extern)

Ghidra 12.1.4 und REA wurden ausschließlich als externe Werkzeuge an Entwicklungsabbildern benutzt. Nichts davon
ist in ECU Studio AI eingebaut, wird mitgeliefert oder zur Laufzeit gebraucht.

- **Prozessor und Format:** Ghidra unterstützt TriCore (TC1796) und lädt die Abbilder mit der Flash-Basis
  0x80000000/0xA0000000. REA konnte die TriCore-ELF eines Entwicklungsstands nicht öffnen (keine TriCore-Unterstützung).
- **Interpolationsroutinen:** MSD80 übergibt die Tabelle in a4 und die Achsköpfe in a5/a6. Teils werden die Achsen
  vorher einzeln gesucht (Prelookup), teils stehen Daten und Achsen als Zeigertripel im Speicher. Bosch MEVD17.2 ruft
  typisierte Hüllroutinen, die in gemeinsame Kernroutinen springen. Das Vorzeichen ist dort nicht an den Ladebefehlen
  ablesbar.
- **Adressierung:** Entwicklungsstände linken die Kalibrierung an eine andere Flash-Adresse als die, an der sie im
  Abbild liegt. Daraus entstand die Lageerkennung über Achsköpfe (§ 5).
- **Abgleich:** Von 729 typisierten 2D-Aufrufstellen, die Ghidra auf einem Entwicklungsstand findet, löst die
  Erkennung jetzt 297 auf (1.20.1: 0). Die aus dem Code gelesenen Zelltypen widersprechen der A2L in keinem Fall.
  Es gibt vorzeichenbehaftete Datensatz-Routinen; die Annahme „nur vorzeichenlose Kennfelder“ ist widerlegt.

## 8. Modelltraining

Es wurde **kein Modell trainiert**. Die Referenzdaten sind private Daten; eine Freigabe für Training und für
veröffentlichte abgeleitete Daten liegt nicht vor. Alle Verbesserungen sind Algorithmen. Das vorhandene, synthetisch
trainierte Strukturmodell ist unverändert; Modellsperre und Firmware-Guard sind unverändert aktiv und geprüft.

## 9. Grenzen

- **Byte-Reihenfolge MSV90-Kalibrierabbilder:** Die Datensätze stimmen dort nur 1,9 : 1 für Little Endian; die an
  den Entwicklungsdaten gewählte Schwelle ist 2 : 1. Deshalb gilt keine Reihenfolge für das ganze Abbild, und
  1 046 exakte Funde haben die falsche Reihenfolge. Eine Änderung der Schwelle anhand des Holdouts wäre eine
  Anpassung an die Testdaten und unterbleibt; sie braucht neue Entwicklungsdaten.
- **Verwechslungen auf MEVD17.2.3-Vollflashs** steigen (§ 6.1, § 6a.3: 3 042 → 3 744). Ursache und Abhilfe sind
  offen; sie sind nur aus dem Holdout bekannt und brauchen Entwicklungsdaten derselben Linie.
- **Breitenregel** (§ 6a.2): 18 16-Bit-Tabellen werden als Byte-Tabelle gelesen, 31 Kennfelder gehen durch
  verdrängende Zeilenabstands-Lesarten verloren (Entwicklung). Vorzeichenfehler steigen, weil die neuen
  Byte-Tabellen ihr Vorzeichen nicht kennen; sie sind als „Datentyp nicht belegt“ markiert.
- **Unabhängige Bestätigung fehlt** für Runde 2: keine neue Testgruppe (§ 6a.7).
- **Vorzeichen:** Bosch-Hüllroutinen springen in gemeinsame Kernroutinen; das Vorzeichen ist dort aus dem Code nicht
  ablesbar. Die Lesart ohne Überlauf irrt bei Kennfeldern mit wenigen Werten nahe 0/255 (Flags). Rest: 2 017
  Vorzeichenfehler unter 49 958 exakten Funden auf dem Holdout.
- **Gemeinsame Achsen ohne eigenen Kopf** und Bosch-Festachsen (FIX_AXIS) sind im reinen Kalibrierabbild ohne Code
  nicht auffindbar; Kalibrierabbilder bleiben deutlich unter Vollflashs (Recall 0,25–0,46 gegenüber 0,63–0,89).
- **Präzision** ist nicht ausgewiesen: Funde außerhalb der A2L-Objekte sind nicht automatisch falsch.
- **Laufzeit** auf Siemens-TriCore-Vollflashs +16 bis +21 % gegenüber 1.20.1 (§ 6a.6); insgesamt 2 % schneller.
- **Nicht wiederholbar:** die realen Paare früherer Berichte und der Negativbestand offener Firmware lagen nicht vor.
- Ghidra/REA nur extern; REA öffnet keine TriCore-ELF. Kein Modelltraining (§ 8).
- Die Ergebnisse gelten für BMW-Steuergeräte von Bosch und Siemens auf TriCore bzw. PowerPC (ME9). Andere
  Hersteller und Familien sind damit nicht gemessen.
