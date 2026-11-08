# Checksummen und Integrität

Stand: 08.11.2026, Branch `feature/1.20-checksum-system` (Basis 1.19.1). Diese Seite dokumentiert die
Bestandsaufnahme, die Architektur, die Nachweise je Verfahren und die Grenzen. Firmwaredateien liegen **nicht** im
Repository. Hier stehen nur Zählwerte und Hash-Präfixe.

**Kurz:**
- Jede Datei erhält genau einen von fünf Status.
- Unabhängig belegt ist ein Verfahren: die Bosch-Multipoint-Prüfsummentabelle (ME7.x, ME9, MED9).
- MED17/EDC17 und EDC16 sind am Original gemessen. Ihre Korrektur bleibt bis zu einem signierten OEM-Nachweis
  gesperrt.
- Signaturen werden getrennt ausgewiesen und nie geprüft, erzeugt oder verändert.
- Kein Ergebnis ist eine Flashfreigabe.

---

## 1. Bestandsaufnahme (Phase 1, vor dieser Änderung)

### Vorhandene Module

| Modul | Aufgabe | Bereichserkennung | Korrektur |
|---|---|---|---|
| `core/checksum_audit.py` | Manuelles, SHA-256-gebundenes Profil (CRC32, CRC16-CCITT, Byte-/Wort-/Doppelwortsummen, Komplemente) | vom Prüfer deklariert | ja, mit Vorschau und Rückrollen |
| `core/checksum_tables.py` | Selbstbeschreibende Tabellen (Start, Ende, Wert, ~Wert), sechs generische Verfahren, mehrere Basisadressen | aus der Datei, Nachweis am Original | ja, Wert und Komplement |
| `core/edc17_checksum.py` | Bosch MED17/EDC17-Blöcke (Signatur FADECAFE/CAFEAFFE, CRC32/ADD32/ADD16) | aus dem Blockkopf | nur ADD-Blöcke und nur mit OEM-Nachweis |
| `core/edc16_checksum.py` | Bosch EDC16-Bereiche (Zielsumme 0xD01FE500) | aus dem Deskriptor | nur mit OEM-Nachweis |
| `core/checksum_validation.py` | OEM-Bescheinigung mit zwei Ed25519-Signaturen aus verschiedenen Prüfergruppen | – | Freigabeschalter |
| `core/checksum_search.py`, `tools/checksum_search.py` | Forschung: Hypothesen für unbekannte Layouts, Profilentwurf mit `reviewed: false` | Suche | nein |
| `core/preflight.py` | Plausibilitätsprüfung vor dem Export (nutzt nur das Profil) | – | – |
| `core/identification.py`, `core/profiles.py` | Steuergerät aus EPK, Klartext, Hardware-/Softwarenummer, Siemens-Kennungen | – | – |

OEM-Manifest (`checksum_oem_validation.json`) und Schlüsselliste (`checksum_validation_keys.json`) sind leer. Damit ist
die EDC17-/EDC16-Korrektur gesperrt, und das bleibt so.

### Befunde

1. **Kein gemeinsamer Status.** Jedes Verfahren kannte nur „match / mismatch / none“. Ob eine Datei unterstützt,
   unvollständig geprüft oder unbekannt ist, war nicht unterscheidbar.
2. **Teilprüfung sah wie eine Gesamtprüfung aus.** Auf ME7.x bestätigte der Tabellendialog „N Blöcke bewiesen …
   nichts zu korrigieren“. ME7.x hat aber weitere Prüfsummen (ROMSYS, CRC-Tabelle, Haupt-Datenprüfsummen,
   Programmseiten, Hintergrund- und Hauptprogrammprüfsummen) und eine RSA-Signatur. Quelle: ME7Sum, siehe § 3.
3. **Generische Verfahren zählten wie belegte.** Die Tabellenprüfung akzeptierte jedes der sechs generischen
   Verfahren, das den gespeicherten Wert ergab, auch CRC32. Sie korrigierte es auch.
4. **Bereits veränderte Dateien.** Eine Datei, die schon verändert geöffnet wurde (z. B. getunt mit veralteter
   Prüfsumme), zeigte betroffene Tabelleneinträge als „unbekannt“ statt als ungültig.
5. **Korrektur in mehreren Schritten.** Die Tabellenkorrektur schrieb jedes Feld als eigenen Undo-Schritt.
6. **Blockierende Oberfläche.** Alle Prüfungen liefen im GUI-Thread. Die bitweise EDC17-CRC brauchte auf einer 2-MiB-Datei
   3,2 s.
