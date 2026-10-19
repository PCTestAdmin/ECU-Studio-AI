# ECU Studio AI v1.7.0 – Präzisions-Workflow, ECU-Fingerprint, geprüfte Metadaten, ORI/MOD

**Direkt aus der vom Benutzer bereitgestellten v1.6 weiterentwickelt.** Enthalten sind Quellcode, Windows-Start-/Buildskripte, bestehendes ML-Strukturmodell, bisherige SQLite-Quellendatenbank, neue Offline-Module, synthetische Beispiele und automatisierte Tests. Es liegt **keine vorgebaute Windows-EXE** bei.

## Die vier umgesetzten Bereiche

1. **Erkennung 2.0:** Die bestehende 2D-Strukturprüfung und das familiengebundene ML-/Transfermodell bleiben erhalten. In den Windows-Kandidatenscan ist eine zweite, konservative Nachbarachsen-Analyse für `u8`/`u16` und mögliche X-/Y-Achsen integriert. Bei quadratischen Kennfeldern wird eine unklare Richtung als `X/Y?` angezeigt. Kandidaten bleiben `Unbekannt`, `verified=False`; die Achsen werden **nicht** automatisch als kalibrierte Achsen eingetragen. Referenzen mit exakt passendem Firmware-Hash haben Vorrang. Getrennt exportierbarer CLI-Scan.
2. **ECU-/Fahrzeugidentifikation:** Bekannte MS43-/GS20-Dateimerkmale aus v1.6; zusätzlich vorsichtige, unbestätigte Bosch-Familientext-Hinweise (`EDC16/17`, `MED17`, `MD1`, `MG1`) mit unabhängigem BOSCH-Textmarker im Randbereich der Firmware. Eine konkrete **Fahrzeugmarke, Baureihe, Motorisierung oder Firmware-Zuordnung** wird nur aus einem *manuell geprüften, exakt SHA-256-matched Datensatz* angezeigt. Ohne Datensatz bleiben diese Angaben bewusst leer. Neue GUI-Menüs für Identifikationsreport und gesicherten Manifest-Import.
3. **Nachprüfbare ECU-Datenbank:** Zusätzliche SQLite-Tabelle `firmware_identity` inklusive Hersteller, Fahrzeugmodell, ECU, Software, Herkunft, Prüfer und exakt gebundenem SHA-256. Atomarer JSON-Massenimport mit verpflichtendem lokalen BIN-Hashnachweis, menschlichem `reviewed=true` und Schutz vor widersprüchlichen Duplikaten. Die v1.6 Datenbank mit 14 öffentlichen Quellen und 118 Hinweisdatensätzen plus sieben markenspezifischen Quellen bleibt unverändert erhalten; professioneller Abdeckungsdialog für Audi, Mercedes-Benz, BMW, Opel und Lamborghini trennt Hinweise von nachweislich geprüften Trainingsdaten. Die vorhandenen Funktionen **Erkennung 1/3 / Viele BIN/XDF-Paare importieren** bleiben verfügbar.
4. **Original-vs.-Modifiziert:** Echter, schreibgeschützter Vergleich auf identischen Byte-Offsets mit SHA-256, Anzahl/Größe der Änderungsblöcke, geänderten Bytes *außerhalb* definierter Kennfelder, geänderten Tabellenzellen (selbst bei strides/endianness), Maximaldifferenzen in Roh-/physischen Werten und CSV-Exports. Neue dialogbasierte Übersicht mit Kennfeld- und Zellansicht und Sprung zur Speicheradresse. Verschiedene Dateilängen werden zurückgewiesen, unbekannte Firmwaregleichheit wird klar benannt. Die Zellansicht zeigt die ersten 3000 Einträge; der Analysebericht speichert bis zu 20000; darüber muss in kleineren Bereichen verglichen werden. Bei sehr großer Fragmentierung werden nicht alle Einzelblöcke materialisiert, die Summen bleiben exakt.

**Wichtiger Bugfix:** Die bisherige `require_image()`-Methode hatte keinen positiven Rückgabewert. Dadurch brachen viele GUI-Werkzeuge auch bei geladener BIN frühzeitig ab. Diese Methode gibt nun bei erfolgreich geladener BIN `True` zurück.

## Windows-Installation und Bedienung

1. ZIP in einen lokalen Ordner entpacken.
2. Windows 10/11, Python 3.10+ vorinstallieren; `start_windows.bat` ausführen. Beim ersten Mal wird eine lokale `.venv` erstellt, die benötigte Pakete herunterlädt. Kein automatischer ECU-Netzzugriff.
3. Im Menü **Werkzeuge**:
   - `Intelligente Kennfeldsuche ...` für Struktur-/Achsenhinweise; erfordert eine geladene BIN.
   - `Fahrzeug / ECU: Fingerprint prüfen ...` für eine nicht irreführende Fahrzeug-/ECU-Auskunft.
   - `Fahrzeug / ECU: geprüfte Hash-Identitäten importieren ...` für überprüfte eigene Daten.
   - `ORI / MOD: Kennfeldvergleich mit CSV ...` (`Strg+Umschalt+C`) – zuerst Originaldatei (idealerweise zusammen mit passenden A2L/XDF-Definitionen) laden, dann zweite Datei wählen.
   - `Datenbank · Abdeckung nach Automarke ...` zum Überblick über Quellen vs. tatsächlich bestätigte Trainingsreferenzen.
