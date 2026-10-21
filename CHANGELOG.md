## Unveröffentlicht (18.10.2026)

- Neue rasterfreie Strukturerkennung (`core/structure_scan.py`): Spaltenzahl und Zeilenzahl werden aus der Datenwiederholung abgeleitet statt aus festen Rastern (8×8, 16×16 …); 8/16 Bit, Little/Big Endian, robuste Ausreißer-Prüfung.
- C16x-Code-Referenzen (Seite+Offset-Ladebefehle) als exakte Start-Hinweise; trennt lückenlos gepackte Kennfelder. Auf MS43 nachgewiesen, auf MS42 ohne Wirkung (andere Adressierung).
- Blind gemessen gegen XDF-Referenzen (`tools/structure_benchmark.py`, nur Geometrie): MS43 430069 Trefferquote 4,5 % → 47 %, exakte Layouts 1 → 88; MS42 0110C6 13 % → 56 %, exakt 5 → 24. Präzision MS43 71 % → 70 %, MS42 72 % → 58 %.
- Bekannte Grenzen: monotone Ebenen ohne Zeilenumbruch-Sprung (z. B. MAF-Raster) und doppelte Spaltenzahl bei gleich großen Nachbarzeilen; Laufzeit 4–8 s statt ~1 s. `structure_limit=0` stellt das bisherige Verhalten her.
- Weiterhin keine Funktionsnamen oder Einheiten aus Rohdaten; Kandidaten bleiben „Unbekannt“ und ungeprüft.
- Achsen-Erkennung (`core/axis_arrays.py`): Stützstellen-Arrays mit vorangestellter Anzahl (8-Bit-Anzahl + 8-Bit-Werte, 16-Bit-LE-Anzahl + 16-Bit-Werte), nur in Ketten benachbarter Arrays. Gegen XDF: MS43 98 % gefunden bei 97 % Präzision, MS42 98,5 % bei 97 %. Achsen erscheinen als 1×n-Kandidaten.
- Achsen-Zuordnung über den Code (MS43: Y-Achse, X-Achse, dann Kennfeld werden nacheinander geladen): Größe und Rohachswerte verankerter Kennfelder kommen aus den Achsen; Kennlinien (eine Achse) werden als 1×n erkannt. Code-Verweise nur noch aus direkt benachbarten Seite/Offset-Befehlen.
- Neuer Stand MS43 (2D ≥ 4×4): Trefferquote 47 % → 68 %, exakte Layouts 88 → 197, Präzision 70 % → 77 %; 1D (Achsen/Kennlinien) 615 exakt bei 96,5 % Präzision. MS42: 2D unverändert 56 %, Präzision 58 % → 70 %; 1D 398 exakt bei 97 %. Benchmark bewertet 2D und 1D getrennt.
- Kennfelder mit zwei vom Code geladenen Achsen passieren die Oberflächen-Glattheitsprüfung auch flach/grob (die Achsen belegen die Form).
- Dateien ohne bekanntes Profil (`core/data_regions.py`): Code/Daten-Trennung über den Anteil kleiner Nachbardifferenzen je Block (128/256 Byte). Kandidaten, die nur auf Glätte beruhen, müssen überwiegend in Datenblöcken liegen. Simuliert durch Scan der ganzen MS42/MS43-Datei ohne Kalibrierfenster: 2D-Präzision MS42 38 % → 61 %, MS43 69 % → 74 %, ohne Verlust an Trefferquote. Für Carrera/RS 235/ARAP/Clio gibt es keine Referenz; dort ungemessen.
- Unbekannte Dateien: Zeilenabstand-Suche nur noch in Datenbereichen (1-MB-ME7: 45 s → 17–25 s). Vorzeichen-Ansichten `s8`/`s16` (Bosch-ME7-Zündkennfelder). Bosch ME7 (Volvo, öffentliche XDFs) als dritte Referenzfamilie: Trefferquote 5–10 % → 48–66 %, exakte Layouts weiterhin selten (2–6) – nächste Baustelle.
- Bosch ME7: Lookup-Aufrufe (`MOV R12/R13` = Kennfeld, `MOV R14/R15` = Achsdaten mit Anzahl-Präfix) liefern Start, Spaltenzahl und X-Achse; die Zeilenzahl kommt aus der Folgeachse oder der Datenanpassung (glattere Lesart gewinnt). 103–123 Kennfelder je Datei werden so im Code gefunden. Gegen die (unvollständigen) XDFs: Trefferquote 48–66 % → 54–71 %, exakte Layouts 2–6 → je 6. MS43/MS42 unverändert. Über den Code gefundene Achsen erscheinen auch ohne Kette als Achsen-Kandidaten (auch mit Vorzeichen).
- Kalibrierte Konfidenz (`core/confidence.py`, `tools/calibrate_confidence.py`): gemessene Trefferquote je Evidenzklasse (MS43+MS42): Code-Verweis+Achsen 100 % (n=227), Code ohne Achsen 97 %, Achsen-Arrays 97 % (n=1020), Code-Kennlinie 91 %, nur Datenglätte 30 %, altes Raster 27 %. Stufen gesichert/wahrscheinlich/Vermutung, unter 20 Beispielen „nicht kalibriert“; farbiger Punkt im Katalog.
- Flash-Preflight (`core/preflight.py`, Datei → Flash-Preflight, automatisch beim Export): Checksummenstatus, Änderungen im Programmcode, unveränderte Zwillinge/Überwachungskopien, nicht mehr aufsteigende Achsen, ungewöhnliche Sprünge, Änderungen außerhalb von Kennfeldern; Ampel mit Begründung.
- Funktionsgraph (`core/function_graph.py`, Werkzeuge → Funktionsgraph): Kennfelder je lesender C16x-Routine und mit gemeinsamen Achsen. MS43: 95 Gruppen, 594 Kennfelder, im Mittel 73 % der Mitglieder mit gleichem Funktionsstamm (z. B. Lambdaregelung, VANOS, Überwachung).
- Signal-Tracing (`core/signal_trace.py`): RAM-Eingänge vor jedem Kennfeldzugriff. MS43-Prüfung gegen Achsnamen: Ansauglufttemperatur 100 %, Kühlmitteltemperatur 80 %, Luftmasse 40 %, Drehzahl 31 % (je bei 0–8 % der anderen Kennfelder).
- Achsen-Semantik (`core/axis_semantics.py`): Skalierungshypothesen mit Rundheitskriterium; MS43 58 % erster Vorschlag, 78 % unter den ersten drei (nur MS43 messbar). Nur Hinweistext, keine automatische Einheit.
- Weitere Prozessoren (`core/cpu_refs.py`): 68HC11 (`LDX/LDY #`) und 8051 (`MOV DPTR,#`) mit automatischer Speicherbasis (HC11 über Reset-Vektor). Erkannt: ARAP/Clio HC11@0xC000, RS 235 HC11@0xE000. Diese Verweise bestätigen nur datenbasierte Kandidaten (eigene, nicht kalibrierte Evidenzklasse).
- CI: Zeilenenden der per Git-Hash festgenagelten Daten (`recognition/data/**`) werden nicht mehr umgewandelt (Ursache des fehlgeschlagenen GitHub-Laufs).
- Neue Referenzdaten (nur lokal genutzt, nicht im Repository): TunerPro Porsche/Renault/Peugeot (8-Bit), Hyundai SIM2K (TriCore, 9 Paare), BMW MSS54 (68k, Teil-Dumps), Subaru 5EAT.
- XDF-Textformat 1.x (`read_legacy_xdf`) und tolerantes XML (Latin-1-Zeichen, unmaskiertes `&`): Porsche- und alle Hyundai-XDFs sind jetzt lesbar.
- Achsen-Arrays nur noch in Ketten ab 4 Arrays: MS43/MS42 behalten 592/398 echte Achsen (Präzision 97,8 %/99,7 %), 75 Zufallsachsen auf alten 8-Bit-Steuergeräten entfallen. Vorzeichen-Lesart nur noch bei tatsächlich negativen Werten.
- Lernmodell für Datenmuster-Funde (`core/candidate_features.py`, `core/candidate_model.py`, `tools/train_candidate_model.py`): logistische Regression als JSON, 2684 gelabelte Kandidaten aus vier Familien. Familienweise geprüft (Familie beim Training ausgelassen): Präzision bei 80 % Trefferquote Hyundai 14 %→34 %, MSS54 7 %→32 %, alte 8-Bit 5 %→35 %, Siemens 29 %→50 % (AUC 0,83–0,92). Kandidaten mit Score < 0,042 (gemessen 0,4–0,7 % Treffer) werden ausgeblendet. MS43/MS42: Präzision 76 %→80 % bzw. 67 %→72 %, exakte Layouts unverändert.
- Konfidenz je Steuergerätefamilie kalibriert (MS43, MS42, unbekannte Dateien): z. B. Achsen-Arrays bei Siemens 98–100 %, bei unbekannten Dateien 18 %; Achsen-Header (nx,ny,X,Y,Z) bei unbekannten Dateien 87 %. XDF-Achsadressen zählen als Referenzobjekte.
- Offen: Code-Verweise für TriCore (Hyundai) und 68k/CPU32 (MSS54) – Daten werden dort über Basisregister adressiert; Laufzeit bei 2,6-MB-Dateien ~100 s.
- Oberfläche: Farbskala kalt→heiß für Heatmap (mit Werten, Achsen, Legende), Tabelle (Zellen eingefärbt, Nachkommastellen nach Skalierung) und 3D (gefüllte Fläche); eigene Liniensymbole in der Werkzeugleiste; überarbeitetes Hell/Dunkel-Theme. `tools/screenshot.py` rendert die Oberfläche offscreen.
- Repository: historische Berichte nach `docs/history/`, neue README, `.gitignore`/`.gitattributes` (keine Firmware, keine Build-Artefakte), GitHub-Actions-Workflow für pytest.
- Neue Referenzfamilien (öffentliche BIN/XDF-Paare, nur lokal genutzt): VAG ME7.5 (06A906032HS, 8E0909518AK), Opel E78 (PowerPC), GM P01 (68k), Volvo M4.4 (8051), Peugeot IAW 8P (XDF selbst spekulativ, nicht belastbar), Subaru 5EAT Denso (SH-2).
- C16x-Speicherbasis automatisch (`c16x_base`, Abstimmung über Lookup-Aufrufe mit gültiger Achse): VAG ME7.5 liegt bei 0x800000. ME7-Datensätze mit vorangestelltem Kopf (`[nx][ny][X][Y][Z]`, Kennlinien `[n][X][Z]`) werden an Code-Verweisen gelesen. VAG 06A906032HS: 2D exakt 16 → 50, Kennlinien exakt 5 → 132, Präzision 38 % → 46 %; 8E0909518AK: 2D exakt 16 → 37, Kennlinien 13 → 41.
- 68k-Absolutoperanden (`abs.L`, `#imm.L`, `m68k_targets`) als verankernde Code-Verweise; Kennlinien ohne Achsenkopf aus dem Abstand zweier referenzierter Adressen (`gap_curve`). GM P01: Trefferquote 21 % → 35 %, 2D exakt 1 → 10, Kennlinien 0 → 21. PowerPC (Opel E78) wird zu Recht nicht als 68k erkannt.
- Denso/SH-2-Beschreibungsblöcke (`pointer_descriptors`: Anzahl X/Y, Zeiger auf X-, Y-Achse und Daten, Typ-Byte; eigene Evidenzklasse `pointer:descriptor`): Subaru 5EAT Denso (9 ROMs) Trefferquote 35–53 % → 93–100 %, exakte Layouts 15–27 → 147–178. Die RomRaider-Definition ist eine Auswahl (147–183 von 250–317 Blöcken je ROM), daher keine Kalibrierung dieser Klasse (Untergrenze 58 %). Blöcke mit Typ 0 bleiben aus (Definition dort widersprüchlich). Auf allen anderen Familien kein einziger Fehltreffer.
- Mustersuche gebündelt und vektorisiert, identisches Ergebnis: MS43 14,5 → 6 s, 3-MB-Opel 67 → 32 s. 2D-Kennfelder und Kennlinien haben getrennte Ergebnisbudgets. Breitere Spaltenbereiche (bis 40, 17/33) gemessen und verworfen (MS42 exakt 22 → 15/18).
- Konfidenz neu kalibriert (MS43, MS42, Hyundai ×2, MSS54): Code-Kennlinie mit Achse 99 % (n=159), nur Datenmuster 19 % (n=732). Benchmark liest auch RomRaider-XML.
- Fehler behoben: Denso-Achsprüfung rechnete Differenzen vorzeichenlos (5 − 10 = 251 bei u8, 65531 bei u16), fallende oder zickzackförmige Achsen galten als aufsteigend. Jetzt mit breitem Datentyp; Regressionstests scheitern am alten Code. Messwerte unverändert (Subaru-Achsen sind Float).
- Flash-Preflight prüft jede geänderte Byteposition einzeln, ermittelt aus den Bytes selbst (nicht aus dem Bearbeitungsprotokoll). Behoben: Ein Änderungsbereich, der ein Kennfeld oder einen Datenblock nur berührte, verdeckte seine Bytes im Programmcode; über das Kalibrierfenster hinausragende Bereiche meldeten falsche Längen; mehr als 10 Code-Bereiche wurden stillschweigend abgeschnitten (jetzt mit Gesamtzahl). Ungeprüfte automatische Kandidaten entschuldigen keine Änderungen im vermuteten Code (gelb). Neues `checks_passed`: nur bei Grün UND verifizierten deklarierten Prüffeldern – ausdrücklich keine Flashfreigabe, da Profile unvollständig sein können; Bericht und Statusleiste sagen sonst „nicht flashbereit“. Prüfsummen werden auch bei unveränderter Datei geprüft.
- Checksummen: CRC-16/CCITT, 16/32-Bit-Wortsummen (BE/LE), 32-Bit-Doppelwortsummen, Einer-/Zweierkomplement, mehrere Teilbereiche je Prüffeld; gegen veröffentlichte Prüfwerte getestet. Verkettete oder überlappende Prüfbereiche werden abgelehnt. Korrektur vorbereitet: `plan_checksum_correction` verweigert, wenn das geprüfte Profil schon am Original nicht stimmt; `apply_checksum_correction` schreibt nur einen aktuellen Plan und setzt zurück, falls danach nicht alle Prüffelder stimmen. Noch nicht in der Oberfläche.
- Fehlalarm-Messung auf Daten ohne Kennfelder (Zufall, komprimiert, gelöscht): 0–5 Kandidaten, keiner höher als „Vermutung“.
- Laufzeit: Behoben, dass eine leere Datenbereichsliste (Datei ohne erkennbare Daten) die Mustersuche über die ganze Datei auslöste. Achsensuche vektorisiert, Fenster-Statistiken in O(n), Überlappungsprüfung per Binärsuche – alle Ergebnisse identisch (Regression über 11 reale Paare). 2 MB Zufallsdaten 38 → 7,5 s, gelöschter 512-KB-Flash 6 → 1,4 s, MS43 6,0 → 4,5 s, ME7 19 → 14 s.
- CI: Workflow mit minimalen Rechten (`contents: read`, `persist-credentials: false`; CodeQL `actions/missing-workflow-permissions`).
- Referenzen korrigiert: Die Opel-E78-XDF ist selbst das Ergebnis einer Tabellensuche (Einträge „Candidate…“, „FloatVector…“) und wird wie Peugeot IAW nicht mehr als Messwert geführt. Weder klassische PowerPC-`lis`/`addi`-Paare noch 32-Bit-Zeiger treffen ihre Adressen.
- Neue Referenzen (nur lokal): Bosch MED17.1.62 (6 Stände, XDF), MED9, BMW ME9 und ME9.2.1 und Siemens MS45 mit **Hersteller-A2L** (TracqiTechnology/MxT, Apache-2.0; MadScientist789/BMW-XDFs-1).
- A2L: RECORD_LAYOUT nach ASAP2 (NO_AXIS_PTS, AXIS_PTS, FNC_VALUES ROW/COLUMN_DIR, Ausrichtung aus MOD_COMMON, STD/COM/FIX_AXIS, AXIS_PTS-Objekte); Anzahl wird aus der Datei gelesen und gegen die A2L-Höchstzahl geprüft. Vorher wurden echte Bosch-/Siemens-A2L zu 0 % verlinkt, jetzt ME9 2733/2733, ME9.2.1 6147/6147, MS45 4673/4701. Linearer RAT_FUNC wird umgerechnet. `suggest_anchor` bestimmt die Speicherbasis aus der Firmware und lehnt nicht passende A2L ab (ME7.2 X5: 76–80 % statt 100 %). Behoben: A2L mit in cp1252 undefinierten Bytes brach ab; `COM_AXIS` ohne Datei wurde mit der Höchst- statt der echten Stützstellenzahl verlinkt.
- Kopf-Datensätze (nx, ny, X, Y, Z) bis 200 statt 55 je Datei: gegen vollständige A2L ME9 exakt 20 → 38 (Präzision 45 → 50 %), ME9.2.1 29 → 56 (62 → 63 %), MS45 21 → 28 (64 → 67 %); VAG 06A906032HS 50 → 59; MS43/MS42/Fehlalarme unverändert.
- Checksummen-Suche (`core/checksum_search.py`, `tools/checksum_search.py`, Idee aus UniversalPatcher): Bereiche × Verfahren gegen einen gespeicherten Wert, mit erwarteter Zufallstrefferzahl, Bestätigung auf weiteren Dateien und Profil-Entwurf mit `reviewed: false`. Bisher nur synthetisch geprüft.
- Checksummen-Korrektur in der Oberfläche (Werkzeuge → „Checksummen korrigieren (mit Vorschau)“ und im Prüfbericht): zeigt jedes zu schreibende Byte, Standard „Nein“, rückgängig machbar, Hinweis „keine Flashfreigabe“.
- Windows-Build: eigenes `.venv-build` mit CPython 3.13 x64 (die portable Laufzeit bündelt python313), Versionsprüfung vorab; `build_release.ps1` mit UTF-8-BOM (Umlaute unter PowerShell 5.1).
- Konkurrenzanalyse in `docs/KONKURRENZANALYSE.md` (ZedSuite, romHEX14, bimmerstein, RomRaider, UniversalPatcher, MxT, tune-editor, xdfkit, medc17-checksum-tool).
- Zwillingskennfelder: Eine identische Kopie gilt nur noch als angepasst, wenn sie **genau gleich** geändert wurde (vorher reichte ein beliebiges geändertes Byte); abweichende Anpassung ist rot mit Anzahl abweichender Byte. Ähnliche Kennfelder, die an verschiedenen Stellen geändert wurden, sind gelb. Paare werden nur einmal gemeldet.
- Prüfstatus in drei getrennten Stufen: Prüfsummen (deklarierte Prüffelder) · Preflight · Flashvalidierung (immer „nicht durchgeführt“, `flash_validated = False`).
- A2L-Identität: `MOD_PAR EPK` an `ADDR_EPK` wird mit der Datei verglichen; bei abweichender EPK wird nichts verknüpft. A2L ohne EPK werden als „Softwarestand nicht belegt“ gekennzeichnet. **Behoben:** Bei Segmentadressierung wurde die EPK gar nicht geprüft; `ADDR_EPK` wird jetzt über dieselbe Segmenttabelle aufgelöst, eine abweichende EPK lehnt die Verknüpfung auch dort ab, und eine Segmenttabelle ohne `ADDR_EPK` erzeugt eine Warnung statt stiller Freigabe. Ohne Dateidaten wird ausdrücklich „EPK nicht geprüft“ gemeldet. Der A2L-Dialog nutzt jetzt die Datensatz-Auswertung (vorher nur einfache Wertefelder: ME9 0 → 2612 verknüpfbare Kennfelder) und bestimmt die Basis auf Knopfdruck aus der Firmware.
- Dateiformate ehrlich abgewiesen statt roh geöffnet: WinOLS-Projekt (.ols), WinOLS-Mappack (.kp), ZIP, ELF/EXE, HEX/S19 (Hinweis auf den Speicherabbild-Import), Definitionsdateien. Keine der 214 vorhandenen Referenz-BINs wird fälschlich abgewiesen.
- Inhaltsgleiche Kennfelder (Dubletten/Überwachungskopien) werden im Katalog vermerkt (`map_groups.content_twins`); MS43: 22 Gruppen unter den Funden, 87 XDF-Kennfelder in 32 Gruppen.
- **Portabler Windows-Build behoben:** Die EXE startete gar nicht (`PySide6.QtSvg` fehlte im Paket, seit die Werkzeugleisten-Symbole SVG nutzen). Benötigte Qt-Module werden jetzt aus den Imports abgeleitet und vor dem Bau geprüft. In frischer `.venv-build` (CPython 3.13): 372 Tests bestanden, Paket gebaut, EXE-Selbsttest bestanden.
- `docs/ECU_SUPPORT.md`: gemessene, unvollständig gemessene und nicht unterstützte ECU-Varianten mit konkreten Dateien (MED17-Dumps: 8V0907404A/E/H/J, 8S0907404G/L). EDC17, MD1, MG1, Simos 18/19: keine frei verfügbaren Referenzpaare, daher ungemessen.
- **Benchmark-System** (`tools/benchmark_suite.py`, Vorlage `examples/benchmark_manifest.template.json`): je Paar Referenzkennfelder, Funde, Recall, exakte Layouts, richtige Achsen, Laufzeit, optional Spitzenspeicher; Präzision/False Positives/False Negatives **nur bei vollständiger Referenz**; Rolle `test`/`development`/`training` je Paar; nahezu identische Softwarestände (≥ 90 % gleiche Bytes) bilden eine Gruppe.
- **Neue vollständige Herstellerreferenzen** (BMW-XDFs-1, nur lokal): Bosch EDC17CP09 (TriCore, 2 MB inkl. Programm, EPK passt, 20 408/20 408 Objekte, 1645/1645 Achsen steigend), Siemens MSD85 und MSD80 (EPK passt), Bosch EDC16C35/C31 (Achsen 100 %). MSD80/MSD85 blieben als unabhängige Testdaten unangetastet.
- **Kopf-Datensätze** (nx, ny, X, Y, Z): Achsen auch vorzeichenbehaftet (EDC17-SWORD-Layouts), bis 1000 statt 200 je Datei, und die Achsen erkannter Datensätze werden als eigene 1D-Kandidaten gemeldet (neue Beweisklasse `axis:record`). Gegen Hersteller-A2L: EDC17CP09 exakt 46 → 157 (Präzision 62 → 71 %), **MSD85 (Test) 91 → 148 (72 → 74 %)**, **MSD80 (Test) 93–96 → 133–137 (73–74 → 77–78 %)**, EDC16C35 91 → 111, EDC16C31 93 → 123; ME9.2.1 56 → 109 (63 → 69 %). 1D exakt von 0–19 auf 212–354 bei 85–92 % Präzision. MS43/MS42/MS45 und Fehlalarme unverändert.
- A2L-Referenzen führen jetzt auch die Achsen innerhalb von Datensätzen als 1D-Objekte (wie XDF-Achsadressen); Benchmark und Kalibrierung akzeptieren eine explizite Basis (`REF@0x8000`) und prüfen sie gegen die Achsen.
- **Behoben:** Intel-HEX/S19 mit abschließendem DOS-Dateiende-Zeichen (`0x1A`) wurden abgewiesen (echte EDC16-Dateien).
- Import-Prüfung über alle Referenzpaare: decodierte Definitionsachsen steigen bei MS42, ME9, ME9.2.1, MS45, MED17, Subaru zu 99–100 %; Abweichungen ließen sich jeweils auf die XDF zurückführen (z. B. VAG-Achse als vorzeichenlos deklariert, Volvo-M4.4-XDF von anderer Motorvariante übernommen), nicht auf den Import.
- WinOLS-`.ols`: Versionsstruktur in 7 echten Projekten gefunden, der gelesene Inhalt stimmt aber nicht mit den Originaldateien überein (30–54 %) – kein Import, dokumentiert in `docs/ECU_SUPPORT.md`.
- **Installation und Updates für Anwender ohne Python:**
  - Paket: `dist/ECU-Studio-AI/ECU-Studio-AI.exe` (fester Name, damit Verknüpfungen Updates überleben) und `ECU-Studio-AI-<version>-windows-x64.zip` mit `.sha256`; Version aus `ecu_studio.__version__`.
  - `build_release.ps1`: zusätzlich `--self-check` der EXE, ZIP-Erstellung, Start des **entpackten ZIPs ohne Python im PATH**, optionaler Installer (Inno Setup 6, `packaging/installer.iss`: pro Benutzer ohne Adminrechte, Startmenü, Deinstallation).
  - `.github/workflows/release.yml`: Tag `vX.Y.Z` → Tag/Version- und CHANGELOG-Prüfung (`tools/release_notes.py`), Tests, Build, EXE-Tests, Installer, Build-Herkunftsbestätigung, GitHub-Release.
  - Update-Prüfung (`core/updates.py`, `ui/updates.py`): GitHub-Releases-API (`/releases/latest`, nur stabile Versionen), beim Start und höchstens täglich, abschaltbar (Einstellungen → „Automatisch nach Updates suchen“ / „Jetzt nach Updates suchen“), offline still; Dialog mit Version, Änderungen und „Jetzt aktualisieren“ / „Später erinnern“ / „Diese Version überspringen“.
  - Download nur von Release-URLs dieses Repositorys, SHA-256 gegen `.sha256` und GitHubs Asset-Digest, Größenprüfung, keine Umleitung auf fremde Server; Übergabe an den separaten Updater (`packaging/updater.ps1`) erst nach dem Schließen (ungespeicherte Arbeit wird abgefragt). Der Updater prüft jede Datei gegen `RUNTIME_INVENTORY.json` und eine vorhandene Authenticode-Signatur, übernimmt eigene Dateien, sichert die alte Version, führt `--self-check` aus und stellt bei Fehlern automatisch wieder her.
  - Gemessen: kompletter Build in frischer 3.13-Umgebung (396 Tests, EXE-Oberflächentest, entpacktes ZIP ohne Python), echtes Update des 50-MB-Pakets mit Selbsttest in 9 s inkl. Erhalt eigener Dateien; Updater-Fehlerfälle (falsche Prüfsumme, manipulierte Datei, fehlgeschlagener Selbsttest → Rollback) als Tests. Installer lokal nicht gebaut (Inno Setup nicht installiert); EXE nicht code-signiert.
