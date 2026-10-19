# ECU Studio AI – Feature-Matrix

**Aktueller Vergleich v1.10 → v1.11:** [FEATURE_MATRIX_V111.md](FEATURE_MATRIX_V111.md).

Die folgende ältere Matrix bleibt als historische Dokumentation erhalten und ist keine aktuelle Abnahme:

## Historischer v1.6-Präzisions- und Quellenstatus

| Ebene | Stand | Grenzen |
|---|---|---|
| 2D-Strukturerkennung | Vorselektion + nachgelagerte Kanten-, Dynamik-, Endian- und Überlappungsprüfung | Unbekannte Kennfeldfunktion bleibt `Unbekannt` |
| Exakte BIN-Datenbank | Per SHA-256 zugeordnet, bestehende Definitionen erhalten | Definition muss fachlich geprüft werden |
| Struktur-KI | 67 echte MS43-Strukturproben aus der vorherigen Version | Keine zusätzlichen echt gelabelten Samples, kein neuer Firmware-Holdout |
| Struktur-KI-Präzision | Noise- und affine-Ebenen-Abstention | Keine nachgewiesene Klassifikationsgenauigkeit auf realen neuen Firmwareständen |
| Supervised ML | Strenge Familien-/Score-/OOD-/Holdout-Gates, Prüfung auf kopierte Oberflächen | Aktuell 0 unabhängig bestätigte Kennfeld-Labels |
| Öffentlich gepinnte XDF-Hinweise | 14 aus v1.5 | Exaktes SW-Matching vor Import erforderlich |
| Zusätzliche Marken-Quellen | 7 Rechercheeinträge: Audi, Mercedes-Benz, BMW, Opel, Lamborghini | Davon 4 SHA-gepinnte Einzeldefinitionen; teils ungeklärte Dateilizenz; keine automatisch trainierbaren ECU-BINs |
| Windows-GUI | Quellenübersicht im Werkzeuge-Menü, Erkennungsstufe automatisch im Scan | Auf Windows nicht live gestartet |
| Prüfung | Lokale Unit-/Regressionstests, Demo-Positivfälle, Zufallsdaten-Negativfälle | Kein Bench von realen ECU-Generationen verschiedener Hersteller |

`model_score`/`confidence` sind **keine kalibrierten Wahrscheinlichkeiten**.

---

# Version 1.4 – Datenbestand

| Eigenschaft | Status |
|---|---|
| Quellenkatalog | 14 öffentlich dokumentierte Quellen mit Source-SHA-1 |
| Offline-XDF-Metadaten | 118 aus MS41/MS42/MS43; vollständige X/Y-Achsen fehlen |
| Auf den MS43-Upload gebundene Vorschaumaps | 81, ungeprüft, Quelle Extended Load |
| GS20 GADC9010 | Keine passende Definition vorhanden; inkompatible XDF blockiert |
| Download + SHA-Prüfung | Implementiert, erfordert Internet auf Windows, nicht live validiert |
| Index vollständiger heruntergeladener XDF | Implementiert mit Importquote und Ausschlussgründen |
| ML-Trainingsdaten fachlich verifiziert | 0 |
| 100-%-Kennfelderkennung beliebiger Firmware | Nein |

# ECU Studio AI v1.3 – Funktions- und Evidenzmatrix

| Ebene | Real implementiert | Grenzen / validierbare Nachweise |
|---|---|---|
| ECU-/Dateiprofil | MS43 430069 / GS20 GADC9010 über Signaturen | Andere Familien benötigen Parser/Signaturen; Dateiname alleine reicht nicht |
| XDF/A2L-Import | Bestehende geprüfte Parser-Teilumfänge | Nicht alle A2L/XDF-Strides und Formeln |
| SQLite-Definitionsdatenbank | Quellhash, Firmwarehash, Map-Metadaten, Herkunft, geprüfter Status | Anfangs leer; keine illegalen Fremddaten |
| Massenerfassung | Batch-Paarliste mit Fehlerberichten | Nur XDF-Paare; Prüfung der ECU-Version nötig |
| Genau gleiche Firmware | Indexierte Definitionen per SHA-256 wieder verfügbar | Gleiche Bytes ≠ unabhängig richtige Definition |
| Firmwareübergreifender Transfer | Signatur-/Formabgleich, same-family, best-vs-runnerup | Nur bestätigte und einfache zusammenhängende Matrizen; Vorschläge |
| ML-Klassifikator | Aus verifizierten Maps trainieren, Firmware-Holdout, JSON-Modell | Noch kein echtes vortrainiertes Modell, empirische Modellgüte offen |
| GUI | Neue Aktionen, Qt-Worker für langen Vergleich und Batchimport | Windows-PySide6-Laufzeit hier noch ungetestet |
| Integrität | Original bleibt unverändert, Import/Training lesend | Export weiterhin ohne Checksummenfreigabe |

**Besonders wichtig:** `confidence`/`model_score` sind **nicht** gleichbedeutend mit einer kalibrierten statistischen Wahrscheinlichkeit oder einer bestätigten physikalischen Kennfeldfunktion.
