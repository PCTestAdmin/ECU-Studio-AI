> **Neu in v1.13.0:** [Mehrere Steuergeräte, RomRaider-Import und neues Strukturtraining](README_V1_13.md).

> **Neu in v1.12.0:** [Kennfelderkennung und Windows-Paket](README_V1_12.md), [Diagnose am realen MS43-Read](DETECTION_REPORT_V112.md), [Feature-Abgleich](FEATURE_MATRIX_V112.md). Falsche 32-Bit-Gruppierung, Rastergrenzen und verknüpfte XDF-Achsen korrigiert; Standard-MS43-430069-Definitionen offline enthalten.

**Aktueller Entwicklungsstand: ECU Studio AI v1.13.0.** Die folgenden älteren Abschnitte dokumentieren die bisherigen Versionen. Der übrige Funktionsstand der 1.11 bleibt erhalten und steht in [README_V1_11.md](README_V1_11.md) sowie [FEATURE_MATRIX_V111.md](FEATURE_MATRIX_V111.md). Aktuelle Grenzen und Prüfung: [README_V1_12.md](README_V1_12.md).

> **Neu in v1.9.0:** siehe [README_V1_9.md](README_V1_9.md) für neue ECU-/TCU-Realdatenquellen, experimentelle TCU-Kurven und transparente Holdout-Tests.

**Aktueller Stand: ECU Studio AI v1.9.0 – vollständige Neuerungen und Grenzen siehe [README_V1_9.md](README_V1_9.md).**

# ECU Studio AI v1.5 – Selbstlernende Erkennung (ehrlich abgesichert)

**Windows-Quellcodepaket mit lokal trainiertem MS43-Strukturmodell, v1.4-Datenbank, Intake für MD1/MG1 und 143 erfolgreichen Python-Tests.**

## Was v1.5 neu kann

1. **Bereits mit echten Daten trainiertes Strukturmodell** `src/ecu_studio/recognition/data/ms43_430069_structure_model.json`: 67 reale Kennfeld-Rohwertoberflächen aus der MS43 430069, unüberwachtes PCA/SVD. Das Modell schlägt vergleichbare *Strukturen* und Referenznamen vor, aber keine als fachlich sicher ausgegebenen Kennfeldtypen.
2. **Aktives Lernen**: eine Prüfqueue mit bis zu 40 unbekannten Kandidaten, die nahe der internen Neuheitsgrenze liegen, macht den nächsten manuellen Prüfschritt effizienter. Diese Kandidaten bleiben ungeprüft.
3. **Gezieltes, sicheres Klassifikationstraining**: Erst ab mindestens 4 unabhängigen Firmwareständen pro Klasse und bestandenen, getrennten Holdout-Prüfungen; jede ECU-Familie erhält ein separates Modell. Kein trainiertes Freigabemodell ohne geprüfte Labels.
4. **Weitere ECU-Familien**: Bosch MD1, MG1, EDC15/16/17, ME/MED, Continental SIMOS/SID, Delphi DCM, Denso und ZF TCU im Datenaufnahme-Register. Kein 100%-Erkennungsschein: Diese Familien benötigen spezifische HW/SW-Kennungen, Binärimages und verlässliche XDF/A2L-Dateien. MD1/MG1 sind noch NICHT als auto-erkennbar implementiert.
5. **Herkunftsgesicherte Intake-CLI** für weitere ECU-Familien. A2L-Daten werden ausschließlich anhand vom Anwender explizit gelieferter ECU-zu-BIN-Segmente übernommen; alle importierten Kennfelder behalten Status `unverified`.
6. **Strengere Modellgeltung**: Ein MS43-Modell wird nicht für GS20/MD1/MG1 eingesetzt, und ältere generische ML-Modelle werden nicht mehr ohne Familienbindung zur automatisch benannten Karte befördert.

## Windows starten

