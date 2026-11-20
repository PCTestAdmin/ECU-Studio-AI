# ECU Studio AI 1.21.0-rc1 – Release Notes

**Release Candidate (Vorabversion) vom 20.11.2026 – zum Testen, nicht für den produktiven Einsatz.**
**Release candidate (pre-release) of 20.11.2026 – for testing, not for production use.**

Inhalt: [PR #29](https://github.com/PCTestAdmin/ECU-Studio-AI/pull/29). Messwerte, Datensätze und ihr
Validierungsstatus: [Entwicklungsbericht 1.21.0](ENTWICKLUNG_1.21.0.md). Gesamtstand: [Roadmap](../ROADMAP.md).

---

## Deutsch

Diese Vorabversion (Release Candidate) ist für Praxistests mit weiteren Steuergerätedateien gedacht, nicht für den
produktiven Einsatz. Sie erkennt Kennfelder ohne Definition auf mehr Wegen als 1.20.1, vor allem in
TriCore-Programmen und in Datensätzen mit Kopf. Alle automatisch erkannten Kennfelder bleiben **ungeprüfte
Vorschläge**. Wo ein Datentyp nicht belegt ist, steht ein „?“ mit Grund. Messwerte nennen diese Notes bewusst
nicht: Sie stammen aus privaten Referenzdaten eines Datengebers und sind seit der ersten Holdout-Messung **nicht
mehr unabhängig bestätigt**. Sie stehen mit Datensatz und Validierungsstatus im Entwicklungsbericht.

### Kennfelderkennung ohne Definition

- **TriCore-Code:** Tabellen, die das Programm an Interpolationsroutinen übergibt, auch wenn der Code den
  Datenbereich an einer anderen Flash-Adresse erwartet (verlagerter Kalibrierbereich). Tabellen aus Zeigertripeln (Daten, X-Achse, Y-Achse).
  Achssuch-Routinen mit unbelegten Achsen (alle Stützstellen gleich). Die TriCore-Codeerkennung ist als
  experimentell gekennzeichnet.
- **Datensätze mit Kopf (Anzahl + Achsen):** gemischte Achsbreiten (8/16 Bit), vorzeichenbehaftete Bytes,
  Wertebreite aus der Grenze zum nächsten Datensatz, 16-Bit-Felder ausgerichtet zum Kopf, eine Byte-Reihenfolge je
  Abbild, wenn eine klare Mehrheit der Datensätze sie festlegt.
- **Weniger Fehlfunde:** Glätte-Lesarten, denen ein Datensatzkopf oder adressierte Einzelobjekte widersprechen,
  werden verworfen. Ein Datensatzkopf verdrängt keinen Fund mehr, den der Programmcode belegt.
- **Namensübertragung zwischen Softwareständen:** flache Blöcke (Nullen, ein einziger Wert) nur noch mit zwei
  übereinstimmenden Ankern. Übertragene Namen sind als „Name übertragen (ungeprüft)“ markiert.

### Achsen- und Datentypprüfung, Unsicherheitskennzeichnung

- **„?“ beim Datentyp**, wenn ihn nichts belegt: Wertebreite offen, Vorzeichen offen, Byte-Reihenfolge offen
  (die Datensätze eines Abbilds sind uneinig), nur aus der Glätte geschätzt oder nur aus dem Datensatzaufbau
  abgeleitet. Mehrere offene Fragen werden gleichzeitig genannt.
- **Vorzeichen:** Datensatz-Tabellen behalten die andere Lesart als offene Alternative, sobald das oberste Bit
  gesetzt ist. Bei TriCore-Tabellen gilt das Vorzeichen nur dann als belegt, wenn alle Tabellen-Ladebefehle der
  Interpolationsroutine in Breite **und** Vorzeichen übereinstimmen. Liest die Routine über denselben Zeiger
  unterschiedlich breite Werte (etwa Anzahl- oder Kopffelder), belegen diese Ladebefehle das Vorzeichen der Zellen
  nicht: Es steht dann „Vorzeichen nicht belegt“, und die andere Lesart bleibt sichtbar.
- **Byte-Reihenfolge:** Entscheidet keine Mehrheit der Datensätze eines Abbilds, steht „Byte-Reihenfolge nicht
  belegt“, statt still eine Reihenfolge zu wählen.

### Filter und Prüfhilfen

- **Kennfeldliste:** Filter „Datentyp nicht belegt (?)“ und „Überschneidet andere Einträge“. Von dir geprüfte
  Einträge stehen fett mit ✓; automatische Funde bleiben ungeprüft, bis du sie bestätigst.
- **Detailansicht:** alle offenen Fragen zum Datentyp, je Frage der fehlende Beleg (z. B. Programmcode, der die
  Werte vorzeichenbehaftet liest, oder eine Definition) und dieselben Bytes in jeder offenen Lesart als Rohwerte
  (min … max). Einträge, die sich Bytes mit dem gewählten Kennfeld teilen, werden mit Status genannt.
- **Prüfliste:** Filter nach Prüfgrund (Widerspruch, Datentyp nicht belegt, Achsen, Überschneidung, nur
  Datenmuster, experimentell) und Spalte „Fehlender Beleg“. Die Reihenfolge zählt Gründe; sie ist keine
  Wahrscheinlichkeit.
- **Vor dem Speichern/Flashen:** Jede Änderung in einem ungeprüften Kennfeldvorschlag ergibt einen gelben Befund.
  Vorschläge gelten nie als geprüfte Grundlage für Änderungen oder eine Flashfreigabe.

### Updates: Testkanal für Vorabversionen

- Der **stabile Update-Kanal** (Standard) bietet nie eine Vorabversion an, auch nicht, wenn ein Release falsch
  gekennzeichnet wäre.
- **Einstellungen → Testkanal: Vorabversionen (Release Candidates) anbieten …** schaltet nach einer Rückfrage den
  Testkanal ein. Er bietet die höchste Version aus stabilen Releases und Vorabversionen an; jedes Update fragt
  weiterhin vorher, wird per SHA-256 geprüft und lässt die vorherige Version als Sicherung zurück.
- Eine installierte Vorabversion bekommt im stabilen Kanal die zugehörige stabile Version angeboten, sobald sie
  erscheint. Die Versionsnummer `1.21.0-rc1` erscheint so in Fenstertitel, „Apps & Features“, Dateinamen und den
  Dateieigenschaften (Produktversion).
- Der Release-Workflow veröffentlicht einen Release Candidate nur als GitHub-Pre-Release, nie als „Latest“, und
  prüft danach, dass kein anderes Release verändert wurde.

### Registry- und Testisolierung

- Der Selbsttest nach einem Update arbeitet mit eigenen, danach gelöschten Einstellungen: Fensterposition und
  Dock-Anordnung bleiben erhalten.
- Testläufe, GUI-Smoke und Selbsttest verwenden isolierte Profile. Ohne nachweisbare Umleitung verweigert das
  Programm im Testprofil jeden Zugriff auf die echten Einstellungen, statt auf die Registry zurückzufallen. Der
  Eintrag in „Apps & Features“ wird im Testprofil nie geschrieben.

### Oberfläche, Laufzeit und Stabilität

- **Englische Oberfläche:** Prüfliste (Spalten, Prüfgründe, Priorität, Zähler), Detailansicht, Stufen und
  Detailzeilen des Preflight-Berichts sowie die Markierungen der Kennfeldliste („Name übertragen (ungeprüft)“,
  „Vorschlag“, „[geändert]“) erscheinen jetzt auf Englisch.
- **Laufzeit:** Die zusätzlichen Erkennungswege kosten etwas Rechenzeit je Vollflash; der Speicherbedarf bleibt
  gleich.
- **Stabilität:** Abgebrochene oder fehlgeschlagene Test- und Selbsttestläufe hinterlassen keine Einstellungsdateien
  und keine Laufordner.

### Installation

- **Von 1.20.1 oder älter:** Installer `ECU-Studio-AI-1.21.0-rc1-setup.exe` oder ZIP aus diesem Release verwenden.
  Die Update-Prüfung von 1.20.1 kennt keinen Testkanal und bietet diese Vorabversion nicht an. Projekte und
  Einstellungen bleiben erhalten.
- **Prüfen:** Zu jedem Paket gehört eine `.sha256`-Datei; die Build-Herkunft lässt sich mit
  `gh attestation verify <Datei> --repo PCTestAdmin/ECU-Studio-AI` prüfen. Die Dateien sind **nicht
  Authenticode-signiert**; Windows kann beim ersten Start warnen.

### Bekannte Einschränkungen

- **Testversion:** keine Empfehlung für produktive Fahrzeugkalibrierungen.
- **Automatisch erkannte Kennfelder sind ungeprüfte Vorschläge**, bis du sie selbst geprüft hast.
- **Keine neue unabhängige Validierung:** Die Verbesserungen dieser Version sind nur an den Referenzdaten eines
  Datengebers gemessen; nach der ersten Holdout-Messung wurden diese Daten nur noch als Regressionstest verwendet.
- **MEVD17.2.3:** Auf Vollflashs bleiben Fehlzuordnungen, dort mehr als mit 1.20.1.
- **MSV90:** Byte-Reihenfolge und Vorzeichen sind nicht immer sicher bestimmt; sie sind dann mit „?“ markiert.
- **Viele automatisch erkannte Datentypen bleiben ungeprüft** („?“). Ein Datentyp ohne „?“ ist ebenfalls nur ein
  Vorschlag.
- **Checksummen nur teilweise unterstützt**, **keine allgemein vertrauenswürdige OEM-Signaturvalidierung** und
  **keine automatische Flashfreigabe**.
- Kein Modelltraining mit den privaten Firmwaredaten des Datengebers; Ghidra und REA wurden nur extern zur Analyse
  verwendet und sind nicht Teil des Programms.
- **Rückmeldung:** Wer eigene Originaldateien mit passender Definition (A2L/XDF) rechtmäßig nutzen darf, kann die
  Erkennung lokal messen (`python -m ecu_studio.tools.validate_pair`, nur Zählwerte, nichts wird hochgeladen; siehe
  [Referenzvalidierung](REFERENCE_VALIDATION.md)) und das Ergebnis über die Vorlage „Erkennungsbericht“ schicken.
  Bitte keine Firmware- oder A2L-Dateien anhängen.

---

## English

This pre-release (release candidate) is meant for practical tests with further ECU files, not for production use.
It detects maps without a definition in more ways than 1.20.1, mainly in TriCore programs and in records with a
header. All automatically detected maps remain **unchecked suggestions**. Where a data type is not backed by
evidence, a "?" with the reason is shown. These notes deliberately give no measurements: they come from private
reference data of one data provider and have **not been independently confirmed since the first holdout
measurement**. They are listed with data set and validation status in the development report.

### Map detection without a definition

- **TriCore code:** tables the program passes to interpolation routines, also when the code expects the data area
  at another flash address (relocated calibration area). Tables from pointer triples (data, X axis, Y axis). Axis lookup routines with unapplied
  axes (all breakpoints equal). TriCore code detection is marked as experimental.
- **Records with a header (count + axes):** mixed axis widths (8/16 bit), signed bytes, value width from the
  boundary to the next record, 16-bit fields aligned to the header, one byte order per image when a clear majority of
  the records fixes it.
- **Fewer false finds:** smoothness readings contradicted by a record header or by individually addressed objects
  are dropped. A record header no longer displaces a find backed by program code.
- **Name transfer between software versions:** flat blocks (zeros, a single value) only with two matching anchors.
  Transferred names are marked "name transferred (unchecked)".

### Axis and data type checks, uncertainty marking

- **"?" at the data type** when nothing backs it: value width open, sign open, byte order open (the records of an
  image disagree), estimated from smoothness only, or derived from the record layout only. Several open questions
  are shown together.
- **Sign:** record tables keep the other reading as an open alternative as soon as the top bit is set. For TriCore
  tables the sign counts as proven only when all table loads of the interpolation routine agree in width **and**
  sign. When the routine reads values of different widths through the same pointer (e.g. count or header fields),
  these loads do not prove the sign of the cells: "sign not proven" is shown and the other reading stays visible.
- **Byte order:** when no majority of the records of an image decides it, "byte order not proven" is shown instead of
  silently choosing one.

### Filters and review aids

- **Map list:** filters "data type not proven (?)" and "overlaps other entries". Entries you checked are shown in bold
  with ✓; automatic finds stay unchecked until you confirm them.
- **Detail view:** all open questions about the data type, for each the missing evidence (e.g. program code reading
  the values as signed, or a definition), and the same bytes in every open reading as raw values (min … max). Entries
  sharing bytes with the selected map are listed with their status.
- **Review list:** filter by review reason (contradiction, data type not proven, axes, overlap, data pattern only,
  experimental) and a "missing evidence" column. The order counts reasons; it is not a probability.
- **Before saving/flashing:** every change inside an unchecked map suggestion produces a yellow finding. Suggestions
  never count as a checked basis for changes or a flash release.

### Updates: test channel for pre-releases

- The **stable update channel** (default) never offers a pre-release, not even if a release were marked wrongly.
- **Settings → Test channel: offer pre-releases (release candidates) …** switches the test channel on after a
  confirmation. It offers the highest version among stable releases and pre-releases; every update still asks first,
  is verified by SHA-256 and keeps the previous version as a backup.
- An installed pre-release is offered the matching stable version on the stable channel as soon as it appears. The
  version number `1.21.0-rc1` appears in the window title, "Apps & Features", the file names and the file properties
  (product version).
- The release workflow publishes a release candidate only as a GitHub pre-release, never as "Latest", and then checks
  that no other release was changed.

### Registry and test isolation

- The self-test after an update works with its own settings, deleted afterwards: window position and dock layout are
  kept.
- Test runs, GUI smoke and self-test use isolated profiles. Without a provable redirect the program refuses any access
  to the real settings in the test profile instead of falling back to the registry. The "Apps & Features" entry is
  never written in the test profile.

### Interface, run time and stability

- **English interface:** the review list (columns, review reasons, priority, counters), the detail view, the levels
  and detail lines of the preflight report and the markers of the map list ("name transferred (unchecked)",
  "suggestion", "[changed]") are now shown in English.
- **Run time:** the additional detection paths cost some computing time per full flash; memory use stays the same.
- **Stability:** aborted or failed test and self-test runs leave no settings files and no run folders behind.

### Installation

- **From 1.20.1 or older:** use the installer `ECU-Studio-AI-1.21.0-rc1-setup.exe` or the ZIP of this release. The
  update check of 1.20.1 has no test channel and does not offer this pre-release. Projects and settings are kept.
- **Verify:** every package comes with a `.sha256` file; the build provenance can be checked with
  `gh attestation verify <file> --repo PCTestAdmin/ECU-Studio-AI`. The files are **not Authenticode-signed**;
  Windows may warn on first start.

### Known limitations

- **Test version:** not a recommendation for production vehicle calibrations.
- **Automatically detected maps are unchecked suggestions** until you have checked them yourself.
- **No new independent validation:** the improvements of this version were measured only on the reference data of
  one data provider; after the first holdout measurement these data were used as a regression test only.
- **MEVD17.2.3:** mismatches remain on full flashes, more than with 1.20.1.
- **MSV90:** byte order and sign are not always determined reliably; they are then marked with "?".
- **Many automatically detected data types stay unproven** ("?"). A data type without "?" is a suggestion too.
- **Checksums only partly supported**, **no generally trustworthy OEM signature validation** and **no automatic
  flash release**.
- No model training with the data provider's private firmware data; Ghidra and REA were used only externally for
  analysis and are not part of the program.
- **Feedback:** if you may lawfully use your own original files with a matching definition (A2L/XDF), you can measure
  the detection locally (`python -m ecu_studio.tools.validate_pair`, counts only, nothing is uploaded; see
  [reference validation](REFERENCE_VALIDATION.md)) and send the result with the "Erkennungsbericht" (detection report) template. Please do
  not attach firmware or A2L files.