- Offen: Code-Verweise für TriCore und PowerPC, 8051 mit Bankumschaltung (Volvo M4.4); Lernmodell nicht neu trainiert, weil die neuen Definitionen unvollständig sind (verrauschte Labels).

## 1.11.0 (17.10.2026)

- Smart Map Transfer mit bestätigten Definitionen, physikalischem Delta/Prozent, Konflikten, Zellvorschau, manueller Auswahl/Freigabe und atomarem Undo.
- CSV Log-to-Map mit Kanal-/Einheitenzuordnung, transparenten Soll/Ist-Regeln, bilinearer Belegungs-Heatmap, Editor-Zellnavigation und HTML-Bericht.
- Mehrere Kennfeldtabs, Schichten, Interpolation über physikalische Achsen, Glättung, disjunkte Auswahl, deklarative Rezepte und sichere Mehrprojekt-CLI.
- Virtueller Kennfeldkatalog, Favoriten/Gruppen, Dezimaleditor, Bitmasken-/Rohwertsuche, ZIP-BIN/ORI-Import und suchbarer Projektindex.
- Originalbackups, Recovery-Dateien, vorherige Projektstände, Hashintegrität, fsync/atomare Writes und Schutz der Originalpfade einschließlich Hardlinks.
- Veraltete Batch-Vorschauen gesperrt; Snapshot-Teilrestore verändert keine Stride-Lücken mehr; fehlender FORMATS-Import im Flächeneditor korrigiert.
- Vektorisierte Stride-Dekodierung und effizient angeordnete notwendige Scannerprüfungen. Vorher/Nachher auf gleichem synthetischen Korpus geprüft; reproduzierbare Größenbenchmarks.
- Schema-2-Migration mit Erhalt bestehender Datensätze; Provenienz-/Lineage-Gates für Training. MOD-Werte dürfen nicht unter ORI-Hash bestätigt werden. Modellkandidaten bleiben inaktiv.
- Strenge exakte Holdout-Metriken mit Herkunftsprüfung, real/synthetisch-Trennung, Leakage-Prüfung und optionalem Family-Holdout. Keine neuen realen Modellgewichte oder geprüften Multi-ECU-Labels erfunden.
- Windows-Regressionen, Qt-Integration, EXE-Build und Prüfung der paketierten Anwendung; siehe README_V1_11.md und QA_REPORT_V111.json.

