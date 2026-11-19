# Entwicklungsbericht 1.21.0 – Kennfelderkennung mit A2L-/HEX-Referenzdaten

Stand: 19.11.2026. 1.21.0 **in Entwicklung, nicht veröffentlicht**; Vorabversion 1.21.0-rc1 als GitHub-Pre-Release veröffentlicht (§ 6e). Ausgangspunkt `v1.20.1` (8cca756), Branch
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
- **Regressionssatz** (15 Fälle): nach Phase 4 exakte Funde in allen Fällen wie 1.20.1 oder besser; die
  MS43-Regression aus Runde 3 (197 → 196) ist behoben (§ 6c.2). Alle Tests grün. Laufzeit insgesamt −5 % gegenüber
  1.20.1 (Runde 3), Spitzenspeicher gleich.
- **Runde 3 (§ 6b), nur an Entwicklungsdaten entwickelt:** Entwicklung 31 142 → 32 058 exakt, Verwechslungen
  7 908 → 5 316, nicht bewertbare Kandidaten 3 252 → 1 743. Die Fehler der Breitenregel aus Runde 2 sind weitgehend
  behoben; eine schwach belegte 8-Bit-Lesart verdrängt die 16-Bit-Lesart nicht mehr. Fehlfunde auf offener
  Firmware ohne Kennfelder (wiederhergestellter Negativbestand, 7 Stände) 875 → 549. Holdout als Regressionsprüfung
  (nicht unabhängig): 51 016 → 52 701 exakt, Verwechslungen 15 459 → 10 743 (1.20.1: 16 820).
- **Phase 4 (§ 6c):** Tests, Selbsttest und GUI-Smoke verändern die Registry nicht mehr (der Selbsttest nach einem
  Update überschrieb das Fensterlayout des Nutzers). Ein Datensatzkopf, dem ein Code-Beleg widerspricht, verdrängt
  keine Lesart mehr (MS43 wieder 197). Nicht belegte Vorzeichen bleiben als Alternative sichtbar: falsche Datentypen
  ohne „?“ auf den Entwicklungsdaten 235 → 0. Funde und Zahlen sonst unverändert.
- **Phase 5 (§ 6d):** Ist die Byte-Reihenfolge eines Abbilds nicht belegt, steht das jetzt am Fund (Holdout als
  Regressionsprüfung: 1 399 von 1 436 falschen Byte-Reihenfolgen tragen ein „?“, MSV90). Prüfhilfen: Filter für
  unbelegte Datentypen und Überschneidungen, fehlender Beleg je offener Frage, Lesarten derselben Bytes
  nebeneinander, Prüfliste nach Prüfgrund. Updater-Tests berühren den echten Eintrag in „Apps & Features“ nicht
  mehr; Abbruch- und Fehlerfälle der Testisolierung sind getestet. Funde unverändert.
- **Vorbereitung 1.21.0-rc1 (§ 6e):** Ein Vorzeichen gilt nur noch als belegt, wenn alle Tabellen-Ladebefehle der
  Routine in Breite und Vorzeichen übereinstimmen (Holdout als Regressionsprüfung: falsche Datentypen ohne „?“ bei
  MSV90 48 → 0; Entwicklung unverändert). Englische Oberfläche der Prüfhilfen vervollständigt. RC-Versionen,
  Testkanal und Release-Workflow für Vorabversionen; Installer-QA auf Windows Server 2022/2025 (1 020 Prüfungen,
  0 fehlgeschlagen) und Release-Probelauf bestanden. Am 19.11.2026 als Pre-Release veröffentlicht.
- **Nicht unabhängig bestätigt:** Für Runde 2, 3, Phase 4 und 5 gibt es keine neue, unbenutzte Testgruppe realer
  Steuergeräte; lokal und öffentlich wurden zweimal keine geeigneten Referenzen gefunden (§ 6c.4, § 6d.1). Eine
  synthetische externe Stichprobe (4 Kennfelder) ersetzt das nicht.
- **Offen:** mehr Verwechslungen auf MEVD17.2.3-Vollflashs (nur im Holdout sichtbar, § 6d.3); Byte-Reihenfolge der
  MSV90-Kalibrierabbilder (gekennzeichnet, nicht bestimmt; § 9). Kein Modelltraining.

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

## 6b. Dritte Runde: Breitenregel, Datenmuster, Fehlfunde

Wieder **nur an den Entwicklungsdaten** (58 Abbilder) entwickelt und mit Ablationen gemessen; jede Regel hat einen
Schalter und synthetische Tests. Der Holdout wurde danach nur als Regressionsprüfung gemessen (nicht unabhängig,
keine Abstimmung daran).

### 6b.1 Bestätigte Ursachen

- **Falsche 8-Bit-Lesarten der Breitenregel (Runde 2: 18):** Der nachfolgende Datensatz begann auf der anderen
  Adressparität als der eigene Kopf. Hinter echten Byte-Tabellen liegt er immer auf derselben Parität
  (1 223 von 1 223), hinter echten 16-Bit-Tabellen meist auf der anderen (82 von 106). Von den verbleibenden Fehlern
  stammen 20 von 24 aus einem einzelnen Kennlinien-Datensatz als einzigem Beleg.
- **Verlorene Kennfelder (Runde 2: 31):** Die richtig verkürzte Byte-Tabelle hat eine schwächere Oberfläche; eine
  früher beginnende Glätte-Lesart (Zeilenabstand) gewinnt die Überlappung und überdeckt auch die folgenden
  Datensätze. Glätte-Lesarten mit einem angenommenen Datensatzkopf in ihrem Bereich waren in den
  Kalibrierabbildern nie exakt (0 von 661), in den Vollflashs einmal (1 von 96).
- **Verwechslungen durch Datenmuster:** Glätte-Lesarten (Zeilenabstand) stellen den größten Teil der Verwechslungen
  (MEVD17.2-Vollflash 860 von 1 290, MSD80-Vollflash 1 929 von 2 031). Rein vorzeichenbehaftete Glätte-Lesarten
  waren bei beiden Herstellern fast nie richtig: 2 exakte gegen 2 128 Verwechslungen.
- **Fehlausgerichtete 16-Bit-Felder:** Unter rund 3 000 angenommenen Datensätzen mit gemischten Breiten lag ein
  16-Bit-Feld 4-mal in ungeradem Abstand zum Kopf, alle 4 Verwechslungen. Auf offener ARM-Firmware (Negativbestand)
  waren genau solche Lesarten die einzigen neuen Strukturfunde.

### 6b.2 Regeln und Ablation (Entwicklung, 58 Abbilder)

Jede Zeile: Wirkung der Regel gegenüber dem Stand ohne sie, alle übrigen Regeln an.

