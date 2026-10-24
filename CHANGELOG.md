## 1.17.0 (24.10.2026)

**Offenes Kennfeldpaket und integrierter Projektworkflow**
- Bestehendes JSON-Map-Pack auf Version 2 erweitert: Original-Hash/-Größe, erkannte ECU-/HW-/SW-Kennungen,
  Definitionen inklusive Strides, Achsadressen und Gruppen, optionale Beschreibungen/Belege und Integritäts-Hash.
  Keine Firmware oder Patches. Format 1 bleibt lesbar; unbekannte Felder werden angezeigt und blockieren die Übernahme.
- Importvorschau mit Konflikten; keine Überschreibung vorhandener Definitionen und keine automatische Verifikation.
  Abweichende Hashes laufen mit lokaler Quell-BIN durch den bestehenden Softwarestand-Vergleich statt an gleiche Offsets.
- Paketübernahme plus Projektversionsstand sind als gemeinsame Katalogtransaktion mit Strg+Z/Strg+Y rückgängig machbar,
  in zeitlicher Reihenfolge mit Byte-Bearbeitungen. Lokaler Projektindex merkt Pakete und bietet beim Öffnen Vorschläge an.
- Export: alle, bestätigte oder ausgewählte Definitionen; Achsadressen/Gruppen optional; private Freitexte standardmäßig aus.
- `tools.validation_report` verbindet die bestehenden Benchmarks und Fehlfundanalysen mit lokalem SHA-256-Manifest,
  getrennten Datenrollen und JSON-/Markdown-Ausgabe. Geänderte Referenz, Rolle oder Software ist nicht vergleichbar.