ZIP entpacken. Auf Windows mit Python 3.11 oder 3.12 `start_windows.bat` ausführen. Die bekannte PySide6-Oberfläche bleibt erhalten. Im Menü **Werkzeuge** stehen zusätzlich:

- `KI · Strukturmodell aus realer BIN trainieren …`
- `KI · Modell- und Familienstatus …`
- `KI · Prüfqueue für unbekannte Kennfelder exportieren …`

Unter **Erkennung 2/3** nutzt der Worker die mitgelieferte MS43-Strukturvorlage als Erklärung zu unsicheren Kandidaten; keine automatisch falschen Kennfeldnamen. Über **Erkennung 3/3** werden weiterhin nur bestätigte Labels gelernt, jetzt mit familienbezogenem Qualitätsgate.

**Hinweis:** Die mitgelieferte `recognition_public_index.sqlite3` ist die Datenbank in der Projektwurzel. Die Desktop-App verwendet standardmäßig `~/.ecu_studio_ai/recognition-v1.sqlite3`. Bei Bedarf dort den öffentlichen Index als Ausgangspunkt verwenden oder die passende Definition über die GUI neu indexieren; bestehende private Datenbank vor dem Ersetzen sichern. Das trainierte MS43-Strukturmodell wird aus der Anwendung automatisch anhand der Softwarekennung angeboten, auch wenn du die SQLite noch nicht manuell übernommen hast.

## CLI-Beispiele

In der Projektwurzel, nach `python -m pip install -e .`:

```powershell
# Registrierte ECU-Familien anzeigen
python -m ecu_studio.tools.safe_learning families --out ECU_FAMILIES.json

# Bereits trainiertes MS43-Strukturmodell mit einer eigenen MS43-Datei prüfen
python -m ecu_studio.tools.safe_learning suggest-structure --bin "C:\ECU\MS43.bin" --model "src\ecu_studio\recognition\data\ms43_430069_structure_model.json" --out vorschlaege.json

# Aktive Prüfqueue (keine automatischen Namen!)
python -m ecu_studio.tools.safe_learning review-queue --db recognition_public_index.sqlite3 --bin "C:\ECU\MS43.bin" --model "src\ecu_studio\recognition\data\ms43_430069_structure_model.json" --out review.json

# Strukturmodell aus einer passenden Original-BIN und importierten, ungeprüften Definitionen erneut trainieren
python -m ecu_studio.tools.safe_learning train-structure --db recognition_public_index.sqlite3 --bin "C:\ECU\MS43.bin" --out mein-strukturmodell.json --accept-unverified

# Wirklich fachlich verifizierte Daten prüfen
python -m ecu_studio.tools.safe_learning train-status --db recognition_public_index.sqlite3

# Erst NACH unabhängiger Verifizierung und Qualitäts-Holdout ein Klassenmodell bauen
python -m ecu_studio.tools.safe_learning train-safe --db recognition_public_index.sqlite3 --family "Bosch MD1" --out md1-klassifikator.json
```

Ein MD1/MG1-Datenpaar explizit aufnehmen (nur wenn die Datei und die XDF/A2L wirklich zusammengehören):

```powershell
# Binärdatei mit Python hashen:
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path(r'C:\ECU\ECU.ori').read_bytes()).hexdigest())"

python -m ecu_studio.tools.safe_learning intake-pair --db recognition_public_index.sqlite3 --bin "C:\ECU\ECU.ori" --definition "C:\ECU\passend.xdf" --family "Bosch MG1" --software "EXAKTE_SW_ID" --variant "EXAKTE_HW_SW_VAR" --sha256 "SHA256_DER_DATEI" --acknowledge-identity
```

Für A2L zusätzlich `--address-segments "C:\ECU\segmente.json"` mit einer Liste von Objekten `{ "ecu_start": 0, "ecu_end": 0, "file_start": 0 }` gemäß **dem echten** ECU-Speicherlayout angeben. Die Nullwerte sind nur Schema-Platzhalter, keine funktionierende ECU-Adresse.

