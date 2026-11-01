# Validierungsbericht 1.19.0 (01.11.2026): Prüfung, Korrekturen, Grenzen

Abschließende Prüfung des Entwicklungszweigs `feature/1.19-recognition` (Basis `main` 0cec5e8 = 1.18.2, vier
Entwicklungs-Commits 8cb0b54, 0a8414c, 4d5982e, be9331f). Gearbeitet wurde in einem eigenen Worktree; die
ursprüngliche Arbeitskopie blieb unverändert. Kein Release, kein Tag, keine Versionsänderung. Firmware und
Referenzdateien haben den Rechner nicht verlassen und liegen nicht im Repository; hier stehen nur Zählwerte.

Entwicklungsbericht mit den Ausgangsmessungen: [ANALYSE_2026-11-01.md](ANALYSE_2026-11-01.md). Herkunft der Daten:
[ECU_SUPPORT.md – Herkunft der lokalen Referenzdaten](ECU_SUPPORT.md#herkunft-der-lokalen-referenzdaten-stand-01112026).
Modell: [MODELLKARTE.md](MODELLKARTE.md).

## 1. Ergebnis in einem Satz

Die neuen Funktionen arbeiten auf allen vorhandenen Vergleichspaaren ohne Rückschritt bei den Erkennungsergebnissen;
die Prüfung fand und behob 15 Fehler (zwei konnten echte Kennfeldwerte verfälschen, drei ließen die Oberfläche
sekunden- bis stundenlang hängen, einer davon schon in 1.18.2). **Die TriCore-Codeerkennung bleibt
experimentell**, weil es keine unabhängige TriCore-Referenz gibt; gemessen ist sie nur an der Entwicklungsdatei.

## 2. Statusbegriffe

| Status | Bedeutung |
|---|---|
| **Validiert** | an unabhängigen Referenzen nachgewiesen, Messung wiederholbar |
| **Experimentell** | vorhanden und getestet, aber nicht an unabhängigen Referenzen nachgewiesen |
| **Nicht validiert** | keine belastbare Messung; keine Aussage zur Erkennung |

| Funktion | Status | Begründung |
|---|---|---|
| TriCore-Interpolationsaufrufe mit Datensatzkopf | Experimentell | nur MSD80 I8A0S (Entwicklungsdatei, Teil-XDF) |
| Drei Erkennungsebenen, Widersprüche | Validiert (Verhalten) | 15 reale Paare unverändert bzw. verbessert; Unit-/GUI-Tests |
| Falsche Definition erkennen | Experimentell | Schwelle an 6 lokalen Paarungen bestimmt (0,1–0,8 % gegen 87–97 %) |
| Datentyp nicht erfunden | Validiert (Verhalten) | Inspektor zeigt Alternativen; 146 Fälle in MSD80 |
| Identifikation mit Stufe | Experimentell | 32 lokale Dateien, keine unabhängige Stichprobe |
| Prüfliste, Entscheidungen, Rücknahme | Validiert (Verhalten) | Tests und echter GUI-Lauf mit Neustart |
| Namensübertragung zwischen Ständen | Experimentell | nur MED17 (Entwicklungsdaten) |
| Reproduzierbares Training | Validiert (Verfahren) | Modell nicht ersetzt; Herkunftssperre ergänzt |
| MG1, MD1, Simos, SID, EDC17 | Nicht validiert | keine Firmware mit Referenz |

## 3. Code-Prüfung und behobene Fehler

| Nr. | Bereich | Fehler | Auswirkung | Behebung |
|---|---|---|---|---|
| F1 | TriCore | `Sites.generic` war ein Klassenattribut und ging beim Erweitern der Aufrufliste verloren | Rollen generischer Routinen fielen weg, je nach Reihenfolge der Dateien | pro Instanz gesetzt, `extended()` übernimmt es; Test |
| F2 | Ebenen | Ein Fund allein über Datenmuster zählte als „unabhängig bestätigt“ | überhöhte Bestätigungszahl | nur Code/Struktur bestätigt; Datenmuster getrennt („stützt die Lage“) |
| F3 | Ebenen | Leere/gelöschte Tabellenbereiche als Warnung | 11–37 % der *richtigen* Definitionen „verdächtig“ | nur noch Hinweis |
| F4 | Ebenen | Eine Definition für eine andere Datei wurde nur kennfeldweise bemängelt | falsche XDF unauffällig importierbar | Gesamtwarnung bei > 10 % Achsumkehr (mind. 20 prüfbare Kennfelder) |
| F5 | GUI-Scan | Ein Fund, der eine Definition teilweise überlappt, kam zusätzlich in die Liste | Doppelungen: MSD80 1, MED17 404A 9 | nur Funde übernehmen, die die Zusammenführung behält |
| F6 | Prüfliste | Ablehnungen galten für jede Datei, unterdrückten stärkere Belege und waren nicht rücknehmbar | gesperrte richtige Funde in anderen Ständen | Bindung an SHA-256 der Originaldatei, Ebene gespeichert, „Entscheidungen …“ mit Rücknahme |
| F7 | Übertragung | Achswerte wurden übertragen, obwohl die Achse am Zielort nicht bestätigt war | **296 von 941 solcher Achsen zeigten falsche Werte** (MED17, 5 Richtungen) | Werte werden nicht übertragen, Hinweis im Kennfeld |
| F8 | Übertragung | Bestätigung durch die Erkennung ignorierte Achsen und Byte-Reihenfolge | falsche Bestätigung möglich | gleiche Byte-Reihenfolge Pflicht; andere Achsen = Konflikt |
| F9 | Übertragung | Übernehmen übersprang gerade die bestätigten Vorschläge (Platz belegt durch unbenannte Erkennung) | beste Vorschläge gingen verloren | ersetzt ungeprüfte, unbenannte Erkennung an derselben Tabelle |
| F10 | Training | Datensatzwerkzeug akzeptierte Rolle *training* ohne Freigabe | MS42 wurde trotz Vermerk „not training“ verwendet | `training_allowed` Pflicht; Kandidatenmodell gelöscht |
| F11 | Doku | Hersteller-A2L-Messungen als aktuell dargestellt | nicht wiederholbare Zahlen | als historisch markiert |
| F12 | Übersetzung | 21 neue Texte ohne Englisch | gemischte Oberfläche | ergänzt; 2061 Texte, 0 offen |
| F13 | Prüfliste | Neuaufbau der Tabelle maß die Spalten nach jeder Zelle neu (quadratisch) | **Oberfläche hing**: 800 Funde 185 s, MSD80 (3832 Funde) über eine Stunde nach jedem Bestätigen/Ablehnen | Spalten einmal nach dem Füllen messen: 800 Funde 0,2 s, 4000 Funde 0,7 s; Test |
| F14 | Ebenen | Die Zusammenführung verglich jeden Fund mit allen behaltenen Tabellen (im Oberflächen-Thread) | Oberfläche nach dem Scan blockiert: MSD80 ohne Definition 1,4 s, mit XDF 5,7 s, MED17 mit XDF 25,6 s | Suche nur im Adressfenster: 0,01–0,13 s, Ergebnis an 7 Paaren × 2 identisch; Test gegen den paarweisen Vergleich |
| F15 | GUI-Scan (seit 1.18.2) | Die 50-%-Regel gegen kuratierte Kennfelder verglich alle Paare | **Fenster nach dem Scan 35–43 s eingefroren**, sobald eine große XDF geladen ist (MED17: 3446 Definitionen) – auch in 1.18.2 | Adressindex, exakt gleiche Regel: MED17 mit XDF 60 s → 20,5 s Scan, längste Pause 0,3 s, gleiche Kennfeldzahl; Test |

TriCore-Prüfung ohne Befund: keine fest eingetragenen Adressen außer den PFLASH-Segmenten 0x80000000/0xA0000000;
Opcode-Tabellen der bedingten Sprünge entsprechen dem TC1.3-Befehlssatz; Datenregister werden nicht verfolgt (JNED/JNEI
ändern daher nichts). **Risiko:** Die Schwellen `RECORD_SHARE` 0,3, `ROLE_SHARE` 0,6 und `RECORD_DOMINANT` 0,75
stammen aus MSD80 und können für andere Stände überangepasst sein.

## 4. Unabhängige TriCore-Blindtests

**Nicht durchführbar.** Gesucht wurde nur an erlaubten Orten (Benutzerprofil, vorhandene Referenzordner):

- Es gibt keinen zweiten TriCore-Vollflash mit Programmcode **und** passender Definition mit dokumentierter Herkunft.
- Der openremap-core-Korpus enthält synthetische Nachbildungen ohne Programmcode.
- Die „V 3.0+“-Dateien zu I8A0S (XDF „I8A0S Custom“, MapSwitchBase-BIN) aus demselben Repository wurden **nicht**
  verwendet: nicht freigegeben, und als gleicher Softwarestand höchstens halb-blind.
- Die früheren Hersteller-A2L (EDC17CP09 `6P8KB574`, EDC16C35 `4M702389`, EDC16C31 `6m661411`, MSD85 `791I200S`,
  MSD80 `37IIAFAA`–`37IIANAA`) liegen lokal nicht mehr vor; ihre Messungen vom 21.10.2026 gelten als historisch.

Ersatzweise geprüft: Auf den übrigen TriCore-Dateien (EDC17C69-Vollflash, EDC17CP09, Kalibrierbereiche MSD80
37IIAFAA, MSD85, MED17 404A) liefert die Code-Analyse vor und nach der Prüfung **0 Deskriptoren** – also keine
ungeprüften zusätzlichen Funde. Eine Präzision oder ein Recall für Code-Funde wird nicht angegeben.

## 5. Regression 1.18.2 → 1.19.0 (gleiches Verfahren, gleicher Rechner, nacheinander)

15 reale Paare (Rolle laut Manifest), Werkzeug `benchmark_suite --memory`:

| Paar | Rolle | exakt 2D | gefunden 2D | exakt 1D | s | MB (1.19) |
|---|---|---|---|---|---|---:|
| MSD80 I8A0S | Entwicklung | **73 → 84** (von 99, Teil-XDF) | 881 → 1116 | 164 → 173 | 10,7 → 12,5 | 86,3 |
| MS43 430069 | Training | 197 → 197 | 315 → 315 | 743 → 743 | 3,8 → 3,8 | 18,6 |
| MS42 0110C6 | Training | 22 → 22 | 143 → 143 | 398 → 398 | 2,2 → 2,1 | 14,0 |
| ME9 770115XE | Entwicklung | 98 → 98 | 212 → 212 | 271 → 271 | 6,7 → 6,0 | 43,1 |
| ME9.2.1 725D601B | Entwicklung | 170 → 170 | 340 → 340 | 597 → 597 | 7,2 → 6,7 | 16,6 |
| MS45 4520D30S | Entwicklung | 30 → 30 | 124 → 124 | 204 → 204 | 3,9 → 3,5 | 43,1 |
| MED17.1.62 ×6 | Entwicklung | 134/136/133/145/128/121 unverändert | unverändert | unverändert | je −0,2 bis −0,8 | 28–33 |
| MED9 1K090711S | Test | 11 → 11 | 379 → 379 | 1 → 1 | 9,5 → 9,2 | 86,9 |
| ME7.5 06A906018CG | Test | 0 → 0 | 110 → 110 | 0 → 0 | 1,6 → 1,7 | 10,8 |
| ME7.5 8E0909518AK | Entwicklung | 43 → 43 | 346 → 346 | 45 → 45 | 6,8 → 6,3 | 43,1 |

Präzision wird nur für vollständige Referenzen genannt (MS43 79 %, MS42 72 %, ME9 62 %, ME9.2.1 72 %, MS45 66 %,
jeweils unverändert); für Teil-XDF (MSD80, MED17, MED9, ME7.5) gibt es **keine** Präzision und keine Gesamtzahl.
14 synthetische Fälle (Zeigertabellen, Negativkontrollen) sind unverändert; die Negativkontrollen bleiben ohne
falschen exakten Fund.

## 6. Grenzfälle und falsche Definitionen

Robustheit (15 Fälle, Speicher mit `tracemalloc`): leere Datei, 1 Byte, ungerade Länge, nur FF/00, Zufall,
MSD80 bei 37/50/99 % abgeschnitten, Programmcode zerstört, Kalibrierung genullt, Halbwörter vertauscht, umgekehrt,
4 MiB (verdoppelt) – **0 Abstürze**, Speicher wächst linear (4 MiB → 173 MB Spitze). Eine A2L einer anderen Familie
wird beim Laden abgewiesen; eine XDF eines anderen Stands erzeugt die Gesamtwarnung (F4). Überlappende Definitionen
sind in MED17-XDF üblich (Tausende) und werden deshalb nicht als Fehler gemeldet.

## 7. Versionsübertragung (MED17, 5 Richtungen, Entwicklungsdaten)

404H→404L, 404L→404A, 404E→404G, 404J→404H, 404A→404L, alt gegen neu: Lage richtig 10026 = 10026, Datentyp und
Bestätigungen identisch, falsche Achsadressen 0 = 0. Unterschied nur bei nicht bestätigten Achsen: vorher 941 mit
Werten (296 davon falsch), jetzt leer mit Hinweis (F7). Größe, Datentyp und Byte-Reihenfolge werden für eine
Bestätigung verlangt; verschobene Achsen verhindern sie (F8).

## 8. Lernmodell

Bootstrap (2000 Ziehungen) mit Familien-Auslassung, 228 Zeilen, 66 positiv, keine doppelten Zeilen zwischen Familien:

| Ausgelassene Familie | AUC-Differenz neu − ausgeliefert (95 %-KI) | Brier neu | Brier ausgeliefert |
|---|---|---:|---:|
| MS42 | [−0,069; +0,027] | 0,148 | 0,157 |
| MS43 | [−0,092; +0,070] | 0,170 | 0,125 |

Kein belegbarer Vorteil → **das ausgelieferte Modell bleibt**. MS42 und MS43 sind Schwesterfamilien; eine echte
Prüfung an unbekannten Familien ist damit nicht möglich. Herkunftsproblem: Das ausgelieferte Modell vom 19.10. nennt
MS42 (Vermerk „not training or redistribution“) sowie SIM2K-, MSS54- und TunerPro-Daten ohne dokumentierte Herkunft
als Trainingsdaten; die Originaldaten fehlen. Das Kandidatenmodell vom 01.11. (mit MS42) wurde gelöscht.
Nutzerentscheidungen fließen nicht automatisch ins Training (siehe Modellkarte §2b′).

## 9. Leistung und Oberfläche

Reaktionsfähigkeit: Ein 20-ms-Zeitgeber im Oberflächen-Thread misst die längste Pause während Scan und Übernahme
(sichtbares Fenster, je 2 Läufe, gleicher Rechner, nacheinander):

| Fall | 1.18.2 | 1.19 vor F14/F15 | 1.19 geprüft |
|---|---|---|---|
| MSD80 ohne Definition: Dauer / längste Pause | 28,2 s / 0,05–0,11 s | 31,1 s / 1,4 s | 27,2–27,4 s / 0,09–0,18 s |
| MSD80 mit Community-XDF | – | – | 27,6 s / 0,15–0,18 s |
| MED17 404A mit XDF (3446 Definitionen) | 61–64 s / **40–43 s** | 56–59 s / **35–39 s** | 20,4–20,7 s / 0,22–0,31 s |

Kennfeldzahlen: MSD80 3352 → 3832 (Code-Analyse), MED17 mit XDF 5562 → 5553 (die neun teilweisen Doppelungen aus F5).

Echter GUI-Lauf mit sichtbarem Fenster am MSD80 I8A0S (2 MiB), Einstellungen in einem Wegwerfordner:

| Prüfung | Ergebnis |
|---|---|
| Abbruch nach 1 s | Scan endet nach 0,22–0,25 s, keine Kennfelder übernommen |
| Scan (2×) | 3832 Funde, beide Läufe gleich; Fortschritt stetig bis 100 %, 8 benannte Stufen |
| Datentyp nicht belegt | 146 Funde, Inspektor zeigt „Datentyp NICHT belegt … ebenfalls möglich“ |
| Prüfliste | 3832 Zeilen; Bestätigen, Ablehnen (mit Grund), Speichern |
| Neustart (neuer Prozess) | 2 Entscheidungen geladen, Bestätigung erhalten, abgelehnte Tabelle beim neuen Scan nicht wieder angeboten, bestätigte bleibt |
| Rücknahme der Ablehnung | nächster Scan bietet die Tabelle wieder an |
| Originaldatei | Byte-gleich |

**Offener Befund – einmaliger Absturz:** Von 13 Neustartläufen (Projekt öffnen, zwei Scans, Prüfliste, Rücknahme)
endete einer mit einer Zugriffsverletzung des Prozesses, ohne Python-Fehler und ohne Stack (Fehlerdiagnose war in
diesem Lauf noch nicht eingeschaltet). In 12 Wiederholungen, 6 davon mit eingeschalteter Diagnose und eine nach den Korrekturen F14/F15, trat er nicht
wieder auf. Ursache unbekannt; denkbar ist ein Qt-Objekt, das beim zweiten Scan freigegeben wird, während Signale
noch zugestellt werden. Nicht behoben, weil nicht reproduzierbar – vor dem Release beobachten.

## 10. Tests

Testsuite: **852 bestanden, 9 übersprungen** (vorher 838/9). Mitgelieferter GUI-Prüflauf (`gui_smoke`): 9 von 9 Prüfungen bestanden. `i18n_extract --check`: 2061 Texte, 0 ohne Übersetzung. Kein Test
wurde deaktiviert oder abgeschwächt. Neu durch die Prüfung: Ablehnung pro Datei und Rücknahme, stärkerer Beleg,
Rücknahme im Dialog, Neuscan mit Ablehnungen nach Neuladen, Tabellen-Neuaufbau ohne Spaltenmessung je Zelle,
Adressfenster der Zusammenführung und der 50-%-Regel gleich dem paarweisen Vergleich (mit Mutationsprobe),
unbestätigte Achsen, Erkennung mit anderen Achsen/Byte-Reihenfolge, Ersetzen beim Übernehmen, Datenmuster stützt nur,
falsche Definition als Ganzes, Aufruflisten behalten generische Aufrufe, Trainingsfreigabe.

## 11. Offene Entscheidungen für den Nutzer

1. **Freigabe 1.19.0** (Versionsnummer, Tag, Release) – nicht ausgeführt.
2. **Ausgeliefertes Modell:** weiter ausliefern trotz MS42-Vermerk und undokumentierter Trainingsdaten, oder durch ein
   Modell nur aus freigegebenen Daten ersetzen (dann ohne belegbaren Qualitätsvorteil).
3. **Referenzen für einen unabhängigen TriCore-Test** bereitstellen (anderer Vollflash mit passender Definition und
   Herkunft) oder die I8A0S-„V 3.0+“-Dateien ausdrücklich freigeben (nur halb-blind).
4. **Hersteller-A2L** der historischen Messungen erneut bereitstellen, falls sie wiederholt werden sollen.
5. **Herkunft der lokalen Referenzpaare** ohne Quellangabe klären (ME9, ME9.2.1, MS45, MED17, MED9, ME7).