## 1.10.0 (16.10.2026)
- Tatsächlich neues 24-Baum-ExtraTrees-Modell auf 4.000 synthetischen Oberflächen trainiert; portables JSON ohne Pickle, Inferenz mit NumPy.
- 1.000 Beispiele zur Validierung und 1.000 disjunkte synthetische Prozessbeispiele als Holdout. Alle Zahlen beziehen sich nur auf künstliche Strukturen.
- Modell als zusätzlicher Kandidaten-Hinweis im bisherigen Präzisions-Ranking integriert, niemals als bestätigter Kennfeldname, Achse oder Fahrzeugtyp.
- Kandidaten mit niedrigem Strukturwert leicht nachrangig behandelt, aber NICHT entfernt (keine validierte reale False-Negative-Rate).
- Bugfix: doppeltes Normalisieren bei der OOD/Unbekannt-Prüfung des semantischen ML-Modells entfernt.
- Zusätzlich zu einem Einzel-Firmware-Holdout erfolgt bei verifizierten Familienmodellen jetzt eine Leave-One-Firmware-Out-Prüfung. Mindestwerte sind Freigabebedingung.
- Kein neues semantisches ML-Modell freigegeben: unverändert 0 unabhängig geprüfte Trainingslabels für neue ECU-/TCU-Familien.
- Keine Drittanbieter-BINs eingebunden oder verteilt. Windows-GUI weiterhin nicht auf echter Windows-Maschine getestet.