Die Intake-CLI verändert ECU-Daten nicht; sie markiert importierte Maps nie als `verified`.

## Messungen und Einschränkungen

- 143/143 Python-Tests bestanden, einschließlich der unveränderten Editor-/Binärtests.
- Training des Strukturmodells auf echter MS43-BIN: 67 Proben aus 81 importierten Vorschau-Maps.
- Für MS43 kann der unsichere Strukturvergleich Kandidaten priorisieren; der bekannte Software-430069-Stand wurde verwendet. Keine unabhängige Firmware-Holdout-Validierung.
- Die GS20 GADC9010-Datei führt bei dem MS43-Modell zu `abstain` und null benannten Vorschlägen.
- **0 bestätigte Trainingsbeispiele für echte Kennfeldfunktion; kein freigegebenes supervisiertes Modell für MD1/MG1/andere.**
- Qt/PySide6 konnte in dieser Umgebung nicht unter Windows ausgeführt werden. Die GUI wurde nur auf Python-Syntax geprüft. Diese Software ist nicht flashfreigegeben.

Mehr: `MODELLKARTE.md`, `MODEL_TRAINING_REPORT.json`, `ACTIVE_LEARNING_REVIEW_QUEUE.json`, `SUPERVISED_TRAINING_STATUS.json`, `ECU_FAMILIES.json`, `QA_REPORT.json`.

---

# Dokumentation der bisherigen v1.4-Funktionen

# ECU Studio AI v1.4 – Befüllter Kennfeld- und Quellenkatalog

**Lieferung:** Lokale SQLite-Datenbank `recognition_public_index.sqlite3`, 14 überprüfbar referenzierte externe XDF-Quellen, 118 echte XDF-Kennfeld-Metadatensätze aus drei ECU-Familien und 81 **ungeprüfte** Tabellenhinweise, die ausschließlich an den SHA-256 des vom Benutzer bereitgestellten Siemens MS43 430069 512-KiB-Fullreads gebunden sind. Der ursprüngliche Binärdump wird **nicht** mitgeliefert.

Dies ist **keine** vollständige universelle Kennfeld-Datenbank: Es gibt **0 unabhängig bestätigte Karten** und **kein trainiertes reales ML-Modell**. Die MS43-81er-Vorschau enthält nur Z-Werte-Definitionen (Namen, relative Adressen, Dimensionen, Datentypen und lineare Umrechnungen), **keine X/Y-Achsen** und keinen verifizierten Extended-Load-Patchstand. Sie darf nicht für die Flashfreigabe verwendet werden.

## Inhalt der Datenbank

| Ebene | Tatsächlich enthalten |
|---|---|
| Quellenregister | 14 konkrete, versionierte und per Git-Blob-SHA-1 gepinnte XDF-Dateien für MS41, MS42, MS43 und GS20 |
| Offline-Metadaten | 118 Kennfeld-Z-Achsen-Definitionen aus MS41 1429861, MS42 0110C6 und MS43 430069 (nur unterstützte Ausschnitte, GPL-3.0) |
| An deinen MS43-Dump gebundene Einträge | 81 mit Quellkennzeichen `xdf-preview`, **verified=0**; Originaldatei nicht enthalten |
| GS20 GADC9010 | **0** benannte Karten; die GS20 G10C9000-XDF ist nicht passend und wird für GADC9010 blockiert |
| Trainierbare Referenzen | 0; aus importierten fremden Definitionen wird nicht ungeprüft gelernt |

Die Quellbibliothek erhält bei jedem Öffnen einer neuen/alten Datenbank per idempotentem Seed die genannten Quellen und Offline-Hinweise. Bereits gespeicherte eigene Kennfelder werden nicht überschrieben. Die separat mitgelieferte SQLite enthält darüber hinaus die 81 vorsichtig indexierten MS43-Vorschauwerte für genau den hochgeladenen Dump.

