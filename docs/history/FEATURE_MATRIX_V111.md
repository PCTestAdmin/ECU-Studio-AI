# Funktionsvergleich v1.10 → v1.11

Stand 17.10.2026. Maßstab: [öffentliche EVC-WinOLS-Beschreibung](https://www.evc.de/en/product/ols/software/) und [Änderungsverzeichnis](https://www.evc.de/en/download/down_winols_whatsnew.asp). Dort sind u.a. Projektversionen, Kartenansichten, Slices und Erweiterungen für Importe/Checksummen/Automatisierung dokumentiert; manche Funktionen sind optionale Features/Module. Kein Anspruch vollständiger Produktparität.

| Funktion | Gelieferte v1.10 | Tatsächlicher Stand 1.11 |
|---|---|---|
| Hex/Dezimal | Virtueller Hexeditor | Dezimalanzeige/-eingabe ergänzt |
| Tabelle/2D/3D | Vorhanden; Flächendekodierung mit fehlendem `FORMATS`-Import | Absturz behoben; vektorisierte Stride-/Endian-Dekodierung |
| Mehrere Kennfelder | Gemeinsame Ansichten für ausgewählte Karte | Mehrere gleichzeitig geöffnete Kennfeldtabs |
| Schichten | Einzelne 2D-Schnitte | Zusätzliche überlagerte Zeilenschnitte |
| Datentypen/Layout | Ganzzahl 8/16/32 signed/unsigned; Strides | Erhalten; keine neue Float-/Bitfeld-Schreibunterstützung |
| Skalierung/Formeln | Affin und sichere nichtlineare Leseformeln | Achsen-/Log-Kanaldefinitionen; nichtlineare Schreibsperre erhalten |
| Bereichsbearbeitung | Rechteckiges add/set/percent | Disjunkte Auswahl, X/Y-/bilineare Interpolation, 3×3-Glättung, Bytevorschau |
| Undo/Audit | Byte-Undo und Batch | Transfer/Rezepte als ein Undo-Schritt; persistentes Byte-Audit, kein gespeicherter Undo-Stack |
| Suche/Gruppen | Name/Typ/Adresse; Hex-Wildcards | Bitmasken, Rohwerte, Dezimaladressen, eigene Gruppen/Favoriten |
| Kennfeldliste | Vollständig aufgebaute QListWidget-Items | Virtuelles Qt-Modell, sichtbare Labels bei Bedarf |
| Projekte | JSON-Dateien, Notizen, Lesezeichen | Suchbarer SQLite-Projektindex und Schema-Migration |
| Original/Speicherung | Copy-on-write, Quellhash, atomarer JSON-Replace | Eigenes Originalbackup, `.bak`, Recovery, Hashintegrität und fsync |
| Versionen | Bis 200 Snapshots | Feste 200er-Grenze entfernt; Projekt max. 256 MiB; Stride-Teilrestore korrigiert |
| Vergleich | Byte-/Kennfeld-ORI/MOD, CSV | Erhalten; mehrere Snapshots über Explorer, kein neuer beliebiger N-Wege-Editor |
| Dateiformate | BIN/ORI, Intel HEX/S-Record mit Segmentprotokoll | Erhalten; begrenzter ZIP-BIN/ORI-Import ergänzt |
| Definitionen | Echte XDF-/A2L-Parser mit Layoutgrenzen | Erhalten; keine vollständige ASAP2-/proprietäre DAMOS-/OLS-/KP-Abdeckung behauptet |
| Austausch | Hashgebundene eigene JSON-Map-Packs | Erhalten |
| Automatisierung | Einzel-Batch und CLI-Werkzeuge | Hashgebundene JSON-Rezepte und vorab geprüfte Mehrprojekt-CLI |
| Plugins | Keine allgemeine Registry | Getestete API für vertrauenswürdige Import-/Prüffunktionen; kein GUI-Manager |
| ECU-Checksummen | Profil-Audit und synthetische Beispiele | Keine neuen ECU-Algorithmen erfunden; unbekannte Profile unsupported |
| Referenzdatenbank | SQLite, öffentliche Hinweise, manuelle Bestätigung | Schema 2 mit Herkunft/Hardware/Rechten/Lineage; **0 neue geprüfte Referenzlabels** |
| Struktur-KI | Mehrtyp-Scanner, Vorlagen, synthetisches Ranking | Effizientere notwendige Vorfilter; identische synthetische Regressionsergebnisse |
| Semantische KI | Firmware-Holdout/LOFO ohne unabhängige reale Basis | Herkunfts-/Lineage-Gates und exakte Metriken; Kandidaten inaktiv; reales neues Training offen |
| Firmwaretransfer | Ungeprüfte Ähnlichkeitsvorschläge | Physikalisches Delta/Prozent auf bestätigte Zieldefinitionen; Konflikte, Zellvorschau, manuelle Übernahme, Audit/Undo |
| Log-to-Map | Fehlte | CSV-Zuordnung, Einheiten, Soll/Ist-Regeln, Belegungs-Heatmap, Zellnavigation, HTML-Bericht |
| GUI | Native Docks, Dark/Light, Toolbar, gespeicherte Layouts | Dunkler Standard für neue Einstellungen; Kennfeldtabs und neue Arbeitsdialoge |
| Worker | Einige Hintergrundanalysen | Chunk-Abbruch, Fortschritt, Lebensdauerprüfung; Log-/Transfer-/Trainingsworker |
| Benchmarks/Tests | Teilbenchmarks und ältere QA | Größenbenchmarks mit RAM/Qt-Heartbeat, neue Transaktions-/I/O-/GUI-Tests, EXE-Smoke |
| Familienabdeckung | Quellenregister und begrenzte echte Referenzen | Keine pauschale Unterstützung von EDC/MED/MD1/MG1/SID/Simos/Denso/Delphi/DQ/ZF aus bloßen Familiennamen |

Die neuen Offline-Werkzeuge sind implementiert und synthetisch geprüft. Reale Erkennungsverbesserung, praktische Fahrzeugkalibrierungsabnahme und vollständiger Master-Auftrag bleiben offen.