---

# v1.8 – 2026-10-16

- Klickbare Kennfeld-Heatmap und neue 2D-Kurvenschnitte (Zeile/Spalte, originale vs. bearbeitete Werte) mit Sprung in editierbare Einzelzellen.
- Verbesserte 3D-Oberfläche mit ORI/MOD-Drahtgitter-Vergleich, Dreh-/Neigungs- und Zoomsteuerung.
- Hashgebundener Import geprüfter, expliziter Prüfbereichs-Profile; lesende CRC32/Summationsprüfung für definierte Bereiche. `unknown` bei fehlendem Profil, `mismatch` bei Differenz; **keine ECU-universelle Checksum-Garantie und keine Reparatur**.
- Integrierter Kalibrierungs-Audit bei BIN-Export: Deltaübersicht, Zelländerungen, ungeprüfte Kennfelder, Dateihash und Bytes außerhalb von Tabellen. JSON-Bericht und CLI.
- Automatische Kennfeldgruppen mit nachvollziehbaren Kriterien, nie automatisches Hochstufen struktureller Kandidaten zu bestätigten ECU-Funktionen; interaktiver Baum und CSV-Export.
- Synthetischer Checksum-Test und sechs neue Regressionstests. **160 bestanden, 4 übersprungen**; Qt-GUI/Windows-EXE mangels PySide6 und Windows in dieser Umgebung nicht live getestet.