## Start unter Windows

1. ZIP entpacken, Python 3.11/3.12 installieren und `start_windows.bat` starten.
2. Deine 512-KiB-MS43-Datei öffnen.
3. **Datei → Öffentliche ECU-Definitionsbibliothek …**: passende 430069-XDF explizit auswählen, Variante prüfen und die vollständige Datei nach bestätigter Lizenz-/Patchstandsprüfung herunterladen. Der SHA-1-Git-Blob-Hash muss stimmen. Danach die Importvorschau mit importierten/ausgeschlossenen Kennfeldern prüfen. Die ECU-BIN wird nicht hochgeladen.
4. Ohne Internet kannst du **Datei → MS43-430069: Offline-Kennfeldvorschau (81) …** benutzen. Diese zeigt nur ungeprüfte Originalnamen mit **unvollständigen Achsendaten** an. Für richtige Werte und Achsen ist die volle XDF weiterhin erforderlich.
5. Unter **Werkzeuge → Erkennung · Datenbankstatistik** siehst du die öffentlichen Quellen und Einträge. Ohne passenden softwaregenauen Original-XDF-Import ist eine unbekannte ECU nicht automatisch benannt.

### Datenbank auf der Kommandozeile

In der Projektwurzel nach `python -m pip install -e .`:

```powershell
python -m ecu_studio.tools.public_definitions stats
python -m ecu_studio.tools.public_definitions list --bin "C:\Dumps\meine_ms43.bin"
python -m ecu_studio.tools.public_definitions fetch-index --bin "C:\Dumps\meine_ms43.bin" --source-id ms43-430069-512 --acknowledge-variant
python -m ecu_studio.tools.public_definitions preview-ms43 --bin "C:\Dumps\meine_ms43.bin" --acknowledge-variant
python -m ecu_studio.tools.public_definitions stats --db "recognition_public_index.sqlite3"
```

`fetch-index` verlangt eine passende ECU-Familie, identischen Softwarestand, korrekte Dateigröße und ausdrückliche Bestätigung der möglicherweise abweichenden Firmware-/Patchvariante. Es lädt die vollständige Original-XDF aus dem gepinnten GitHub-Pfad (Internet erforderlich), validiert den Git-Blob-Hash und indexiert die vom Parser sicher unterstützten Maps **als ungeprüft**. Es findet keine automatische, heimliche Übernahme statt. Eine Importquote unter 100 % ist möglich, insbesondere bei komplexen Achsen/Strides/Umrechnungen.

Die bei Installation verwendete Standarddatenbank liegt weiterhin unter `~/.ecu_studio_ai/recognition-v1.sqlite3`. Eine ggf. schon vorhandene Benutzerdatenbank wird nicht gelöscht und nicht ersetzt. Die Beispiel-DB im ZIP kann separat durchsucht werden; die GUI enthält dafür eine eigene Offline-Vorschau-Funktion.

## Nachvollziehbare Datenherkunft und Lizenz

Die lokalen Metadaten stammen **aus öffentlich bereitgestellten Original-XDFs** der MS4x Dev Team-Projekte:

- https://github.com/ms4x-net/ms43 – MS43 430069 Extended-Load-512K v1.14
- https://github.com/ms4x-net/ms42 – MS42 0110C6 512K
- https://github.com/ms4x-net/ms41 – MS41 1429861 256K

Die reduzierten Metadaten stehen gemäß Ursprungsdefinition unter GPL-3.0; Attribution, Änderungsangaben und eine Kopie der Lizenz liegen unter `src/ecu_studio/recognition/data/`. Bei GS20 werden nur URL und Git-Hash aus einer öffentlich zugänglichen Sammlung indexiert, aber **keine** fremden XDF-Inhalte beigepackt; Lizenz und Eignung müssen vor Verwendung überprüft werden. Eine Liste öffentlich erreichbarer Dateien beweist weder ihre Präzision noch die Kompatibilität mit deiner Binärdatei.

