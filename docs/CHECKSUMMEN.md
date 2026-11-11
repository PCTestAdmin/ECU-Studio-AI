# Checksummen und Integrität

Stand: 08.11.2026, Version 1.20.0. Ergänzt am 11.11.2026 um die weiteren ME7-Prüfsummen (§ 3, unveröffentlicht,
Branch `feat/me7-checksums`). Diese Seite
dokumentiert die Bestandsaufnahme, die Architektur, die Nachweise je Verfahren und die Grenzen. Firmwaredateien
liegen **nicht** im Repository. Hier stehen nur Zählwerte und Teilenummern.

**Kurz:**
- Jede Datei erhält genau einen von fünf Status.
- Unabhängig belegt ist ein Verfahren: die Bosch-Multipoint-Prüfsummentabelle (ME7.x, ME9, MED9).
- MED17/EDC17 und EDC16 sind am Original gemessen. Ihre Korrektur bleibt bis zu einem signierten OEM-Nachweis
  gesperrt.
- **Unveröffentlicht (nach 1.20.0):** Die weiteren ME7-Prüfsummen (ROMSYS, CRC-Tabelle, Hauptdaten-Prüfsumme,
  Hauptprogramm) werden **geprüft, nicht korrigiert**. Sie sind am Original gemessen und nicht unabhängig validiert.
- Signaturen werden getrennt ausgewiesen und nie geprüft, erzeugt oder verändert.
- Kein Ergebnis ist eine Flashfreigabe.

**Einordnung für 1.20.0 – erste validierte Ausbaustufe.** Keine untersuchte Originaldatei erreicht eine
vollständige Checksummenabdeckung.

| Einordnung | Verfahren | Prüfung | Korrektur |
|---|---|---|---|
| **Unterstützt** (unabhängig belegt) | Bosch-Multipoint-Tabellen (ME7.x, ME9, MED9) | ja | ja, nur unter Regel A oder B (§ 2) |
| **Unterstützt** (vom Nutzer belegt) | geprüftes, SHA-256-gebundenes Profil | nur deklarierte Prüffelder | ja |
| **Teilweise geprüft** | MED17/EDC17-Blöcke, EDC16-Bereiche | ja | gesperrt bis zum signierten OEM-Nachweis |
| **Teilweise geprüft** (unveröffentlicht) | ME7: ROMSYS, CRC-Tabelle, Hauptdaten-Prüfsumme, Hauptprogramm | ja | nein, nur Prüfung |
| **Nicht unterstützt** | ME7: Hauptdaten-CRC32 und indirekte CRC-Blöcke; Siemens/Continental; MG1/MD1; übrige Familien | nein | nein |
| **Nie** | digitale Herstellersignaturen | nicht verifiziert (unveröffentlicht: nur mit vertrauenswürdigem Schlüssel, § 6) | nie verändert |

Daraus folgt ausdrücklich:
- Nicht alle Checksummen werden automatisch korrigiert.
- ME7, ME9, EDC16 und EDC17 sind nicht vollständig unterstützt.
- Eine korrigierte Datei ist nicht flashbereit.
- Signaturen werden nicht verifiziert.

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

| Datei (Familie, Software) | Belegt am Original |
|---|---|
| Bosch ME7.5 8E0909518AK (1 MiB, Vollflash) | 70/70 Tabelleneinträge (Wortsumme LE) |
| BMW ME9 770115XE (1 MiB) | 63/63 Tabelleneinträge (Wortsumme BE) |
| Bosch MED9.1 1K090711S (2 MiB) | 66/66 Tabelleneinträge (Wortsumme BE), 2 Einzelkandidaten ohne Verfahren |
| Bosch EDC17CP09 (2 MiB) | 8/11 Blockstrukturen (2 stimmen am Original nicht, 1 außerhalb des Blocks) |
| Bosch EDC16C31 (4,5 MiB) | 1/1 Bereich |
| Bosch EDC16C35 (2 MiB) | 1/1 Bereich |
| Siemens MS43 430069, MS42 0110C6, MSD80, MSD85, MS45, ME9.2.1 | kein Verfahren nachweisbar |
| Bosch MED17.1.62 ×6 (Kalibrierbereich), ME7.2 (64-KiB-Teilabbilder), ME7.5 06A906018CG (256 KiB) | kein Verfahren nachweisbar (nur Füllmuster-Kandidaten) |