| Regel | Schalter | exakt | teilweise | Verwechslung | n. bewertbar | Funde |
|---|---|---:|---:|---:|---:|---:|
| Folgedatensatz nur auf der Parität des eigenen Kopfs | `BOUNDARY_SAME_PARITY` | +2 | −2 | −3 | ±0 | −8 |
| 8 Bit nur bei starkem Beleg (2D-Datensatz oder Datensatzkette); sonst 16 Bit, Breite als offen markiert | `BOUNDARY_STRONG_ONLY` | −52 | +52 | −14 | ±0 | −14 |
| Glätte-Lesart verworfen, wenn ein angenommener Datensatzkopf in ihr liegt | `PITCH_NO_RECORDS` | +677 | −56 | −422 | −3 | +196 |
| Rein vorzeichenbehaftete Glätte-Lesarten verworfen | `PITCH_UNSIGNED_ONLY` | −1 | −220 | −1 893 | −1 502 | −3 664 |
| 16-Bit-Felder eines Datensatzes in geradem Abstand zum Kopf | `RECORD_ALIGNED_16` | ±0 | ±0 | ±0 | ±0 | ±0 |

`BOUNDARY_STRONG_ONLY` kostet auf den Entwicklungsdaten exakte Funde: Bei schwachem Beleg (nur ein einzelner
Kennlinien-Datensatz dahinter, gleiche Parität) ist die 8-Bit-Lesart 101-mal richtig und 20-mal falsch. Die Regel
folgt trotzdem der Vorgabe, dass eine schwach belegte 8-Bit-Lesart die 16-Bit-Lesart nicht verdrängt: Die
16-Bit-Lesart bleibt, die Breite wird als „nicht belegt (auch möglich: 8-Bit-Tabelle gleicher Form)“ gezeigt und
ist ein Grund in der Prüfliste. Der Schalter macht die Abwägung umkehrbar.

`RECORD_ALIGNED_16` ist auf den Entwicklungsdaten ohne Wirkung, weil dort die Ausrichtung des ganzen Abbilds
(`ALIGNED_16`, Runde 2) schon entscheidet. Sie wirkt auf Abbildern mit zu wenigen Datensätzen für diese
Entscheidung: im Negativbestand 9 Strukturfunde weniger (§ 6b.4). Technisch begründet: C-Strukturen und
Halbwortzugriffe auf TriCore und C16x legen 16-Bit-Felder auf gerade Abstände.

Auf den 27 Kalibrierabbildern der Breitenregel-Ablation verliert der neue Stand gegenüber „Breitenregel aus“ 16
exakte Kennfelder und gewinnt 1 198 (Runde 2: 54 verloren, 420 gewonnen).

### 6b.3 Ergebnisse Entwicklung (58 Abbilder)

| | 1.20.1 | Runde 2 | Runde 3 |
|---|---:|---:|---:|
| exakt (von 52 508 verifizierbaren) | 20 517 | 31 142 | **32 058** |
| teilweise | 3 812 | 2 449 | 2 197 |
| Verwechslung | 9 020 | 7 908 | **5 316** |
| nicht bewertbar | 1 371 | 3 252 | 1 743 |
| Funde gesamt | 35 003 | 45 104 | 41 619 |
| Datentyp richtig unter exakten | 77,0 % | 96,2 % | 95,8 % |
| Vorzeichenfehler | 1 890 | 1 158 | 1 326 |
| Byte-Reihenfolge falsch | 2 829 | 21 | 20 |

Gegenüber Runde 2 gehen 84 exakte Kennfelder verloren (davon 52 durch `BOUNDARY_STRONG_ONLY`), 1 000 kommen hinzu.
Gegenüber 1.20.1: 32 verloren, 11 573 hinzu. **Vorzeichenfehler:** Alle 31 081 exakten Funde, die in beiden Ständen
vorkommen, behalten ihren Datentyp. Der Zuwachs stammt vollständig aus den 975 neu gefundenen Datensatz-Tabellen,
die vorher von Glätte-Lesarten überdeckt waren; ihr Vorzeichen ist als ungeprüft markiert.

### 6b.4 Negativbestand und Regressionssatz

Der Negativbestand früherer Berichte wurde aus den offiziellen Quellen wiederhergestellt (FOME- und rusEFI-Builds
für f407-discovery, Speeduino-Releases; Größe und Prüfsummen stimmen mit den früheren Angaben überein). Die Dateien
liegen nur lokal. Jeder Fund dort ist ein Fehlfund.

| | 1.20.1 | 1.21 Runde 3 |
|---|---:|---:|
| Funde gesamt (7 Firmwarestände) | 875 | 549 |
| davon Datenmuster-Vermutung | 839 | 513 |
| davon Strukturbeleg | 36 | 36 |

Ohne die Ausrichtungsregel (`RECORD_ALIGNED_16`) waren es 554 Funde mit 45 Strukturbelegen: je FOME-Stand drei
zusätzliche aus einem Datensatz, dessen 16-Bit-Achse in ungeradem Abstand zum Kopf lag. Laufzeit und Speicher
wie 1.20.1. „Sicher falsch“ (Füllbytes, Text, Code) bleibt 0; die übrigen Funde sind nicht automatisch
widerlegbar und bleiben als Vermutung gekennzeichnet.

Regressionssatz (15 Fälle): synthetische Fälle und Negativdateien unverändert. MS42 exakt 22 → 22 (Präzision
66 % → 71 %), MSD80 86 → 86. MS43 197 → 196 exakt (Präzision 74 % → 78 %): Das verlorene Kennfeld war eine
Glätte-Lesart mit einem Datensatzkopf im Bereich (`PITCH_NO_RECORDS`).

### 6b.5 Prüfung vor dem Speichern und Anzeige

- Jede Änderung in einem ungeprüften Kennfeldvorschlag (automatisch erkannt oder Name übertragen), die keine
  Definition und kein geprüftes Kennfeld abdeckt, ergibt den gelben Befund „Änderung in ungeprüftem
  Kennfeldvorschlag“. Bisher gab es das nur im vermuteten Programmcode. Ein Vorschlag ist damit nie eine geprüfte
  Grundlage; ohne vollständige Checksummenprüfung bleibt jede geänderte Datei ohnehin „nicht flashbereit“.
- Die Detailansicht nennt alle Einträge, die sich Bytes mit dem gewählten Kennfeld teilen, mit Status.
- Offene Wertebreite: Datentyp mit „?“, Grund im Tooltip und in der Detailansicht, Prüflisten-Grund.

### 6b.6 Unabhängige Validierung und Referenzdaten

- **Keine neue unabhängige Testgruppe.** Im lokalen Referenzordner liegen keine unbenutzten Sätze (alle Abbilder
  sind über ihren Inhalt als Entwicklung oder Holdout bekannt). Die zwölf realen Paare früherer Berichte ohne
  dokumentierte Herkunft wurden weder gesucht noch heruntergeladen; öffentlich frei lizenzierte A2L-/HEX-Paare
  wurden nicht gefunden. Die frei verfügbaren MS42-/MS43-Abbilder sind dieselben Softwarestände wie im
  Regressionssatz und daher nicht unabhängig.