---

# v1.7 – 2026-10-16

- GUI-Blocker behoben: `require_image()` liefert wieder booleschen Erfolgswert.
- Read-only ORI/MOD-Kennfeld- und Zellvergleich (strided und endian-korrekt), Einzelzell-/Summen-CSV, Diff-Dialog mit Sprungfunktion.
- Neue Hash-genaue Fahrzeug-/ECU-Identitätsdatenbank mit atomarem, belegpflichtigem JSON-Massenimport und Konfliktsperre; zusätzliche vorsichtige Bosch-Text-Familienhinweise.
- Präzisionssuche ergänzt um konservative Nachbarachsen-Hinweise (ohne automatische Kennfeld-/Einheitenfreigabe).
- Transparentes Datenbank-Abdeckungsfenster für Audi / Mercedes-Benz / BMW / Opel / Lamborghini und read-only CLI-Workflows.
- Neues synthetisches ORI/MOD-Beispiel und neue Regressionstests. Keine neuen echten Hersteller-Firmware-Trainingspaare.

---

# v1.6 – 2026-10-16

- Präzisions-Postfilter für 2D-Struktur, Endian-Ambiguität und überlappende Kandidaten; unbekannte Funktion immer unbekannt.
- Strengere MS43-Strukturmodell-Abstention bei generischen linearen Ebenen/Rauschflächen.
- Familiengebundene supervisierte Prognose, OOD-Gate und Oberflächen-Duplikatsperre über Firmware-Holdouts.
- Markenübergreifende Referenzverwaltung (7 Links/Hinweise für Audi, BMW, Opel, Mercedes und Lamborghini), vier konkrete per Git-Blob gepinnte XDF-Pfade; keine Drittanbieter-BINs enthalten.
- Windows-GUI-Quellenanzeige, Offline-SQLite-Index, CLI und synthetischer Reproduktionsbenchmark.
- 146 Tests bestanden, drei übersprungen. Windows-Laufzeit nicht ausgeführt.
- **Kein weiteres supervised Training erfolgt:** unabhängig verifizierte Kennfeldlabels weiterhin 0, MS43-Modell aus v1.5 unverändert.

