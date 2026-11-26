# ECU Studio AI 1.21.0-rc2 – Release Notes

**Experimentelle Vorabversion (Release Candidate) vom 26.11.2026 – zum Testen, nicht für den produktiven Einsatz.**
**Experimental pre-release (release candidate) of 26.11.2026 – for testing, not for production use.**

Inhalt: [PR #30](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/30). Messwerte, Datensätze und ihr
Validierungsstatus: [Entwicklungsbericht nach 1.21.0-rc1](ENTWICKLUNG_NEXTGEN.md). Freigabestand:
[Release-Bereitschaft rc2](RELEASE_READINESS_RC2.md). Gesamtstand: [Roadmap](../ROADMAP.md).

---

## Deutsch

Diese Vorabversion (Release Candidate) ist für Praxistests gedacht, nicht für den produktiven Einsatz. Gegenüber
1.21.0-rc1 nutzt die Erkennung ohne Definition mehr Belege aus dem Programmcode (TriCore, experimentell), kennzeichnet
offene Datentypfragen häufiger mit „?“, zeigt zu Achsen und Funktionen den Beleg und prüft jede Bearbeitung zentral,
bevor Bytes geschrieben werden. Alle automatisch erkannten Kennfelder, Achsen und Funktionsnamen bleiben
**ungeprüfte Vorschläge**. Messwerte nennen diese Notes bewusst nicht: Sie stammen aus privaten Referenzdaten eines
Datengebers und sind **nicht unabhängig bestätigt**. Sie stehen mit Datensatz und Validierungsstatus im
Entwicklungsbericht.

### Auf einen Blick

- **Schreibprüfung mit echter Zellbreite der Achsen:** gespeicherte Achsen werden mit ihrer tatsächlichen Breite
  (8, 16 oder 32 Bit, Float32) geschützt, nicht mehr pauschal mit 2 Byte je Stützstelle.
- **Zentrale Schreibprüfung** für jede Änderung von Bytes, mit Ablehnung statt Bestätigung bei unklaren gemeinsamen
  Achsen.
- **Lokaler Erkennungstest mit Assistent** in der Oberfläche (Werkzeuge-Menü).
- **Datenschutzfreundliche Testerberichte:** nur gerundete Zählwerte, Vorschau vor dem Speichern, nichts wird gesendet.
- **Erkennung ohne Definition:** mehr Belege aus dem Programmcode (TriCore, experimentell), mehr offene Datentypen
  mit „?“, Achsidentität und Funktionshypothesen mit Beleg.
- **Stabilität:** Schreibprüfung auch bei sehr großen Definitionen ohne spürbare Wartezeit je Eingabe; Analyse im
  Assistenten abbrechbar, Schließen während der Analyse sicher.
- **Geprüfte Installations- und Update-Wege** auf frischen Windows-Server-2022/2025-Systemen, einschließlich des
  Updates von 1.21.0-rc1 über den Testkanal.

### Kennfelderkennung ohne Definition

- **Programmcode als Beleg (TriCore, experimentell):** Adressen, die der Code direkt lädt, beginnen ein eigenes
  Objekt; eine nur aus dem Werteverlauf gefundene Fläche, in der eine solche Adresse liegt, wird verworfen. Ein
  Fund mit Codebeleg wird nicht mehr von einem reinen Datenmuster verdrängt.
- **Achsen und Kennlinien aus dem Code:** Liest eine Interpolationsroutine einen Kopf als Achse, gilt er auch mit
  wiederholten oder ganz gleichen Stützstellen als Achse, wenn dieselbe Routine an vielen Aufrufen dieselbe Breite
  zeigt. Routinen, die Kennlinien aus ihrem eigenen Datensatz interpolieren, benennen je Aufruf eine Kennlinie.
  Achsen solcher Kennlinien kommen nur mit der Kennlinie; eine verwaiste Achse braucht mindestens drei Stützstellen.
- **Weniger Fehlfunde:** Köpfe verketteter Kennlinien-Datensätze widerlegen Datenmuster, die in ihnen beginnen.
- **Breite aus der Lücke:** Passt in eine Lücke sowohl eine 16-Bit-Tabelle als auch zwei Bytetabellen, entscheiden
  mehrere Aufrufe derselben Routine; eine einzelne Passung ist nur eine schwache Stimme.

### Datentyp, Achsen und Funktionen

- **Datentyp mit Status und Quelle:** Wertebreite, Vorzeichen und Byte-Reihenfolge tragen „bestätigt“,
  „abgeleitet“, „alternativ“ oder „unbestimmt“ mit Beleg. Mehr offene Fälle tragen „?“ statt einer stillen Wahl:
  16-Bit-Achsen, deren Bytes auch einzeln steigen, Kennlinien ohne Datensatz dahinter, Achsen gegen die Mehrheit
  der Datensätze. Ist die Byte-Reihenfolge offen, ist auch das Vorzeichen offen.
- **Umrechnung mit Herkunft:** Faktor, Offset und Einheit nennen ihre Quelle; erkannte Tabellen bleiben Rohwerte.
- **Achsenreferenzen und Achsidentität:** Jede Achse ist „gespeichert“, „fest“ oder „ungeklärt“. Eine gemeinsame
  Achse ist „eindeutig gemeinsam“ (Definition), „plausibel gemeinsam“, „wertgleich“ oder „unbekannt“. Gleiche
  Werte verbinden nie zwei Achsen; eine wertgleiche Kopie an anderer Adresse macht die Identität „unbekannt“.
- **Funktionsebene (Prototyp):** Für Tabellen ohne Definition eine Funktionshypothese mit Status und Belegen (gemeinsame
  Achse, gleiche Coderoutine, Nachbarschaft zu Tabellen bekannter Funktion). Ohne ausreichenden Beleg bleibt die
  Funktion „unbekannt“; die zurückgehaltene Funktion und der fehlende Beleg werden genannt.
- **Prüfhilfen:** Filter „Gemeinsame Achse“, „Achsenreferenz ungeklärt“, „Funktion unbekannt“, „Funktion vermutet“,
  „Widersprüchliche Funktionsbelege“; Funktionsgraph mit Beziehungen aus dem Programmcode.

### Sichere Bearbeitung

- **Zentrale Schreibprüfung:** Jede Änderung der Bytes – Zelle, Hexansicht, Fläche, Stapel, Rezept, Übertragung,
  Wiederherstellung, Checksummenkorrektur – wird unmittelbar vor dem Schreiben geprüft. Betrifft sie andere Kennfelder
  oder eine gespeicherte Achse, werden alle betroffenen Kennfelder und Adressen gezeigt und müssen bestätigt werden.
- **Abgelehnt statt bestätigt:** Schreiben in eine gemeinsame Achse mit unbekannter Identität wird abgelehnt; eine
  weitere Bestätigung hebt das nicht auf. Freigegeben wird nur nach einer technischen Klärung mit Speicherbereich,
  Punktzahl, Zellbreite, Nutzern und Herkunft. Die Klärung verfällt, wenn sich Firmware, Layout oder Nutzer ändern.
- **Zellbreite gespeicherter Achsen (neu in rc2):** Der Zelltyp einer Achse ist ein eigenes Merkmal und kommt aus
  der Definition (A2L-`AXIS_PTS`/`RECORD_LAYOUT`, XDF einschließlich Stützstellenabstand) oder aus der Erkennung,
  die die Achse mit dieser Breite gelesen hat – nie aus dem Datentyp der Kennfeldwerte. Geschützt wird der
  tatsächliche Speicherbereich; Schreiben in die obere Hälfte einer 32-Bit- oder Float-Achse ist jetzt ein
  Achskonflikt. Ist die Breite unbekannt (etwa in Projekten aus älteren Versionen), wird vorsichtig mit 4 Byte je
  Stützstelle geschützt; widersprechen sich Breiten, wird der Widerspruch angezeigt und eine gemeinsame Achse
  abgelehnt. Eine Klärung verwendet ihre Zellbreite, kann eine belegte Breite nicht verkleinern und verfällt auch,
  wenn sich die Breite ändert. Im Definitionsdialog muss der Zelltyp einer Achse ausdrücklich gewählt werden.
- **Widersprüchliche Rezepte** (zwei Schritte schreiben dieselben Bytes) werden vor dem Schreiben abgelehnt.
- Original, Rückgängig und Wiederholen bleiben unverändert; es wird nichts auf andere Adressen kopiert.

### Lokaler Erkennungstest für Tester

- **Werkzeuge → Kennfelderkennung überprüfen (lokaler Test) …** führt in sieben Schritten durch die Messung mit
  eigener Firmware und passender Definition (A2L, XDF oder CSV): Dateiprüfung, Passungsprüfung, Analyse im
  Hintergrund mit Abbruch, Ergebnis, Export mit vollständiger Vorschau und freiwilliges Feedback mit festen
  Antworten.
- Exportiert werden nur gerundete Zählwerte, erst nach Häkchen und Wahl eines Dateinamens; vorhandene Dateien
  werden nie überschrieben. Das Programm sendet nichts.
  Anleitung: [deutsch](BETA_TESTER_ANLEITUNG.md), [englisch](BETA_TESTER_GUIDE.md).

### Installation

- **Von 1.21.0-rc1 mit eingeschaltetem Testkanal:** Das Update wird im Programm angeboten; es fragt vorher, wird per
  SHA-256 geprüft und lässt die vorherige Version als Sicherung zurück.
- **Von 1.20.1 oder älter:** Installer `ECU-Studio-AI-1.21.0-rc2-setup.exe` oder ZIP aus diesem Release verwenden.
  Der stabile Kanal bietet diese Vorabversion nicht an. Projekte und Einstellungen bleiben erhalten.
- **Prüfen:** Zu jedem Paket gehört eine `.sha256`-Datei; die Build-Herkunft lässt sich mit
  `gh attestation verify <Datei> --repo PCTestAdmin/ECU-Studio-AI` prüfen. Die Dateien sind **nicht signiert**
  (weder Authenticode noch Update-Signatur); Windows kann beim ersten Start warnen.

### Bekannte Einschränkungen

- **Testversion:** keine Empfehlung für produktive Fahrzeugkalibrierungen. Keine Zusage zur Erkennungsgenauigkeit
  und keine Zertifizierung für bestimmte Firmware oder Steuergeräte.
- **Achsen ohne Typangabe** (z. B. aus Projekten von rc1 oder älter) werden mit 4 Byte je Stützstelle geschützt; das
  kann zusätzliche Rückfragen oder Ablehnungen auslösen. Abhilfe: Definition neu importieren oder den Zelltyp im
  Definitionsdialog angeben.
- **Keine neue unabhängige Validierung:** Alle Verbesserungen sind nur an den Referenzdaten eines Datengebers
  gemessen. Nach der ersten Holdout-Messung wurden diese Daten nur noch als Regressionstest verwendet. Unabhängige
  Referenzdaten anderer Steuergerätefamilien fehlen weiterhin.
- **TriCore-Codeerkennung, Kennlinien aus dem Code und Funktionsebene sind experimentell.**
- **Gemeinsame Achsen werden bei MEVD17.2 kaum gefunden**, weil die Tabellen, die sie nutzen, oft nicht erkannt
  werden. Viele gemeinsame Achsen bleiben „unbekannt“ und sind dann nicht beschreibbar, bis sie technisch geklärt
  sind.
- **Datentypen:** Ein Teil falscher Breiten und Vorzeichen bei Achsen und Kennlinien bleibt unmarkiert, weil die Werte
  beide Lesarten nicht unterscheiden. Ein Datentyp ohne „?“ ist ebenfalls nur ein Vorschlag.
- **Bearbeitung großer Definitionen:** Die Schreibprüfung kostet bei sehr vielen Kennfeldern etwas Zeit je Zelle.
- **Checksummen nur teilweise unterstützt**, **keine allgemein vertrauenswürdige OEM-Signaturvalidierung** und
  **keine automatische Flashfreigabe**.
- Kein Modelltraining mit den privaten Firmwaredaten des Datengebers.

---

## English

This pre-release (release candidate) is meant for practical tests, not for production use. Compared with 1.21.0-rc1,
detection without a definition uses more evidence from program code (TriCore, experimental), marks open data type
questions with "?" more often, shows the evidence for axes and functions, and checks every edit centrally before bytes
are written. All automatically detected maps, axes and function names remain **unchecked suggestions**. These notes
deliberately give no measurements: they come from private reference data of one data provider and are **not
independently confirmed**. They are listed with data set and validation status in the development report.

### At a glance

- **Write check with the real cell width of axes:** stored axes are protected with their actual width (8, 16 or 32 bit,
  float32), no longer with a flat 2 bytes per breakpoint.
- **Central write check** for every change of bytes, refusing instead of confirming when a shared axis is unclear.
- **Local detection test with an assistant** in the user interface (Tools menu).
- **Privacy-friendly tester reports:** rounded counts only, preview before saving, nothing is sent.
- **Detection without a definition:** more evidence from program code (TriCore, experimental), more open data types
  marked with "?", axis identity and function hypotheses with evidence.
- **Stability:** the write check stays responsive per input even with very large definitions; the analysis in the
  assistant can be cancelled and closing during the analysis is safe.
- **Tested installation and update paths** on fresh Windows Server 2022/2025 systems, including the update from
  1.21.0-rc1 through the test channel.

### Map detection without a definition

- **Program code as evidence (TriCore, experimental):** addresses the code loads directly start an object of their
  own; a surface found only from the course of values that contains such an address is dropped. A find backed by code
  is no longer displaced by a pure data pattern.
- **Axes and curves from code:** when an interpolation routine reads a header as an axis, it counts as an axis also
  with repeated or all-equal breakpoints, if the same routine shows the same width at many calls. Routines that
  interpolate curves from their own record name one curve per call. Axes of such curves come only together with the
  curve; an orphaned axis needs at least three breakpoints.
- **Fewer false finds:** headers of chained curve records refute data patterns that start inside them.
- **Width from the gap:** when both one 16-bit table and two byte tables fit a gap, several calls of the same routine
  decide; a single fit is only a weak vote.

### Data type, axes and functions

- **Data type with status and source:** value width, sign and byte order carry "confirmed", "derived", "alternative"
  or "undetermined" with evidence. More open cases carry "?" instead of a silent choice: 16-bit axes whose bytes also
  rise one by one, curves without a record behind them, axes against the majority of records. When the byte order is
  open, the sign is open too.
- **Conversion with origin:** factor, offset and unit name their source; detected tables stay raw values.
- **Axis references and axis identity:** every axis is "stored", "fixed" or "unresolved". A shared axis is "clearly
  shared" (definition), "plausibly shared", "value-equal" or "unknown". Equal values never join two axes; a
  value-equal copy at another address makes the identity "unknown".
- **Function layer (prototype):** for tables without a definition, a function hypothesis with status and evidence
  (shared axis, same code routine, neighbourhood of tables with a known function). Without enough evidence the function
  stays "unknown"; the held-back function and the missing evidence are named.
- **Review aids:** filters "shared axis", "axis reference unresolved", "function unknown", "function suspected",
  "contradicting function evidence"; function graph with relations from program code.

### Safe editing

- **Central write check:** every change of bytes – cell, hex view, surface, batch, recipe, transfer, restore,
  checksum correction – is checked right before writing. When it affects other maps or a stored axis, every affected
  map and address is shown and must be confirmed.
- **Refused instead of confirmed:** writing into a shared axis of unknown identity is refused; another confirmation
  does not lift that. It is released only after a technical clarification with storage range, point count, cell
  width, users and origin. The clarification expires when firmware, layout or users change.
- **Cell width of stored axes (new in rc2):** the cell type of an axis is a property of its own and comes from the
  definition (A2L `AXIS_PTS`/`RECORD_LAYOUT`, XDF including the distance between breakpoints) or from the detection
  that read the axis with that width – never from the data type of the map values. The actual storage range is
  protected; writing into the upper half of a 32-bit or float axis is now an axis conflict. When the width is unknown
  (for example in projects from older versions), it is protected cautiously with 4 bytes per breakpoint; when widths
  contradict each other, the contradiction is shown and a shared axis is refused. A clarification uses its cell
  width, cannot narrow a stated width and also expires when the width changes. In the definition dialog the cell type
  of an axis must be chosen explicitly.
- **Contradicting recipes** (two steps write the same bytes) are refused before writing.
- Original, undo and redo are unchanged; nothing is copied to other addresses.

### Local detection test for testers

- **Tools → Check map detection (local test) …** guides through the measurement with your own firmware and a matching
  definition (A2L, XDF or CSV) in seven steps: file check, fit check, analysis in the background with cancel, result,
  export with a complete preview and voluntary feedback with fixed answers.
- Only rounded counts are exported, and only after ticking the box and choosing a file name; existing files are never
  overwritten. The program sends nothing.
  Guide: [English](BETA_TESTER_GUIDE.md), [German](BETA_TESTER_ANLEITUNG.md).

### Installation

- **From 1.21.0-rc1 with the test channel switched on:** the update is offered in the program; it asks first, is
  verified by SHA-256 and keeps the previous version as a backup.
- **From 1.20.1 or older:** use the installer `ECU-Studio-AI-1.21.0-rc2-setup.exe` or the ZIP of this release. The
  stable channel does not offer this pre-release. Projects and settings are kept.
- **Verify:** every package comes with a `.sha256` file; the build provenance can be checked with
  `gh attestation verify <file> --repo PCTestAdmin/ECU-Studio-AI`. The files are **not signed** (neither
  Authenticode nor an update signature); Windows may warn on first start.

### Known limitations

- **Test version:** not a recommendation for production vehicle calibrations. No promise of detection accuracy and
  no certification for any particular firmware or ECU.
- **Axes without a type** (for example from projects of rc1 or older) are protected with 4 bytes per breakpoint; this
  can cause additional questions or refusals. Remedy: import the definition again or set the cell type in the
  definition dialog.
- **No new independent validation:** all improvements were measured only on the reference data of one data provider.
  After the first holdout measurement these data were used as a regression test only. Independent reference data of
  other ECU families are still missing.
- **TriCore code detection, curves from code and the function layer are experimental.**
- **Shared axes are rarely found on MEVD17.2**, because the tables using them are often not detected. Many shared axes
  stay "unknown" and cannot be written until they are clarified technically.
- **Data types:** some wrong widths and signs of axes and curves stay unmarked, because the values do not tell the two
  readings apart. A data type without "?" is a suggestion too.
- **Editing large definitions:** with very many maps the write check takes some time per cell.
- **Checksums only partly supported**, **no generally trustworthy OEM signature validation** and **no automatic flash
  release**.
- No model training with the data provider's private firmware data.