- Der Holdout ist seit Runde 1 bekannt; die Messung in § 6b.7 ist eine Regressionsprüfung, keine unabhängige
  Bestätigung. **Die Ergebnisse dieser Runde sind nicht unabhängig validiert.**

### 6b.7 Holdout als Regressionsprüfung (nicht unabhängig)

Einmal gemessen, nach dem Einfrieren des Quellstands; nichts wurde danach geändert. Die Testlinien sind seit
Runde 1 bekannt; die Zahlen zeigen nur, ob die Änderungen dort schaden.

| | 1.20.1 | Runde 2 | Runde 3 |
|---|---:|---:|---:|
| exakt (von 91 370 verifizierbaren) | 35 382 | 51 016 | **52 701** |
| teilweise | 7 181 | 4 074 | 3 484 |
| Verwechslung | 16 820 | 15 459 | **10 743** |
| unklar | 2 173 | 1 676 | 1 275 |
| nicht bewertbar | 3 052 | 6 235 | 3 585 |
| Funde gesamt | 64 637 | 78 476 | 71 804 |
| Datentyp richtig unter exakten | 80,5 % | 92,9 % | 92,6 % |
| Vorzeichenfehler | 2 639 | 2 281 | 2 486 |
| Byte-Reihenfolge falsch | 4 270 | 1 336 | 1 436 |

- Gegenüber Runde 2: 216 exakte Kennfelder verloren, 1 901 hinzu. Gegenüber 1.20.1: 85 verloren, 17 404 hinzu.
- Verwechslungen sinken in allen Linien. MEVD17.2.3-Vollflashs: 1.20.1 3 042, Runde 2 3 744, Runde 3 3 297; damit
  noch 255 über 1.20.1.
- Byte-Reihenfolge: Der Anstieg (+100) betrifft neu gefundene Tabellen in den MSV90-Kalibrierabbildern
  (1 046 → 1 118) und den MEVD17.2.3-Vollflashs (86 → 114). Die Ursache bei MSV90 ist die offene
  Reihenfolge-Entscheidung (§ 9); sie wurde nicht am Holdout nachgestellt.
- Vorzeichenfehler steigen mit den neu gefundenen Datensatz-Tabellen (wie in § 6b.3), vor allem in
  MSD80-N43- und MSV90-Kalibrierabbildern; ihr Vorzeichen ist als ungeprüft markiert.

### 6b.8 Laufzeit und Speicher

Zuerst profiliert (seriell, MSD80-Vollflash, 1.20.1 gegen jetzt): Die Mehrzeit liegt in der TriCore-Auswertung der
Aufrufstellen (Lageerkennung verlagerter Kalibrierung, Rollensuche) und im Ranking der fast doppelt so vielen
Kandidaten; Zeigertripel kosten unter 0,1 s. Die Lageerkennung und die Rollensuche prüfen zehntausende mögliche
Achs- und Datensatzköpfe; die meisten scheitern schon am ersten Wertepaar. Diese Prüfung kommt jetzt zuerst
(exakt, gegen die vollständige Prüfung über alle 8-Bit-Paare und 200 000 16-Bit-Proben verglichen). Ergebnisgleichheit:
alle Kandidaten aller 15 Leistungsabbilder identisch.

Leistungssatz, 15 Abbilder, nacheinander ohne Last, 1.20.1 → Runde 2 → Runde 3:

| Linie | Abbild | Laufzeit (s) | Spitzenspeicher (MB) | exakt |
|---|---|---|---|---|
| ME9 | Kalibrierung | 5,1 → 5,1 → 4,6 | 19 → 19 → 19 | 101 → 127 → 139 |
| MEVD17.2 | Kalibrierung / Vollflash | 8,4 / 12,1 → 7,7 / 10,7 → 7,4 / 10,1 | 38 / 172 → gleich → gleich | 940 → 1 077 → 1 120 |
| MEVD17.2.3 (3 Linien) | Kalibrierung | 17,2 → 15,9 → 14,6 | 22 → 22 → 22 | 1 001 → 1 398 → 1 465 |
| MEVD17.2.3 (3 Linien) | Vollflash (10 MB) | 59,7 → 55,9 → 55,5 | 431 → 431 → 431 | 1 553 → 1 880 → 1 893 |
| MSD80 (2 Linien) | Kalibrierung | 16,4 → 15,8 → 15,9 | 45 → 45 → 45 | 528 → 621 → 675 |
| MSD80 (2 Linien) | Vollflash | 20,3 → 23,5 → 23,4 | 88 → 86 → 87 | 630 → 1 462 → 1 464 |
| MSV90 | Kalibrierung / Vollflash | 7,7 / 13,3 → 7,2 / 14,1 → 7,0 / 13,6 | 36 / 86 → gleich → gleich | 296 → 702 → 738 |
| **Summe** | | **160,3 → 155,9 → 152,2** | **431 → 431 → 431** | **5 049 → 7 267 → 7 494** |

1.20.1 wurde für diese Tabelle neu gemessen (160,3 s statt 159,5 s in § 6a.6, Messstreuung). Gegenüber 1.20.1
insgesamt 5 % schneller bei 48 % mehr exakten Funden. Langsamer bleiben die MSD80-Vollflashs (+15 %, Runde 2:
+21 %); dort findet die TriCore-Auswertung mehr als doppelt so viele Tabellen. MSV90-Vollflash +2 % (Runde 2: +16 %).

**Prüfungen Runde 3:** pytest 1 167 bestanden, 22 übersprungen, 0 fehlgeschlagen (inkl. GUI, Firmware-Guard,
Modellsperre); die Registry-Einstellungen wurden nach jedem einzelnen Test verglichen und blieben unverändert.
GUI-Smoke 10/10, Übersetzungsprüfung 2 265 Texte ohne Lücke, geänderte Dateien parsen unter Python 3.11 und 3.12,
Firmware-Guard über den ganzen Baum ohne Befund.

### 6b.9 Nicht gelöst

- **MEVD17.2.3-Vollflashs (mehr Verwechslungen als 1.20.1):** Auf den Entwicklungsdaten nicht nachstellbar; dort
  sinken die Verwechslungen. Eine Abhilfe ohne Entwicklungsdaten derselben Linie wäre eine Anpassung an den Holdout.
- **MSV90-Byte-Reihenfolge:** Kein unabhängiger Beleg (keine MSV90-Entwicklungsdaten; in Kalibrierabbildern ohne
  Programmcode gibt es keinen Code-Hinweis auf die Reihenfolge). `DECISIVE_VOTES` bleibt aus.
- **Nicht bewertbare Kandidaten:** stark verringert (Entwicklung 3 252 → 1 743), aber weiter ungeprüft und als
  Datenmuster-Vermutung gekennzeichnet; bestätigt ist keiner.

## 6c. Qualitätsphase 4: Testisolierung, MS43, Datentypen, Referenzen

Stand 15.11.2026. Alle Regeln wurden nur an den Entwicklungsdaten und am Regressionssatz geprüft. Der Holdout wurde
einmal nach dem Einfrieren der Erkennungsregeln als Regressionsprüfung gemessen.