7. **Exportdialog und Statusleiste.** Der Export zeigte nur den Profilstatus („Es erfolgt KEINE
   Checksummenreparatur“). Die Statusanzeige „CHECKSUMME: OFFEN“ wurde nie aktualisiert.
8. **Doppelte Abläufe.** Vier getrennte Dialoge (Profil, Tabellen, EDC17, EDC16) hatten je eigene Vorschau- und
   Bestätigungslogik.

### Messung auf lokalen Dateien (nur Zählwerte)

| Datei (Familie, Software) | SHA-256 (Präfix) | Belegt am Original |
|---|---|---|
| Bosch ME7.5 8E0909518AK (1 MiB, Vollflash) | `50ca08d8f62e` | 70/70 Tabelleneinträge (Wortsumme LE) |
| BMW ME9 770115XE (1 MiB) | `70aa4e7b317e` | 63/63 Tabelleneinträge (Wortsumme BE) |
| Bosch MED9.1 1K090711S (2 MiB) | `7f2480ddbb03` | 66/66 Tabelleneinträge (Wortsumme BE), 2 Einzelkandidaten ohne Verfahren |
| Bosch EDC17CP09 (2 MiB) | `f9057f1a05f0` | 8/11 Blockstrukturen (2 stimmen am Original nicht, 1 außerhalb des Blocks) |
| Bosch EDC16C31 (4,5 MiB) | `1d7ed00be179` | 1/1 Bereich |
| Bosch EDC16C35 (2 MiB) | `30757e6cf332` | 1/1 Bereich |
| Siemens MS43 430069, MS42 0110C6, MSD80, MSD85, MS45, ME9.2.1 | – | kein Verfahren nachweisbar |
| Bosch MED17.1.62 ×6 (Kalibrierbereich), ME7.2 (64-KiB-Teilabbilder), ME7.5 06A906018CG (256 KiB) | – | kein Verfahren nachweisbar (nur Füllmuster-Kandidaten) |

**Herkunft und Nutzung:** Die MS43-Datei gehört dem Nutzer. Für die übrigen Dateien gibt es keine dokumentierte
Herkunft ([ECU-Unterstützung](ECU_SUPPORT.md), Abschnitt „Herkunft der lokalen Referenzdaten“). Sie wurden deshalb
nur lokal gelesen und gemessen, wie dort dokumentiert. Sie wurden nicht verändert, nicht veröffentlicht und nicht zum
Training verwendet.

---

## 2. Architektur (Phase 2)

`core/integrity.py` legt eine Schicht über die vorhandenen Parser und rechnet nichts doppelt.

```
check_integrity(image) ─┬─ identification.identify(original)          Familie, Software, Stufe
                        ├─ checksum_tables.find_checksum_tables → Bosch-Multipoint (Wortsumme) | generisch
                        ├─ edc17_checksum.find_blocks / _evaluate      MED17/EDC17 + Signaturblöcke
                        ├─ edc16_checksum.analyze                      EDC16
                        └─ checksum_audit.verify_checksums             geprüftes Profil
                        → IntegrityReport(status, Gründe, Verfahren[Bereiche], Signaturen, ungeprüft)
plan_correction(image, report) → CorrectionPlan(Schritte je Byte, abgelehnte Verfahren, Warnungen)
apply_correction(image, plan)  → ein Undo-Schritt, vorher unabhängige Nachprüfung
write_corrected_copy(image, plan, ziel) → Kopie + Änderungsprotokoll, Sitzung und Original unverändert
```

### Status

| Status | Bedingung |
|---|---|
| **Unterstützt und gültig** | Alle bekannten Prüfsummen geprüft und richtig. Jedes Verfahren ist belegt (Referenz, geprüftes Profil oder signierter OEM-Nachweis). Familie eindeutig identifiziert, keine weiteren bekannten Prüfungen offen. Heute nur mit einem geprüften Profil `"complete": true` erreichbar. |
| **Unterstützt und ungültig** | Mindestens eine geprüfte Prüfsumme stimmt nicht mit den aktuellen Bytes überein. |
| **Unvollständige Prüfung** | Die geprüften Prüfsummen stimmen, aber mindestens eines trifft zu: unbestätigte Bereiche, Verfahren ohne unabhängigen Nachweis, Familie nicht eindeutig, weitere Prüfsummen der Familie ungeprüft. |
| **Nicht unterstützt** | Familie identifiziert, aber kein Verfahren in der Datei nachweisbar (z. B. MS43). |
| **Unbekannt** | Weder Familie noch Verfahren nachweisbar. |

