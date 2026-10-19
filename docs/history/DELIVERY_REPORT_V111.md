# Lieferung ECU Studio AI 1.11

**Ergebnis:** nutzbare Weiterentwicklung im vorhandenen Python-/PySide6-Projekt, getestete Windows-Ausgabe und nachvollziehbare technische Nachweise. **Der vollständige Master-Auftrag ist nicht abgeschlossen oder als Profi-Kalibrierlösung abgenommen.** Ein reales Genauigkeitsplus und eine große neue verifizierte ECU-/TCU-Datenbasis fehlen.

## Gelieferte Artefakte

| Gewünschte Ausgabe | Lieferung |
|---|---|
| Aktualisierter Quellcode | Projektverzeichnis und `release/ECU-Studio-AI-1.11-source.zip` |
| Erforderliche Modellgewichte | Vorhandene JSON-Gewichte unverändert enthalten; Hashvergleich in `CHANGE_MANIFEST_V111.json`. Keine unbelegt verbesserten neuen Gewichte |
| ECU-/TCU-Datenbank | `recognition_public_index.sqlite3`, Schema 2; alter Stand zusätzlich separat gesichert. Alle 81 Definitionen/14 Quellen/118 öffentlichen Hinweise erhalten; 0 bestätigte Referenzen, 0 neue Ground-Truth-Labels |
| Windows-Ausgabe | `dist/ECU-Studio-AI-1.11/ECU-Studio-AI-1.11.exe` samt Runtime und portables ZIP unter `release/`; Buildskript und exakter Abhängigkeitsstand |
| Tests | 233 bestanden, 3 mangels realer Nutzerdateien übersprungen; keine Fehler. XML, maschinenlesbarer QA-Bericht und Buildlog |
| Funktionsvergleich | `FEATURE_MATRIX_V111.md`, mit öffentlich dokumentierten Vergleichsfunktionen und ausdrücklichen Grenzen |
| KI-Fortschritt | `TRAINING_STATUS_V111.json`: strengere Daten-/Evaluationsgates, kein neues reales semantisches Training; reale Genauigkeit unbekannt |
| Änderungen/Installation | `CHANGELOG.md`, `README_V1_11.md`, `CHANGE_MANIFEST_V111.json` |

## Stand nach Phasen

1. **Gezielte Analyse, Fehlerbehebung und Baseline geliefert.** Alle 86 Quellmodule sind syntaktisch inventarisiert (`SOURCE_INVENTORY_V111.json`); bestehende Regressionen und kritische Laufzeitwege wurden geprüft. Kein Anspruch eines vollständigen formalen Security-Audits. Unter dem System-Python fehlten zunächst Abhängigkeiten; die tatsächlichen Vergleichstests liefen danach in der eingerichteten Projektumgebung.
2. **Wesentliche Editor-/Projektfunktionen implementiert.** Kennfeldtabs, Schichten, Auswahlbearbeitung, physikalische Interpolation, Glättung, Rezepte, Favoriten/Gruppen, virtuelle Liste, Sucherweiterungen, ZIP und Projektindex. Bestehende Parser/Formatgrenzen sind erhalten; kein vollständiger Ersatz sämtlicher professioneller Import-/Pluginfunktionen.
3. **Trainings-/Evaluationsinfrastruktur verbessert, reale Daten-/Modellarbeit offen.** Nutzungsrechte, Herkunft und unabhängige Lineages werden verlangt; exakte Metriken und Leakage-Prüfung ergänzt. Keine neuen Labels aus ungeprüften Community-Definitionen, kein Austausch aktiver Modellgewichte aufgrund synthetischer Zahlen.
4. **Beide neuen Offline-Arbeitsabläufe implementiert.** Transfer mit Vorschau, expliziter Auswahl, Konflikten, Audit/Undo; CSV-Loganalyse mit Einheiten und bilinearer Belegung. Reale Tunerabnahme, neue inkompatible Achsenlayouts und breitere Loggerformate offen. Logdiagnose ist regelbasiert und trifft keine bewiesene Ursachenfeststellung.
5. **GUI und gemessene Scannerperformance verbessert.** Dark-Standard für neue Einstellungen, mehrere Tabs, vektorisierte Matrixzugriffe, bessere Vorfilter, Abbruch/Fortschritt und Hintergrunddialoge. Keine neue GPU-Engine oder umfassende Multi-Monitor-/DPI-Abnahme.
6. **Windows-Build und automatisierte Integration geliefert.** Sowohl Quellversion als auch paketierte EXE haben die isolierte Qt-Integration bestanden. Kein physischer Fahrzeug-, Flash-, Prüfstands- oder interaktiver Langzeittest.

## Test- und Messnachweise

- Ausgangssuite: 174 bestanden, 3 übersprungen, 1 abgewählt. Der alte Qt-Guard-Test blieb beim interaktiven Speicherhinweis seines Test-Teardowns stehen; seine Bereinigung wurde korrigiert. Im finalen Lauf ist er enthalten und erfolgreich.
- Final: **233 bestanden, 3 übersprungen**, 0 Fehler. Drei vorhandene Tests benötigen nicht bereitgestellte reale MS43-/GS20-Dateien; sie gelten ausdrücklich nicht als bestanden.
- GUI/EXE-Smoke: Fenster, Kennfeldtab, numerische Fläche, Bearbeitung/Undo/Redo, virtueller Katalog/Favoriten, CSV-Zuordnung, Heatmap, Transfer-Zellvorschau, bestätigte Transaktion, Originalbackup und Projektindex. Screenshots in `qa-artifacts/` wurden visuell geprüft. Qt-Offscreen unter Windows, keine manuelle Fahrzeugbedienung.
- Neue Regressionen prüfen u.a. verschobene Transfers mit unterschiedlicher Zielskalierung/-Bytefolge, Hardware-/Achsenkonflikte, stale previews, Überläufe, überlappende Ziele, auf-/absteigende Achsen, Einheiten/Fehlwerte, nichtuniforme Interpolation, Stride-Lücken, Projekthashes, Hardlinks, simulierten Speicherfehler, ZIP-Pfade, Migrations-/Plugin-/Batchgrenzen und Leakage.
- Gleiche Detektorausgabe auf fünf synthetischen Fällen. Performance: drei Analyseläufe pro Größe. 4 MiB median 19,821 → 8,860 s; 8 MiB 27,818 → 15,497 s. Suchgrenzen, RAM, Qt-Ereignisintervalle und Einzelwerte stehen in `PERFORMANCE_V111.md` und den JSON-Dateien.

## Verbleibende verbindliche Abnahme

Benötigt werden ein rechtlich nutzbarer, unabhängig fachlich geprüfter Firmware-/Definitionskorpus mit belastbarer Familien-/Softwaretrennung, gepaarte echte Modellvergleiche, verifizierte ECU-spezifische Checksummenprofile und praktische Tuner-/Fahrzeugabnahmen. Die aktuelle Quellenrecherche liefert dafür keine ausreichende Ground Truth. Das darf weder durch erfundene Trainingswerte noch pauschale Familien-/Flashfreigaben ersetzt werden.

Das unveränderte Ausgangsprojekt liegt zusätzlich in `../ECU-Studio-AI-v1.10-original.zip`. Keine Emissions-, Diagnose-, Wegfahrsperren- oder Sicherheitsabschaltungsfunktion wurde ergänzt.