**Kennungen:** Die Teilenummern stehen bereits in der Herkunftstabelle von [ECU-Unterstützung](ECU_SUPPORT.md). SHA-256-Werte der Dateien werden nicht veröffentlicht: Für die meisten Dateien ist die Herkunft nicht dokumentiert, und für den Nachweis genügen Familie, Größe und Zählwerte. Die vollständigen SHA-256 stehen nur im lokalen Manifest; die Opt-in-Tests prüfen sie vor jeder Messung.

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
  - Reihenfolge beim Speichern der Kopie (`write_corrected_copy`):
    1. Ein vorhandenes Protokoll wird zuerst entfernt, weil es eine andere Datei beschreibt.
    2. Die Kopie wird atomar geschrieben und per SHA-256 zurückgelesen.
    3. Erst dann wird das Protokoll geschrieben und zurückgelesen. Es muss den SHA-256 der Kopie nennen.
  - Jeder Fehler in diesen Schritten stellt Zieldatei und Protokoll wieder her. Das gilt für vollen Datenträger,
    Schreib- und Lesefehler, abweichenden Inhalt und Abbruch im Programm. Der Fehler wird als `CopyNotSaved`
    gemeldet.
  - Scheitert sogar die Wiederherstellung, nennt die Meldung, was noch liegt, und wo der vorherige Stand liegt
    (`.bak`). Sie warnt davor, die Zieldatei zu verwenden.
  - Ein Protokoll dokumentiert nie einen Stand, der nicht auf dem Datenträger liegt. Wird der Prozess hart zwischen
    Schritt 2 und 3 beendet, bleibt höchstens eine Kopie *ohne* Protokoll zurück, nie eine mit falschem Protokoll.
  - Original und Protokollpfad werden geschützt: Weder die Kopie noch ihr Protokoll darf auf die geöffnete
    Originaldatei zeigen.
- **Wann eine Multipoint-Korrektur angeboten wird** (Review PR #19): Ein am Original bestätigtes Tabellenmuster
  allein genügt nicht. Die Korrektur ist frei, wenn
  - **A)** das Steuergerät eindeutig als ME7, ME9 oder MED9 identifiziert ist, oder
  - **B)** das Steuergerät nicht identifiziert ist, das Original die Tabellen aber stark belegt: mindestens 32
    bestätigte Einträge (je 64 Bit aus Wert und Komplement), eine Tabelle mit mindestens 16 davon und kein Eintrag,
    der nur aus einem bereits veränderten Original abgeleitet ist. Das ist der Fall der ME9-Referenz (nicht
    identifiziert, 63 Einträge). Bericht und Vorschau kennzeichnen diesen Fall eigens.

  Ist das Steuergerät als *andere* Familie identifiziert, oder sind es zu wenige Belege, bleibt es bei „nur
  Prüfung“: Die Fehler werden angezeigt, die Korrektur ist gesperrt. Dann bleibt der Weg über ein geprüftes,
  SHA-256-gebundenes Profil.

  Einträge, die am geöffneten „Original“ nicht stimmen, gelten nur dann als korrigierbare Fehler, wenn die Mehrheit
  der Einträge dieser Tabelle (mindestens zwei) am Original bestätigt ist. Sonst sind sie „nicht bestätigt“.

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
- Die Statusleiste zeigt den Status („CHECKSUMME: UNVOLLSTÄNDIG“ usw.). Das Panel nennt immer „Flashfreigabe:
  keine“.
