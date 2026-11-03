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
| Reproduzierbares Training | Validiert (Verfahren) | nur freigegebene Daten; ausgeliefertes Modell abgeschaltet (§ 12) |
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

Kein belegbarer Vorteil → das ausgelieferte Modell wurde zunächst behalten; **seit 03.11. ist es abgeschaltet** (§ 12). MS42 und MS43 sind Schwesterfamilien; eine echte
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

**Befund – einmaliger Absturz (Nachuntersuchung in § 12.2):** Von 13 Neustartläufen (Projekt öffnen, zwei Scans, Prüfliste, Rücknahme)
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
2. **Ausgeliefertes Modell:** am 03.11. abgeschaltet (§ 12.1); offen sind nur noch die Fragen in § 12.5.
3. **Referenzen für einen unabhängigen TriCore-Test** bereitstellen (anderer Vollflash mit passender Definition und
   Herkunft) oder die I8A0S-„V 3.0+“-Dateien ausdrücklich freigeben (nur halb-blind).
4. **Hersteller-A2L** der historischen Messungen erneut bereitstellen, falls sie wiederholt werden sollen.
5. **Herkunft der lokalen Referenzpaare** ohne Quellangabe klären (ME9, ME9.2.1, MS45, MED17, MED9, ME7).

## 12. Nachtrag 03.11.2026: letzte Release-Blocker

Prüfstand: Commits 41ea49d (Modell abgeschaltet, Worker-Freigabe), b17a4fb (EXE-Prüflauf) und ed70a45 (Fenster
während des Scans), gleicher Rechner. Die GUI-Zyklen liefen mit dem Programmcode von 41ea49d (das Prüfskript startet
das Fenster direkt, ohne den Programmstart aus ed70a45).

### 12.1 Herkunft des Lernmodells und Abschaltung

Die Herkunft aller gelernten Daten wurde einzeln geprüft (Tabelle und Quellen: [Modellkarte § 2d](MODELLKARTE.md)).
Für das Datenmuster-Modell (`candidate_model.json`) ist eine Trainingsfreigabe **nicht nachweisbar**: MS42 trägt den
Vermerk „not training or redistribution“, für SIM2K-Firmware, MSS54 (Repository ohne Lizenz) und TunerPro-Daten gibt
es keine belegte Freigabe, MS43 ist ohne dokumentierte Trainingsfreigabe. Das Modell ist seit 1.15.0 in jedem Release
enthalten und aktiv (Quellcode und Windows-Build; im Build geprüft: `recognition/data/candidate_model.json`).

Entscheidung: Ein Modell wird nur noch angewendet, wenn es den Vermerk `training_data_cleared` trägt; das Training
setzt ihn nur bei ausschließlich freigegebenen Daten (`training_allowed`). Das ausgelieferte Modell trägt ihn nicht und
wird **nicht mehr angewendet**; der Scanbericht und die Scanmeldung sagen das. Die Datei bleibt zur Nachvollziehbarkeit
im Repository (Entscheidung über das Ausliefern: § 12.5). Ein Ersatzmodell wurde **nicht** trainiert: Es gibt keinen
freigegebenen Datensatz mit vollständiger Referenz (rusEFI-Firmware ohne Kennfeld-Referenz, Speeduino CC BY-NC,
MS43 nicht freigegeben). Definitionen, Code-/Strukturerkennung und die regelbasierte Datenmuster-Erkennung bleiben
unverändert.

Gemessene Wirkung (15 reale Paare, gleiches Verfahren wie § 5; „mit Modell“ = be9331f):

| Paar (vollständige Referenz) | exakt 2D / Typ / Achsen | gefunden 2D | Präzision 2D | Fehlfunde |
|---|---|---|---|---|
| MS43 430069 | unverändert (197 / 184 / 175) | 315 → 336 | 79 → 75 % | 65 → 83 |
| MS42 0110C6 | unverändert (22 / 22 / 0) | 143 → 172 | 72 → 66 % | 40 → 58 |
| ME9 770115XE | unverändert (98 / 90 / 96) | 212 → 328 | 62 → 42 % | 81 → 190 |
| ME9.2.1 725D601B | unverändert (170 / 139 / 155) | 340 → 400 | 72 → 64 % | 94 → 145 |
| MS45 4520D30S | unverändert (30 / 29 / 9) | 124 → 241 | 66 → 38 % | 42 → 150 |

Gegen 1.18.2 (selber Rechner): exakte Kennfelder, Datentypen, Achsen, Achsadressen, exakte 1D und Gruppenpaare auf
14 Paaren **gleich**, auf MSD80 besser (§ 5). Teil-Referenzen (MSD80, MED17 ×6, MED9, ME7.5 ×2): nur mehr
Kandidaten (z. B. MSD80 1116 → 1246), keine Präzision angebbar. Synthetisch: Negativkontrollen ohne exakten
Fehlfund; „negative-ramps“ 1 → 10 und „synthetic-pointer-u16“ 0 → 1 ungeprüfte Funde, übrige unverändert.
Laufzeiten gleich oder etwas kürzer. Die zusätzlichen Funde tragen die Evidenzklasse „nur Datenmuster“ (gemessene
Trefferquote 23 %) und stehen als Vermutung in der Prüfliste.