---

# v1.5 – 2026-10-16

- Reales PCA/SVD-Strukturmodell aus 67 MS43-Rohwertoberflächen trainiert und als JSON in Paket integriert. Externe Ausgangsdefinitionen unbestätigt; **keine** automatischen Funktionsnamen als sicher behauptet.
- Aktive Prüfqueue und Erklärungssuche für unsichere, unbekannte Tabellen.
- Familienregister für MD1/MG1/EDC17/EDC16/EDC15/ME-MED/SIMOS/SID/DCM/Denso/GS20/ZF.
- Explizite XDF/A2L-Datenaufnahme mit Firmware-SHA, manuell geprüfter Identität und bei A2L obligatorischen Speichersegmenten.
- Familienbezogenes supervised Training mit Klasse-/Firmware-Holdout und Mindestpräzision/-trefferquote; verweigert derzeit Freigabe wegen 0 unabhängiger Labels.
- Training/Status/Prüfqueue zusätzlich in der GUI; Schutz vor alten, ungeprüft familienübergreifenden ML-Klassifizierungen.
- 143 Python-Tests bestanden. Windows-Qt nicht live validiert.

---

# Version 1.4 – Öffentliche Datenbank befüllt

- 14 konkrete und SHA-gepinnte XDF-Quellen (MS41, MS42, MS43, GS20).
- 118 echte, lizenz- und quellengebundene Kennfeld-Metadatensätze aus MS41/MS42/MS43.
- Separate SQLite mit 81 auf die echte MS43-BIN-SHA bezogenen, **nicht** fachlich bestätigten XDF-Vorschaudefinitionen; BIN selbst nicht mitgeliefert.
- Erststart-Seed aller vorhandenen SQLite-Kataloge idempotent und ohne Überschreiben bestehender Daten.
- Windows-Menü: öffentlicher Quellenkatalog, SHA-gepinnter XDF-Download und manuelle MS43-Offline-Vorschau.
- CLI: öffentliche Quellen auflisten, softwaregebundenen Original-XDF-Import auslösen, separate Offline-Vorschau indexieren.
- Lizenzhinweise und Originalquellen dokumentiert; keine fremden Daten als validierte Trainingsbeispiele markiert.
- 137 Tests bestanden, GUI nicht live auf Windows getestet.