Ein generisches Verfahren (CRC, Summe), das zufällig eine passende Zahl liefert, macht eine Datei nie gültig.
Generische Tabelleneinträge laufen als „experimentell“. Sie werden geprüft, aber nicht korrigiert.

### Bereiche, Signaturen, Korrektur

- **Bereich:** Verfahren, Name, abgedeckter Bereich, Adresse des Prüffelds, Algorithmus, gespeicherter und
  berechneter Wert. Zustand: *stimmt*, *FEHLER* oder *nicht bestätigt*.
- **Signaturen:** getrennte Liste, Zustand *erwartet* (bei der Familie üblich), *erkannt* (Struktur vorhanden, z. B.
  EDC17-Block „Tuning protection“) oder *unbekannt*. Es gibt keinen Zustand „gültig“. Wo eine Signatur erwartet oder
  erkannt wird, steht in Bericht und Vorschau: Eine Prüfsummenkorrektur ersetzt keine gültige Herstellersignatur.
- **Sichere Korrektur (Phase 5):**
  - Vorschau mit jedem Byte, erst nach ausdrücklicher Bestätigung schreibbar.
  - Plan an Revision und SHA-256 der aktuellen Bytes gebunden; ein veralteter Plan wird abgelehnt.
  - Unabhängige Nachprüfung, bevor etwas geschrieben wird:
    - Nur die dokumentierten Positionen dürfen sich ändern.
    - Vollständige Neuprüfung auf einem frisch aufgebauten Abbild.
    - Multipoint-Felder werden mit einer zweiten, einfachen Implementierung (`reference_word_sum`) nachgerechnet.
  - In der Sitzung ein Undo-Schritt. Als Kopie atomar geschrieben, ein vorhandenes Ziel bleibt als `.bak` erhalten.
    Dazu kommt `<ziel>.korrektur.json` mit Hashes, Schritten, abgelehnten Verfahren und Warnungen.
  - Scheitert das Protokoll, wird die Kopie entfernt bzw. das alte Ziel wiederhergestellt. Es gibt keine
    Teilausgabe.
  - Das Original ist geschützt.

### Oberfläche (Phase 6)

- **Bereich „CHECKSUMMEN & INTEGRITÄT“** im Eigenschaften-Panel: Status, Steuergerät, Software, Verfahren, Zahl der
  Bereiche, Fehler mit Adresse, Korrekturmöglichkeit, Signaturstatus. Dazu die Schaltflächen **Checksummen prüfen**
  und **Korrekturvorschau**.
- Die Prüfung läuft im Hintergrund (`IntegrityWorker`) auf einem Schnappschuss (`BinaryImage.snapshot`), mit
  Fortschritt und Abbrechen.
- Nach dem Öffnen und nach Bearbeitungen wird automatisch neu geprüft, nach Bearbeitungen 0,9 s verzögert. Ein
  veralteter Bericht ist markiert.
- **Detailbericht** mit JSON-Export.
- **Korrekturvorschau:** „In Sitzung übernehmen“ oder „Korrigierte Kopie speichern“.
- **Exportdialog:** zeigt Status und Gründe, bei korrigierbaren Fehlern mit der Schaltfläche „Korrekturvorschau …“.
- Die Statusleiste zeigt den Status („CHECKSUMME: UNVOLLSTÄNDIG“ usw.).
- Die vier alten Einzel-Dialoge sind durch den gemeinsamen Ablauf ersetzt. Die Profilfunktionen (Profil
  importieren, Plausibilitätsbericht) bleiben.
- Alle Texte gibt es auf Deutsch und Englisch.

---

## 3. Verfahren und Nachweise

| Verfahren | Familien | Stufe | Korrektur |
|---|---|---|---|
| Bosch-Multipoint-Prüfsummentabelle | ME7.x (C16x, LE), ME9 und MED9 (PowerPC, BE) | **unabhängig belegt** | ja |
| Bosch MED17/EDC17-Blöcke | MED17, EDC17 | am Original gemessen | gesperrt (OEM-Nachweis) |
| Bosch EDC16-Bereiche | EDC16 (MPC5xx) | am Original gemessen | gesperrt (OEM-Nachweis) |
| Geprüftes Profil | beliebig | manuell geprüft | ja |
| Selbstbeschreibende Tabelle, generisch | – | experimentell | nein |