## Technischer Qualitätsnachweis

- 137 Python-Tests inklusive 5 neuer Tests für Seed, Wiederanlauf, Quellenfilter, GS20-Mismatch und SHA-spezifische 81er-Vorschau.
- 81 Vorschau-Definitionen ließen sich auf der tatsächlich hochgeladenen MS43-BIN technisch innerhalb der Speichergrenzen indexieren; SHA-256-Zuordnung ist exakt.
- Der vollständige 3,6-MB-MS43-XDF-Import wurde **hier nicht** mit dieser BIN durch TunerPro/WinOLS unabhängig validiert. Die neue Downloadfunktion konnte mangels Netzwerkzugang im lokalen Windows-Laufzeitkontext nicht live getestet werden.
- Die Windows-PySide6-GUI konnte hier nicht gestartet werden. Ein technisch erfolgreicher Python-Test ist kein Beweis für semantisch korrekte ECU-Kalibrierungen.
- Keine Checksummenkorrektur, keine Flashfreigabe und keine automatische Tuning-Änderung.

## Älterer Funktionsumfang

# ECU Studio AI v1.3 – 3-stufige, nachvollziehbare Kennfelderkennung

**Eigenständiger Windows-Desktop-Prototyp mit vollständigem Python-Quellcode.** Er enthält einen echten lokalen Definitionsindex, einen Firmware-übergreifenden Matcher und ein trainierbares ML-Modell. **Die Datenbank wird nicht mit tausenden urheberrechtlich bzw. lizenzrechtlich fremden Kennfeldern ausgeliefert, und es liegt noch kein anhand realer ECU-Kennfelder trainiertes Modell bei.** Die unverifizierten Beispiele sind NICHT für Fahrzeugkalibrierungen geeignet. Keine Flash- oder Checksummenfreigabe.

## Installation

1. Windows 10/11 x64, Python 3.11 oder 3.12 installieren (Python-Launcher `py`).
2. ZIP entpacken, `start_windows.bat` ausführen. Beim ersten Start installiert es PySide6, NumPy und DefusedXML. Eine Windows-EXE kann mit `build_exe_windows.bat` *auf Windows* erstellt werden.
3. BIN/ORI/MOD öffnen. Die alte 2D-Rohdatenansicht, Editieransichten, DAMOS/A2L-Teilimport und XDF-Import bleiben vorhanden.

## Erkennung 1/3: Definitionsdatenbank

- Über **Datei → TunerPro XDF mit BIN koppeln** oder **A2L / textuelles DAMOS koppeln** eine *softwarestand- und patchgenaue* Definition importieren; Speicheradressen und Konversionsdaten im Audit überprüfen.
- Über **Werkzeuge → Erkennung 1/3 · Definitionen indexieren** die importierten Definitionen in `~/.ecu_studio_ai/recognition-v1.sqlite3` übernehmen.
- **Wichtig:** Indexierung ≠ fachliche Verifizierung. Das gilt selbst für Definitionen, deren Dateiname die ECU-Kennung enthält. Eine spätere bytegleiche BIN öffnet die gespeicherten Namen nur nach ausdrücklicher Bestätigung erneut.
- Nach unabhängiger manueller Prüfung eines Kennfelds dieses auswählen und **Werkzeuge → Erkennung 1/3 · Ausgewähltes Kennfeld fachlich bestätigen** aufrufen. Der Vorgang erfordert die Eingabe `BESTÄTIGT` und die unveränderte Originaldatei. Nur solche Referenzen können die Ebenen 2 und 3 speisen.
- Für hunderte oder tausende **legal bereitgestellte, paarweise zugehörige** BIN- und XDF-Dateien über **Werkzeuge → Erkennung 1/3 · Viele BIN/XDF-Paare importieren** eine JSON-Paarliste wie `examples/example_pairs_manifest.json` laden. Die Batchverarbeitung läuft in einem Qt-Worker und zeigt einen Bericht. Es werden keine kompletten BINs in der SQLite-Datenbank gespeichert.
- Pro Definition gespeichert: SHA-256 der ECU-Firmware, Controllerfamilie, bekannte Softwarekennung, Tabellenname, Datentyp, Achsen, Umrechnung, Dateioffset, Quellbezeichnung/Quellhash, Bestätigungsstatus. Für **fachlich bestätigte** Einträge werden zusätzlich begrenzte Rohwert-Proben für das Wiederfinden gespeichert.