### 12.2 Zugriffsverletzung beim erneuten Öffnen und Scannen

**Diagnose:** Windows-Fehlerberichte sind auf diesem Rechner maschinenweit abgeschaltet
(`HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\Disabled = 1`); Absturzabbilder (`LocalDumps`) lassen sich
ohne Administratorrechte nicht einschalten. Ein eigener Debugger-Wächter (`MiniDumpWriteDump`) erhielt auf diesem
Rechner keine Ausnahme-Ereignisse und lieferte daher keine Abbilder. Eingesetzt wurden stattdessen `faulthandler`
(alle Threads), ein Qt-Meldungshandler, Exitcodes und Speicherwerte je Schritt. Für eine Wiederholung mit Abbildern
(als Administrator):

```
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe" /v DumpType /t REG_DWORD /d 2
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\ECU-Studio-AI.exe" /v DumpType /t REG_DWORD /d 2
```

**Code-Prüfung** (Signale, Worker-Threads, Lebensdauer, Freigabe): Gefunden wurde ein echtes Zeitfenster in Qt 6.12:
Während `QThread` endet, meldet `isRunning()` schon `False`, der Thread läuft aber noch, bis `wait()` zurückkehrt.
Die Oberfläche gab den alten Scan-, Erkennungs- und Definitions-Worker in diesem Fenster frei, sobald ein neuer
gestartet oder das Fenster geschlossen wurde. In 2000 gezielten Versuchen führte das Freigeben in diesem Fenster
zu **keinem** Absturz (Qt wartet im Destruktor selbst); als Ursache ist es daher **nicht belegt**. Härtung ohne
Ausnahmeunterdrückung: beendete Worker werden vor der Freigabe und beim Schließen abgewartet (`_release_worker`,
Regressionstest `test_finished_workers_are_waited_for_before_release`).

**Neuer Befund aus den GUI-Zyklen – Fenster steht während des Scans:** Ein 20-ms-Zeitgeber im Oberflächen-Thread
feuerte bei MS43 während des ersten Scans nach dem Öffnen und während des Scans nach dem Schließen der Prüfliste
**kein einziges Mal** (4,6–5,1 s = ganze Scandauer); ein zweiter Scan lief flüssig (längste Pause 0,05 s). 1.18.2
zeigt dasselbe beim ersten Scan (4,66 s); der Fall „nach der Prüfliste“ ist neu, weil es die Prüfliste nur in 1.19
gibt. Ursache (nachgewiesen): Muss das Fenster während eines Scans neu zeichnen, ruft Qt die Python-Modelle tausendfach
auf; bei jedem Wechsel behielt der Scan-Thread die globale Python-Sperre (GIL) für das volle Umschaltintervall von 5 ms.
Abhängigkeit vom Intervall: 5 ms und 1 ms → 4,7–5,2 s Stillstand, 0,5 ms und 0,2 ms → längste Pause 0,10–0,12 s; Scandauer
gleich (MS43 4,9–5,1 s, MSD80 31,7–35,6 s auf belastetem Rechner). Isoliert nachgestellt (Tabelle neu zeichnen bei
rechnendem Python-Thread): 0,293 s → 0,024 s. **Behebung:** Die Anwendung setzt beim Start das Intervall auf 0,5 ms
(`keep_gui_responsive`, gilt auch für den EXE-Prüflauf); Regressionstests: Einstellung beim Programmstart (immer) und Messung des Neuzeichnens unter Last (mit
`ECU_STUDIO_GUI_TESTS=1`; auf den geteilten CI-Rechnern ist der Stillstand selbst nicht nachstellbar: 0,12 gegen 0,13 s);
beide schlagen ohne die Änderung fehl. Eine Zugriffsverletzung erklärt dieser Befund nicht.

Nebenbefund des Prüfskripts: Im ersten MS43-Zyklus kam der zufällige Abbruch erst nach Scan-Ende an (das Fenster stand
still), deshalb wurden die Funde übernommen; das Programm verhielt sich richtig. Ein Abbruch wirkt bei MS43 erst nach
3,2–4,6 s, weil das Einlesen der mitgelieferten Definition nicht unterbrechbar ist – gleich in 1.18.2.

**Belastung:**

