# Entwicklungsbericht 1.19.1 – Fehlfunde reduzieren, Prozessorarchitektur erkennen

Stand: 08.11.2026 (abschließende Prüfung von PR #16: § 11; letzte Korrekturen vor 1.19.1: § 12). Branch `feature/1.19.1-false-positive-reduction`, Ausgangspunkt `v1.19.0` (63ea112). Noch kein
Release, Versionsnummer unverändert. Firmware und Referenzdateien bleiben lokal; dieser Bericht enthält nur Zählwerte,
Offsets und Hashes.

## 1. Kurzfassung

- **Negativ-Benchmark** über sieben offene Firmwarestände ohne Abstimmungsdaten (FOME, rusEFI, Speeduino):
  1.19.0 erzeugte **1795 Funde**, davon **921 nachweislich falsch** (514 auf Text, 406 auf Zeigertabellen und der
  Vektortabelle, 1 Code-Beleg einer fremden Architektur). Nach den Änderungen: **875 Funde, 0 nachweislich
  falsch**. Die übrigen 874 bzw. 875 Funde sind „unklar“: Programm-Images enthalten auch echte Konstanten-Tabellen,
  die ohne Symbole nicht von Fehlfunden zu unterscheiden sind.
- **Falscher Code-Beleg auf ARM:** Die C16x-Referenzsuche lief ohne Architekturprüfung auf jedem Image. Derselbe Fehler
  erzeugte auf drei echten MED17-Dateien (TriCore) einen falschen C16x-Code-Beleg und verdrängte in einem synthetischen
  Fall einen richtigen Datensatz. Behoben durch eine Architekturerkennung, die jeden Code-Decoder nur auf seiner
  belegten Architektur zulässt.
- **Keine Regression:** Auf 15 realen Paaren bleiben exakte Kennfelder, Datentypen, Achsen und Achsadressen
  identisch; 14 synthetische Fälle: ein exakter Fund mehr, sonst gleich. Laufzeit 90,0 → 88,8 s, Speicher gleich.
- **Strukturbelege auf Programm-Images:** 294 → 36. Die übrigen 36 sind ohne zusätzliche Informationen nicht
  entscheidbar (§ 6).

## 2. Testdaten und Verfahren

### 2.1 Negativ-Bestand (lokal, nicht im Repository)

Offizielle Releases der Projekte (GPL), Herkunft und SHA-256 im mitgelieferten README des Bestands. Die Dateien sind
nur zur lokalen statischen Analyse verwendet worden; kein Training, keine Weitergabe.

| Firmware | Architektur | Größe | SHA-256 (Anfang) | Ladeadresse (Beleg) |
|---|---|---:|---|---|
| FOME 251103_01 | ARM Cortex-M4 | 675 608 | `dd3c5fddf33dbb23` | 0x08000000 (SREC desselben Builds ab BIN-Offset 0x8000, 0 abweichende Bytes) |
| FOME 260501_01 | ARM | 666 128 | `c38d6ca03d492e50` | 0x08000000 (wie oben) |
| FOME 260501_02 | ARM | 666 168 | `fa590a34009e734c` | 0x08000000 (wie oben) |
| rusEFI 2026-10-31 | ARM | 678 508 | `d705b76e52d9db38` | 0x08000000 (SREC ab 0x8000, 12 abweichende Kopfbytes) |
| rusEFI 2026-11-01 | ARM | 678 500 | `3eaac086987b106b` | 0x08000000 (wie oben) |
| Speeduino 202501.5 | AVR ATmega2560 | 225 398 | `b921647d391bbbdb` | 0x0 (Intel-HEX) |
| Speeduino 202501.6 | AVR | 225 516 | `90b982b801b195c6` | 0x0 (Intel-HEX) |

Hinweis zum README des Bestands: Die FOME- und rusEFI-BIN-Dateien beginnen bei 0x08000000 und enthalten den
32-KiB-Bootloader; erst die SREC-Update-Dateien beginnen bei 0x08008000. Die SHA-256 der Speeduino-Zeilen gelten für
das aus der HEX-Datei erzeugte Speicherabbild (Lücken 0xFF), nicht für die HEX-Datei selbst.

Die INI-Dateien des Bestands beschreiben TunerStudio-Seiten (z. B. Speeduino `veTable` Seite 1, Offset 0), keine
Flash-Adressen; die Abstimmung liegt in einem eigenen Flash-Sektor (rusEFI/FOME) bzw. im EEPROM (Speeduino) und ist
nicht Teil der Images. Die Images sind deshalb Negativ-Daten, aber kein vollständiger Negativ-Beweis (§ 2.3).

### 2.2 Werkzeug

`python -m ecu_studio.tools.negative_benchmark MANIFEST.json --out … [--markdown …] [--scanner-src SRC] [--pair A B]`
(Vorlage: `examples/templates/negative_manifest.template.json`).

- Je Image ein eigener Prozess: Scanzeit und Spitzen-Speicher (tracemalloc) sind getrennt gemessen.
- `--scanner-src` scannt mit einem anderen Quellstand (hier ein Worktree von `v1.19.0`), die Einordnung bleibt
  dieselbe. Dadurch sind Vorher- und Nachher-Werte mit identischen Regeln gezählt.
- `--pair` vergleicht zwei fast gleiche Builds (Versionsstabilität, § 7).
- Erfasst: Familie, Architektur erwartet/erkannt mit Begründung, Größe, SHA-256, Ladeadresse, Funde gesamt und je MiB,
  Code-/Struktur-/Datenmuster-Belege, Funde auf Text, auf Zeigertabellen, fremde Code-Belege, Scanzeit, Speicher.

### 2.3 Was als „sicher falsch“ gilt

Die Einordnung beruht nur auf den Bytes, nie auf dem geprüften Detektor:

| Klasse | Regel |
|---|---|
| Text | ≥ 90 % des Fundes liegt in Läufen von mindestens zwei NUL-terminierten Zeichenketten (≥ 4 druckbare Zeichen, Buchstaben, keine Zahlenrampe; NUL-Auffüllung bis 16 Byte) |
| Zeiger | ≥ 90 % liegt in ausgerichteten Tabellen von ≥ 4 Little-Endian-Adressen in das eigene Flash-, SRAM- oder CCM-Fenster (≥ 75 % adressartig, ≤ 25 % NULL, ≥ 3 verschiedene Ziele) oder in der Cortex-M-Vektortabelle; oder ein Datensatzkopf, dessen Achsen sämtlich auf Adresswörtern liegen |
| fremder Code-Beleg | Code-Beleg auf einem Image, dessen Architektur keinen Code-Decoder in ECU Studio hat (ARM, AVR) |

Alles andere ist **unklar**. Eine Präzision wird nicht berechnet: Es gibt keine vollständige Referenz der
Konstanten-Tabellen in diesen Images.

## 3. Ausgangswerte 1.19.0

| Firmware | Funde | je MiB | Code | Struktur | Datenmuster | Text | Zeiger | fremder Code | sicher falsch | unklar | s | MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FOME 251103_01 | 330 | 512 | 0 | 38 | 292 | 148 | 81 | 0 | 229 | 101 | 18,2 | 29,0 |
| FOME 260501_01 | 349 | 549 | 0 | 59 | 290 | 154 | 93 | 0 | 247 | 102 | 17,9 | 28,7 |
| FOME 260501_02 | 350 | 551 | 0 | 58 | 292 | 153 | 91 | 0 | 244 | 106 | 17,2 | 28,7 |
| rusEFI 2026-10-31 | 320 | 495 | 0 | 33 | 287 | 29 | 40 | 0 | 69 | 251 | 25,2 | 67,5 |
| rusEFI 2026-11-01 | 390 | 603 | 1 | 94 | 295 | 29 | 101 | 1 | 131 | 259 | 25,0 | 54,3 |
| Speeduino 202501.5 | 27 | 126 | 0 | 6 | 21 | 1 | 0 | 0 | 1 | 26 | 3,7 | 10,2 |
| Speeduino 202501.6 | 29 | 135 | 0 | 6 | 23 | 0 | 0 | 0 | 0 | 29 | 3,9 | 10,2 |
| **Summe** | **1795** | | **1** | **294** | **1500** | **514** | **406** | **1** | **921** | **874** | | |

Nach Belegstufe: Von 294 Strukturbelegen waren 258 nachweislich Zeigerstrukturen, von 1500 Datenmuster-Vermutungen
662 Text oder Zeiger.

Zur Ausgangsmeldung („rund 150 ASCII-Funde im rusEFI-Image“): Die rund 150 Text-Funde liegen in den FOME-Images
(148–154); im rusEFI-Image sind es 29, dazu der eine Code-Beleg.

## 4. Technische Ursachen

### 4.1 Code-Beleg auf ARM (rusEFI 2026-11-01, 0xA5218)

- `scan_structures` rief `c16x_reference_positions()` für **jedes** Image auf. Die Funktion liest jedes Bytemuster
  `E6 Fx ?? ??` als C16x-Befehl `MOV Rw,#imm16` und zwei benachbarte als Seite + Offset.
- Im Thumb-Code von rusEFI ergaben zwei solche Zufallsmuster die Adresse 0xA5218: mitten in der Zeichenkettenliste
  „Injector Second Stage 4 … 12“. Daraus wurde ein 8 × 12-u16-„Kennfeld“ mit Klasse `candidate:code-reference`, also
  Stufe Code-Beleg („Startadresse im Programmcode referenziert (Seite+Offset-Ladebefehle)“).
- Die TriCore-Aufrufanalyse hatte bereits eine Vorprüfung (`looks_like_tricore`), die C16x-Suche, die ME7-Aufrufsuche,
  die HC11/8051/68k-Suche und die SH-2-Zeigerdeskriptoren nicht.
- **Auch auf echten Dateien:** MED17.1.62 404A/404E/404G (TriCore-Kalibrierbereich) hatten in 1.19.0 je einen
  C16x-Code-Beleg bei 0x12600 (13 × 10 u16 auf Bytes `01 01 01 …`); im synthetischen Fall „aligned-padded“ verdrängte
  ein solcher Zufalls-Beleg den richtigen Datensatz bei 0x88E.

### 4.2 Text

Die Zeilenabstands-Suche (Datenmuster) bewertet Wiederholung: Zeichenkettenlisten fester Breite
(`"TLE8888.INJ1\0\0\0\0TLE8888.INJ2…"`, 16 Byte je Eintrag) wiederholen sich exakt im Abstand der Eintragsbreite und
sehen für sie wie Tabellenzeilen aus (FOME 0x80070: 28 × 16 u8).

### 4.3 Zeigertabellen und Vektortabelle

- Sortierte Zeigertabellen (`0x08070984, 0x08070990, …`) sind als Bytes gelesen glatt und steigend; die Suche fand
  sie auch an ungeraden Offsets (FOME 0x712BD, 106 × 4 s8).
- Die Cortex-M-Vektortabelle der FOME-Images enthält in den reservierten Einträgen 7 und 8 Prüfsumme und Länge des
  Images; ein Zählachsen-Fund lag bei 0x1A darin.

### 4.4 Strukturbelege aus Zeigerobjekten (rusEFI)

- 258 der 294 Strukturbelege waren Zeigerstrukturen, vor allem in rusEFI: Tabellenobjekte (Map3D) der Form
  `[CCM-Zeiger 0x1000xxxx] [04 00 04 00] [Zeiger] [Zeiger] [Zeiger] [0 …]`.
- Die Datensatzkopf-Erkennung liest `04 00 04 00` als „4 × 4“ und die folgenden Zeiger als u8-Achsen: 0x080A1011 ist
  als Bytes `11 10 0A 08` eine fallende Achse [17, 16, 10, 8]. Little-Endian-Adressen 0x080Axxxx ergeben immer eine
  solche fallende Folge.
- Die echten rusEFI-Tabellen liegen im RAM (Abstimmung); diese Bytes sind nur ihre Beschreibung.
- Strukturbelege umgingen bei unbekanntem Kalibrierbereich bewusst die Datenblock-Prüfung (unabhängiger Beleg). Die
  Belegstufe war damit für Zeigerstrukturen nicht gerechtfertigt: Die „Struktur“ war ein Zufall der Adressbytes.

## 5. Umgesetzte Änderungen

| Änderung | Datei | Wirkung |
|---|---|---|
| Architekturerkennung TriCore / C16x / ARM / AVR / unbekannt aus zwei unabhängigen Merkmalen | `core/architecture.py` | Grundlage für alle Code-Decoder |
| C16x-Referenzen und ME7-Aufrufe nur auf C16x, TriCore-Aufrufe nur auf TriCore, HC11/8051/68k und SH-2-Deskriptoren nur bei unbekannter Architektur | `core/scoped_scan.py`, `core/structure_scan.py` | keine Code-Belege auf fremder Architektur |
| Text- und Zeigertabellen-Erkennung, Vektortabelle, Adresswörter | `core/region_classes.py` | Grundlage der Filter |
| Filter im Scan: Funde zu ≥ 90 % auf Text oder Zeigertabellen; Datensatzköpfe/Achsen, deren Achsen Adresswörter sind (nur ARM) | `core/scoped_scan.py` | unterdrückte Funde je Grund in `diagnostics['suppressed']` |
| Negativ-Benchmark | `tools/negative_benchmark.py` | reproduzierbare Messung, Vorher/Nachher mit gleichen Regeln |

### 5.1 Architekturerkennung

| Architektur | Merkmal 1 | Merkmal 2 |
|---|---|---|
| ARM Cortex-M | Vektortabelle: Stack-Zeiger im SRAM/CCM, ≥ 8 von 15 Handlern ungerade (Thumb) nahe dem Reset-Vektor | Thumb-Dichte: `bx lr` ≥ 40 und `push {…, lr}` ≥ 60 je 64 KiB |
| AVR | ≥ 16 Interrupt-Sprungvektoren (`jmp`/`rjmp`) ab Adresse 0 | `ret` ≥ 50 je 64 KiB |
| C16x | ≥ 16 von 128 Trap-Vektorplätzen ab Adresse 0 mit `jmps seg,addr` (gerade Zieladresse) | C16x-Code-Dichte: `rets` ≥ 40 und `mov Rw,#imm16` ≥ 150 je 64 KiB |
| TriCore | `ret` (16 Bit) ≥ 32 je 64 KiB | `movh.a` ≥ 300 je 64 KiB (unverändert aus 1.19.0) |

Trifft keine oder mehr als eine Architektur zu, gilt **unbekannt** (bei Widerspruch mit Nennung der Familien). Ein
einzelnes Merkmal genügt nie. Gemessene Werte (je 64 KiB):

| Datei | Ergebnis | Merkmale |
|---|---|---|
| MSD80 I8A0S | TriCore | ret 261, movh.a 620 |
| MS43 430069, MS42 0110C6, ME7.5 8E0909518AK | C16x | Trap-Vektoren 128 / 127 / 120, rets 151–235, mov 571–964 |
| FOME ×3, rusEFI ×2 | ARM | Vektortabelle gültig, bx lr 118–222, push 140–169 |
| Speeduino ×2 | AVR | Sprungvektoren ab 0, ret 218 |
| ME9, ME9.2.1, MS45, MED17 ×6, MED9, ME7.5 06A906018CG | unbekannt | Kalibrierbereiche ohne Programmcode bzw. ohne zwei Merkmale (höchstens rets 2, mov 9, bx lr 1) |

Die Kalibrierbereiche ohne Code verlieren damit nur Code-Belege, die dort nie begründet waren (3 MED17-Fälle, § 4.1).

Die C16x-Regel wurde in der abschließenden Prüfung geändert (§ 11.2): Bis 59f355d genügten ≥ 20 ME7-Aufrufsequenzen
(`mov R12..R15`) allein. Alle anderen 19 Dateien haben 0 Trap-Vektorplätze mit `jmps`.

### 5.2 Schutz echter Kennfelder

- Text: Kalibrierwerte sind oft druckbar (0x20–0x7E), haben aber keine NUL-Terminierung zwischen „Wörtern“ und
  verlaufen als Rampen; beides schließt die Regel aus. Eine einzelne Zeichenkette in einer Tabelle macht die Tabelle
  nicht zu Text (90 %-Abdeckung).
- Zeiger: nur bei belegter ARM-Architektur und bekanntem Fenster. u16-Tabellen um 2048 (Q11-Faktor 1,0 = 0x0800 →
  Wort 0x0800_0800) und u8-Tabellen kleiner Werte gelten nicht als Zeigertabellen. Steigende u8-Achsen ergeben nie
  Adresswörter (z. B. [8, 10, 16, 17] → 0x11100A08); die Achsenregel betrifft nur Datensätze, deren Achsen **alle** auf
  Adresswörtern liegen, eine Einzelachse nur mit einem weiteren Adresswort daneben.
- Nicht angewendet auf TriCore, C16x und unbekannte Images: Dort ist kein Zeigerformat belegt.

## 6. Ergebnisse je Firmware (nach den Änderungen)

| Firmware | Funde | je MiB | Struktur | Datenmuster | Text | Zeiger | fremder Code | sicher falsch | unklar | s | MB |
|---|---|---:|---|---|---|---|---|---|---|---|---|
| FOME 251103_01 | 330 → 101 | 157 | 38 → 6 | 292 → 95 | 148 → 0 | 81 → 0 | 0 | 229 → 0 | 101 | 18,2 → 17,4 | 29,0 |
| FOME 260501_01 | 349 → 102 | 161 | 59 → 6 | 290 → 96 | 154 → 0 | 93 → 0 | 0 | 247 → 0 | 102 | 17,9 → 17,7 | 28,7 |
| FOME 260501_02 | 350 → 106 | 167 | 58 → 6 | 292 → 100 | 153 → 0 | 91 → 0 | 0 | 244 → 0 | 106 | 17,2 → 17,4 | 28,7 |
| rusEFI 2026-10-31 | 320 → 251 | 388 | 33 → 3 | 287 → 248 | 29 → 0 | 40 → 0 | 0 | 69 → 0 | 251 | 25,2 → 25,6 | 67,5 |
| rusEFI 2026-11-01 | 390 → 260 | 402 | 94 → 3 | 295 → 257 | 29 → 0 | 101 → 0 | 1 → 0 | 131 → 0 | 259 → 260 | 25,0 → 25,8 | 54,3 |
| Speeduino 202501.5 | 27 → 26 | 121 | 6 | 21 → 20 | 1 → 0 | 0 | 0 | 1 → 0 | 26 | 3,7 → 3,5 | 10,2 |
| Speeduino 202501.6 | 29 | 135 | 6 | 23 | 0 | 0 | 0 | 0 | 29 | 3,9 → 3,5 | 10,2 |
| **Summe** | **1795 → 875** | | **294 → 36** | **1500 → 839** | **514 → 0** | **406 → 0** | **1 → 0** | **921 → 0** | **874 → 875** | | |

Code-Belege: 1 → 0. rusEFI 2026-11-01 „unklar“ 259 → 260: An der Stelle des entfernten Code-Belegs bleibt eine
Datenmuster-Vermutung (nicht als Text belegt, weil die Zeichenkettenliste den Fund nicht zu 90 % abdeckt).

**Verbleibende 36 Strukturbelege (unklar):**

- FOME (je 6): ein Datensatz 8 × 7 u8 mit glatten Werten 0x05–0x14 (wahrscheinlich eine echte Konstanten-Tabelle;
  die als Achsen gelesenen u16-Werte sind aber vermutlich falsch gelesen) und ein Datensatz 5 × 4 mit Achse
  [6, 8, 11, 12], je mit ihren Achsen-Funden.
- rusEFI (je 3): ein Datensatz 4 × 4 s16 und zwei Achsen-Funde in Literal-Pools / Thumb-Code (`70 b5` = `push`).
  Thumb-Code lässt sich byteweise nicht eindeutig beweisen; nicht unterdrückt.
- Speeduino (je 6): Bitmasken-Tabellen (Achsen 1, 2, 4, … 128) und eine steigende Achse; als Lookup-Tabellen
  im PROGMEM plausibel, ohne Symbole nicht entscheidbar.

**Verbleibende 839 Datenmuster-Vermutungen (unklar):** größtenteils Code-Bereiche und Konstanten (rusEFI rund 250 je
Image). Sie sind als Vermutung gekennzeichnet. Ein belastbarer Code-Filter für ARM-Thumb (Disassemblierung) wäre der
nächste Schritt (§ 10).

## 7. Versionsstabilität FOME 260501_01 → 260501_02

| | 1.19.0 | neu |
|---|---:|---:|
| gleiche Bytes, gleiche Form, gleicher Typ, gleiche Stufe (stabil) | 245 | 74 |
| Bytes verändert (Code-Änderung zwischen den Builds) | 90 | 20 |
| Bytes gleich, aber nicht wiedergefunden | 14 (6 davon sicher falsch) | 8 (0 sicher falsch) |
| nur in _02 | 107 | 34 |

- Alle 6 Strukturbelege sind stabil, jeweils um 0x28 verschoben.
- Die 8 nicht wiedergefundenen Funde sind ausschließlich Datenmuster-Vermutungen; drei davon erscheinen in _02 als
  größerer zusammengefasster Fund an derselben Stelle (z. B. 0x6E780 14 × 16 → 0x6E770 20 × 16), die übrigen fallen
  aus der Rangliste der Zeilenabstands-Suche (Budget). Das ist erklärt, aber ein Zeichen, dass Datenmuster-Funde
  vom Umfeld abhängen.
- Stabilität ist ein Hinweis, kein Beweis für ein echtes Kennfeld.

## 8. Regressionsprüfung gegen 1.19.0

Gleicher Rechner, nacheinander, `benchmark_suite --memory`. Die Ausgangsmessung mit unverändertem 1.19.0 stimmt in
allen Erkennungsfeldern mit der Release-Messung überein (0 Unterschiede auf 29 Zeilen).

| Bereich | Ergebnis |
|---|---|
| 15 reale Paare, exakte 2D | **unverändert auf allen 15** (MSD80 84, MS43 197, MS42 22, ME9 98, ME9.2.1 170, MS45 30, MED17 134/136/133/145/128/121, MED9 11, ME7.5 0/43) |
| Datentypen, Achsen, Achsadressen, exakte 1D, Gruppenpaare, Präzision | unverändert |
| gefundene 2D | MED17 404A/404E/404G je −1 (der falsche C16x-Code-Beleg bei 0x12600), sonst gleich |
| 14 synthetische Fälle | „aligned-padded“: exakt 2 → 3, Typ 2 → 3, Achsen 2 → 3, 1D 4 → 6 (Datensatz bei 0x88E nicht mehr verdrängt); übrige 13 gleich, Negativkontrollen ohne Fehlfund |
| Laufzeit (15 Paare) | 90,0 → 88,8 s (je Paar −0,8 … +1,0 s, Messrauschen) |
| Spitzen-Speicher | 86,9 → 86,9 MB, je Paar gleich (±0,4 MB) |
| Negativ-Benchmark Laufzeit | je Image −0,4 … +0,8 s |

Die bekannte MSD80-Regression aus 1.19.0 (0x4FB18, 0x5604C) ist von dieser Änderung nicht betroffen und bleibt
offen (Aufgabe 1).

## 9. Tests

Neu (synthetische Images, keine Firmwarebytes):

- `tests/test_architecture_false_finds.py` (20 Tests): jede Architektur mit zwei Merkmalen; ein Merkmal allein
  reicht nicht; Zufall, Kalibrierdaten, leere und winzige Images unbekannt; widersprüchliche Merkmale → unbekannt mit
  Begründung; abgeschnittene/beschädigte Images (Vektortabelle abgeschnitten, gelöschter Stack-Zeiger, ungerade
  Länge); C16x-Befehle in ARM-, AVR- und unbekanntem Code ohne Code-Beleg; C16x-Code-Belege auf C16x erhalten;
  Text fester und gepackter Breite; druckbare Kalibrierwerte und Rampen sind kein Text; einzelne Zeichenkette in einer
  Tabelle; ARM-Zeigertabelle (auch an ungeradem Offset); keine Zeigertabellen ohne Zeigerformat; Q11-, u8- und
  u32-Tabellen mit zeigerähnlichen Werten bleiben; Vektortabelle mit reservierten Einträgen; Datensatz mit
  Zeigerachsen gegen echte Achsen; echte Tabelle zwischen Text und Zeigern bleibt erhalten.
- `tests/test_negative_benchmark.py` (3 Tests): Einordnung, Versionsvergleich, Ladeadresse aus SREC (mit
  abweichenden Kopfbytes und fremdem Build).
- `tests/test_axis_arrays.py`: Der Test der Scan-Achsen nutzt jetzt ein Image mit C16x-Code-Dichte, weil der Scan
  C16x-Decoder nur noch auf belegtem C16x anwendet; die Prüfungen sind unverändert, zusätzlich wird die Erkennung als
  C16x geprüft.

Ergebnisse (05.11.2026, Windows, Python 3.13):

| Prüfung | Ergebnis |
|---|---|
| pytest vollständig | 886 bestanden, 10 übersprungen (1.19.0: 863/10; keine Tests deaktiviert oder abgeschwächt); nach § 11: 897/10 |
| Übersetzungsprüfung (`i18n_extract --check`) | 2061 Texte, 0 ohne Übersetzung; nach § 11: 2060/0 |
| Firmware-Guard (`firmware_guard.py staged`) | sauber |
| GUI-Smoke (`tools.gui_smoke`, mit lokaler MS43-Datei) | 10/10 Prüfungen, MS43 856 Kennfelder (wie 1.19.0) |
| Bestehende Kennfeld-Benchmarks | § 8 |
| Negativ-Benchmark | § 3, § 6, § 7 |
| Laufzeit und Speicher | § 8 |

## 10. Offene Einschränkungen

- **Unklare Funde bleiben:** 875 Funde auf Programm-Images sind weder als richtig noch als falsch belegt. Ohne
  Symbole (ELF/Map) lassen sich Konstanten-Tabellen nicht von Code und Daten unterscheiden. Nächster Schritt:
  Speeduino oder rusEFI aus dem Quellcode bauen, Konstanten-Tabellen aus der Map-Datei als Referenz (Toolchain nötig).
- **Kein Thumb-/AVR-Code-Filter:** Datenmuster-Funde in Programmcode werden nicht unterdrückt; dafür wäre eine
  Disassemblierung mit Kontrollfluss nötig. Nicht als Regel ohne Beleg eingeführt.
- **Zeigerfilter nur für ARM.** TriCore- und C16x-Zeigertabellen werden nicht gefiltert (Fenster und Format dort nicht
  belegt; auf den realen Paaren auch nicht gemessen).
- **Architekturerkennung:** gemessen auf 22 lokalen Dateien. Weitere Familien (PowerPC/MPC5xx, SH-2, V850, HC12,
  68k) werden als „unbekannt“ geführt; für 68k/HC11/8051 bleibt die bestehende Anreicherungsprüfung (`cpu_refs`).
- **Anzeige:** Die Zahl unterdrückter Funde steht in den Scan-Diagnosedaten, nicht in der Oberfläche.
- **Negativ-Bestand ≠ unabhängige Validierung:** Die Regeln wurden an diesen sieben Images entwickelt; die Zahlen
  „sicher falsch“ messen nur die Klassen, die die Regeln selbst definieren. Keine Präzisions- oder Recall-Angabe.
- Keine Lernmodelle verändert oder trainiert; keine Firmware im Repository.

## 11. Abschließende Prüfung von PR #16 (07.11.2026)

### 11.1 Zwischenspeicher mit ganzen Firmwaredateien

**Ursache.** Drei modulweite `lru_cache` verwendeten die vollständigen Firmwarebytes als Schlüssel und hielten sie
dadurch über das Ende eines Scans und das Schließen eines Projekts hinaus:

| Cache | seit | höchstens gehalten |
|---|---|---|
| `architecture._detect` | 59f355d (PR #16) | 8 Images |
| `structure_scan._c16x_base` (C16x-Ladeadresse) | 1.19.0 (bc0e7fd) | 8 Images |
| `structure_benchmark._a2l_cached` (A2L-Referenz, auch Namensübertragung und Versionsvergleich) | 8e063c0 | 4 Images |

**Aufrufhäufigkeit (gemessen).** `detect_architecture` läuft genau einmal je Scan (3–17 ms, 2 MiB MSD80); der
Cache brachte innerhalb eines Scans nichts. Die C16x-Ladeadresse wurde auf C16x-Images dreimal je Scan angefragt
(einmal berechnet, ≤ 3 ms).

**Korrektur.** Kein Cache mehr für Architektur und Ladeadresse: `scoped_scan` berechnet beide einmal und gibt die
Ladeadresse an `lookup_descriptors` und `scan_structures(base=…)` weiter. Die A2L-Referenz wird weiter
zwischengespeichert (höchstens 4 Einträge, mit Sperre für Worker-Threads), aber unter Pfad, SHA-256 und Anker; der
Speicher hält nur die verknüpften Kennfelder, nie die Firmware. Entscheidungen und Ergebnisse sind unverändert.

**Speicher über wiederholte Scans** (ein Prozess, 10 verschiedene reale Dateien nacheinander, danach fünfmal MS42,
jedes Mal neu geöffnet und Ergebnisse verworfen; Python-Heap nach dem Scan gegenüber dem Start, `tracemalloc`):

| Stand | nach 10 Dateien | nach 5 weiteren Scans | Verlauf |
|---|---|---|---|
| 59f355d | +5,08 MB | +4,59 MB | wächst mit jeder neuen Datei (Cache-Schlüssel) |
| neu | +0,03 MB | +0,03 MB | konstant |

Die Prozessgröße (RSS) schwankt in beiden Ständen um 20–50 MB durch den Speicherverwalter und ist kein Maß für
gehaltene Daten.

### 11.2 C16x-Regel

**Befund.** Bis 59f355d genügten ≥ 20 ME7-Aufrufsequenzen allein. Eine Aufrufsequenz besteht aus vier
`mov Rw,#imm16` und ist damit derselbe Befehl wie das Dichtemerkmal, kein zweites unabhängiges Merkmal.

**Neue Regel.** Wie bei ARM und AVR: Strukturmerkmal **und** Befehlsdichte. Strukturmerkmal ist die Trap-/Interrupt-
Vektortabelle ab Adresse 0: ≥ 16 der 128 Vier-Byte-Plätze 0x000–0x1FF mit `jmps seg,addr` (0xFA) auf eine gerade
Adresse. Gemessen: MS43 128, MS42 127, ME7.5 8E0909518AK 120, alle anderen 19 Dateien 0. Die Aufrufsequenzen
stehen nur noch in den Messwerten (`signs`), nicht mehr in der Begründung.

**Architekturzuordnung** auf allen 22 lokalen Dateien unverändert (MS42, MS43, ME7.5 8E0 C16x; MSD80 TriCore;
FOME/rusEFI ARM; Speeduino AVR; übrige unbekannt). Grenze: Ein C16x-Image ohne die ersten 512 Bytes (z. B. nur der
Programmteil) gilt jetzt als unbekannt; dann laufen keine C16x-Decoder.

### 11.3 Generik-Decoder (HC11, 8051, 68k) und SH-2-Deskriptoren

Nur Diagnose, keine Regeländerung (keine Referenzimages dieser Familien vorhanden). Ausgeführt auf 22 realen Dateien,
14 synthetischen Fällen und Zufallsdaten (128 KiB, 512 KiB):

- Keine Ausgabe auf allen Images mit erkannter Architektur, auf Zufallsdaten und auf allen synthetischen Fällen.
- **Einziger Befund:** ME7.5 06A906018CG (256 KiB, kein Programmcode) wird von `cpu_refs.detect_cpu` als HC11
  (Basis 0x8000) mit 305 Adresszielen erkannt, 0 davon exakte Referenzstarts. Im Scan entsteht daraus ein
  unbegründeter Code-Beleg bei `0x5C6` (4 × 4). Unverändert seit 1.19.0; offen als Aufgabe 11.
- Neuer Test: SH-2-Deskriptoren und Generik-Decoder liefern auf ARM, AVR, C16x und TriCore keine Funde, auf
  unbekannten Images weiterhin.

### 11.4 Regression und Laufzeit

| Vergleich | Ergebnis |
|---|---|
| 15 reale Paare gegen 59f355d | 0 Unterschiede in allen Erkennungsfeldern (exakt 2D/1D, Typen, Achsen, Achsadressen, Gruppenpaare, Funde) |
| 15 reale Paare gegen 1.19.0 | wie § 8: nur MED17 404A/E/G gefunden 2D je −1 (falscher C16x-Code-Beleg); kein exakter Fund verloren |
| 14 synthetische Fälle gegen 59f355d | 0 Unterschiede; gegen 1.19.0 wie § 8 (aligned-padded exakt 2 → 3), Negativkontrollen unverändert |
| Negativ-Benchmark | 875 Funde, 0 nachweislich falsch, 875 unklar (36 Strukturbelege, 839 Datenmuster), je Image wie 59f355d; Stabilität FOME 74 / 20 / 8 / 34 wie 59f355d |
| Laufzeit 15 Paare | direkt nacheinander gemessen: 59f355d 92,7 s, neu 89,4 s; einzelne Läufe streuten je nach Rechnerlast 88,8–95,0 s; Wechselmessung je Datei ohne Unterschied |
| Spitzen-Speicher | 86,9 MB (unverändert) |
| Negativ-Benchmark Laufzeit | 111,8 s (59f355d 110,8 s), Spitze 67,5 MB |

Die 875 unklaren Funde sind keine bestätigten Kennfelder.

### 11.5 Tests

- `tests/test_firmware_cache.py` (neu, 6 Tests): 10 verschiedene Images nacheinander halten nichts fest (Architektur,
  Ladeadresse, vollständiger Scan); wiederholter Scan und erneut geöffnetes Projekt liefern identische Ergebnisse
  ohne Wachstum; Architektur und Ladeadresse werden je Scan einmal berechnet; der A2L-Speicher hält keine Firmware.
- `tests/test_architecture_false_finds.py` (+5 Tests): C16x mit Vektortabelle und Code-Dichte, jedes Merkmal allein
  unbekannt; Aufrufsequenzen allein (Zufall, leer) unbekannt und ohne Code-Beleg; zufällige C16x-Sequenzen in ARM-,
  AVR- und TriCore-Code ändern deren Zuordnung nicht; reine Kalibrierdaten, abgeschnittene Vektortabelle, gelöschter
  Bootsektor und zu kurze Images unbekannt; Generik- und SH-2-Decoder nur ohne erkannte Architektur.
- Angepasste Testbilder (Prüfungen unverändert): Die synthetischen C16x-Images in `test_architecture_false_finds.py`
  und `test_axis_arrays.py` haben jetzt eine `jmps`-Vektortabelle; der Widerspruchsfall ARM + C16x enthält die
  Vektortabelle ab Platz 16.
- Gegen 59f355d schlagen fehl: alle Speichertests (2,1–4,3 MB gehalten) und die vier C16x-Regeltests. Nicht
  fehlschlagend gegen 59f355d, weil Schutz gegen künftige Fehler: einmalige Berechnung je Scan, wiederholter Scan
  derselben Datei, Generik-/SH-2-Gate.

| Prüfung | Ergebnis |
|---|---|
| pytest vollständig | 897 bestanden, 10 übersprungen, 0 fehlgeschlagen |
| Übersetzungsprüfung | 2060 Texte, 0 ohne Übersetzung (nicht mehr benutzter Text „Kennfeld-Aufrufsequenzen“ entfernt) |
| GUI-Smoke | 10/10, MS43 856 Kennfelder |
| Firmware-Guard (`firmware_guard.py staged`) | sauber |

## 12. Letzte Korrekturen vor 1.19.1 (07./08.11.2026)

Branch `feature/1.19.1-final-fixes` ab `main` (eb30c81, Stand nach PR #16). Versionsnummer unverändert. Verglichen
wird mit eb30c81 (direkt nacheinander auf demselben Rechner gemessen) und mit 1.19.0.

### 12.1 A2L-Zwischenspeicher

**Ursache.** Der Schlüssel der A2L-Referenz war (Pfad, SHA-256 der Firmware, Anker). Eine unter demselben Pfad
geänderte A2L – auch bei gleicher Größe – lieferte die zuvor verknüpften Kennfelder, bis der Eintrag aus dem Speicher
fiel (4 Einträge) oder das Programm neu startete. Betroffen: Namensübertragung, Versionsvergleich, Benchmarks.
Außerdem bekamen alle Aufrufer dieselben `MapDefinition`-Objekte; eine Änderung durch einen Aufrufer (Umbenennen,
Übernehmen) hätte die nächste Antwort verändert.

**Korrektur.** Die A2L wird einmal gelesen; Schlüssel ist (SHA-256 der A2L-Bytes, SHA-256 der Firmware, Anker), und
dieselben Bytes werden verknüpft. Jeder Aufrufer erhält eine tiefe Kopie. Sperre, Größe (4) und „keine Firmware im
Speicher“ bleiben. `core.a2l.read_a2l` ist in `read_a2l_bytes` und `decode_a2l` geteilt (Verhalten gleich).

**Tests** (`tests/test_a2l_reference_cache.py`, 7 Tests, synthetische A2L und Images): zwei A2Ls zur selben
Firmware; derselbe Pfad mit geändertem Inhalt und mit gleicher Größe (auch verschobene Adresse); Kopien je Aufrufer;
Namensübertragung und Versionsvergleich nach Änderung der Definition; wiederholtes Öffnen verknüpft nur einmal;
8 Threads, 48 Aufrufe mit zwei Definitionen und drei Images; Projektwechsel halten keinen Block ≥ 256 KiB und weniger als 1 MiB.
Gegen eb30c81 schlagen 3 fehl (geänderter Inhalt, Kopien, Namensübertragung/Versionsvergleich); die übrigen 4 sichern
bestehendes Verhalten ab.

### 12.2 MSD80: 0x4FB18 und 0x5604C

**Vorgehen.** Kandidaten je Stufe in 1.18.2, 1.19.0 und eb30c81 protokolliert (TriCore-Aufrufe, Strukturfunde,
Eingang/Ausgang der Rangfolge, Endergebnis). In 1.18.2 kommen beide Tabellen aus TriCore-Interpolationsaufrufen
(nicht aus Datenmustern, wie Aufgabe 1 ursprünglich annahm). In 1.19.0/eb30c81 fehlen sie schon in
`call_descriptors`; Strukturfunde, Rangfolge und Zusammenführung verwerfen nichts. An ihrer Stelle füllen
Zeilenabstands-Funde (0x4FADE, 0x4FB26) die Lücke.

**Ursache.** `tricore_refs._walk` hält je Adresse höchstens 8 verschiedene Registerzustände (älteste zuerst). Seit
1.19.0 werden bedingte Vorwärtssprünge verfolgt; jeder Sprung zu einem Zusammenführungspunkt bringt eine eigene
Kopie mit. An den Aufrufstellen 0x12A786 (Tabellen 0x4FB18/0x4FB6C) und 0xBB618 (0x55FEC/0x5604C) kommen mehr als
8 Zustände an; der Zustand mit der zweiten Tabellenadresse in `a4` traf zuletzt ein und wurde abgeschnitten.

**Korrektur.** `MAX_STATES` 8 → 32. Gemessen auf MSD80 I8A0S (exakte 2D): 8 → 84, 16 → 85, 32 → 86 (beide Tabellen),
64 → 86. Keine Adressen, keine Sonderregel für I8A0S. Der Test
`test_states_from_many_branches_keep_every_table_of_a_call_site` baut 12 Aufrufstellen mit je 9 Verzweigungen vor
dem Zusammenführungspunkt; mit 8 Zuständen fehlen die zweiten Tabellen (schlägt gegen eb30c81 fehl). Der
Opt-in-Test mit der echten Datei verlangt jetzt ≥ 86 exakte Kennfelder und beide Offsets mit 16-Bit-Zellen
(bestanden, lokal).

**Einschränkung.** Nachgewiesen nur an der Entwicklungsdatei I8A0S (Teil-XDF). Auf den übrigen 14 realen Paaren
läuft der TriCore-Decoder nicht (Architektur nicht als TriCore belegt) und die Ergebnisse sind identisch. Eine
unabhängige TriCore-Referenz fehlt weiterhin.

### 12.3 HC11-Code-Beleg auf ME7.5 06A906018CG

**Ursache.** `cpu_refs.detect_cpu` sucht HC11- (`CE hi lo`, `18 CE hi lo`) und 8051-Ladebefehle (`90 hi lo`) und
bildet die 16-Bit-Adresse linear auf die Datei ab (`Datei = Adresse − Basis`). Das beschreibt nur Images bis 64 KiB;
die Prüfung lief aber auf Images bis 256 KiB (ursprüngliche Absicht in c326003: „64 KB address space only“). Auf 06A
(256 KiB, keine HC11-Firmware, Daten im ersten 64-KiB-Fenster konzentriert) gab es 1090 zufällige `CE hi lo`-Treffer,
933 davon außerhalb des adressierbaren Fensters und nur 5 % in Datenbereichen. Mit Basis 0x8000 landeten 77 % der
Ziele in Datenbereichen; gemessen am Datenanteil des ganzen Images reichte das für die Anreicherungsschwelle. Ergebnis: „HC11, Basis
0x8000“, 305 Ziele, 0 exakte Referenzstarts (18 zufällig innerhalb von Referenzkennfeldern), daraus ein Code-Beleg
bei 0x5C6 (4 × 4 u16, nicht in der XDF).

**Geprüfte Alternativen.** Eine Anreicherung gegen das adressierbare Fenster statt das ganze Image ist statistisch
richtig, senkt 06A aber nur auf 2,6 (Schwelle 2,5) – keine sichere Korrektur. Eine Schwellenänderung wäre an einer
Datei abgestimmt und ohne HC11-Referenz unbelegt; nicht übernommen.

**Korrektur.** HC11/8051 nur auf Images bis 64 KiB. Keine Änderung am Decoder, an den Schwellen oder an 68k.

**Wirkung.** Decoder-Diagnose auf 38 Images (15 reale Paare, 14 synthetische Fälle, offene Firmware, Zufallsdaten):
nur 06A ändert sich (kein CPU-Befund mehr). Im Scan von 06A entfällt der Code-Beleg 0x5C6; weil die 305 Zufallsziele
nicht mehr als Anker die Datenbereiche teilen, verschieben sich einige Datenmuster-Funde (161 → 165 Funde, 06A
gefunden 2D 147 → 151, exakt unverändert 0). Verdrängt hatte der Code-Beleg kein Referenzkennfeld.

**Grenze.** Größere HC11-/8051-Images (Speicherbänke) erhalten keine Code-Belege mehr; dafür gab es nie
Referenzdaten. Test `test_hc11_is_not_claimed_from_chance_loads_into_the_only_data_of_a_larger_image` (synthetisch,
256 KiB, Daten nur am Anfang, zufällige `CE hi lo`): kein CPU-Befund, kein Code-Beleg; schlägt gegen eb30c81 fehl.
Die echte 06A-Datei ist nicht im Repository.

### 12.4 Windows-Dateiversion

`ECU-Studio-AI.exe` wird aus `packaging/windows_launcher.cs` mit `csc` gebaut; ohne Assembly-Attribute steht in den
Dateieigenschaften 0.0.0.0. `build_portable_runtime.compile_launcher` kompiliert jetzt zusätzlich eine erzeugte
Datei mit Produktname, Hersteller und Version (Dateiversion `x.y.z.0`, Produktversion `x.y.z`) aus `__version__`.
Der Installer setzt `VersionInfoVersion`/`VersionInfoProductVersion` aus `AppVersion`. Tests: kompilierte EXE trägt
Version und Icon; Installer-Skript enthält die Angabe.

### 12.5 CodeQL: Syntaxfehler in `tests/test_a2l_records.py`

GitHub-Code-Scanning (Python, CodeQL 2.27.4, Stand eb30c81) meldete „Could not process some files due to syntax
errors“ für `tests/test_a2l_records.py`; Python selbst übersetzt die Datei fehlerfrei (3.8–3.13). Lokal mit dem
CodeQL-CLI 2.27.4 nachgestellt: Der Extraktor meldet „has encoding 'counts'“. Ursache ist die erste Docstring-Zeile
`"""ASAP2 RECORD_LAYOUT decoding: counts …`: Das PEP-263-Muster `coding[:=]\s*name` wird in Zeile 1–2 auch
außerhalb eines Kommentars gefunden. Docstring umformuliert; danach meldet CodeQL über `src` und `tests` keine
Kodierungs- und Syntaxwarnung mehr. Test `tests/test_source_encoding_lines.py` prüft alle Python-Dateien (schlägt mit
der alten Zeile fehl).

### 12.6 Regression, Laufzeit, Speicher

Gleicher Rechner; `benchmark_suite --memory` und `negative_benchmark` für eb30c81 und den neuen Stand.

| Vergleich | Ergebnis |
|---|---|
| eb30c81 gegen PR-#16-Messung (59f355d-Lauf) | 0 Unterschiede in allen Erkennungsfeldern (Ausgangsstand bestätigt) |
| 15 reale Paare, neu gegen eb30c81 | nur zwei Paare ändern sich: **MSD80** exakt 2D 84 → 86, Typ richtig 83 → 85, Achsen richtig 74 → 77 (mit Achsen 81 → 84), Achsadresse richtig 141 → 147 (von 160 → 166), Gruppenpaare 45/45/47 → 51/51/51, gefunden 2D 1246 → 1253, 1D 2716 → 2731; **ME7.5 06A** gefunden 2D 147 → 151 (Code-Beleg 0x5C6 entfällt, Datenmuster verschoben), exakt unverändert |
| Exakte Kennfelder je Paar | keines verloren (Mengenvergleich der exakten Layouts gegen 1.19.0 und eb30c81); neu exakt nur 0x4FB18 6 × 7 und 0x5604C 6 × 8 (16 Bit) |
| Datentypen, Achsen, Achsadressen auf den übrigen 13 Paaren | unverändert |
| 15 reale Paare gegen 1.19.0 | wie oben, zusätzlich MED17 404A/E/G gefunden 2D je −1 (PR #16, falscher C16x-Code-Beleg) |
| 14 synthetische Fälle | identisch zu eb30c81; gegen 1.19.0 weiterhin aligned-padded exakt 2 → 3, Negativkontrollen unverändert |
| Negativ-Benchmark (7 Images) | je Image identisch zu eb30c81 (alle Felder außer Zeit/Speicher): 875 Funde, 0 nachweislich falsch, 875 unklar (36 Strukturbelege, 839 Datenmuster); Stabilität FOME 74 / 20 / 8 / 34. Die 921 entfernten Fehlfunde kommen nicht zurück. Die 875 unklaren Funde sind keine bestätigten Kennfelder. |
| Laufzeit 15 Paare (Summe) | neu 91,8 s; eb30c81 im selben Durchgang 116,3 s, davon ein Ausreißer ME9.2.1 27,8 s statt ~6,5 s (parallel lief die CodeQL-Prüfung); PR-#16-Messung 89,4 s. Je Paar ohne Ausreißer −1,9 … +1,3 s |
| MSD80 allein, 4 × abwechselnd, ohne Nebenlast (voller Scan 2 MiB) | eb30c81 29,2–29,9 s, neu 30,3–32,4 s (Median +1,2 s, ≈ +4 %): Kosten der 32 Registerzustände |
| Spitzen-Speicher | 15 Paare 86,3 MB (eb30c81 86,3); MSD80 mit `tracemalloc` 87,4 MB in beiden Ständen; Negativ-Benchmark je Image gleich (Spitze 67,5 MB) |
| Wiederholte Scans (10 Dateien + 5 × MS42, ein Prozess) | Python-Heap nach dem Scan +0,03 MB in beiden Ständen, kein Wachstum |
| Projektwechsel / A2L | Test: 8 Projekte zu je 1 MiB mit wechselnden Definitionen halten keinen Block ≥ 256 KiB, < 1 MiB gesamt, Cache bleibt bei 4 Einträgen |

### 12.7 Tests und Prüfungen

| Prüfung | Ergebnis |
|---|---|
| pytest vollständig | 909 bestanden, 10 übersprungen, 0 fehlgeschlagen (eb30c81: 897/10); kein Test deaktiviert oder abgeschwächt. Der Opt-in-Test der echten MSD80-Datei ist schärfer (≥ 86 statt ≥ 84, beide Offsets) |
| MSD80-Opt-in mit lokaler Datei | bestanden (38/38 in `test_tricore_refs.py`) |
| Übersetzungsprüfung | 2060 Texte, 0 ohne Übersetzung |
| GUI-Smoke (mit lokaler MS43-Datei) | 10/10, MS43 856 Kennfelder; enthält Speichern und Wiederöffnen eines Projekts |
| Firmware-Guard (`firmware_guard.py staged`) | sauber |
| CodeQL 2.27.4 lokal (Python, `src` + `tests`) | keine Kodierungs- oder Syntaxwarnung |

Neue bzw. geänderte Tests: `test_a2l_reference_cache.py` (7), `test_tricore_refs.py` (+1, Opt-in verschärft),
`test_analysis_features.py` (+1 HC11), `test_app_icon.py` (+2 Version), `test_source_encoding_lines.py` (1).

### 12.8 Offen

- MSD80-Korrektur und Fehlfund-Zahlen sind an Entwicklungsdaten gemessen; keine unabhängige TriCore-Referenz.
- HC11/8051/68k: keine Referenzimages; Images über 64 KiB erhalten keine HC11-/8051-Code-Belege mehr.
- Aufgaben 2–10 unverändert offen (Präzision der Datenmuster, Achsen, Darstellung, Abbruch, lange Pfade, Absturz,
  Konstanten-Referenz, Thumb/AVR, Anzeige unterdrückter Funde).