### 6c.1 Registry und Testisolierung

- **Befund:** Der Selbsttest, den der Updater nach dem Installieren startet (`--self-check`), öffnete das
  Hauptfenster mit den echten Einstellungen. Beim Schließen speichert das Fenster sein Layout. So ersetzte nach jedem
  Update das Layout des unsichtbaren Prüffensters Fensterposition und Dock-Anordnung des Nutzers. Zusätzlich schrieb
  jeder Programmstart das Farbschema neu, auch unverändert.
- **Behoben:** Der Selbsttest arbeitet mit eigenen, danach gelöschten Einstellungen und ohne Update-Suche. Der
  Programmstart schreibt keine Einstellungen mehr; erst das Schließen (Layout) oder eine Auswahl des Nutzers.
- **Ein Einstellungsort** (`app_settings`): Registry für das installierte Programm wie bisher. `ECU_STUDIO_SETTINGS_DIR`
  leitet in eine INI-Datei um, auch für Prozesse, die ein Test startet. Im Testprofil (`ECU_STUDIO_TEST_PROFILE`)
  verweigert das Programm ohne Umleitung jeden Zugriff, statt auf die Registry zurückzufallen, und schreibt nie den
  Deinstallationseintrag („Apps & Features“).
- **Testlauf:** eigener Einstellungsordner je Test und je Lauf (am Ende gelöscht, auch nach Fehlern), keine
  Update-Suche, keine sichtbaren Fenster. Vor jedem Test wird die Umleitung geprüft, sonst wird der Test nicht
  ausgeführt. Die Registry-Schlüssel des Programms werden vor dem Lauf und nach jedem Test nur **gelesen**; eine
  Änderung lässt den Lauf fehlschlagen und nennt den Test. Ein statischer Test lässt Registry-Schreibzugriffe nur an
  der einen bekannten Stelle (Deinstallationseintrag) zu.
- **Prüfung:** voller Testlauf und GUI-Smoke ohne Änderung an den Registry-Werten (Vergleich vorher/nachher, nur
  lesend). Die produktive Registry wurde in dieser Phase nicht verändert. Die Änderung, die nach dem ersten Testlauf
  von Runde 3 auffiel, lässt sich nachträglich keinem Test zuordnen; die Tests schreiben nachweislich nicht.
  Wahrscheinlicher ist eine gleichzeitig laufende Sitzung des installierten Programms.

### 6c.2 MS43-Regression aus Runde 3

Der verlorene MS43-Fund war eine Glätte-Lesart (8 × 8 Byte), in deren Bereich ein Datensatzkopf lag. Dessen Datensatz
überdeckt aber ein Kennfeld, das der Programmcode mit beiden Achsen adressiert; im Ranking unterliegt er ohnehin.
Ein solcher Kopf ist ein unbestätigter Beleg und durfte die Lesart nicht vorab verdrängen.

**Regel (allgemein, Schalter `HEADS_CODE_CHECKED`):** Ein Datensatzkopf widerspricht einer Glätte-Lesart nur, wenn
kein Code-Beleg (Code-Verweis, Aufruf, Zeigertripel) mit anderem Start seinen Datensatz überdeckt. Keine Sonderregel
für eine Familie oder Adresse; synthetischer Test in `tests/test_record_boundaries.py`.

| | Runde 3 | Phase 4 |
|---|---:|---:|
| MS43 exakt | 196 | **197** (Präzision 78 % → 78 %) |
| MS42 / MSD80 exakt | 22 / 86 | 22 / 86 |
| Entwicklung exakt / Verwechslungen | 32 058 / 5 316 | 32 058 / 5 316 |
| Negativbestand (Funde / sicher falsch) | 549 / 0 | 549 / 0 |

Auf den Entwicklungsdaten liegt unter 483 Glätte-Lesarten mit Kopf im Bereich genau eine exakte (431 Verwechslungen);
die Regel ändert dort nichts. Die synthetischen Fälle und Negativdateien des Regressionssatzes sind unverändert.

### 6c.3 Datentypen

Die Lesart „ohne Überlauf benachbarter Zellen“ wählt das Vorzeichen, belegt es aber nicht. Bei Flag-Tabellen nahe
0/255 irrt sie; bei flachen Tabellen (alle Zellen gleich, oberstes Bit gesetzt) entscheidet sie gar nicht, und es
entstand bisher nur eine Lesart ohne Alternative.

**Regel (Schalter `SIGN_KEEPS_ALTERNATIVE`):** Bei Datensatz-Tabellen legt kein Code das Vorzeichen fest. Ist das
oberste Bit gesetzt, bleibt die andere Lesart als Alternative erhalten. Die Anzeige zeigt den Typ mit „?“ und
nennt den Grund; die Prüfliste führt ihn als Prüfgrund. Datentyp und Funde ändern sich nicht. 8/16-Bit-Breite:
`BOUNDARY_STRONG_ONLY` bleibt an, offene Breiten bleiben wie in Runde 3 mit „?“ markiert.

| Entwicklung (58 Abbilder) | Runde 3 | Phase 4 |
|---|---:|---:|
| Datentyp richtig unter exakten | 95,8 % | 95,8 % |
| falscher Datentyp **ohne** „?“ | 235 ¹ | **0** |
| exakte Funde mit „?“ | 9 234 ¹ | 13 318 |

¹ Abgeleitet: Runde 3 hat dieselben Funde und Typen; abgezogen sind die Funde, deren „?“ erst die neuen Regeln setzen.

Die Kennzeichnung kostet Übersicht: 41 % der exakten Funde tragen ein „?“. Das entspricht dem Stand der Belege.

### 6c.4 Neue Referenzdaten und unabhängige Validierung

- **Lokal:** Im Referenzordner liegt außer den bekannten Linien nur ein Satz „MED17.1.1“ (4 Abbilder, 2 A2L). Alle
  sechs Dateien sind bytegleich mit dem MEVD17.2-Entwicklungssatz und damit nicht unabhängig. Neue Dateien seit der
  ersten Bestandsaufnahme: keine. Andere persönliche Verzeichnisse wurden nicht durchsucht.
- **Öffentlich:** Gesucht wurden frei lizenzierte A2L-/HEX-Paare (MEVD17, MSV90, andere Familien). Gefunden wurden nur
  ein Demonstrationsarchiv des Standardisierungsgremiums ASAM (Beispiel-A2L mit HEX-Datei; Nutzungslizenz nicht
  angegeben, kein reales Steuergerät), Beispiel-A2L ohne Abbild und Abstimmungen offener Steuergeräte (rusEFI:
  Lizenz der Abstimmungen nicht angegeben; Speeduino: CC BY-NC 4.0, bereits als Teilreferenz gemessen). Keines davon
  ist eine geeignete, rechtlich klare Referenz für die BMW-Familien; nichts wurde heruntergeladen.