| Lauf | Umfang | Ergebnis |
|---|---|---|
| Scans hintereinander (ein Prozess) | 3000 Scans, jeder vierte abgebrochen, 737 s | 0 Abstürze, 0 Qt-Meldungen, kein Stack |
| GUI-Zyklen (je Zyklus neuer Prozess = Neustart; MSD80, MS43, ME9.2.1 im Wechsel) | 100 × Öffnen (99 × gespeichertes Projekt), Scan mit zufälligem Abbruch, Scan, Prüfliste bestätigen/ablehnen, Neuscan, Speichern, Schließen; 62 min | **100/100 Exitcode 0**, 0 Stacks, 1 Qt-Warnung (§ 12.4), Originaldateien byte-gleich, gespeicherte Kennfelder und Entscheidungen bei jedem der 99 Neustarts exakt wieder geladen; Spitzenspeicher MSD80 326 → 356 MB, MS43 218–221 MB, ME9.2.1 217–224 MB (wächst nur mit dem Projekt: 2 → 68 Entscheidungen) |
| Windows-Build (EXE, b17a4fb, `build_release.ps1` vollständig: EXE-Prüflauf, ZIP ohne Python, Installer) | 50 × `--smoke-test` mit echtem MS43-Scan (je zwei Scans, 857 Kennfelder) + 50 × `--self-check` | 50/50 bestanden, Exitcode 0, 12,9–16,8 s, Spitzenspeicher 178–181 MB ohne Anstieg |

Zusätzlich der Endstand ed70a45 gebaut (`build_release.ps1` vollständig) und 20 × geprüft: 20/20 bestanden, 11,6–14,0 s, 178–181 MB.

**Ergebnis:** In 3000 Scans, 100 Neustartzyklen und 70 EXE-Läufen trat **keine** Zugriffsverletzung auf. Die Ursache des einmaligen Absturzes vom 01.11. ist damit **nicht gefunden**; die Worker-Freigabe ist gehärtet, das Stillstehen des Fensters während des Scans behoben. Ohne Absturzabbild bleibt ein Restrisiko (§ 12.4).

### 12.3 Regression und Tests

Testsuite **856 bestanden, 10 übersprungen** (mit `ECU_STUDIO_GUI_TESTS=1` zusätzlich die Zeitmessung bestanden) (neu: Neuzeichnen unter rechnendem Scan-Thread, angewendetes Modell nur mit Freigabe, Scan ohne Modell behält
Datenmuster-Funde und nennt den Grund, Training nur mit freigegebenen Zeilen, Worker-Freigabe). `i18n_extract
--check`: 2064 Texte, 0 offen. Firmware-Prüfung (`firmware_guard tree HEAD`): ohne Befund. Der lokale MS43-Schritt des
GUI-Prüflaufs erwartete den ungerundeten Zellwert `91.919216`; die Anzeige rundet aber auf einen Rohwertschritt
(`91.9`) – auch in 1.18.2. Der Schritt prüft jetzt den vollen Wert (Bearbeitungswert) und die Anzeige getrennt;
Kennfeld (Adresse 0x76503, 6 × 6, u8) und Anzahl (857) sind in 1.18.2 und 1.19 gleich.

### 12.4 Verbleibende Risiken

1. **Mehr ungeprüfte Datenmuster-Funde** ohne Modell (Präzision bis 66 → 38 % bei MS45); die exakten Ergebnisse
   sind unverändert, die zusätzlichen Funde sind als Vermutung gekennzeichnet.
2. **Ursache der einmaligen Zugriffsverletzung unbekannt**; ohne Absturzabbild nicht weiter eingrenzbar.
3. **TriCore-Codeerkennung experimentell** (§ 4), Schwellen aus MSD80.
4. **Lange Installationspfade:** Liegt der Programmordner tiefer als rund 200 Zeichen, scheitert das Laden der
   Qt-Bibliothek („Dateiname zu lang“); einzelne mitgelieferte Dateien liegen bis 125 Zeichen tief. Unverändert
   gegenüber 1.18.2; im Prüflauf aufgetreten, weil der Build in einem sehr tiefen Ordner lag.
5. Weitere gelernte bzw. kalibrierte Daten mit offener Freigabe (MS43-Strukturmodell, Konfidenzkalibrierung).
6. **Abbruch bei MS43 träge** (3,2–4,6 s bis zur Wirkung, wie 1.18.2); es werden keine Funde eines abgebrochenen
   Scans übernommen.
7. Eine Qt-Warnung „QFont::setPointSize: Point size <= 0“ in einem von 100 Zyklen (Qt-intern, ohne Folgen; der
   Programmcode setzt keine Schriftgrößen ≤ 0).

### 12.5 Offene Fragen für den Nutzer

1. Umgang mit **1.15.0 bis 1.18.2**, die das Modell enthalten (nicht verändert).
2. `candidate_model.json` in 1.19 **weiter mitliefern** (abgeschaltet) oder aus dem Paket entfernen.
3. **Trainingsfreigabe der MS43-Daten** (betrifft `ms43_430069_structure_model`).
4. Einordnung der **Konfidenzkalibrierung** (Messung an Referenzen, kein Training).
5. Release-Freigabe 1.19.0 – nicht ausgeführt.
