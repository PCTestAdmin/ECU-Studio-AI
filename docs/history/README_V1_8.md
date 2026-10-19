# ECU Studio AI v1.8.0 – Kennfeldeditor, Gruppen, Checksum-/Plausibilitätsprüfung

**Weiterentwicklung der im Gespräch bereitgestellten v1.7 (nicht neu geschrieben).** Enthalten: Windows-GUI-Quellcode, Offline-Datenbank, bisheriges ML-Strukturmodell, vorhandene Test-/Beispieldateien und neue v1.8-Module. Keine vorgebaute Windows-EXE.

## Neue Funktionen

### 1. Präziserer 2D-/3D-Kennfeldeditor

- **2D-ORI/MOD-Kurve** als neue Registerkarte: auswählbare Zeile oder Spalte, Rohindex oder hinterlegte X-/Y-Definitionsachse, Original (grau gestrichelt) gegen veränderte Daten (blau). Klick auf einen Punkt öffnet die entsprechende Zelle in der editierbaren Kennfeldtabelle.
- **Heatmap** ist nun anklickbar: Klick auf ein Farbfeld navigiert zur realen Kennfeldzelle. Bei gerasterten großen Karten wird auf die repräsentierte Zelle gesprungen.
- **3D-Drahtgitteransicht**: Vorher-/Nachher-Overlay bei Änderungen, horizontale Drehung, vertikale Neigung und Mausrad-Zoom. Die Z-Höhe bleibt relativ normalisiert und ist kein Belastungs-/Leistungsnachweis.
- Bearbeitung erfolgt wie bisher in der Tabelle (Rohwertkonvertierung, Umrechnungsprüfung, Änderungsprotokoll und Undo); Batchbearbeitung mit Vorschau bleibt erhalten. Nicht invertierbare XDF-Formeln sind weiterhin schreibgeschützt.

### 2. ECU-Checksummen und Kalibrierungsplausibilität

**Prüfung statt vorgetäuschter Universalkorrektur.** Im Menü `Werkzeuge`:

- `ECU-Checksummenprofil importieren …`: ausschließlich lokal überprüfte JSON-Profile mit Ursprung, Prüfer, Originaldatei-SHA-256 und expliziten Prüfregionen/Feldern. Unpassende Hashes, unzulässige Offsets oder Prüffeld-Selbstreferenzen werden abgewiesen.
- `Checksum- und Plausibilitätsprüfung …` (`Strg+Umschalt+Q`): `match`/`mismatch`/`unknown`, Prüffeld-Einzelwerte, Hash, Anzahl veränderter Bytes, editierte Kennfelder und geänderte Bytes außerhalb zugeordneter Tabellen sowie Kennfeld-Decodehinweise. Als JSON exportierbar.
- Jeder BIN-Export zeigt vor der manuellen Bestätigung den neuen Prüfschritt, einschließlich Warnungen bei fehlendem oder fehlerhaftem Profil. Originaldatei wird nie überschrieben.
- Unterstützt nur **explizit beschriebene** `crc32-ieee` (CRC-32/IEEE, zlib), `sum16-bytes` (Byte-Summe mod 2^16) und `sum32-bytes` (Byte-Summe mod 2^32); Angabe je Region mit separatem Speicherfeld und Byte-Reihenfolge. Es gibt **keine** automatische Reparatur.

**WICHTIG:** Das sind mathematische Prüfverfahren, keine universellen OEM-Checksummenalgorithmen. Ein passender Wert beweist lediglich die deklarierten Bereiche und garantiert weder vollständige ECU-Checksummen noch Flashbarkeit, Motor-/Abgasverträglichkeit, zulässigen Betrieb oder Sicherheit. Für echte ECUs bedarf es unabhängig bestätigter Profile einschließlich aller Bereiche und weiterer Schritte.

JSON-Profilformat:

```json
{
  "format": 1,
  "firmware_sha256": "64 hex Zeichen des Original-BIN-SHA-256",
  "source": "prüfbare Herkunft / Dokumentation",
  "reviewer": "manueller Prüfer",
  "reviewed": true,
  "slots": [
    {
      "name": "durch Prüfer bestätigter Bereich",
      "algorithm": "crc32-ieee",
      "start": 0,
      "end": 1024,
      "storage_offset": 4092,
      "endian": "big"
    }
  ]
}
```

`start` ist inklusive, `end` exklusiv. Die Zahlen oben sind **nur eine Formatillustration**, nicht gültig für ein bestimmtes ECU-Modell. Datei und Speicherbereiche müssen zusammenpassen. `reviewed: true` dokumentiert einen Eintrag und ist **kein automatischer Beweis** für herstellerseitige Validierung.