## Erkennung 2/3: Wiederfinden zwischen Firmwareständen

**Werkzeuge → Erkennung 2/3 · Firmware-Transfer + Modellvorschläge** (`Strg+Umschalt+K`) analysiert eine unveränderte BIN in einem Hintergrundthread.

- Der Matcher betrachtet nur **fachlich bestätigte** Referenzen aus derselben identifizierten ECU-Familie; ohne Familienzuordnung gibt es keinen Transfer.
- Vergleicht 8-/16-/32-Bit-Matrizen über eine zweistufige numerische Suche, normalisierte Wertverläufe und lokale Gradienten.
- Strenge Geometrie- und Varianzvoraussetzungen, Konkurrentensuche und Mindestabstand zum zweitbesten Treffer. Mehrdeutige Fundstellen werden **nicht** automatisch übernommen.
- Bei vom Benutzer akzeptierten Vorschlägen stehen Originalreferenz, Ähnlichkeit und Warnhinweis im Kennfeldinspektor. **Auch ein eindeutiges Muster beweist nicht die semantische Funktion, Achsen oder Skalierung in der Zielfirmware.** Nur Vorschläge, keine automatisch flashbaren Definitionen.
- Nicht zusammenhängende, strided oder bitverschobene Layouts werden vom Transfer *noch nicht* verarbeitet; der reguläre XDF-Editor kann einen Teil dieser Speicherlayouts weiterhin dekodieren.

## Erkennung 3/3: Lernbares ML-Modell

Über **Werkzeuge → Erkennung 3/3 · Lokales ML-Modell trainieren** trainieren. Die reine NumPy-Implementierung erzeugt ein portables, prüfbares **JSON-Modell** (kein unsicheres Pickle), das lokal unter `~/.ecu_studio_ai/trained-map-model.json` gespeichert wird.

- Trainingsdaten ausschließlich aus manuell bestätigten Tabellen. Mindestens zwei Kennfeldtypen, jeweils mindestens sechs Exemplare aus wenigstens drei voneinander verschiedenen Firmware-Dateien; für reale Verlässlichkeit werden deutlich mehr unabhängige Fahrzeug-/Softwarekombinationen benötigt.
- Shape-Features (normalisierte 8×8-Surface, Gradienten, monotone Abschnitte, Kontrast, Dimensionen), standardisierte Softmax-Klassifikation mit Regularisierung.
- **Firmware-getrennter Holdout:** Keine Firmware darf gleichzeitig in Training und Prüfmenge sein. Pro Kategorie wird der Recall und gesamt der Macro-Recall gemessen.
- Das Modell **enthält keine vortrainierten, echten ECU-Labels**, da die dafür nötigen verifizierten Trainingsdaten nicht vorliegen. Bei fehlenden Daten wird Training ehrlich abgelehnt. Bei schlechtem Holdout-Macro-Recall oder geringer Klassensicherheit wird ebenfalls kein Typ ausgegeben (`abstain`).
- Modellscore **ist keine kalibrierte Wahrscheinlichkeit**. Hypothesen werden explizit als `ML-Vermutung` angezeigt und sind nicht verifiziert.

## Kommandozeile / Qualitätsprüfung

Von der Projektwurzel nach `python -m pip install -e .`:

```powershell
python -m ecu_studio.tools.recognition_v13 --catalog stats
python -m ecu_studio.tools.recognition_v13 --catalog index --bin C:\Dumps\ecu.ori --xdf C:\Definitionen\passend.xdf --json indexbericht.json
python -m ecu_studio.tools.recognition_v13 --catalog batch --manifest C:\Datenbank\paarliste.json --json batchbericht.json
python -m ecu_studio.tools.recognition_v13 --catalog train --model modell.json
python -m ecu_studio.tools.recognition_v13 --catalog predict --bin C:\Dumps\neu.bin --model modell.json --json erkennung.json
python -m pytest -q
```

Die Batchliste hat die Form `{"pairs":[{"bin":"dump1.bin","xdf":"dump1.xdf"}, ...]}` mit Pfaden relativ zur JSON-Datei. Je Paar wird nur die verknüpfte XDF als importierte Definition übernommen; A2L kann über die bestehende GUI anhand explizit eingerichteter ECU-Adresssegmente geladen und danach indexiert werden.

Der mitgelieferte Batch-Test kann ohne externe Dateien gegen `examples/example_pairs_manifest.json` ausgeführt werden. Er indexiert **synthetische** XDF-Testdefinitionen, jedoch keine verifizierten Trainingsbeispiele.

## Validierung am MS43-/GS20-Upload

- MS43-Upload (512 KiB): Siemens MS43, 430069, 512 KiB.
- GS20-Upload (64 KiB): Siemens GS20, Kalibrierkennung GADC9010, 64 KiB.
- Beide wurden mit leerer Datenbank durch die neue Pipeline geprüft: **0 extern verifizierte Kennfeldnamen**. Ihre Dateiinhalte sind nicht im ZIP. Die konkreten JSON-Berichte `MS43_ECHTDATEI_DIAGNOSE.json` und `GS20_ECHTDATEI_DIAGNOSE.json` liegen im Paket.
- Ein vollständig validierter, zu **genau diesen Dumps** passender XDF/A2L-Satz ist in dieser Sitzung nicht verfügbar. Vor allem MS4X-Extended-Load-Definitionen dürfen nicht ohne Prüfung mit serienmäßiger Firmware gleichgesetzt werden.

## Was weiterhin fehlt

- Eine großflächig befüllte, rechtmäßig verwendbare Datenbank mit unabhängig verifizierten ECU-Kennfeldpaaren. Die SQLite-Architektur und Batchimporter sind fertig, **der Datenbestand nicht**.
- Ein brauchbares, ECU-übergreifend trainiertes Modell mit echten Labels. Die Trainingspipeline ist implementiert und mit synthetischen Beispielen getestet; reale Trainingsdaten fehlen.
- 100-prozentige Identifikation unbekannter Firmwares. Binärdaten enthalten oft keine Namen; selbst sehr hohe Formähnlichkeit kann die falsche Funktion treffen.
- Vollständiges proprietäres/binäres DAMOS, sämtliche A2L-RECORD_LAYOUTs, Stride-Transfer, Checksummen-/Flashmodule und Windows-Live-GUI-Abnahme.

**Lizenzhinweis:** Externe A2L-/XDF-Dateien unterliegen ihren jeweiligen Lizenzen. MS4X stellt öffentliche Definitionsquellen unter GPL-3.0 bereit: https://github.com/ms4x-net/ms43 . Diese Drittanbieterdateien sind **nicht** in unserem ZIP. Das Projekt kopiert keine WinOLS-Dateien oder WinOLS-Algorithmen. Datenquellen und Lizenzen vor kommerzieller Nutzung prüfen.

**Qualitätsstand:** 132 automatisierte Python-Tests bestanden; `compileall` erfolgreich. Kein Live-Windows-Test (PySide6 hier nicht installiert). Keine Checksum-/Flashfreigabe und keine Validierung gegen echte Prüfstandsmessungen.
