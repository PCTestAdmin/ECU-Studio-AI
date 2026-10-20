# Konkurrenzanalyse quelloffener ECU-Editoren (Stand 20.10.2026)

Grundlage: GitHub-Metadaten, Projektbeschreibungen und gezielt gelesene Quelldateien. Fremder Code wurde
**nicht** übernommen; übernommen wurden nur Ideen, eigenständig implementiert und an eigenen Referenzen gemessen.

## Durchgang 1 – Funktionsvergleich

| Projekt | Lizenz | Sprache | Schwerpunkt | Automatische Kennfeldsuche | Checksummen | Definitionen |
|---|---|---|---|---|---|---|
| [ZedSuite](https://github.com/LeZed97/ZedSuite) | GPL-3.0 | TypeScript + Rust (Tauri) | Editor, EDC15/EDC16 | ja, nur EDC15/16, mit „erwartete vs. gefundene Kennfelder“ | EDC15P, EDC16 | XDF, JSON-Mappack, **WinOLS-.ols-Import** |
| [romHEX14 community](https://github.com/ctabuyo/romHEX14-community) | **keine Lizenz** | C++ | A2L-Editor | – | – | A2L |
| [bimmerstein-bin-analyzer](https://github.com/CAATZ/bimmerstein-bin-analyzer) | GPL-3.0 | TypeScript | BMW MS41 | Achsen als monotone Läufe ohne Anzahl-Präfix | MS41 | XDF |
| [RomRaider](https://github.com/RomRaider/RomRaider) | GPL-2.0 | Java | Subaru, Logger | nein (nur Definitionen) | Subaru | RomRaider-XML |
| [UniversalPatcher](https://github.com/joukoy/UniversalPatcher) | GPL-3.0 | C# | GM, Patches | Tabellensuche nach Mustern | **Checksummen-Forschung** (Bereich/Verfahren suchen) | XDF, eigene |
| [MxT / ME7Tuner](https://github.com/TracqiTechnology/MxT) | Apache-2.0 | Kotlin | ME7/MED17-Rechner | nein | – | XDF, A2L |
| [tune-editor](https://github.com/TheFlashBold/tune-editor) | GPL-3.0 | TypeScript | Simos12/18, DQ250 | nein | Simos | A2L, XDF, **OLS-Parser** |
| [xdfkit](https://github.com/nyetlabs/xdfkit) | LGPL-3.0 | Go | Formatwandler | – | – | XDF, KP, DAMOS, A2L |
| [medc17-checksum-tool](https://github.com/ConnorHowell/medc17-checksum-tool) | MIT | Python | MED17/EDC17 | – | MED17/EDC17 | – |

**Was ECU Studio AI fehlt (Stand vor dieser Runde):** Werkzeug zum Finden unbekannter Checksummen-Layouts;
A2L-Datensätze mit gespeicherten Achsen (`STD_AXIS`, `COM_AXIS`) – sie wurden komplett abgelehnt;
WinOLS-.ols-Import; familienbezogene Vollständigkeitsanzeige („erwartet vs. gefunden“).

**Was ECU Studio AI voraus hat:** familienübergreifende Erkennung ohne Definition mit Code-Verweisen
(C16x, 68k, Denso, HC11, 8051), gemessene Trefferquoten je Beweisart, Fehlalarm-Messung, Flash-Preflight je Byte.

## Durchgang 2 – Technische Tiefenanalyse

| Ansatz (Quelle) | Mechanismus | Nutzen für uns | Lizenz/Integration | Entscheidung |
|---|---|---|---|---|
| Checksummen-Suche (UniversalPatcher `ChecksumSearcher.cs`, native DLL) | Bereiche × Verfahren durchprobieren, bis der gespeicherte Wert entsteht | Grundlage für ECU-spezifische Profile | Idee frei; eigener Code (Präfixsummen, NumPy) | **umgesetzt** |
| A2L-RECORD_LAYOUT (tune-editor `a2lParser.ts`, MxT) | Positionen von Anzahl, Achsen, Werten | echte OEM-Referenzen, A2L-Import | eigener Code nach ASAP2-Spezifikation | **umgesetzt** |
| Achsen ohne Anzahl-Präfix (bimmerstein `axes.ts`) | jeder streng monotone Lauf ist Kandidat, Zähler-Malus | höhere Trefferquote bei MED17-Gruppenachsen | einfach | **nicht übernommen** (s. Durchgang 3) |
| OLS-Container (ZedSuite, tune-editor `olsParser.ts`) | Marker 0x42007899 je Binärversion | Projekte aus WinOLS öffnen | GPL-3.0 kompatibel | **vertagt**: keine .ols-Testdatei vorhanden |
| „Erwartete Kennfelder“ (ZedSuite) | Liste je Familie | Vollständigkeitsanzeige | trivial | vertagt (braucht gemessene Listen je Familie) |
| EDC15/EDC16-Checksummen (ZedSuite), MED17 (medc17-checksum-tool) | feste Algorithmen | Profile für diese Familien | MIT/GPL | vertagt: ohne Original-Dumps nicht prüfbar |

## Durchgang 3 – Kritische Gegenprüfung

- **Belegte Messwerte:** Kein untersuchtes Projekt veröffentlicht Trefferquoten gegen unabhängige Referenzen.
  Aussagen wie „automatische Erkennung“ sind dort unbelegt; ZedSuite deckt nur EDC15/16 ab.
- **Monotone Läufe als Achsen (bimmerstein):** In Kalibrierdaten sind viele Zeilen und Kennlinien selbst
  monoton – ohne Anzahl-Präfix oder Code-Verweis ist das keine Achse. Unsere Messung zeigt, dass
  datenmusterbasierte Funde ohnehin nur 19 % treffen; eine weitere ungesicherte Quelle würde die
  Präzision senken. Verworfen.
- **Checksummen-Suche:** Bei vielen geprüften Kombinationen trifft ein 16-Bit-Wert auch zufällig. Deshalb
  meldet unsere Umsetzung die erwartete Zahl an Zufallstreffern, verlangt Bestätigung auf weiteren
  Dateien und erzeugt nur einen Profil-Entwurf mit `reviewed: false`, den die Prüfung abweist.
- **romHEX14:** ohne Lizenz – weder Code noch Ableitungen nutzbar.
- **A2L-Engine:** Risiko falscher Offsets. Gegenmaßnahme: Anzahl wird aus der Datei gelesen und gegen die
  A2L-Höchstzahl geprüft; die Speicherbasis wird nur akzeptiert, wenn ≥ 90 % von ≥ 20 Achsen aufsteigen.
  ME7.2-X5-A2L wurde so korrekt als „passt nicht zur BIN“ erkannt.

## Umgesetzt (gemessen)

| Änderung | Datei | Ergebnis |
|---|---|---|
| ASAP2-RECORD_LAYOUT (NO_AXIS_PTS, AXIS_PTS, FNC_VALUES ROW/COLUMN_DIR, Ausrichtung, COM/FIX/STD_AXIS), linearer RAT_FUNC | `core/a2l.py` | Vorher 0 Objekte (STD/COM_AXIS abgelehnt). Jetzt ME9 2733/2733, ME9.2.1 6147/6147, MS45 4673/4701 verlinkt; Achsen steigen zu 100 % (661/662, 1264/1264, 1265/1270) |
| Speicherbasis aus der Firmware (`suggest_anchor`, konstante Achsen zählen nicht) | `core/a2l.py` | ME9 0x400000, ME9.2.1 0xFC0000, MS45 0 (je 100 %); ME7.2-X5-A2L (anderer Softwarestand, 76–80 %) abgelehnt |
| A2L-Leser: Bytes, die cp1252 nicht kennt | `core/a2l.py` | echte BMW-A2L lesbar statt Abbruch |
| `COM_AXIS` ohne Datei nicht mehr mit der Höchst- statt der echten Stützstellenzahl verlinkt | `core/a2l.py` | vorher falsche Kennlinienlänge möglich |
| A2L als Benchmark-Referenz | `tools/structure_benchmark.py` | erste OEM-Referenzen (ME9, ME9.2.1, MS45) |
| Kopf-Datensätze (nx, ny, X, Y, Z): Limit 55 → 200 | `core/scoped_scan.py` | gegen vollständige A2L: ME9 exakt 20 → 38 (Präzision 45 → 50 %), ME9.2.1 29 → 56 (62 → 63 %), MS45 21 → 28 (64 → 67 %); VAG HS 50 → 59; MS43/MS42 und Fehlalarme unverändert |
| Checksummen-Suche mit Zufallsniveau und Bestätigung | `core/checksum_search.py`, `tools/checksum_search.py` | synthetisch geprüft; reale Validierung fehlt (keine Dumps mit bekanntem Layout) |
| Checksummen-Korrektur mit Byte-Vorschau in der Oberfläche | `ui/main_window.py` | Standard „Nein“, rückgängig machbar, keine Flashfreigabe |

## Nächste Schritte

1. WinOLS-.ols-Import (Formatbeschreibung in ZedSuite/tune-editor, GPL-3.0) – sobald eine .ols-Testdatei vorliegt.
2. MED17/TriCore: 1971 XDF-Kennfelder, Trefferquote 10–16 %. Viele Kennfelder nutzen getrennte Gruppenachsen;
   dafür braucht es Verweise aus dem Programmcode (TriCore-Adressierung), nicht mehr Datenmuster.
3. Checksummen-Profile für MED17/EDC17 und EDC15/16 nach den offenen Algorithmen – nur mit echten Original-Dumps prüfbar.
