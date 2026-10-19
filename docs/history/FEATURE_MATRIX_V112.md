# Feature-Abgleich Kennfelderkennung 1.12

Gezielter Nachtrag zur allgemeinen `FEATURE_MATRIX_V111.md`. Keine Zusage einer identischen oder vollständigen WinOLS-Erkennungsleistung.

| Arbeitsprinzip / Funktion | Öffentlicher Bezug | ECU Studio AI 1.12 |
|---|---|---|
| Programm-/Datenbereiche trennen | [EVC: automatische Prozessor-/Bereichserkennung](https://www.evc.de/en/product/ols/software/) | Bekannte MS43-/GS20-Kalibrierfenster; **kein** allgemeiner Prozessor-Disassembler |
| Potenzielle Kennfelder suchen | [EVC: automatische Kennfeldsuche mit Vorschau](https://www.evc.de/en/product/ols/software/) | Begrenzte Struktursuche, jetzt zusätzlich Count-/Axis-Record-Hypothese; Ergebnisse bleiben ungeprüft |
| Namen und physikalische Werte aus passender Definition | [MS4X: passende XDF in TunerPro verwenden](https://github.com/ms4x-net/ms43) | Vollständige offline Standard-XDFs MS43 430069 für 64/512 KiB, gebundene Software-/Achsenprüfung |
| Achsen-/Datentyp-/Formelimport | [MS4X-XDF v1.14](https://github.com/ms4x-net/ms43/tree/72feadb3e965743fb1c16b36a79b14e98d0c684e/definitions) | Verknüpfte Achsen einschließlich ihrer Formel und Einheiten; alte eingebettete Platzhalter werden übergangen |
| Konstante oder ungewöhnlich dimensionierte Tabellen | Definitionsbasiert eindeutig darstellbar | Aus XDF auch 6×6-Konstantflächen und ungerade Adressen; generisch nur belegte Record-Hypothesen |
| Bytebreite prüfen | Proprietäre Suchdetails anderer Editoren nicht öffentlich belegt | Gleicher Speicherbereich als schmalere Werte gegengeprüft; breite Kandidaten bei Mehrdeutigkeit verworfen |
| Bestehende Projekte neu scannen | Katalogpflege | Alte ungeprüfte Heuristik ersetzen, manuelle/geprüfte Definitionen erhalten, Quellalias-Ansichten behalten |
| Variantenunterschiede | [MS4X: Extended Load braucht passende XDF](https://www.ms4x.net/index.php?title=Siemens_MS43_Extended_Load_Limit) | Mitgelieferte Standard-Definition ausdrücklich ungeprüft; Extended Load/MS43X nicht automatisch als kompatibel bestätigt |
| Reale Genauigkeitsmessung | Unabhängig geprüfte Referenzdaten erforderlich | Lokale reale Regression und Definitionsübereinstimmung; **keine** unabhängige 856-Kennfelder-Grundwahrheit oder allgemeine Precision/Recall-Zusage |
| Selbstlernen | Eigenständige Produktfunktion | Bestehende Freigabegates beibehalten; keine automatische Übernahme der Benutzerdatei oder XDF-Vorschläge als verifizierte Trainingsdaten |

Bestehende Hex-/2D-/3D-/Tabellenansichten und Bearbeitungsfunktionen sind weiterhin vorhanden. Der Windows-Starter und die Laufzeitdateien liegen in einem portablen, einsehbaren Ordner. Endgültige Prüfungen: `QA_REPORT_V112.json`.