- **Folge:** Eine neue, vor der ersten Auswertung festgelegte Testgruppe ließ sich nicht bilden. **Runde 2, 3 und
  Phase 4 sind nicht unabhängig validiert.** Die einzige unabhängige Messung bleibt Runde 1 (§ 6.1).

### 6c.5 Holdout als Regressionsprüfung (nicht unabhängig)

Phase 4 gegen Runde 3: exakt 52 701 → 52 701, Verwechslungen 10 743 → 10 743, Datentyp richtig 92,6 % → 92,6 %,
Vorzeichen- / Byte-Reihenfolge-Fehler 2 486 / 1 436 unverändert, MEVD17.2.3-Vollflashs 3 297 Verwechslungen
(unverändert, weiterhin über 1.20.1). Die „?“-Zählung des Holdouts stammt aus einem Zwischenstand ohne die Regel für
flache Tabellen und wird nicht ausgewiesen.

### 6c.6 Laufzeit und Speicher

Leistungssatz (15 Abbilder, nacheinander ohne Last). Runde 3 wurde am selben Tag unter gleichen Bedingungen neu
gemessen, weil der Wert vom Vortag (152,2 s) davon abweicht:

| | 1.20.1 | Runde 3 (neu gemessen) | Phase 4 |
|---|---:|---:|---:|
| Laufzeit gesamt | 160,3 s | 141,8 s | 144,4 s |
| Spitzenspeicher | 431 MB | 431 MB | 431 MB |
| MSD80-Vollflash / MSV90-Vollflash | 20,3 / 13,3 s | 21,5 / 12,8 s | 20,7 / 13,1 s |
| exakte Funde, Funde gesamt | – | gleich | gleich |

Phase 4 enthält keine Laufzeitänderung. Die neue Kopfprüfung kostet höchstens 3 ms je Abbild (einzeln gemessen an
allen sieben Vollflash-Linien); die Abweichungen von 1–5 % je Linie sind Messstreuung. Die Ziele (höchstens
152,2 s und 431 MB) sind eingehalten.

## 6d. Qualitätsphase 5: Referenzsuche, MEVD17.2.3/MSV90, Prüfhilfen, Isolierung

Stand 17.11.2026. Keine Regel wurde an Holdout-Daten abgestimmt. Der Code wurde vor allen Messungen eingefroren.

### 6d.1 Suche nach neuen Referenzdaten

- **Lokal:** Der Referenzordner des Datengebers ist seit dem 14.11.2026 unverändert (6 Linien, keine neuen Dateien).
  Andere persönliche Verzeichnisse wurden nicht durchsucht.
- **Öffentlich** (Suche 17.11.2026; gesucht nach MEVD17.2.3, MSV90, MED17.5/17.7, EDC17, MG1/MD1, Simos/SID, TCU,
  Forschungsdatensätzen und offenen Steuergeräteprojekten):

| Quelle | Inhalt | Lizenz / Herkunft | Eignung |
|---|---|---|---|
| Tuners Toolkit, `testdata/demo` (TT-DEMO-1) | A2L + HEX eines erfundenen Steuergeräts (Generator des Projekts) | MIT; „nothing here comes from a real ECU“ | **genutzt** als externe synthetische Stichprobe (§ 6d.2), keine Validierung realer Steuergeräte |
| calibrationReader (asap2Go), `testing/` | ASAP2-Demo (A2L + HEX/S19) | Repository MIT, Demodateien aus dem ASAM-/Werkzeugumfeld ohne eigene Lizenzangabe | nicht genutzt (Herkunft der Demodateien ungeklärt, kein reales Steuergerät) |
| ApexECUVault | „original binary dumps“ und TunerPro-Definitionen vieler Hersteller | als MIT gekennzeichnet, die Firmware gehört aber den Herstellern | **ausgeschlossen** (zweifelhafte Herkunft; der Hochladende kann Herstellerfirmware nicht lizenzieren) |
| ecu_tcu_files u. ä. | ECU-/TCU-Abbilder mit XDF | keine Lizenzangabe | ausgeschlossen |
| SimosDefinitions, RomRaider-Definitionen | Definitionen ohne Abbilder bzw. für andere Hersteller | teils ohne Lizenzangabe | nicht geeignet (keine Abbilder, Abbilder wären Herstellerdateien) |
| XCPlite (Vector), Atlas, FOME, rusEFI, Speeduino | Demo-/Kalibrierwerkzeuge bzw. offene Firmware | offene Lizenzen | keine realen BMW-/Bosch-Kalibrierungen; FOME/rusEFI/Speeduino bereits im Negativbestand |
| Forschungsdatensatz (Zenodo, Motorsteuerung) | Mess- und Regelungsdaten | offen | keine Firmware, keine A2L |

**Folge:** Keine neuen, rechtmäßig nutzbaren A2L-/HEX-Paare realer Steuergeräte. **Anzahl neuer unabhängiger
Testdateien realer Steuergeräte: 0.** Bekannte Testdaten wurden nicht als neuer Holdout ausgegeben.

### 6d.2 Externe synthetische Stichprobe (TT-DEMO-1)

Vor dem Download festgelegt: nur Test, eine Auswertung, eingefrorener Code, keine Änderung danach. Das Abbild ist
das 32-KiB-Flash-Segment der HEX-Datei (Startadresse laut Projektbeschreibung). Die Dateien liegen nur lokal, nicht im
Repository.

| | 1.20.1 | 1.21.0 (Phase 5) |
|---|---:|---:|
| 2D-Kennfelder laut A2L | 4 | 4 |
| exakt | 1 | 1 |
| Verwechslungen | 2 | 1 |
| Datentyp / Achsen richtig unter exakten | 1/1 / 1/1 | 1/1 / 1/1 (mit „?“) |
| exakte 1D-Objekte (Achsen) | 2 | 2 |
| Laufzeit / Spitzenspeicher | 0,29 s / 8 MB | 0,27 s / 8 MB |

Vier Kennfelder sind statistisch bedeutungslos. Die Stichprobe zeigt nur, dass Import, Adressumsetzung und Abgleich
mit einer fremd erzeugten A2L funktionieren und 1.21.0 dort nicht schlechter ist.

### 6d.3 MEVD17.2.3-Vollflashs

MEVD17.2.3 liegt nur im Holdout. Untersucht wurde deshalb zuerst die Entwicklungslinie derselben Bauart
(MEVD17.2-Vollflashs, TriCore), danach der Holdout nur als Zählung ohne Abstimmung.

- **Entwicklung:** Das Muster tritt dort nicht auf. Datensatz-Verwechslungen mit einem Kennfeld sinken gegenüber
  1.20.1 (176 → 127), Zeilenabstands-Verwechslungen über mehrere Objekte ebenfalls (711 → 415).