---

# v1.3 – Erkennungsarchitektur in drei Ebenen

- Neu: opt-in SQLite-Definitionsdatenbank mit ECU-/Quellenhash, Familienzuordnung und rückverfolgbarer Herkunft.
- Neu: erneut geladene byteidentische Definitionen, nach Nutzerfreigabe.
- Neu: manuelle Fachprüfung pro Map, erforderlich für Referenztransfer und ML-Training.
- Neu: Batchimport für hunderte bis tausende lokale BIN/XDF-Paare aus JSON-Paarlisten.
- Neu: Referenzbasierte Suche für verschobene und moderat veränderte, zusammenhängende Map-Matrizen derselben ECU-Familie.
- Neu: Einzigartigkeitsprüfung mit zweitbestem Treffer und Mehrdeutigkeitsabstinenz.
- Neu: rein lokal trainierbares, versioniertes JSON-ML-Modell mit Firmware-getrenntem Holdout und klassenspezifischem Recall.
- Neu: NumPy-ML-Features aus Oberflächen, Gradienten und Statistiken; Score- und Qualitätsabstinenz.
- Neu: Qt-Menüaktionen und Hintergrundworker für Matching sowie Batchimport.
- Neu: CLI `python -m ecu_studio.tools.recognition_v13` für Index, Batch, Training und Erkennungsberichte.
- Schutz: Nach Veränderung einer bereits bestätigten Definition fällt der Bestätigungsstatus zurück.
- Tests: 132 bestanden, einschließlich echtem Upload-Dateiprofil, verschobenem Map-Fund, doppeltem/mehrdeutigem Fund und ML-Firmware-Holdout mit synthetischen Daten.