### Bosch-Multipoint (unabhängig belegt)

**Verfahren:** Ein Tabelleneintrag besteht aus 16 Byte: Startadresse, Endadresse, Wert, ~Wert, in der Byte-Reihenfolge
der CPU. Der Wert ist die Summe der 16-Bit-Wörter über [Start, Ende] modulo 2³². Gesucht wird über das Paar
Wert/~Wert, nicht über den Familiennamen. Eine Tabelle gilt als nachgewiesen, wenn mindestens ein Eintrag den
gespeicherten Wert am Original exakt reproduziert. Weitere Einträge derselben zusammenhängenden Tabelle mit gleicher
Adresslage werden mitgeprüft. Stimmen sie nicht, sind sie Fehler (die Datei war bereits verändert), nicht unbekannt.

**Nachweise, unabhängig von dieser Implementierung:**

1. **Herstellerwerte:** Drei unveränderte Originale aus drei Familien und zwei CPU-Architekturen reproduzieren
   199 von 199 Tabelleneinträgen (ME7.5: 70, ME9: 63, MED9.1: 66). Jeder Eintrag ist ein 32-Bit-Wert mit 32-Bit-Komplement
   über einen von der Datei selbst angegebenen Bereich. Diese Werte hat die Werkzeugkette des Herstellers erzeugt,
   nicht dieser Code. Ein zufälliger Treffer ist ausgeschlossen (Wert 2⁻³², zusätzlich Komplement und Bereich).
2. **Unabhängige Spezifikation:** Das quelloffene ME7Sum (BSD-Lizenz, github.com/nyetwurk/ME7Sum, Commit `cbe6df9`)
   berechnet Multipoint-Prüfsummen in `CalcChecksumBlk16` als Summe der Little-Endian-16-Bit-Wörter von Start bis
   Ende einschließlich. Es prüft Wert und `~Wert` getrennt (`DoChecksumBlk`). Das stimmt mit diesem Verfahren
   überein. Der Quelltext wurde nur gelesen und verglichen; ME7Sum wurde **nicht** ausgeführt (kein Fremdcode).
   ME7Sum deckt nur ME7.x ab. Für ME9/MED9 (Big-Endian) stützt sich der Nachweis allein auf die Herstellerwerte.
3. **Korrektur gegen Herstellerbytes** (`tests/test_integrity_reference.py`, lokale Originale):
   - Je Datei bis zu 8 gespeicherte Felder beschädigt. Die Korrektur stellt die Herstellerbytes bitgenau wieder her.
   - Ein Datenbyte im größten abgedeckten Bereich geändert. Fehler werden genau in den Einträgen gemeldet, die das
     Byte abdecken. Nach der Korrektur ändern sich nur Prüffeld-Bytes, die zweite Implementierung bestätigt jeden
     Eintrag.
   - Byte zurückgesetzt und erneut korrigiert: Die Datei ist bitgenau gleich dem Original.
   - Alles auf ME7.5, ME9 und MED9.1 bestanden.

Ein reiner Selbsttest (eigene Summe schreiben, eigene Summe prüfen) liegt zusätzlich synthetisch vor
(`tests/test_integrity.py`). Er dient nur der Regression und ist nicht der Nachweis.

**Grenzen:** Nur die Multipoint-Tabellen. Auf ME7.x bleiben ROMSYS, CRC-Tabelle, Haupt-Datenprüfsummen,
Programmseiten, Hintergrund- und Hauptprogrammprüfsummen sowie die RSA-Signatur ungeprüft. Der Status bleibt daher
„Unvollständige Prüfung“, und die Vorschau sagt, dass die Datei dadurch nicht flashbereit ist. Für ME9/MED9 ist nicht
dokumentiert, welche weiteren Prüfungen es gibt.

### MED17/EDC17 und EDC16 (am Original gemessen)

- **EDC17CP09:** 8 von 11 Strukturen reproduziert. Zwei Dataset-#0-Strukturen stimmen auf der lokalen Datei nicht
  (die Datei ist möglicherweise kein unverändertes Original), eine liegt außerhalb des Blocks.
- **EDC16C31 und EDC16C35:** je 1 von 1 Bereich.
- Es gibt keine unabhängige Spezifikation oder Referenzimplementierung, die geprüft wurde, und keine signierte
  OEM-Bescheinigung. Die Prüfung meldet Änderungen als „ungültig“, die Korrektur bleibt gesperrt.