- **Holdout (Diagnose):** Gegenüber 1.20.1 entfallen 1 984 Verwechslungen, 2 239 kommen hinzu. Die neuen sind vor
  allem 8-Bit-Lesarten mit Datensatzkopf (u8/s8, 691), 16-Bit-Datensatzlesarten über mehrere Objekte (351) und
  Datenmuster-Lesarten (u. a. 541 Zeilenabstand über mehrere Objekte). Die Speicherabbildung ist nicht die Ursache:
  exakte Funde und Adressen stimmen.
- **Folge:** Eine Regel dagegen ließe sich nur am Holdout belegen. Sie unterbleibt; nötig sind Entwicklungsdaten
  der Linie MEVD17.2.3. Die betroffenen Lesarten sind Strukturbeleg oder Datenmuster-Vermutung, nie Code-Beleg, und
  bleiben ungeprüfte Vorschläge.

### 6d.4 MSV90: unentschiedene Byte-Reihenfolge sichtbar

Wenn sich die Datensätze eines Abbilds nicht auf eine Byte-Reihenfolge einigen (keine Mehrheit nach der bestehenden
Regel), behielt jeder 16-Bit-Datensatz bisher still die Reihenfolge seiner eigenen Lesart.

**Regel (Schalter `ENDIAN_KEEPS_OPEN`):** In diesem Fall trägt jeder 16-Bit-Datensatz ohne eigene 16-Bit-Zähler den
Hinweis „Byte-Reihenfolge nicht belegt“. Anzeige mit „?“, Prüflistengrund, die andere Reihenfolge als Lesart in
der Detailansicht. Keine Schwelle wurde geändert und kein Fund verändert; `DECISIVE_VOTES` bleibt aus. Die Regel
beruht auf einer technischen Eigenschaft (keine Mehrheit), nicht auf Holdout-Zahlen.

| | ohne Regel | Phase 5 |
|---|---:|---:|
| Entwicklung: Funde, Typen, „?“ | 32 058 exakt, 13 318 „?“ | gleich (alle 58 Abbilder fundgleich) |
| Holdout (nur Regression): exakte Funde mit falscher Byte-Reihenfolge | 1 436 | 1 436 |
| davon mit „?“ | 0 | **1 399** (97 %) |
| Holdout: falscher Datentyp **ohne** „?“ | – ² | 48 |
| Holdout: exakte Funde mit „?“ | – ² | 25 011 (47 %) |

² Die Holdout-Messung von Phase 4 stammt aus einem Zwischenstand vor der Regel für flache Tabellen (§ 6c.5); ihre
„?“-Zählung ist nicht vergleichbar. Holdout-Funde der Phase 5 sind mit Phase 4 identisch (alle 105 Abbilder).

Die Reihenfolge selbst ist weiter nicht bestimmt; nur die Unsicherheit ist sichtbar. Die 48 falschen Typen ohne „?“
liegen alle auf MSV90-Vollflashs (Vorzeichen); sie wurden nicht einzeln untersucht, weil sie nur im Holdout auftreten.
Auf den Entwicklungsdaten trägt jeder falsche Datentyp ein „?“.

### 6d.5 Prüfhilfen für Tuner

- **Kennfeldliste:** Filter „Datentyp nicht belegt (?)“ und „Überschneidet andere Einträge“, neben den
  Belegstufen und „Noch nicht manuell geprüft“. Von dir geprüfte Einträge stehen fett mit ✓; automatische Vorschläge
  behalten Belegstufe und Status „ungeprüft“.
- **Detailansicht:** alle offenen Fragen zum Datentyp gleichzeitig; je Frage der fehlende Beleg (z. B. für das
  Vorzeichen: Programmcode, der die Werte vorzeichenbehaftet liest, oder eine Definition); dieselben Bytes in jeder
  offenen Lesart als Rohwerte (min … max), die gewählte markiert.
- **Prüfliste:** Filter nach Prüfgrund, Spalte „Fehlender Beleg“, Überschneidungen und Byte-Reihenfolge als Gründe.
  Die Reihenfolge ist eine Zählung von Gründen (Widerspruch 5, Definitionswarnung 4, Datentyp 3, Achsen 2, …), keine
  Wahrscheinlichkeit.
- **Unverändert:** Automatische Funde bleiben ungeprüft, bis der Nutzer sie bestätigt; Änderungen in ihnen ergeben vor
  dem Speichern einen gelben Befund.
- **Synthetische Tests:** `tests/test_review_aids.py` (8 Tests, u. a. Abschalten der neuen Regel).

### 6d.6 Registry- und GUI-Isolierung

- **Neuer Befund:** Die Updater-Tests starteten `updater.ps1` mit dem echten Schlüssel von „Apps & Features“ als
  Vorgabe. Geschützt war er nur durch den Vergleich des Installationsordners. Jetzt ignoriert der Updater im
  Testprofil den echten Schlüssel, auch wenn er ausdrücklich übergeben wird. Auf einem Rechner mit installierter
  1.20.1 hätte der alte Stand die Installer-Prüfung mit Exit 2 abgebrochen (nur gelesen, nichts geschrieben).
- **Aufräumen:** Die Einstellungsdatei jedes Tests wird nach dem Test gelöscht, auch nach einem Fehler. Laufordner
  abgebrochener Läufe (älter als 6 Stunden) entfernt der nächste Lauf.
- **Abbruch und Fehler (neue Tests):**
  - Ein verschachtelter Testlauf schreibt Einstellungen, schlägt fehl und wird abgebrochen. Danach sind Laufordner
    und Einstellungsdatei weg, die Einstellungen lagen nie in der Registry, und die Registry ist unverändert.
  - Ein nicht anlegbarer Einstellungsordner führt zu einem Fehler statt zu einem Rückfall auf die Registry, auch
    beim Fensterstart.
  - Ein statischer Test prüft, dass kein Test das installierte Programm startet.
- **Unverändert aus Phase 4:** zentrale Einstellungsverwaltung, INI-Testprofil, Prüfung vor jedem Test, nur lesender
  Registry-Wächter. Die gesicherte `.reg`-Datei wurde nicht importiert und nicht verändert.

### 6d.7 Laufzeit, Speicher und Regressionen

| Leistungssatz (15 Abbilder) | Laufzeit | Spitzenspeicher | exakte Funde |
|---|---:|---:|---:|
| Phase 4 (15.11., ohne Fremdlast) | 144,4 s | 431 MB | 7 494 |
| **Phase 5 (17.11., ohne Fremdlast)** | **149,6 s** | **431 MB** | 7 494 |
| 1.20.1 (18.11., mit Fremdlast) | 161,2 s | 431 MB | 5 049 |
| Phase 5 (18.11., mit Fremdlast) | 165,0 s | 431 MB | 7 494 |
| A/B abwechselnd am 18.11. (mit Fremdlast): Phase 4 / Phase 5 | 183,4 · 182,9 s / 162,0 · 189,2 s | – | gleich |

