# Open-Source-Algorithmusvergleich zur Kennfelderkennung (Qualitätsphase 4)

Stand 24.11.2026, Branch `feat/post-rc1-recognition-nextgen` (Draft-PR #30). Einordnung aller Aussagen:
**rc1** (in 1.21.0-rc1 enthalten), **Draft-PR** (in PR #30, nicht veröffentlicht), **experimentell** (hinter einem
Schalter, Standard aus), **entwicklungsgemessen** (an den Entwicklungsdaten des Datengebers gemessen),
**Holdout-Regression** (Holdout nur zur Regressionskontrolle, nicht unabhängig), **unabhängig validiert** (bisher
nichts), **nur Idee**, **verworfen**.

## Vorgehen und Sicherheit

- Die fünf Projekte wurden als Quelltext in ein temporäres Verzeichnis außerhalb aller Arbeitskopien geklont und
  **nur gelesen**. Es wurden keine fremden Skripte, Installer, Build-Schritte oder Abhängigkeiten ausgeführt.
  Kein fremder Code hatte Zugriff auf private Firmwareverzeichnisse.
- Aus fremden Projekten wurde **kein Quelltext kopiert, übersetzt oder umbenannt**. Übernommen wurden nur Ideen.
  Die Umsetzung ist eigenständig und an unseren Daten gemessen.
- Lizenz: ECU Studio steht unter GPL-3.0. Vier der fünf Projekte sind GPL-3.0 (eines „-only“, eines „-or-later“),
  eines MIT. Eine Codeübernahme wäre damit grundsätzlich lizenzrechtlich möglich (unter Erhalt der Hinweise). Sie
  fand trotzdem nicht statt, weil die Algorithmen auf andere Architekturen zugeschnitten sind und eine eigene
  Umsetzung kleiner und prüfbarer ist.
- Fremde Firmwaredateien (z. B. in Testordnern) wurden weder geöffnet noch verwendet.

## A. Projekte

| Projekt | URL | untersuchter Commit | Lizenz |
|---|---|---|---|
| OpenRemap Core | https://github.com/v-arapidis/openremap-core | `6c6ba85` (24.10.2026) | MIT |
| ZedSuite | https://github.com/LeZed97/ZedSuite | `77d75fb` (08.10.2026) | GPL-3.0-only |
| BimmerStein (bin-analyzer) | https://github.com/CAATZ/bimmerstein-bin-analyzer | `3149194` (18.11.2026) | GPL-3.0-or-later |
| PPD Maps | https://github.com/jazdw/ppd-maps | `71b08ad` (11.03.2013, archiviert) | GPL-3.0 |
| Denso ECU Toolkit | https://github.com/PabloSoage/Denso-ECU-Toolkit | `b7be067` (23.11.2026) | GPL-3.0 |

### A.1 OpenRemap Core

- **Algorithmus:** Kennfeldsuche über Wertebilder (`openremap/_rs/src/maps/map_hunter.rs`): Glätte-Bewertung,
  Abschläge für Platzhalterwerte (`is_sentinel` Z. 90, `sentinel_penalty` Z. 197). `probe_table_series` (Z. 401)
  sucht hinter einem Fund weitere Blöcke gleicher Geometrie („Serien“, die sich Achsen teilen).
- **Codebezug:** `openremap/core/arch/tricore.py` erkennt nur `movh.a` + `lea`-Paare und eine globale Basis `a0`
  (`_find_a0` Z. 84). `openremap/core/arch/refs.py` `_detect_base` (Z. 154) wählt eine Ladebasis nach der Zahl der
  Querverweise, die in Tabellenbereiche fallen (`_MIN_BASE_HITS = 3`, Z. 78). Querverweise gehen nur als
  Bewertungsbonus ein (`openremap/core/services/maps/scan_maps.py` `xref_for_file` Z. 90).
- **Voraussetzungen:** keine Definition. Grenzen: keine Argumentauflösung, keine Achsenzuordnung über Code, keine
  Unsicherheitsangabe je Datentyp.
- **Tests:** 133 Testdateien. Keine reproduzierbaren Erkennungsbenchmarks gegen Definitionen im Repository gefunden.
- **Vergleich mit uns:** `movh.a`/`lea` und Basisregister sind bei uns seit rc1 vorhanden, dazu Stapelslots,
  Basisregister a0/a1/a8/a9, Relokation und Datenfluss. Neu für uns wäre nur die Basiswahl nach Trefferzahl.
  **Nutzen gering:** Unsere Basen kommen aus dem Code, nicht aus Treffern.

### A.2 ZedSuite

- **Algorithmus:** Familien-Detektoren mit festen Vorlagen
  (`src-tauri/src/detector/ecu/bosch/edc16u31/mod.rs`): `detect_driver_wish_shared_axes` (Z. 1320) sucht gemeinsame
  Achsen mit fest codierten Dimensionen und Drehzahlbereichen. `identify_map_type_by_axes` (Z. 3023) **benennt
  Kennfelder nach Wertebereichen** der Achsen. Dazu eine Signaturdatenbank je Familie (`signatures.rs`).
- **Tests:** 54 Rust-Tests.
- **Vergleich:** Familien-Sonderlösungen und Namen aus Werten widersprechen unseren Regeln („Werte benennen keine
  Funktionen“, keine Sonderlösungen für einzelne Softwarestände). **Verworfen.**

### A.3 BimmerStein

- **Algorithmus:**
  - Achsen-Pool mit Anzahlpräfix (`packages/engine/src/pool.ts`: `scanPrefixedAxes` Z. 29, `findPoolAnchor`
    Z. 142, `poolAnchors` Z. 160, `poolAdjacentTables` Z. 229): Zu einer Tabelle gehört das nächste vorangehende
    Achsenpaar mit passenden Anzahlen. Mehrfachnutzung ist erlaubt, Alternativen werden mitgeliefert.
  - Für MS41 löst `resolveMs41CurveAxes` (`packages/engine/src/family/ms41/runtime-axes.ts` Z. 108) Achsen über
    RAM-Zustandszellen auf: Vorbereitungsroutinen schreiben Zellen, Leseroutinen lesen sie. Der Rückwärtsgang läuft
    über **alle** Vorgängerpfade, mit Zwischenspeicher. Aufgerufene Routinen erhalten den Zustand
    (`preservesMs41State` Z. 65). Bei uneinigen Pfaden bleibt die Achse ungelöst.
- **Weitere Teile:** `packages/core/src/types.ts` (`DetectorTier` Z. 84; die „Axis Library“ Z. 63 ist manuelles
  Zuweisen, keine Erkennung). `packages/formats/src/xdf.ts` exportiert gemeinsame Achsen als verknüpfte Objekte.
- **Tests:** 158 Testdateien.
- **Vergleich:** Der Allpfad-Ansatz entspricht unserem Problem bei MSD80 (Prelookup-Ergebnis als impliziter
  Zustand). Unser Positionsprinzip nimmt dagegen die letzten zwei Prelookups **eines** Pfades. Die Allpfad-Idee
  passt auf die Klassen „kein/nur ein Prelookup auf dem Pfad“ und „beide gleich“ (zusammen 2 973 Aufrufe, siehe B).

### A.4 PPD Maps

- **Algorithmus (`mapsearch.cpp`):**
  - `findTableStarts` (Z. 103): Folgen von mindestens drei 32-Bit-Zeigern in den Datenbereich.
  - `examineAddr` (Z. 604): Kennfeld oder Achse, je nach Gültigkeit einer Achse.
  - `search`: Zeigertupel ergibt Kennfeld + Achsen.
  - `findExistingAxis` (Z. 675): gemeinsame Achsen über identische Rohadresse.
  - `checkR2` (Aufruf Z. 596): Prüfung der PowerPC-Small-Data-Basis r2.
  - `axis.cpp`: Anzahl als Byte oder 16 Bit; Achsenwerte **nicht fallend** (gleiche Stützstellen erlaubt), höchstens
    32 Punkte.
- **Tests:** keine. Das Projekt ist archiviert.
- **Vergleich:** Zeigertabellen (Daten, X, Y) sind bei uns als `pointer_triples` vorhanden (Draft-PR, QP2).
  Relevante Idee: Achsen dürfen **gleiche Stützstellen** haben. Bei uns galt bisher streng steigend.

### A.5 Denso ECU Toolkit

- **Algorithmus (`Scripts/AnalyzeDensoMaps.py`, Ghidra-Skript für SH/V850):**
  - `resolve_descriptor_address` (Z. 139) folgt dem Argumentregister R4 einschließlich Verzögerungsslot.
  - `rank_callees` (Z. 310) und `detect_masters` (Z. 336) finden Interpolationsroutinen selbst: Aufgerufene
    Routinen werden nach dem Anteil ihrer Aufrufe geordnet, die einen gültigen Deskriptor übergeben
    (`MIN_CALLS = 20`, Z. 47).
  - `decode_2d`/`decode_3d` prüfen die Deskriptoren: ROM-Zeiger, Daten hinter Achsen.
  - `infer_widths` (Z. 263) bestimmt die Breite nur aus der exakten Lücke zum nächsten Block (1/2/4), sonst leer.
- **Weitere Teile:** `Scripts/AnalyzePotentialDensoMaps.py` ist ein Blindscan über alle Deskriptoren
  (Obermenge). `docs/findings.md` beschreibt den Elementtyp aus dem Ladebefehl der Leseroutine.
- **Tests:** 129, nur für den Betrachter, nicht für die Erkennung.
- **Vergleich:** Die Rollenfindung über den Anteil gültiger Aufrufe entspricht unserem `prelookup_roles` /
  `record_roles` (`PRELOOKUP_SHARE`, `MIN_ROLE_CALLS`). Der Typ aus Ladebefehlen entspricht `routine_cells`
  (Draft-PR). Die Breite nur aus exakter Lücke entspricht `cell_widths`. **Bestätigt unseren Weg.** Neu wäre nichts
  Wesentliches.

## B. Vergleichsmatrix

Legende: **I** implementiert und im Quellcode nachgewiesen, **T** teilweise, **D** nur dokumentiert, **–** nicht
vorhanden, **?** nicht überprüfbar.

| Fähigkeit | OpenRemap | ZedSuite | BimmerStein | PPD Maps | Denso | ECU Studio (PR #30) |
|---|---|---|---|---|---|---|
| Allgemeine Kennfeldsuche | I | T (familienweise) | I | T (Zeiger) | T (Blindscan) | I |
| Codebasierte Erkennung | T (xref-Bonus) | – | I (MS41) | I (Zeiger) | I | I |
| Dynamische Adressauflösung | T (movh/lea, a0) | – | T (Zustandszellen) | T (r2) | T (R4 + Slot) | I (Basen, Stapel, Datenfluss) |
| Automatische Achsenzuordnung | – | T (Vorlagen) | I | I | I | I |
| Gemeinsame Achsen | T (Serien) | T (Vorlagen) | I | I (Adressgleichheit) | – | I |
| Funktionsidentifikation | – | T (aus Werten, verworfen) | – (manuell) | – | – | I (mit Enthaltung) |
| Datentypprüfung | – | – | T | T (Achse) | I (Ladebefehle, Lücke) | I |
| Unsicherheitsbewertung | T (Score) | – | T (Stufen) | – | T (leer statt Raten) | I („?“, Status) |
| Reproduzierbare Benchmarks | – | – | T (Eval-Pakete) | – | – | I (privat, Zählwerte) |

### Die fünf besten Ideen (Nutzen × Nachweisbarkeit ÷ Aufwand/Risiko)

1. **Achsen mit gleichen Stützstellen zulassen, wenn der Code sie als Achse liest** (Anstoß: PPD-Achsengültigkeit
   „nicht fallend“; eigene Verbindung mit gelernten Routinen). Hoher Nutzen: MSD80 hat 8 857 Tabellenaufrufe, deren
   beide Prelookup-Achsen streng genommen nicht lesbar sind. Gut messbar, geringer Aufwand. **Umgesetzt als
   Prototyp 1** (Abschnitt C).
2. **Allpfad-Zustandsauflösung** (BimmerStein MS41): Prelookups über alle Vorgängerpfade, ungelöst bei
   Uneinigkeit. Mittlerer Nutzen (2 973 Aufrufe), mittlerer Aufwand. **Prototyp 2** (Abschnitt C).
3. **Selbstprüfende Rollenfindung und Typ aus Ladebefehlen** (Denso): bei uns schon vorhanden. Bestätigung, kein
   neuer Code.
4. **Serien gleicher Geometrie und Basiswahl nach Treffern** (OpenRemap): geringer Nutzen, weil Basen bei uns aus
   dem Code kommen. Nur Idee.
5. **Zeigertabellen (Daten, X, Y)** (PPD): bei uns als `pointer_triples` vorhanden. Bei MEVD17.2 fanden sich 0
   Flash-Zeigertabellen. Kein weiterer Nutzen.

Verworfen: Vorlagen je Familie und Namen aus Wertebereichen (ZedSuite).

## C. Prototypen und Vergleich mit unserem Stand

Alle Prototypen sind eigene Umsetzungen hinter Schaltern und wurden zuerst in privaten Prüfskripten gemessen (nur
Zählwerte, A2L nur zur Auswertung), danach im vollen Entwicklungsbenchmark (58 Abbilder).

| Prototyp | Anstoß | Ergebnis (Entwicklungsdaten) | Entscheidung |
|---|---|---|---|
| 1. Code-belegte Achsen (`CODE_AXES`) | PPD Maps: Achse gültig, wenn nicht fallend | +3 101 exakte 2D-Kennfelder (MEVD17.2 +1 767, MSD80 +1 334), 0 verloren; 46 neue falsche Achsadressen, davon 38 wertgleiche Kopien | **übernommen** (Draft-PR), mit Markierung |
| 2a. Vorabsuchen im Aufrufer | BimmerStein: Zustand über alle Vorgängerpfade | 0 Auflösungen bei 160 Aufrufen (2 MSD80-Abbilder) | **verworfen** |
| 2b. Vorabsuchen derselben Routine (`PRE_FUNCTION`) | BimmerStein, eingeschränkt auf eindeutige Fälle | allein: +50 exakte 2D-Kennfelder (nur MSD80; MEVD17.2 unverändert), 0 verloren, +7 Verwechslungen (reine Datenmuster-Funde); zusammen mit Prototyp 1: +67 | **übernommen** (Draft-PR); die Achsen zählen nur als Teil einer angenommenen Tabelle |
| 3. Flash-Zeigertabellen für MEVD17.2 | PPD `findTableStarts` | 0 Treffer | **verworfen** (bei uns als `pointer_triples` schon vorhanden) |
| 4. Basisregister mit genau einer Definition | OpenRemap Basiswahl / eigene Datenflussidee | 4 Adressen auf 2 Abbildern | **verworfen** |
| 5. Kennlinien-Datensatzköpfe widerlegen Datenmuster-Funde (`CURVE_HEADS_REFUTE_PITCH`) | eigene Idee aus der Analyse verlorener 1D-Treffer (kein Projekt) | allein: Verwechslungen 5 113 → 4 469, exakte 1D-Funde +4 553, 0 verloren (2D und 1D) | **übernommen** (Draft-PR) |
| 6. 8-Bit-Lesart bei Datensatzkopf hinter den 8-Bit-Werten (`CURVE_U8_BY_HEAD`) | eigene Idee (Fehlerklassen der Breite) | +972 richtige Kennlinienbreiten, 0 verloren | **Experiment, aus** (Typänderung; braucht Prüfung außerhalb der Entwicklungsdaten) |

Vergleich mit dem Stand vor QP4 und Ablation: [ENTWICKLUNG_NEXTGEN.md § 9.9](ENTWICKLUNG_NEXTGEN.md#99-gesamtvergleich-und-ablation).

## D. Nachweis je Inspiration

| Projekt | Was wir übernommen haben | Art | Nutzen (gemessen) | Namensnennung |
|---|---|---|---|---|
| PPD Maps (`axis.cpp`) | Gedanke: Achsenwerte dürfen gleich bleiben | Idee, eigene Umsetzung mit Codebeleg und gelernter Breite | siehe Prototyp 1 | in `tricore_refs.py` (Kommentar) und hier |
| BimmerStein (`runtime-axes.ts`) | Gedanke: Achsenzustand über mehrere Wege, ungelöst bei Uneinigkeit | Idee, eigene Umsetzung (Routine statt Pfad, nur genau zwei Achsen) | siehe Prototyp 2b | in `tricore_refs.py` (Kommentar) und hier |
| Denso ECU Toolkit | keine Übernahme; bestätigt Rollenfindung, Typ aus Ladebefehlen, Breite aus exakter Lücke | – | – | hier |
| OpenRemap Core | keine Übernahme (Basiswahl nach Treffern geprüft, kein Nutzen) | – | – | hier |
| ZedSuite | keine Übernahme (Vorlagen, Namen aus Werten widersprechen unseren Regeln) | – | – | hier |

Kein fremder Quelltext wurde kopiert, übersetzt oder umbenannt; daher sind keine fremden Copyright-Hinweise in
unseren Quelldateien nötig. Die Projekte werden hier und in den Code-Kommentaren als Anstoß genannt.