- Die CRC32-Berechnung läuft jetzt über zlib, weil sie mathematisch identisch ist. Gleichheit mit der bitweisen
  Referenz ist getestet. Die Laufzeit sank auf der EDC17CP09-Datei von 3,2 s auf unter 0,1 s. Die Ergebnisse sind
  unverändert.

---

## 4. Messwerte

Gemessen am 08.11.2026 auf dem Entwicklungsrechner (Windows 11, Python 3, ein BLAS-Thread). Werte sind der Median aus
fünf Läufen von `check_integrity` nach einem Aufwärmlauf. Der Speicher ist die tracemalloc-Spitze während einer Prüfung.
Die Firmwaredateien selbst liegen nicht im Repository.

| Datei | Größe | Status am Original | Bereiche | Prüfung | Speicherspitze |
|---|---|---|---|---|---|
| ME7.5 8E0909518AK | 1 MiB | unvollständig | 70 | 108 ms | 5 MiB |
| ME9 770115XE | 1 MiB | unvollständig | 63 | 110 ms | 5 MiB |
| MED9.1 1K090711S | 2 MiB | unvollständig | 66 | 225 ms | 10 MiB |
| EDC17CP09 | 2 MiB | unvollständig | 11 | 221 ms | 10 MiB |
| EDC16C31 | 4,5 MiB | unvollständig | 1 | 452 ms | 22 MiB |
| EDC16C35 | 2 MiB | unvollständig | 1 | 208 ms | 10 MiB |
| MS43 430069 | 0,5 MiB | nicht unterstützt | 0 | 63 ms | 2,5 MiB |
| MSD80 I8A0S | 2 MiB | unbekannt | 0 | 229 ms | 10 MiB |

„Unvollständig“ bedeutet hier: Alle erkannten Bereiche stimmen, aber die Familie hat weitere Prüfungen
(z. B. ME7-ROMSYS/CRC-Tabellen, RSA-Signatur), die dieses Programm nicht abdeckt.

Korrekturlauf (ein Wort in der Mitte des größten Multipoint-Bereichs geändert):

| Datei | betroffene Bereiche | geänderte Prüfbytes | Prüfung + Plan | Kopie mit Protokoll | Übernahme in Sitzung |
|---|---|---|---|---|---|
| ME7.5 8E0909518AK | 3 | 6 | 142 ms | 135 ms | 118 ms |
| ME9 770115XE | 1 | 2 | 126 ms | 147 ms | 124 ms |
| MED9.1 1K090711S | 1 | 2 | 282 ms | 262 ms | 238 ms |

Die Prüfung läuft in der Oberfläche in einem eigenen Thread mit Fortschritt und Abbruch. Es wird keine zweite Kopie der
Firmware dauerhaft gehalten. Der Speicher ist nur während der Prüfung belegt, etwa das Fünffache der Dateigröße für
die numpy-Wortsummen.

---

## 5. Grenzen und offene Punkte

- Kein Verfahren erreicht heute „Unterstützt und gültig“ ohne geprüftes Profil mit `"complete": true`. Das ist
  beabsichtigt, solange weitere Prüfsummen der Familie ungeprüft sind.
- ME7.x: ROMSYS, CRC-Tabelle, Haupt-Datenprüfsummen, Programmseiten, Hintergrund- und Hauptprogrammprüfsummen fehlen.
  Sie sind in ME7Sum beschrieben und wären der nächste Schritt zu einer vollständigen ME7-Prüfung. Die RSA-Signatur
  wird nie verändert.
- MED17/EDC17, EDC16: Für die Korrektur fehlen eine unabhängige Referenz und die signierte OEM-Bescheinigung.
- Siemens/Continental (MS4x, MSD8x, MS45, Simos, SID): kein Verfahren implementiert (Status „Nicht unterstützt“).
- Die Referenzdateien außer MS43 haben keine dokumentierte Herkunft. Deshalb wurden sie nur lokal gemessen. Eine
  unabhängige Bestätigung mit rechtmäßig bereitgestellten Originalen (zwei Softwarestände je Familie) steht aus.
- Signaturen werden nur als vorhanden/erwartet ausgewiesen. Es gibt keine Umgehung, Fälschung oder Änderung.

### Lokale Referenztests ausführen

```
set ECU_STUDIO_CHECKSUM_REFERENCES=C:\pfad\checksum-references.json
python -m pytest tests/test_integrity_reference.py
```

Die Manifestdatei liegt außerhalb des Repositorys und enthält je Eintrag `name`, `bin`, `sha256`, `method`, `regions`
und `unproven`.