Am 18.11. lief ein anderes Programm des Nutzers dauerhaft mit (etwa ein halber Prozessorkern). Die Messungen dieses
Tages streuen deshalb um bis zu 17 % bei gleichem Code und sind nur untereinander vergleichbar. Im Mittel der
abwechselnden Läufe ist Phase 5 nicht langsamer als Phase 4 (175,6 s gegenüber 183,2 s). Phase 5 fügt der Suche nur
eine Schleife über die fertigen Funde hinzu; die Prüfhilfen rechnen erst in der Oberfläche. Die einzige Messung
ohne Fremdlast (149,6 s, 431 MB) hält die Ziele (höchstens 152,2 s und 431 MB) ein. Eine Wiederholung auf einem
unbelasteten Rechner vor dem Release steht aus.

- **Regressionssatz** (15 Fälle): unverändert gegenüber Phase 4 (MS42 22, MS43 197, MSD80, synthetische Fälle).
- **Negativbestand** (FOME, rusEFI, Speeduino): 549 Funde, 0 sicher falsch, unverändert.
- **Entwicklung und Holdout:** alle Abbilder fundgleich mit Phase 4 (§ 6d.4).

## 6e. Vorbereitung 1.21.0-rc1 (19.11.2026, als Pre-Release veröffentlicht)

### 6e.1 Die 48 falschen Vorzeichen ohne „?“ (MSV90-Vollflashs)

**Herkunft der Untersuchung:** Die 48 Fälle traten nur im Holdout auf (§ 6d.4). Sie wurden hier untersucht, weil eine
Vorabversion keine falsche Sicherheit zeigen darf. Es wurde **keine Schwelle** an ihnen abgestimmt; geprüft wurde nur,
welche vorhandene Regel die Sicherheit behauptet.

- **Befund:** Alle 48 sind TriCore-Tabellen an Interpolationsroutinen (Belegstufe „Code-Beleg“, u8 statt s8). Ihre
  Routinen lesen über den Tabellenzeiger Werte **unterschiedlicher Breite** (z. B. Anzahl- oder Kopffelder neben den
  Zellen). Bisher wurden Breite und Vorzeichen getrennt ausgewertet: Die Breite blieb offen, aber das gemeinsame
  „vorzeichenlos“ dieser Ladebefehle galt als Beleg für die Zellen. Ein privater Prüflauf (nur Zählwerte) zeigt: In
  allen Fällen, in denen die Ladebefehle auch die Breite festlegen, stimmt das Vorzeichen (Entwicklung und Holdout);
  falsch war es nur bei uneinheitlicher Breite.
- **Allgemeine Regel:** Ein Vorzeichen gilt nur noch als belegt, wenn **alle** Tabellen-Ladebefehle der Routine in
  Breite **und** Vorzeichen übereinstimmen. Sonst bleibt es offen („?“, beide Lesarten sichtbar, fehlender Beleg
  genannt). Keine Sonderbehandlung nach Steuergerät, Softwarestand, Dateiname oder Adresse.
- **Synthetische Tests:** `tests/test_tricore_refs.py` (gemischte Breiten mit gleichem Vorzeichen, mit beiden
  Vorzeichen, mehrheitlich eine Breite; Anzeige von „?“, Alternative und fehlendem Beleg).

| | Phase 5 | 1.21.0-rc1 |
|---|---:|---:|
| Entwicklung: exakt / Verwechslungen / Typ richtig / „?“ / falsch ohne „?“ | 32 058 / 5 316 / 30 712 / 13 318 / 0 | gleich |
| Holdout (nur Regression): exakt / Verwechslungen | 52 701 / 10 743 | gleich |
| Holdout MSV90: falscher Datentyp **ohne** „?“ | 48 | **0** |
| Holdout MSV90: mit „?“ markiert / Datentyp richtig | 4 375 / 11 047 | 4 423 / 11 063 |
| Holdout, andere Linien | – | unverändert |

Die 48 tragen jetzt ein „?“; 16 davon bekommen über die bestehende Lesart ohne Überlauf das richtige Vorzeichen.
Das Vorzeichen bleibt bei MSV90 damit **nicht** sicher bestimmt, nur die Unsicherheit ist sichtbar. Der Holdout
ist seit Runde 1 keine unabhängige Prüfung; eine neue unabhängige Testgruppe gibt es weiterhin nicht.

### 6e.2 Englische Oberfläche

Beim Durchgehen der Prüfhilfen in der englischen Oberfläche waren Teile deutsch geblieben: Spalten, Prüfgründe,
Priorität, Zähler und Zellen der Prüfliste (Tabellenzellen zeichnet Qt selbst, ohne übersetzten Setter), Teile der
Detailansicht (zusammengesetzte Zeilen), die Stufen des Preflight-Berichts und eingerückte Detailzeilen sowie
Markierungen der Kennfeldliste („Name übertragen (ungeprüft)“, „Vorschlag“, „[geändert]“). Behoben; ein GUI-Test
prüft die angezeigten Texte gegen deutsche Wörter (`tests/test_english_interface.py`). Funktional war nichts
betroffen.

### 6e.3 Release Candidate: Versionen, Kanäle, Workflow