Nicht geändert: XDF/A2L-Parser enthalten weiterhin einen dokumentierten Teilumfang; keine 100-%-Semantik unbekannter Firmware. Keine neuen Checksummen-/Flash-Funktionen.

## 1.9.0 (16.10.2026)
- Neuer opt-in 1D-TCU-(X,Y)-Kurvenscanner; Strides, BE/LE, Terminator, keine Typfreigabe.
- Firmware-Holdout-Benchmark mit SHA-256, Split-Leakage-Prüfung, ein-zu-eins zugeordneten Kennfeldpositionen und transparenter räumlicher Deckungsmetrik.
- Quellenkatalog für Subaru 5EAT (Hitachi/Denso), Volvo ME7, Hyundai SIM2K, VAG DQ250.
- Realdaten-Vorfilterdiagnose an drei publizierten Holden-68HC11-Bankfragmenten, keine Labels und keine ROM-Weitergabe.
- Weitere registrierte ECU/TCU-Familien, ausdrücklich ohne neue automatische Typidentifikation.
- Neues Windows-Werkzeugmenü für 1D-Getriebekurven.
- Keine neuen KI-Funktionslabels oder semantischen Trainingsgewichte: es fehlen geprüfte, rechtmäßig verwendbare Trainings-/Holdout-Paare.
