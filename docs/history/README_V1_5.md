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