- **Versionsschema:** `X.Y.Z-rcN`; Windows-Dateiversion `X.Y.Z.N` (stabil `.0`), eindeutig, aber nicht über
  stabil/RC geordnet; Versionsvergleiche nutzen nie die Dateiversion. Einzelheiten und die erst beim Release
  gesetzten Angaben: [RELEASE.md](RELEASE.md#release-candidates-ab-1210).
- **Update-Kanäle:** stabiler Kanal ohne Vorabversionen, auch bei falscher Markierung; Testkanal nur nach Rückfrage.
- **Workflow:** RC nur als Pre-Release, nie „Latest“; Entwurf → Prüfung → Veröffentlichung → Prüfung, Vergleich aller
  anderen Releases. Negativtests (`release_guard selftest`) laufen in jedem Build. `release_notes` lehnt einen Tag ab,
  dessen CHANGELOG-Überschrift oder Release-Notes-Kopf noch „geplant/nicht veröffentlicht“ enthält.
- **Probelauf** (`release-dry-run/1.21.0-rc1`, Commit mit den Release-Angaben nur auf diesem Zweig): build,
  update-test auf Windows Server 2022/2025 und `publish-plan` bestanden; Plan `--prerelease --latest=false`, Latest
  bleibt v1.20.1. Pakete: Dateinamen und Versionen `1.21.0-rc1`, Dateiversion `1.21.0.1`, SHA-256 der `.sha256`-Dateien
  stimmen, ZIP mit einem Wurzelordner, Inventar 1.21.0-rc1, keine Firmwaredateien. Nichts veröffentlicht.

### 6e.4 Installer-QA (GitHub-Runner, Windows Server 2022 und 2025)

Zweig `qa/1.21.0-rc1` (wird nie gemergt), 9 Modi × 2 Systeme, 1 020 Einzelprüfungen, **0 fehlgeschlagen**:
Neuinstallation, Update von v1.20.1, In-App-Update im eingeschalteten Testkanal (RC → RC), kein Angebot im stabilen
Kanal (auch bei falsch markiertem Release), Reparaturinstallation, Wiederherstellen der Vorversion, Rollback nach
simuliertem Fehler, vorhandene Sicherungs- und Staging-Ordner, gesperrte Dateien, unbekannte und geänderte
Nutzerdateien, Registry-Isolierung von Selbsttest und GUI-Smoke, Deinstallation nach Update und nach Reparatur.

Zwei vorherige Läufe schlugen fehl, beide wegen der QA-Werkzeuge, nicht wegen des Kandidaten:

1. Die QA-Testversion trug „nicht veröffentlicht“ in der Überschrift; die neue Release-Prüfung lehnte das ab (gewollt).
2. Im Modus Update veränderte der **Selbsttest der veröffentlichten 1.20.1** (vor der Installation des Kandidaten)
   das Fensterlayout in der Registry, der in § 6c.1 gefundene und in 1.21.0 behobene Fehler. Er wird jetzt als bekannte
   Einschränkung von 1.20.1 protokolliert; Selbsttest und GUI-Smoke des Kandidaten bleiben strikt geprüft (unverändert).

### 6e.5 Laufzeit und Speicher

Abwechselnd je 5 Läufe in eigenen Prozessen (Zeit), 2 Läufe mit Speichermessung; ein MSD80- und ein MSV90-Vollflash.
**Unter Fremdlast** (ein anderes Programm des Nutzers lief dauerhaft mit und wurde nicht angehalten): die Werte sind
untereinander vergleichbar, aber **kein Nachweis** für einen unbelasteten Rechner.

| Vollflash | 1.20.1 Median (Min–Max) | 1.21.0-rc1 Median (Min–Max) | Spitzenspeicher | exakte Funde |
|---|---:|---:|---:|---:|
| MSD80 (Entwicklung) | 12,72 s (12,47–13,48) | 13,65 s (13,09–13,95) | 87,3 → 87,5 MB | 315 → 620 |
| MSV90 (Holdout) | 12,66 s (12,45–12,99) | 13,61 s (13,51–14,06) | 86,3 → 86,3 MB | 146 → 526 |

Der Kandidat braucht etwa 7 % länger bei zwei- bis dreieinhalbmal so vielen exakten Funden; der Speicher ist gleich.
Ohne nachgewiesenen Engpass wurde an der Leistung nichts geändert.

### 6e.6 Weitere Prüfungen

- pytest lokal (Python 3.13) 1 254 bestanden, 22 übersprungen, 0 fehlgeschlagen; ebenso mit Version 1.21.0-rc1
  (Probelauf-Stand). CI: pytest 3.11/3.12 und CodeQL bestanden.
- GUI-Smoke 10/10 und `--self-check` im isolierten Profil; Registry vorher/nachher nur lesend verglichen: unverändert.
- Übersetzungen ohne Lücke; Firmware-Guard `tree`, `staged`, `push` ohne Befund; Modellsperre in pytest.
- Regressionssatz (15 Fälle) unverändert; Negativbestand 549 Funde, 0 sicher falsch; TT-DEMO-1 unverändert
  (1 exakt, 1 Verwechslung).

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
  1 046 (Runde 3: 1 118) exakte Funde haben die falsche Reihenfolge. Eine Änderung der Schwelle anhand des Holdouts wäre eine
  Anpassung an die Testdaten und unterbleibt; sie braucht neue Entwicklungsdaten. Seit Phase 5 tragen diese Funde
  „Byte-Reihenfolge nicht belegt“ („?“, § 6d.4).
- **Verwechslungen auf MEVD17.2.3-Vollflashs** liegen über 1.20.1 (§ 6.1, § 6a.3, § 6b.7: 3 042 → 3 744 → 3 297).
  Diagnose (§ 6d.3): vor allem 8-Bit-Datensatzlesarten und Datenmuster-Lesarten; auf den Entwicklungsdaten tritt das
  Muster nicht auf. Eine Abhilfe braucht Entwicklungsdaten derselben Linie.
- **Breitenregel** (§ 6a.2, § 6b): Die Fehler aus Runde 2 (18 falsche Byte-Lesarten, 31 verdrängte Kennfelder)
  sind weitgehend behoben; gegenüber „Breitenregel aus“ gehen auf 27 Kalibrierabbildern noch 16 exakte Kennfelder
  verloren. Bei schwachem Beleg bleibt die 16-Bit-Lesart mit offener Breite stehen, obwohl dort die 8-Bit-Lesart
  auf den Entwicklungsdaten öfter stimmt (101 : 20). Vorzeichen der neu gefundenen Datensatz-Tabellen sind oft nicht
  belegt und als ungeprüft markiert.
- **Kennfeldvorschläge** sind nie eine geprüfte Grundlage für Änderungen oder Flashfreigaben: Änderungen in ihnen
  ergeben in der Prüfung vor dem Speichern immer einen gelben Befund (§ 6b.5).
- **Unabhängige Bestätigung fehlt** für Runde 2, 3, Phase 4 und 5: keine neue Testgruppe realer Steuergeräte
  (§ 6a.7, § 6b.6, § 6c.4, § 6d.1).
- **Vorzeichen:** Bosch-Hüllroutinen springen in gemeinsame Kernroutinen; das Vorzeichen ist dort aus dem Code nicht
  ablesbar. Die Lesart ohne Überlauf irrt bei Kennfeldern mit wenigen Werten nahe 0/255 (Flags). Rest: 2 017
  Vorzeichenfehler unter 49 958 exakten Funden auf dem Holdout. Seit Phase 4 tragen solche Tabellen die andere
  Lesart als Alternative („?“); auf den Entwicklungsdaten ist jeder falsche Datentyp so gekennzeichnet (§ 6c.3).
- **Gemeinsame Achsen ohne eigenen Kopf** und Bosch-Festachsen (FIX_AXIS) sind im reinen Kalibrierabbild ohne Code
  nicht auffindbar; Kalibrierabbilder bleiben deutlich unter Vollflashs (Recall 0,25–0,46 gegenüber 0,63–0,89).
- **Präzision** ist nicht ausgewiesen: Funde außerhalb der A2L-Objekte sind nicht automatisch falsch.
- **Laufzeit:** insgesamt schneller als 1.20.1 (§ 6b.8, § 6c.6). MSD80-Vollflashs lagen in Runde 3 um 15 % darüber,
  bei der Messung von Phase 4 auf dem Stand von 1.20.1; die Streuung zwischen Messtagen beträgt bis 7 %.
- **Nicht wiederholbar:** die realen Paare früherer Berichte lagen nicht vor. Der Negativbestand offener Firmware
  wurde aus den offiziellen Quellen wiederhergestellt (§ 6b.4).
- Ghidra/REA nur extern; REA öffnet keine TriCore-ELF. Kein Modelltraining (§ 8).
- Die Ergebnisse gelten für BMW-Steuergeräte von Bosch und Siemens auf TriCore bzw. PowerPC (ME9). Andere
  Hersteller und Familien sind damit nicht gemessen.