### 3. Automatische Kennfeldgruppen

- Neuer Menüpunkt `Kennfelder automatisch gruppieren …` (`Strg+Umschalt+G`): navigierbarer Baum und CSV-Export.
- Bereits benannte Kennfeldtypen (Drehmoment, Ladedruck, Zündung, Lambda, Einspritzung, AGR, Drehzahl, Temperatur, etc.) werden nach ihren **vorhandenen** Typen sortiert.
- Unbenannte Kandidaten können bei ähnlicher Form und räumlicher Nähe zu einer **ausdrücklich unbestätigten** Nachbarschaftsgruppe zusammengefasst werden. Keine Funktionsnamen werden aus bloßer Form erfunden.
- Verifizierungsstatus wird je Kennfeld fortgeführt, nicht auf eine Gruppe übertragen. Gruppen beweisen **keine** logische/physikalische Kopplung.

## Synthetisches Beispiel (kein echtes Fahrzeug)

Die drei mitgelieferten Dateien:

- `examples/checksum_demo_synthetic.bin`: fiktive Rohdaten mit künstlichem CRC-32-Prüffeld.
- `examples/checksum_demo_profile.json`: darauf hashgebundenes und im Testkontext überprüftes Profil.
- `examples/checksum_demo_modified.bin`: absichtlich verändertes fiktives Abbild ohne CRC-Korrektur.

Im Windows-Programm die Original-Demo-BIN öffnen und anschließend das passende Profil importieren: `match`. Danach an Offset `0x70` und/oder `0x71` einzelne Bytewerte ändern und erneut prüfen: `mismatch`. Die mitgelieferte MOD-Demo kann über die **CLI** mit `--mod` gegen die unveränderte Original-BIN geprüft werden. Wer nur die MOD-Datei als neues Original öffnet, kann das an die Original-BIN gebundene Profil **nicht** importieren – das ist ein gewollter Schutz. Keine echte ECU-Firmware enthalten.

## Automatisierung ohne GUI

Im Projektverzeichnis `python -m pip install -e .` (auf Windows optional die Starter-BAT) oder `PYTHONPATH=src` setzen.

```bash
python -m ecu_studio.tools.calibration_v18 audit examples/checksum_demo_synthetic.bin --profile examples/checksum_demo_profile.json --out examples/demo_check_pass.json
python -m ecu_studio.tools.calibration_v18 audit examples/checksum_demo_synthetic.bin --mod examples/checksum_demo_modified.bin --profile examples/checksum_demo_profile.json --out examples/demo_check_fail.json
python -m ecu_studio.tools.calibration_v18 groups examples/demo_synthetic.bin examples/demo_definitions.csv --csv examples/demo_groups_v18.csv
```

Im zweiten Fall wird die Änderung **nur im Arbeitsspeicher** betrachtet; das Original wird nicht modifiziert.

## Teststatus und Einschränkungen

- `PYTHONPATH=src pytest -q` – **160 bestanden, 4 übersprungen** in dieser Linux-Umgebung (Stand Paketierung). Die neuen Kernmodule besitzen sechs Regressionstests; zusätzlich bestehen alle bisherigen 154 Tests.
- Python-Syntaxkompilierung ist bestanden. Der tatsächliche Start der Windows-PySide6-Oberfläche und Windows-EXE-Build konnten hier **nicht** ausgeführt werden (PySide6 fehlt, und es gibt keine Netzwerkverbindung zur Installation).
- Weiterhin kein zusätzliches unabhängiges KI-Training und **keine** neuen bestätigten Hersteller-BIN/Kennfeld-Paare. v1.7-KI-/Hash-ECU-Funktionen wurden beibehalten.
- Keine automatische ECU-Checksum-Reparatur und keine vollständige OEM-Checksum-Abdeckung. Ergebnisse sind für kontrollierte Offline-Analyse gedacht.

## Windows-Start

1. ZIP entpacken, Python 3.10+ verfügbar machen.
2. `start_windows.bat` starten, das Programm erstellt eine `.venv` und installiert benötigte Pakete. Beim ersten Mal Internetzugang erforderlich.
3. Für einen lokalen EXE-Build optional `build_exe_windows.bat` ausführen; **EXE nicht im Archiv enthalten**.

Vor einem realen Steuergeräte-Schreibvorgang unabhängig für ECU-Hardware, Softwarevariante, alle Checksummen, Sicherheit, emissionsrechtliche Anforderungen und Wiederherstellbarkeit validieren.