- **Preflight und Exportdialog (Review PR #19)** führen getrennte Stufen, die nie vermischt werden:

  | Stufe | Bedeutung |
  |---|---|
  | Profil-Prüffelder | alle im geladenen Profil *deklarierten* Felder stimmen (Profil kann unvollständig sein) |
  | Bekannte Prüfsummen | alle geprüften Prüfsummen (Profil und nachgewiesene Verfahren) stimmen |
  | Checksummenabdeckung | vollständig nur bei Integritätsstatus „gültig“ bzw. bestätigt vollständigem Profil |
  | Signaturen | immer „nicht geprüft“ |
  | Preflight | grün / gelb / rot |
  | Flashfreigabe | immer „keine“ |

  `checksum_verified` und `checks_passed` bedeuten seither *vollständige* Abdeckung. Ein passendes Teilprofil
  genügt nicht mehr. Vorher konnte ein passendes Teilprofil bei unvollständiger Integritätsprüfung einen grünen
  Preflight mit `checks_passed=True` ergeben.

  Eine bearbeitete Datei ohne vollständige Abdeckung bekommt immer einen gelben Befund. Bei passendem Profil lautet
  er „Profil-Prüffelder stimmen, Checksummenabdeckung unvollständig“.
- Die vier alten Einzel-Dialoge sind durch den gemeinsamen Ablauf ersetzt. Die Profilfunktionen (Profil
  importieren, Plausibilitätsbericht) bleiben.
- Alle Texte gibt es auf Deutsch und Englisch.

---

## 3. Verfahren und Nachweise

| Verfahren | Familien | Stufe | Korrektur |
|---|---|---|---|
| Bosch-Multipoint-Prüfsummentabelle | ME7.x (C16x, LE), ME9 und MED9 (PowerPC, BE) | **unabhängig belegt** | ja |
| Bosch ME7-Prüfsummen (ROMSYS, CRC-Tabelle, Hauptdaten, Hauptprogramm), unveröffentlicht | ME7.x (C16x, 512 KiB/1 MiB) | am Original gemessen | nein, nur Prüfung |
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

### Bosch ME7 – weitere Prüfsummen (am Original gemessen, nur Prüfung; unveröffentlicht)

`core/me7_checksums.py` ist eine eigene Python-Umsetzung der Verfahren, die das quelloffene ME7Sum beschreibt.
- **Quelle:** github.com/nyetlabs/ME7Sum (früher nyetwurk), Datei `me7sum.c`, Commit `7095f930` vom 09.11.2026.
- **Lizenz:** Erlaubnishinweis im Kopf von `me7sum.c` („Permission is hereby granted, free of charge … to use, copy,
  modify …“, MIT-Wortlaut); das README nennt „BSD open source license“.
- **Umgang:** Der C-Quelltext wurde gelesen und verglichen. Er wurde nicht ausgeführt und nicht kopiert, auch
  `ME7Check.exe` nicht.
- **Rückverfolgbarkeit:** Die Kommentare im Modul nennen die ME7Sum-Funktionen.
- **Einbindung:** `core/integrity.py`, Verfahren `bosch-me7`. Es gelten dieselben Regeln wie bei EDC16/EDC17:
  - am Original nachweisen, an den aktuellen Bytes prüfen;
  - was am geöffneten Original nicht stimmt, bleibt „nicht bestätigt“;
  - eine veränderte Struktur gilt als Fehler;
  - die Korrektur ist gesperrt.

| Nr. | Prüfpunkt | ROMSYS Startup / ParamPage / ProgramPages | CRC-Tabelle | Hauptdaten-Prüfsumme | Hauptdaten-CRC32 | Hintergrund 1/2 | Hauptprogramm |
|---|---|---|---|---|---|---|---|
| 1 | Dokumentation | `DoROMSYS_*`, `CheckROMSYSHeader` | `FindCRCTab`, `crc_table_fallback` | `FindMainCSMOffsets`, `DoMainCSMs` | `FindMainCRC*`, `DoMainCRCs` | `FindBgChecksums`, `DoBgChecksums` | `FindMainProgram*`, `DoMainProgramCSM` |
| 2 | Bereiche | Wort 0x8000 + 0xFFFE; Wort Parameteranfang + -ende; erstes + letztes Wort jeder 8-KiB-Seite in 0–0xFFFF und 0x20000–Flashende | 1024 Byte ab Code-Verweis (`mov r4/r5`) oder Tabellenanfang | Blöcke aus den Code-Verweisen (Start/Ende) | dieselben Blöcke, ggf. verkettet ab Vorblock | Deskriptoren (Start, Ende, Wert, ~Wert), Anker bei Start 0x814000 | zwei Bereiche aus dem Deskriptor (0–0xFBFF, 0x20000–Flashende) |
| 3 | Byte-Reihenfolge | 16-Bit-Wörter LE, Ergebnis 32 Bit | Standard-CRC-32 (gespiegelt, 0xEDB88320), Einträge LE | Bytesumme, Wert + Komplement LE | CRC-32 wie zlib | 16-Bit-Wörter LE, Wert + Komplement | 16-Bit-Wörter LE, Wert + Komplement am Dateiende − 0x20 |
| 4 | Unabhängiger Vergleich | ME7Sum-Quelltext (gelesen); Herstellerwerte | ME7Sum; Tabelle aus zlib unabhängig erzeugt | ME7Sum; Herstellerwert | nur ME7Sum, **kein Original mit diesem Feld** | ME7Sum; zugleich Multipoint-Einträge (unabhängig belegt) | ME7Sum; Herstellerwert |
| 5 | Unveränderte Referenzen | 1 (ME7.5 8E0909518AK, Herkunft nicht dokumentiert) | 1 | 1 | 0 | 1 (+ Multipoint-Nachweis) | 1 |
| 6 | Erkennung von Änderungen | je 1 Byte im Bereich → genau die abdeckenden Prüfungen falsch (synthetisch und am Original) | ja | ja | synthetisch nicht belegt | über Multipoint | ja |
| 7 | Falsch-Positive | keine auf ME9, MED9.1, EDC17CP09, EDC16C31/C35, MS43, MS45, MSD80, MSD85, MED17, Zufall, Nullen, 0xFF | ebenso | ebenso | ebenso | ebenso | ebenso |
| 8 | Grenzfälle | gekürzte/vergrößerte Datei, falscher Kopf → „nicht gefunden“ | ohne Code-Verweis über Tabellenanfang; mehr als 2 Tabellen → nicht gefunden | mehrdeutige Verweise → nicht gefunden | 3 Ablageorte nötig, sonst nicht gefunden | zweiter Anker → nicht gefunden; ungültiger Vorgänger beendet die Kette | zweiter Deskriptor oder Wert ≠ ~Komplement → nicht gefunden |
| 9 | Laufzeit/Speicher | gesamt +14 ms auf ME7.5 (1 MiB), höchstens +64 ms auf anderen Dateien, kein zusätzlicher Spitzenspeicher (§ 4) | | | | | |
| 10 | Tests | `tests/test_me7_checksums.py` (40, synthetisch, mit zweiter, einfacher Implementierung), `tests/test_integrity_reference.py` (Opt-in) | | | | | |

**Einstufung:**
- ROMSYS (3 Werte), CRC-Tabelle, Hauptdaten-Prüfsumme und Hauptprogramm: **am Original gemessen**. Die
  gespeicherten Werte eines unveränderten ME7.5-Originals werden exakt reproduziert, und das Verfahren stimmt mit
  ME7Sum überein. Das ist **kein** unabhängiger Nachweis im Sinne dieser Seite: Es gibt nur eine Datei mit
  undokumentierter Herkunft, keinen zweiten Softwarestand und keinen Lauf eines zweiten Werkzeugs. Deshalb gilt:
  - nur Prüfung;
  - der Status bleibt „Unvollständige Prüfung“;
  - eine Korrektur ist gesperrt.
- Hauptdaten-CRC32: **nicht validiert**. Implementiert, aber auf keinem Original gefunden. Zählt nur, wenn ein
  geöffnetes Original den gespeicherten Wert selbst reproduziert. Indirekte CRC-Blöcke (`FindIndirectCRCBlks`) sind
  **nicht unterstützt**. Fehlt die CRC, steht sie im Bericht als ungeprüft.
- Hintergrund-Prüfsummen: Ihre Deskriptoren haben genau das Format eines Multipoint-Eintrags (gleiches Feld, gleiche
  Wortsumme). Sie sind deshalb seit 1.20.0 als Multipoint-Einträge geprüft und korrigierbar. Das neue Verfahren
  meldet sie nicht doppelt, sondern verweist auf den Multipoint-Eintrag.
- Gemessen auf ME7.5 8E0909518AK: 8 von 8 Werten reproduziert, davon 2 (Hintergrund) bereits über Multipoint.

| Prüfung | Prüffeld | gespeichert = berechnet |
|---|---|---|
| ROMSYS Startup | 0x8038 | 0x0000FB39 |
| ROMSYS ParamPage | 0x1E4FA | 0x0000971D |
| ROMSYS ProgramPages (120 Seiten) | 0x803C | 0x009B5F0C |
| CRC-Tabelle (über Code-Verweis) | 0x1D40A | Standardtabelle |
| Hauptdaten-Prüfsumme (4 Blöcke) | 0x9FEE6 | 0x008BBA6B |
| Hintergrund 1 / 2 | 0x14230 / 0x14240 | 0x0CFD55CC / 0x004DE5DC |
| Hauptprogramm | 0xFFFE0 | 0xB46D0EA8 |

**Zusammenspiel mit der Multipoint-Korrektur (neu, gilt für alle Verfahren):**
- **Simulation vor der Vorschau.** Die Korrekturvorschau rechnet das Ergebnis vorab vollständig nach. Würde eine
  Korrektur eine bisher stimmende Prüfsumme irgendeines Verfahrens falsch machen, wird sie insgesamt verweigert,
  mit Begründung. Beispiel: ein Multipoint-Feld auf einem Wort, das ROMSYS ProgramPages summiert.
- **Nicht korrigierte ME7-Prüfsummen bleiben sichtbar.** Ändert eine Bearbeitung Bytes, die auch ME7-Prüfsummen
  abdecken, korrigiert die Multipoint-Korrektur nur die Multipoint-Felder. Die ME7-Prüfsummen bleiben als Fehler
  stehen, und die Vorschau warnt ausdrücklich: Die Datei bleibt „Unterstützt und ungültig“ und ist nicht
  flashbereit.
- **Gemessen auf ME7.5:** Ein Datenwort im größten Multipoint-Bereich wurde geändert. Danach sind 3 Multipoint-Einträge
  sowie ROMSYS ProgramPages und Hauptprogramm falsch. Nach der Korrektur stimmen die Multipoint-Einträge, die beiden
  ME7-Prüfsummen bleiben falsch, der Status ist „ungültig“. Nach dem Zurücksetzen des Wortes und erneuter Korrektur
  ist die Datei bitgleich mit dem Original, ohne Fehler.
- **Folge:** In 1.20.0 erschien dieselbe Datei nach der Korrektur als „unvollständig“, weil die ME7-Prüfsummen
  unbekannt waren. Jetzt wird sie richtig als ungültig gemeldet.

### MED17/EDC17 und EDC16 (am Original gemessen)

- **EDC17CP09:** 8 von 11 Strukturen reproduziert. Nachuntersuchung am 11.11.2026, nur gemessen, Code
  unverändert:
  - **Dataset #0:** CRC32 über 0x20000–0x7FEFF und ADD32 über 0x20CE4–0x2230F stimmen beide nicht. Alle anderen
    Blöcke stimmen. Das passt zu einem veränderten Kalibrierdatensatz. Zudem ist die Datei 1 Byte kürzer als 2 MiB
    (2 097 151 Byte). Ohne zweites Original ist das nicht entscheidbar; die Strukturen bleiben „nicht bestätigt“.
  - **Startup-Block, zweite Struktur:** Sie deckt 0x1FF00–0x1FFDF ab, also hinter dem deklarierten Blockende
    0x1FEFF. Sie reproduziert ihren Wert mit CRC32. Die Regel „Bereich liegt im Block“ bleibt trotzdem streng; erst
    ein zweites Original kann sie für diesen Bereich erweitern.
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

**Nach der ME7-Ergänzung (unveröffentlicht, 11.11.2026)**, gleiche Methode, Vergleich mit `main` (1.20.0) auf
demselben Rechner:

| Datei | ME7-Prüfungen | Status | Prüfung vorher → nachher | Speicherspitze |
|---|---|---|---|---|
| ME7.5 8E0909518AK | 6 stimmen (+2 über Multipoint) | unvollständig | 110 → 124 ms | 5,0 MiB (gleich) |
| ME9 770115XE | – | unvollständig | 114 → 122 ms | 5,0 MiB |
| MED9.1 1K090711S | – | unvollständig | 240 → 244 ms | 10,0 MiB |
| EDC17CP09 | – | unvollständig | 277 → 258 ms | 10,0 MiB |
| EDC16C31 | – | unvollständig | 527 → 591 ms | 22,4 MiB |
| EDC16C35 | – | unvollständig | 246 → 287 ms | 9,9 MiB |
| MS43 430069 | – | nicht unterstützt | 56 → 67 ms | 2,5 MiB |
| MSD80, MSD85 (je 256 KiB) | – | unbekannt | 29 → 34 / 27 → 34 ms | 1,3 MiB |
| MS45 | – | unbekannt | 109 → 118 ms | 5,0 MiB |
| MED17.1.62 (Kalibrierbereich) | – | unbekannt | 57 → 62 ms | 2,4 MiB |

Kein ME7-Verfahren schlägt auf einer Nicht-ME7-Datei an. Die Korrekturvorschau rechnet das Ergebnis jetzt vorab
nach. Dadurch dauert „Prüfung + Plan“ etwa doppelt so lange: ME7.5 139 → 305 ms, ME9 150 → 294 ms, MED9.1
299 → 584 ms. Kopie und Übernahme bleiben unverändert.

Korrekturlauf (ein Wort in der Mitte des größten Multipoint-Bereichs geändert; Werte von 1.20.0):

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
- ME7.x (unveröffentlicht): ROMSYS, CRC-Tabelle, Hauptdaten-Prüfsumme und Hauptprogramm werden geprüft, aber nur
  am Original gemessen, nicht korrigiert. Es fehlen:
  - die Hauptdaten-CRC32 (kein Original mit diesem Feld);
  - indirekte CRC-Blöcke;
  - ein zweiter Softwarestand;
  - ein Lauf eines zweiten Werkzeugs.

  Die RSA-Signatur wird nie verändert. ME7Sum prüft sie mit dem Schlüssel aus der Firmware selbst; das ist kein
  Vertrauensanker und wird nicht übernommen.
- MED17/EDC17, EDC16: Für die Korrektur fehlen eine unabhängige Referenz und die signierte OEM-Bescheinigung.
- Siemens/Continental (MS4x, MSD8x, MS45, Simos, SID): kein Verfahren implementiert (Status „Nicht unterstützt“).
- Die Referenzdateien außer MS43 haben keine dokumentierte Herkunft. Deshalb wurden sie nur lokal gemessen. Eine
  unabhängige Bestätigung mit rechtmäßig bereitgestellten Originalen (zwei Softwarestände je Familie) steht aus.
- Signaturen werden nur als vorhanden/erwartet ausgewiesen. Es gibt keine Umgehung, Fälschung oder Änderung.
  Digitale Herstellersignaturen werden nicht geprüft.
- EDC17CP09: 3 von 11 Strukturen bleiben unbestätigt. 2 stimmen am Original nicht, 1 liegt außerhalb des Blocks.
- Keine der untersuchten Originaldateien hat eine vollständige Checksummenabdeckung. ECU Studio AI erteilt keine
  Flashfreigabe.
- Die Grenzwerte der Regel B (32/16 Einträge) sind eine Sicherheitsabwägung, keine Messgröße des Steuergeräts. Sie
  liegen deutlich unter den 63 Einträgen der ME9-Referenz und deutlich über zufälligen oder kleinen Tabellen. Die
  Grenzen selbst sind getestet (`tests/test_integrity_safety.py`):
  - 31 bestätigte Einträge bleiben gesperrt, 32 geben die gekennzeichnete Korrektur frei.
  - Eine größte Tabelle mit 15 Einträgen bleibt gesperrt, eine mit 16 nicht.
  - Ein einziger abgeleiteter Eintrag sperrt immer.
  - Regel A gilt nur bei eindeutiger Identifikation.
- Die ME9-Referenz wird von der Identifikation nicht erkannt (Familie leer). Eine bessere ME9-Identifikation würde
  sie von Regel B auf Regel A heben.

### Einstufung der Familien (11.11.2026)

| Familie | belegt (unabhängig) | experimentell / am Original gemessen | nicht validiert | unbekannt |
|---|---|---|---|---|
| ME7.x | Multipoint (inkl. Hintergrund-Prüfsummen) | ROMSYS, CRC-Tabelle, Hauptdaten-Prüfsumme, Hauptprogramm | Hauptdaten-CRC32, indirekte CRC-Blöcke | – |
| ME9, MED9 | Multipoint | – | – | weitere Prüfungen der Familie |
| MED17 | – | Bosch-Blockleser (auf EDC17CP09 gemessen) | auf MED17 selbst: nur Kalibrierabbilder ohne Blöcke vorhanden | Signaturblöcke (nur „erkannt“) |
| EDC17 | – | 8 von 11 Strukturen auf EDC17CP09 | Dataset #0, Struktur hinter dem Startup-Block | – |
| EDC16 | – | 1 von 1 Bereich auf C31 und C35 | – | weitere Prüfungen der Familie |
| MG1/MD1 | – | – | – | kein Verfahren, keine Datei |
| MS42/MS43 | – | – | – | kein Verfahren (MS43: „nicht unterstützt“) |
| MSD80/MSD85 | – | – | – | kein Verfahren (Teilabbilder: „unbekannt“) |
| Simos, SID | – | – | – | kein Verfahren, keine Datei |

### Lokale Referenztests ausführen

```
set ECU_STUDIO_CHECKSUM_REFERENCES=C:\pfad\checksum-references.json
python -m pytest tests/test_integrity_reference.py
```

Die Manifestdatei liegt außerhalb des Repositorys und enthält je Eintrag `name`, `bin`, `sha256`, `method`, `regions`
und `unproven`.

---

## 6. Signaturen (Architektur, unveröffentlicht)

Herstellersignaturen in der Firmware sind etwas anderes als Prüfsummen. Sie werden getrennt geführt
(`core/firmware_signatures.py`). Drei Arten von Signaturen werden nie vermischt:

| Art | Wo | Wer prüft |
|---|---|---|
| OEM-Firmwaresignatur | im Steuergeräte-Abbild, vom Hersteller | dieses Modul, nur mit vertrauenswürdigem Schlüssel |
| Authenticode | auf den Windows-Programmdateien von ECU Studio AI | Windows; die EXE ist derzeit nicht code-signiert |
| GitHub-Build-Attestation | Herkunft der Release-Dateien | `gh attestation verify` (Release-Workflow und Nutzer) |

**Sechs Status je Firmwaresignatur:**

| Status | Bedeutung |
|---|---|
| gültig | mit einem vertrauenswürdigen Schlüssel kryptographisch geprüft; die signierten Bytes sind unverändert |
| ungültig | mit einem vertrauenswürdigen Schlüssel geprüft; Daten oder Signatur sind verändert |
| Struktur erkannt, nicht geprüft | Ort und Verfahren bekannt, aber kein vertrauenswürdiger Schlüssel |
| erwartet, nicht gefunden | die Familie trägt üblicherweise eine Signatur; in der Datei nicht lokalisiert |
| nicht unterstützt | Signatur vorhanden, für ihr Verfahren gibt es keinen Prüfer |
| unbekannt | nichts bekannt |

**Regeln:**
- „Gültig“ und „ungültig“ gibt es nur nach einer echten kryptographischen Prüfung mit einem Schlüssel aus dem vom
  Nutzer ausdrücklich angegebenen Vertrauensspeicher. Jeder Schlüssel braucht eine angegebene Herkunft.
- Ein Schlüssel, der in der Firmware selbst steht, ist kein Vertrauensanker. Wer die Firmware ändert, kann ihn
  mit austauschen.
- Prüfer ohne Fremdbibliothek:
  - Ed25519 (RFC 8032, vorhandene Implementierung mit den RFC-Testvektoren);
  - RSASSA-PKCS1-v1_5 mit SHA-256 (RFC 8017), Modul mindestens 2048 Bit.
- Fehlerhafte Eingaben führen nie zu „gültig“, darunter falsche Länge, `s ≥ n`, gerader Exponent, kleiner Modul,
  anderer Hash und Bereich außerhalb der Datei.
- Eine Signatur ändert nie den Checksummenstatus. Eine gültige Signatur ist keine Flashfreigabe, eine
  Prüfsummenkorrektur ersetzt keine Signatur.
- Das Modul prüft nur. Es hat keine Funktion, die eine Signatur erzeugt, verändert, entfernt oder umgeht; ein Test
  sichert die öffentliche Schnittstelle ab.

**Stand der Familien:**
- Für keine Steuergerätefamilie ist ein Ort der Herstellersignatur nachweisbar lokalisiert. Es gibt auch keinen
  vertrauenswürdigen OEM-Schlüssel. Ergebnis wie bisher:
  - ME7.x: RSA-Signatur „erwartet“;
  - MED17/EDC17: „erwartet“, die Bosch-Blöcke *Tuning protection*, *Customer Tuning protection* und
    *Application Attestation* „Struktur erkannt“;
  - ME9/MED9 und EDC16: „unbekannt“.
- ME7Sum prüft die ME7-RSA-Signatur mit einem Schlüssel aus der Firmware selbst. Nach der Regel oben ergibt das
  höchstens „Struktur erkannt“, nie „gültig“. Deshalb ist es nicht übernommen.
- Belegt ist die Architektur mit **synthetischen** Testschlüsseln (`tests/test_firmware_signatures.py`). Ed25519
  aus einem festen Startwert; RSA mit 2048 Bit, im Test erzeugt und nirgends sonst verwendet.