4. Mit `build_exe_windows.bat` kann auf Windows selbst ein EXE-Build erstellt werden. Dieser Windows-Build wurde hier nicht live ausgeführt.

## Beispiel für die neue Identitätsdatenbank

`examples/IDENTITY_MANIFEST_SCHEMA.json` enthält ein **leeres, gültiges** `records`-Array und ein *nicht importiertes* Beispiel. Die Struktur eines einzulesenden Datensatzes:

```json
{
  "format": 1,
  "records": [{
    "firmware_sha256": "64 hex Zeichen der Original-BIN",
    "byte_count": 524288,
    "brand": "BMW",
    "model": "vom Menschen bestätigtes Modell",
    "engine": "vom Menschen bestätigter Motor",
    "ecu": "genaue ECU-Variante",
    "family": "Siemens MS43",
    "software": "konkrete Softwareversion",
    "source": "dokumentierter Prüfbeleg",
    "reviewer": "Prüferkennung",
    "firmware_file": "relativer/Pfad/zur/Originaldatei.bin",
    "reviewed": true
  }]
}
```

`firmware_sha256` ist **kein** Platzhalter beim echten Import. Der Import schlägt bei abweichender lokaler BIN/Größe/Hash fehl. Es werden keine vollständigen Binärdaten in die Identitätsdatenbank kopiert. Ein manueller Prüfvermerk ist ein **Herkunftsnachweis**, kein unabhängiges TÜV-/Herstellerzertifikat.

## Headless-Bedienung (für Reproduzierbarkeit)

Die Module sind mit `python -m` auszuführen (bei nicht installiertem Paket vorher `pip install -e .`, oder `PYTHONPATH=src` setzen):

```bash
python -m ecu_studio.tools.pro_workflows identify meine_original.bin
python -m ecu_studio.tools.pro_workflows import-identities identities.json
python -m ecu_studio.tools.pro_workflows scan meine_original.bin --axes --out scan_v17.json
python -m ecu_studio.tools.pro_workflows compare original.bin mod.bin --maps maps.csv --csv maps_diff.csv --cells-csv cells_diff.csv --out report.json
python -m ecu_studio.tools.pro_workflows coverage --brand Mercedes-Benz
```

Für einen vollständig synthetischen, reproduzierbaren Vergleich liegen `examples/demo_synthetic.bin`, `examples/demo_modified_synthetic.bin`, `examples/demo_definitions.csv`, die beiden CSVs und `examples/demo_ori_mod_report_v17.json` bei. Darin sind **2 Demo-Kennfelder geändert, 1 Byte außerhalb der beiden Tabellen**, Gesamtzahl **3 geänderte Bytes**. Keine realen Fahrzeugkalibrierungen.

## Verifizierungsstand / Grenzen

- **Nicht** erfolgt: Neues beaufsichtigtes KI-Training für Audi, Mercedes, BMW-MG1, Opel oder Lamborghini. Es fehlen geprüfte, rechtmäßig verwendbare und zueinander exakt passende BIN+Definition+Softwarestand-Trainingspaare.
- **Nicht** erfolgt: unabhängiger Holdout-Test mit unbekannten Firmwareständen dieser fünf Marken. **Keine** 100%-Erkennungsquote behauptet. Das bisherige 67-Sample-MS43-Strukturmodell hat keine unabhängig verifizierten Klassifikationslabels.
- **Nicht** erfolgt: Windows-Qt-Laufzeittest in dieser Linux-Umgebung (PySide6 hier nicht installiert), ECU-Flash, Checksum-Korrektur, Leistungsprüfstand oder Fahrzeugfreigabe.
- Die neuen Selbsttests decken Identitätsimport, Prüfer-/Hashpflicht, abgelehnte Kollisionen, bewusst unbekannte ECU-Marker, Achsen-Abstention, stride-sensitiven ORI/MOD-Vergleich und CLI-Ausgaben ab. Details siehe `QA_REPORT_V17.json`.
- In den enthaltenen Katalog-/Quelldaten waren beim Build **0 fachlich bestätigte** neue Kennfeldlabels; neue **verifizierte** Herstellerdaten sind nicht erfunden. Ein Quellenlink oder ein Git-Blob-Hash belegt nur die Quelldatei, nicht die Firmware-Funktion.

Die Erkennungssoftware verändert Firmwaredateien **nicht** automatisch. Kennfeldnamen, Achsen, Einheiten, Checksummen und vor allem die sichere Änderbarkeit benötigen externe Definitionen, fachliche Verifikation und Messdaten.