- Keine Änderung am Scanner oder an OEM-Korrektursperren. Prioritätsfamilien ohne Referenzen bleiben **nicht neu gemessen**.
  [Format](https://github.com/PCTestAdmin/ECU-Studio-AI/blob/v1.17.0/docs/MAP_PACK.md),
  [Messworkflow](https://github.com/PCTestAdmin/ECU-Studio-AI/blob/v1.17.0/docs/REFERENCE_VALIDATION.md),
  [technischer Prüfbericht](https://github.com/PCTestAdmin/ECU-Studio-AI/blob/v1.17.0/docs/ANALYSE_2026-10-24.md).
- Geprüft: 591 Tests bestanden, 7 optionale Referenztests übersprungen; synthetischer GUI-Ablauf und Windows-Paketbau.
  Die MS42-Kontrolle bleibt bei 22/213 exakten 2D-Layouts. Kein neuer unabhängiger OEM- oder Transfernachweis.

## 1.16.4 (23.10.2026)

Bericht mit allen Messungen: [docs/ANALYSE_2026-10-23.md](docs/ANALYSE_2026-10-23.md).

**Projektkompatibilität und Werteübernahme**
- Kennfeldfelder aus einer neueren Projektversion werden beim toleranten Öffnen weiterhin nicht angezeigt,
  aber jetzt verlustfrei am Kennfeld mitgeführt und beim Speichern unverändert zurückgeschrieben.
- Unabhängige synthetische Transfer-Matrixtests decken mehrere Softwarestand-Layouts, Datentypen, Byte-Reihenfolgen,
  Skalierungen, Überlauf-/Review-Sperren und den gemeinsamen Undo-Schritt ab. Das ist kein OEM-Nachweis.

**Gemeinsame Achsen (Gruppenkennfelder)**
- Kennfelder kennen die Dateiadresse ihrer X-/Y-Stützstellen (A2L `STD_AXIS`/`COM_AXIS` mit Achsobjekt-Namen,
  XDF eingebettete und verlinkte Achsen, Kopf-/Kennlinien-Datensätze und Code-Verweise der Erkennung). Gespeichert
  im Projekt; alte Projekte laden unverändert.
- Neues Modul `core/axis_groups.py`: Gruppen **nur über dieselbe Achsadresse**, mit Evidenz *aus Definition* oder
  *strukturell, ungeprüft* und Markierung *unsicher* bei Widersprüchen. Gleiche Achswerte an anderer Adresse sind nur
  eine Hypothese. Katalog („Achse geteilt“), Detailbereich, Funktionsgruppen (inkl. CSV) und Funktionsgraph zeigen
  die Gruppen; der Funktionsgraph gruppierte vorher nach gleichen Achswerten.
- Gemessen an MS43 430069 (Rolle *training*): 491 von 491 erkannten Gruppenpaaren richtig, 86 % der Referenzpaare
  unter den exakt gefundenen Kennfeldern.

**Softwarestände vergleichen und Definitionen übernehmen** (*Werkzeuge*, neu)
- Zuordnung über eindeutige Anker in Klassen exakt / strukturell / wahrscheinlich / mehrdeutig / nicht zuordenbar;
  gleiche Adresse allein ist kein Beleg. Differenzen je Kennfeld, zwei synchronisierte Wertetabellen, Filter,
  Liste „nur in Stand B“.
- Übernahme nur von Definitionen (BIN unverändert), alles oder nichts, „wahrscheinlich“ nur mit Bestätigung,
  mehrdeutig nie; Protokoll im Projekt-Journal und Versionsstand mit den übernommenen Definitionen.
- MS43 E46 → E39 (1454 Definitionen, 0,31 s): alle 1140 zugeordneten am richtigen Ort. Zugeordnet wird über die
  Originale beider Stände, Bearbeitungen in Stand A ändern die Zuordnung nicht.
- **Werteänderungen von Stand A übertragen …**: markierte, eindeutige Zuordnungen gehen an den geprüften
  Delta-Transfer (bestätigte Identität und Definitionen, gleiche Achsen und Einheiten, Vorschau, ein Undo-Schritt).
  Nicht bestätigte Achsen in Stand B werden bei der Definitionsübernahme nicht aus Stand A übernommen.

**Projektbibliothek und Versionen**
- Projektliste mit Familie, HW/SW-Kennung, Definitionsquellen, App-Version, geprüften/ungeprüften/geänderten
  Kennfeldern und Versionen; eigene Tags und Kommentare; Filter nach Familie und Tag. Die Angaben stehen in
  zusätzlichen Tabellen: Ältere Versionen öffnen und beschreiben dieselbe Projektdatenbank weiterhin.
- Tests laufen mit temporären Benutzerordnern und berühren die echte Projektdatenbank nicht mehr.
- **Projekte aus neueren Versionen** öffnen jetzt mit einer Warnung, die die unbekannten Kennfeldangaben nennt
  (sie bleiben beim Speichern unverändert erhalten), statt mit einem Fehler abzubrechen. Hinweis: Projekte dieses Stands lassen
  sich in 1.16 und älter **nicht** öffnen – dort fehlt diese Toleranz noch.
- Versions-Explorer: zwei beliebige Stände vergleichen (Bytes, Kennfelder, Definitionen).

**Messwerkzeuge**
- `tools/miss_analysis`: Ursachen verfehlter Referenzkennfelder je Paar.
- `benchmark_suite`: Version, Commit, Referenzquelle/-lizenz, Achsadress- und Gruppenkennzahlen, `--baseline` für
  einen Vorher/Nachher-Bericht (mehr Kandidaten allein gilt nie als Verbesserung).

**Nicht erreicht:** Keine Änderung an der Kennfeldsuche. Die Referenzpaare der Prioritätsfamilien (EDC17CP09, EDC16,
MSD80/85) waren nicht verfügbar; zwei an MS42/MS43 geprüfte Ansätze für Gruppenkennfelder wurden wegen zu geringer
Präzision verworfen (Bericht, Abschnitt 3).

## 1.16.3 (22.10.2026)

- **Updater repariert:** Der PowerShell-Updater läuft jetzt mit einem Arbeitsordner außerhalb der Installation,
  damit Windows den Installationsordner beim Austausch nicht selbst als „in Benutzung“ sperrt.
- Der Austausch wartet bei kurzfristigen Windows-Dateisperren bis zu 30 Sekunden und bricht danach unverändert ab.
- Nutzer von 1.16.2 müssen 1.16.3 einmal manuell über ZIP oder Installer installieren: Der bereits installierte
  1.16.2-Updater kennt den externen Arbeitsordner noch nicht. Danach funktionieren automatische Updates wieder.

## 1.16.2 (22.10.2026)

**Prüfsummen: Bosch MED17/EDC17-Blockverfahren** (neu: *Werkzeuge → EDC17/MED17-Prüfsummenblöcke prüfen / korrigieren …*)
- Neues Modul `core/edc17_checksum.py` liest die selbstbeschreibenden Bosch-Prüfsummenblöcke (Signatur
  FADECAFE/CAFEAFFE), rechnet TriCore-Flash-Adressen (0x8/0xA-Alias) auf Dateioffsets um und rechnet die drei
  dokumentierten Verfahren nach: CRC32 (reflektiert, Startwert 0xFADECAFE, gespeichert als Komplement),
  ADD32 (Dword-Summe) und ADD16 (16-Bit-Wortsumme mit dokumentiertem Schlusswort). Ein Block gilt nur als
  **nachgewiesen**, wenn er den gespeicherten Wert aus dem **unveränderten Original** exakt reproduziert; aus dem
  Familiennamen wird nichts geschlossen.
- Korrektur nur für additive Blöcke (ADD32/ADD16) über ihr Kompensationswort, mit Byte-Vorschau, Endprüfung und
  Rücknahme. CRC32-Blöcke werden nur geprüft (könnten Signaturen/Sicherheitsfelder abdecken – bewusst nicht
  angefasst). Keine Signatur-Umgehung, keine Flashfreigabe.
- Der Prüf-/Exportbericht (`audit_export`) warnt jetzt auch bei falschen EDC17/MED17-Blockprüfsummen.
- Korrektur schreibt alle Kompensationswörter in **einem** Undo-Schritt: ein einziges Strg+Z nimmt die gesamte
  Korrektur zurück (vorher nur das zuletzt geschriebene Feld).
- Eindeutiger Prüfstatus **vollständig / teilweise / nicht prüfbar**: `check_current`/`verify` und die Oberfläche
  weisen nicht am Original nachgewiesene Strukturen jetzt klar als ungeprüft aus, statt für einige Strukturen einen
  positiven Status zu zeigen.
- Strengere Grenzprüfung: Jede Prüfsummenstruktur muss vollständig innerhalb ihres Blocks liegen; Strukturen
  beschädigter/ungewöhnlicher Dateien, deren Bereich aus dem Block fällt, gelten als „nicht prüfbar“ und erzeugen
  keinen irreführenden Treffer und kein Schreibziel.
- `tools/validate_pair` misst zusätzlich die EDC17/MED17-Prüfsummenabdeckung (nicht nur die Kennfelderkennung).
- Herkunft des Blockformats: öffentlich dokumentiertes Bosch-Layout, gegengeprüft am MIT-lizenzierten
  medc17-checksum-tool (Connor Howell). Die Mechanik ist synthetisch im Bosch-Format end-to-end getestet
  (`tests/test_edc17_checksum.py`, u. a. unabhängige CRC-Gegenrechnung). **Ein OEM-Nachweis an echter EDC17CP09-
  Firmware steht aus – es liegt keine echte Firmware im Repository** (siehe `docs/ECU_SUPPORT.md`). EDC17/MED17-
  Korrekturen sind ohne einen SHA-256-gebundenen OEM-Nachweis gesperrt; Teilstrukturen werden nie korrigiert.
- EDC16U1/U31/U34: selbstbeschreibende FADECAFE/CAFEAFFE-Bereiche mit BE-DWORD-Summe `0xD01FE500` werden
  geprüft und nur nach vollständigem Originalnachweis sowie OEM-Freigabe korrigiert. Ohne OEM-Eintrag bleibt die
  Funktion bewusst im Prüfmodus.
- OEM-Freigaben akzeptieren nicht mehr nur Metadaten: `checksum_validation.py` verlangt mindestens zwei
  verschiedene vertrauenswürdige Ed25519-Signaturen über eine kanonische, SHA-256-gebundene Bescheinigung und
  einen Hash der Evidenz. Die menschliche Unabhängigkeit bleibt ein Review-Prozess und wird nicht behauptet.

- Hinweisbalken nach dem Öffnen: Siemens-Dateien ohne Bosch-EPK (MS41/MS42/MS43, GS20) galten als „nicht
  bestimmbar“, obwohl die App sie an ihren Softwaremarkern erkennt (Titelzeile). Die Erkennung nutzt diese Marker
  jetzt auch für Hinweisbalken, Kennungsanzeige und Unterstützungsstatus.

## 1.16.1 (22.10.2026)

> ⚠️ **Bitte diese Version einmal von Hand installieren** (Installer `…-setup.exe` oder ZIP), wenn du 1.15.0 oder
> 1.16.0 nutzt: Deren Update-Funktion installiert nichts (siehe unten). Ab 1.16.1 funktioniert das Update aus der App.

- **Automatisches Update repariert:** Die App startete das Update-Programm mit einer Windows-Option, bei der
  Windows PowerShell sofort beendet, ohne das Skript auszuführen – das Update meldete keinen Fehler, die alte
  Version blieb. Betroffen: alle Updates aus der App bis einschließlich 1.16.0. **Wer 1.15.0 oder 1.16.0 nutzt,
  muss diese Version einmal von Hand installieren** (Installer oder ZIP); danach funktioniert das Update aus der App.
  Ein neuer Test startet das Update-Programm genau wie die App und prüft, dass das Skript wirklich läuft.
- Update-Prüfung bei **jedem Start** (bisher höchstens einmal am Tag): Wurde kurz vor einer Veröffentlichung geprüft,
  blieb die neue Version bis zu 24 Stunden unsichtbar (so bei 1.16.0). Während die App läuft, weiter einmal täglich.
- Messung ohne A2L (`validate_pair DATEI.bin --family …`): Kennung, Funde je Konfidenz und Laufzeit; Familie wird
  „experimentell“, nie „validiert“. Ergebniszeilen heißen nach Familie und Hash, nicht nach dem Dateinamen.
- Signaturschlüssel-Erzeugung gibt Pfad und Inhalt der Schlüsseldatei nicht mehr aus (CodeQL-Hinweis).
- README mit englischer Kurzfassung.

## 1.16.0 (22.10.2026)

**Kennfelderkennung** (alt → neu, gleiche Referenzen und gleiche Messmethode; *Test* = nie zum Einstellen verwendet)
- Siemens MSD85 · *Test*: exakt 148 → **279** von 1026, Präzision 74 → **81 %**.
- Siemens MSD80 · *Test* (6 Stände, davon 4 neu als Testpaare): exakt 133–143 → **217–224** von 864, Präzision 77–78 → **81–82 %**.
- Bosch EDC16C35 / EDC16C31: exakt 111 → **283** / 123 → **272**, Präzision 66 → **81 %** / 71 → **82 %**, Abdeckung 80 / 84 %.
- Bosch EDC17CP09: exakt 157 → **463** von 703, Präzision 71 → **85 %**; BMW ME9.2.1 109 → 170, ME9 41 → 98; BMW MSS54 69 → 97.
- Bosch MED17.1.62 (6 Stände, Teil-XDF): exakt 49–64 → 121–145.
- Kopf-Datensätze (Anzahl, Achsen, Werte) werden auch mit flachen oder groben Werten erkannt; Größe und Achsen belegt
  der Kopf (eigene Evidenzklasse `header:nxny:shape`, gemessen 98 % Treffer). Verrauschte Datensätze nur innerhalb einer
  Kette direkt aneinanderliegender Datensätze. Gelockerte Achsenregel nur bei 16-Bit-Zählern: auf Zufallsdaten,
  komprimierten und gelöschten Daten 0 Kandidaten (Negativkontrolle, 13 Dateien).
- Belegte Funde (Kopf-Datensatz, Code-Verweis, Deskriptor) gewinnen Überlappungen gegen reine Glattheits-Kandidaten –
  außer ihr Kopf liegt im Inneren einer früher beginnenden Tabelle – und werden nicht mehr vom Ergebnislimit abgeschnitten.
- Vorzeichen: bei gleich guter Lesart wird s16 nur gewählt, wenn die Bytes negative Werte enthalten.
- Konfidenz neu kalibriert, nur auf Entwicklungs- und Trainingspaaren (Testdaten nicht mehr in der Kalibrierung).

**Roadmap mit Clips**
- Jede neue Funktion in der Roadmap mit kurzem GIF-Clip und Version (wie bei Feature-Listen kommerzieller Editoren).
  Die Clips sind echte Aufnahmen der App: `tools/feature_clips.py` bedient das Hauptfenster offscreen, zeichnet
  Mauszeiger und Klicks ein und schreibt GIFs mit einem eigenen Encoder (`tools/gif_writer.py`, nur NumPy).
- Vorführdatei `core/showcase.py`: synthetische Kopf-Datensätze, keine Herstellerdaten.

**Englische Oberfläche**
- Komplette Oberfläche auf Englisch: Menüs, Werkzeugleiste, Dialoge, Meldungen, Statuszeile, Kennfeldliste, Prüfberichte.
  Auswahl unter *Einstellungen → Sprache / Language* (Standard: Systemsprache, deutsche Systeme bleiben deutsch).
- Auch gezeichnete Ansichten (Heatmap, 3D, Kurven, Speicheratlas) und zusammengesetzte Statuszeilen
  („16 × 16 · u16 · Unbekannt“) werden übersetzt.
- Übersetzungskatalog `recognition/data/i18n/en.json` (1792 Texte); `tools/i18n_extract.py` sammelt neue Texte aus dem
  Quellcode, ein Test verhindert unübersetzte Texte. Auswahlfelder zeigen Englisch, Projekte und Programmlogik bleiben
  sprachunabhängig.

**Rechtlich saubere Referenzdaten**
- Recherche nach rechtmäßig verfügbaren Original/Definition-Paaren für MD1, MG1, Simos, SID, MED17.5/17.7: keine gefunden
  (öffentliche Uploads Dritter ohne Lizenz wurden nicht heruntergeladen; Begründung in docs/ECU_SUPPORT.md).
- Neu: `tools/tunerstudio_image.py` – Kalibrierabbild + vollständige Referenz aus TunerStudio-Definition (.ini) und
  Abstimmung (.msq) für offene Steuergeräte (Speeduino, rusEFI, MegaSquirt); sichere Ausdrucksauswertung ohne `eval`,
  versionsgenaue Definition wird erzwungen.
- Speeduino gemessen (14 offizielle Abstimmungen, GPL-2.0/CC BY-NC 4.0): ohne Definition nur 0–2 von 18–20 Tabellen
  exakt – Tabellen liegen vor ihren Achsen ohne Anzahl-Kopf. Ein Scanner dafür wurde gebaut, gemessen und verworfen
  (auf anderen Familien hunderte Fehlfunde). Status „teilweise“.
- Unterstützungsmatrix: „validiert“ verlangt jetzt zusätzlich ≥ 20 % exakt gefundene Referenztabellen; Siemens MS45
  und MS42 stehen damit ehrlich auf „teilweise“.

**Neue Steuergeräte-Familien validierbar machen**
- Identifikation erkennt zusätzlich Klartext-Kennungen von Continental/Siemens (Simos, SID, MSV, MSD) und MD1/MG1;
  auf den 27 Referenzdateien keine falsche Familie. Matrix-Zuordnung fällt auf die übergeordnete Familie zurück
  (SIMOS18.1 → Simos 18).
- Neu: `tools/validate_pair.py` – ein Befehl misst für ein Original + passende A2L Kennung, exakte Kennfelder, Typ,
  Achsen, Präzision und Fehlfunde und schreibt eine Ergebniszeile; `support_matrix` übernimmt sie (auch für Familien
  ohne bisherige Messung). MD1, MG1, Simos, SID, MED17.5/17.7 bleiben **nicht validiert**, bis echte Paare gemessen sind.

**Vertrauen: signierte Updates**
- Ed25519-Signaturen nach RFC 8032 (reines Python, gegen die RFC-Testvektoren geprüft, keine neue Abhängigkeit).
- Release-Workflow signiert ZIP und Installer, sobald das Secret `UPDATE_SIGNING_KEY` existiert; ist ein öffentlicher
  Schlüssel im Repository, fehlt aber das Secret oder passt es nicht, bricht der Release ab.
- Die App verlangt eine gültige Signatur, sobald ein öffentlicher Schlüssel eingebaut ist – geprüft wird **vor** dem
  Download, gebunden an Dateiname und SHA-256. Einrichtung: `docs/RELEASE.md` → „Signierte Updates einrichten“.

**Prüfsummen** (neu: *Werkzeuge → Prüfsummen-Tabellen der Datei prüfen / korrigieren …*)
- Selbstbeschreibende Prüfsummen-Tabellen (Start, Ende, Wert, ~Wert) werden gefunden; ein Block gilt nur als bewiesen,
  wenn ein Verfahren den gespeicherten Wert am **unveränderten Original exakt** reproduziert (Basisadresse, Byte-Reihenfolge
  und Verfahren kommen aus der Datei, nicht aus einer Familienliste).
- Gemessen an Originaldateien: ME7.5 (2 Stände) 68/68 und 70/70 Blöcke, ME7 Volvo 51/52 und 67/68, MED9 66/68, ME9 63/63
  (32-Bit-Wortsumme). EDC16C31/C35 und EDC17CP09: Die gefundenen Einträge sind offenbar keine Prüfsummen
  (Füllmuster, unplausible Bereiche); kein Verfahren reproduziert sie – keine Korrektur.
- Korrektur mit Byte-Vorschau, verketteter Blöcke in mehreren Durchgängen, Endprüfung aller Blöcke, sonst Rücknahme;
  rückgängig machbar. Prüfbericht vor dem Export warnt bei falschen Tabellen-Prüfsummen. Signaturen (z. B. RSA) und
  weitere ECU-Prüfungen sind nicht abgedeckt – keine Flashfreigabe.

**Arbeitsoberfläche**
- Hinweisbalken nach dem Öffnen: erkanntes Steuergerät mit Fundstelle und gemessener Unterstützungsstatus
  (z. B. „Bosch EDC17CP09 … validiert – 463 von 703 Kennfeldern exakt, Präzision 85 %“), Knopf zur Matrix.
- Kennfeldkatalog: Filter nach gemessener Konfidenz (gesichert / wahrscheinlich / Vermutung / geprüft bzw. aus Definition).
- Tastenkürzel: Strg+G war doppelt belegt; Funktionsgraph jetzt Strg+Umschalt+U (ein Test verhindert Doppelbelegungen).

**ORI/MOD-Vergleich**
- Neuer Reiter **„Außerhalb bekannter Kennfelder“**: geänderte Bereiche, die zu keinem Katalog-Kennfeld gehören
  (zusammengefasst bei Lücken bis 16 Byte, größte zuerst), Doppelklick springt zur Stelle – dort stecken oft
  unbekannte, aber angepasste Tabellen.
- Neuer Reiter **„Differenz-Heatmap“**: Änderung je Zelle (MOD − ORI, roh) für das gewählte Kennfeld, rot höher, blau niedriger.

**Kennfeldnamen aus Schwesterständen** (neu: *Werkzeuge → Softwarestände: Namen aus Schwesterstand übernehmen …*)
- Namen und Layouts einer Definition (XDF/A2L/RomRaider/CSV) werden auf einen verwandten Softwarestand ohne Definition
  übertragen: Ausrichtung über Anker, die in beiden Dateien genau einmal vorkommen; Vorschlag nur mit Beleg am Zielort
  (identisch · gleicher Kopf · ähnliche Werte · gleiche Umgebung), immer ungeprüft.
- Gemessen gegen die eigene XDF des Zielstands (`tools/name_transfer_benchmark.py`): MED17.1.62 404A/H/L, 5 Richtungen,
  60–80 % der gemeinsamen Namen übertragen, davon **92–96 % richtig** (über gleiche Adresse allein: 6 %); MSD80-Schwesterstände
  99 % übertragen, 100 % richtig; nicht verwandte ME7.5-Stände: 14 von 110 übertragen (Zurückhaltung statt Raten).
- Kein Funktionsklassifikator: Namen kommen nur aus einer Definition, nicht aus einem Modell.

**Kennlinien** (neu: Kennlinien-Datensätze `n, X[n], W[n]`, z. B. Bosch Cur_Xs16Ws16; 1D exakt, alt → neu)
- *Test:* MSD85 642 → **1128**, MSD80 439 → **839**, EDC16C35 562 → **942**, EDC16C31 544 → **943** (Präzision 1D 89–96 %).
- *Entwicklung:* EDC17CP09 946 → **1668** (93 %), ME9.2.1 385 → 597, ME9 205 → 271, MS45 176 → 200; 2D-Werte unverändert.
- Nur in Datensatz-Ketten, an geraden Adressen und in der Byte-Reihenfolge, die die Kennfeld-Datensätze der Datei
  dominiert; Achsenketten (Siemens MS4x) werden nicht als Kennlinie gelesen. Eigene Evidenzklasse `curve:record`
  (gemessen 92 % Treffer). Negativkontrollen weiterhin 0 Kandidaten.

**Geschwindigkeit** (gleicher Rechner, 16 Kerne; Ergebnisse bitgenau gleich, per Vergleich geprüft)
- Kennfeldsuche nutzt mehrere CPU-Kerne: Zeilenabstands-Suche je Datenbereich und Lesart in eigenen Prozessen,
  Datensatz- und Raster-Suche laufen gleichzeitig dazu. EDC17CP09 (2 MB) 33 → **10 s**, MED17.1.62 25 → **7 s**,
  EDC16C31 (4,6 MB) 22 → **11 s**, MSD85 12 → 7 s. Kleine Dateien (< 256 KB Daten) bleiben einkernig.
- Mehrere Prozesse nur, wenn ein geschützter Einstiegspunkt sie einschaltet (App, Benchmark);
  `ECU_STUDIO_WORKERS=1` erzwingt einen Kern. Abbrechen verwirft noch nicht gestartete Teilaufgaben.
- Datensatz-Suche: vektorisierter Vorfilter und Achsenprüfung ohne NumPy-Overhead (2 MB: 1,7 s statt mehrere Sekunden).

**Steuergeräte-Identifikation und Unterstützungsmatrix**
- Neu: Kennungen aus der Datei mit Fundstelle – Bosch-EPK, Hardware-/Softwarenummer, VAG-Teilenummer, Siemens-Hardware;
  widersprüchliche Angaben werden als „mehrdeutig“ gemeldet.
- Neu: **Hilfe → Unterstützte Steuergeräte …** mit Status (validiert / teilweise / experimentell / nicht validiert),
  gemessenen Softwareständen, Kennzahlen und benötigten Dateien; Datei-Info zeigt Kennung und Status der geladenen Datei.
- `tools/support_matrix.py` erzeugt Matrix und docs/ECU_SUPPORT.md aus Benchmark-Ergebnissen; `benchmark_suite` misst
  zusätzlich den exakten Datentyp (Breite, Byte-Reihenfolge, Vorzeichen).

- Neu: [ROADMAP.md](ROADMAP.md) – in Entwicklung, geplant, wartet auf Referenzdaten, bewusst nicht geplant; Kurzfassung in der README.
- `docs/KONKURRENZANALYSE.md` heißt jetzt `docs/OPEN_SOURCE_VERGLEICH.md` und ist auf dem aktuellen Stand (veraltete Lücken und die `.ols`-Entscheidung korrigiert).
- Repository aufgeräumt und neu gegliedert: `examples/` in `demo/`, `checksum/`, `memory/`, `holdout/`, `templates/` mit Übersicht; `docs/README.md` als Doku-Index; Paketdateien (`launcher.py`, gesperrte Abhängigkeiten) nach `packaging/`; Testdateien mit sprechenden Namen statt Versionsendungen; 59 alte Berichte aus `docs/history/` entfernt (in der Git-Historie bis v1.15.0).
- Versehentlich committeter Test-Zwischenordner (mit Kopien von `cmd.exe`) aus der gesamten Historie entfernt; neue Repository-Tests verhindern Programmdateien, Archive, Firmware außerhalb von `examples/` und lokale Pfade im Repository.
- Hinweise beim Öffnen von ZIP-, HEX- und S19-Dateien nennen jetzt die tatsächlichen Menüpunkte.
- README neu gestaltet: Banner, Inhaltsübersicht, Installation in drei Schritten, Funktionsübersicht, Erkennungsgüte, Steuergeräte-Tabelle mit Status, Ablaufdiagramm, Sicherheitshinweis.
- Neu: [docs/PROGRESS.md](docs/PROGRESS.md) – Fortschritt der Kennfelderkennung je Meilenstein und Steuergerät; jeder Stand wurde aus der Git-Historie neu gemessen, mit denselben Referenzen und derselben Messmethode.
- **Vorherige Version wiederherstellen** (Einstellungen): tauscht die vom Updater angelegte Sicherung mit der aktuellen Version, Selbsttest, bei Fehlschlag zurück; die ersetzte Version bleibt als Sicherung (Updater-Modus `-Restore`, getestet: hin, zurück, defekte Sicherung, keine Sicherung).
- **Update-Praxistest vor jeder Veröffentlichung:** Der Release-Workflow aktualisiert auf Windows Server 2022 und 2025 das zuletzt veröffentlichte Release mit dessen eigenem Updater, prüft Oberfläche, Wiederherstellen und Installer; nur bei Erfolg wird veröffentlicht.
- Hinweis zur Windows-SmartScreen-Warnung (nicht code-signiert) in README und automatisch in jedem Release-Text; im Update-Fenster wird dieser allgemeine Teil ausgeblendet.

## 1.15.0 (21.10.2026)

**Installation und Updates**
- Windows-Paket ohne Python: ZIP entpacken und `ECU-Studio-AI.exe` starten, oder Installer mit Startmenü-Eintrag und Deinstallation.
- Automatische Update-Prüfung (abschaltbar unter Einstellungen) mit geprüftem Download, Sicherung der alten Version und automatischer Wiederherstellung bei Fehlern.

**Kennfelderkennung** (gemessen gegen Hersteller-A2L)
- Bosch EDC17CP09: exakt erkannte Kennfelder 46 → 157, Präzision 62 → 71 %.
- Siemens MSD80/MSD85 (unabhängige Testdaten): 91–96 → 133–148 exakt.
- Achsen gespeicherter Datensätze werden als eigene Kandidaten gemeldet (85–92 % exakt).
- Denso/SH-2 (Subaru), ME7.5-Speicherbasis, 68k-Verweise (GM) neu; schnellere Suche.

**Definitionen und Sicherheit**
- A2L-Datensätze mit gespeicherten Achsen werden importiert; Software-Kennung (EPK) wird geprüft, auch bei Segmentkopplung.
- Flash-Preflight prüft jede geänderte Byteposition und Zwillingskennfelder auf gleiche Änderung; Prüfsummen, Preflight und Flashvalidierung werden getrennt ausgewiesen.
- Checksummen: weitere Verfahren, Korrektur mit Byte-Vorschau, Suche unbekannter Prüfsummen-Layouts.
- WinOLS-Projekte (.ols/.kp) werden klar abgewiesen statt als Rohdatei geöffnet.

Unterstützte Steuergeräte und Messwerte: docs/ECU_SUPPORT.md. Keine Flashfreigabe – geänderte Dateien vor dem Flashen mit einem geeigneten Werkzeug prüfen.

## Entwicklungsverlauf zu 1.15.0 (18.–21.10.2026)

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
- Repository: historische Berichte nach `docs/history/` (inzwischen entfernt, in der Git-Historie bis v1.15.0), neue README, `.gitignore`/`.gitattributes` (keine Firmware, keine Build-Artefakte), GitHub-Actions-Workflow für pytest.
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
- **Benchmark-System** (`tools/benchmark_suite.py`, Vorlage `examples/templates/benchmark_manifest.template.json`): je Paar Referenzkennfelder, Funde, Recall, exakte Layouts, richtige Achsen, Laufzeit, optional Spitzenspeicher; Präzision/False Positives/False Negatives **nur bei vollständiger Referenz**; Rolle `test`/`development`/`training` je Paar; nahezu identische Softwarestände (≥ 90 % gleiche Bytes) bilden eine Gruppe.
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
