# Lokale, hashgebundene Referenzmessungen

`benchmark_suite` und `miss_analysis` bleiben die bestehenden Messwerkzeuge. Der neue Einstiegspunkt
`validation_report` verbindet beide mit einem strikt geprüften **lokalen** Manifest. Ein Bericht enthält
Benchmarkergebnisse und jedes verfehlte Referenzkennfeld; keine BIN-Bytes, Definitionstexte oder Dateipfade.

```json
{
  "schema": 1,
  "pairs": [{
    "name": "EDC17CP09-SW-A",
    "family": "Bosch EDC17CP09",
    "software": "SW-A",
    "bin": "private/original.bin",
    "sha256": "64-stellige-kleingeschriebene-SHA256",
    "reference": "private/reference.a2l",
    "reference_sha256": "64-stellige-kleingeschriebene-SHA256",
    "complete": true,
    "role": "development",
    "group": "EDC17CP09-sister-group",
    "data_kind": "real",
    "source": "public provenance label",
    "license": "local permitted use label",
    "anchor": "0x80000000"
  }]
}
```

Pfade werden relativ zum Manifest aufgelöst; absolute lokale Pfade sind ebenfalls erlaubt.
Dieses Beispiel ist eine Vorlage, keine vorhandene Messdatei. Öffentliche Aliase enthalten keine Kunden- oder
Dateinamen; Familie, Software, Quelle und Nutzungshinweis sind öffentliche Kurztexte, keine lokalen Pfade.
Das Manifest gehört in `.qa/` außerhalb der Git-Veröffentlichung. Quellenbelege und Nutzungsrechte separat lokal
aufbewahren. Ein Manifest kann diese Rechte oder die behauptete Vollständigkeit nicht automatisch beweisen.

```text
python -m ecu_studio.tools.validation_report .qa/manifest.json --out .qa/current.json --markdown .qa/current.md --baseline .qa/baseline.json --memory
```

Die Eingaben müssen vor dem Lauf ihren gespeicherten SHA-256-Werten entsprechen. Explizite Rollen
`training/development/test` sind Pflicht. Derselbe Hash oder dieselbe deklarierte Unabhängigkeitsgruppe darf
keine verschiedenen Rollen tragen; nahezu identische Dateien werden zusätzlich durch das bestehende
`group_images` geprüft. Ein gemeinsamer Test mit Trainingsdaten wird abgelehnt. Synthetische Datensätze zählen
separat und erhöhen nie `independent_pairs` für reale Firmware. Eine absolute Garantie gegen alle Formen der
Datenabhängigkeit liefert dieser Vergleich nicht; die Gruppenzuordnung muss fachlich gepflegt werden.

In CI sind in diesem Workflow nur `data_kind=synthetic` erlaubt. Der Bericht übernimmt keine Eingabepfade;
Fehlerausgaben des CLI unterdrücken pfadführende Decoder-/Dateisystemdetails. Ausgabeziele dürfen weder
Original, Referenz, Manifest noch Baseline überschreiben. Höchstens 100 Paare, 2 MiB Manifest und 128 MiB pro
Eingabedatei, insgesamt höchstens 512 MiB; Firmware wird wie im übrigen Programm nur lesend geöffnet.

`--memory` misst den Python-Allokationspeak in einem separaten Scannerlauf (`tracemalloc`), nicht den gesamten
Prozess-RSS. Laufzeit und Speicher werden deshalb nicht im selben Scan gemessen. `--limits` vergleicht zusätzlich
die bisherigen erweiterten Ergebnisgrenzen. Präzision/FP/FN bleiben auf als vollständig deklarierte Referenzen
beschränkt. Scannen und Fehlfundanalyse bleiben deterministisch; Laufzeiten können schwanken.

Vorher/Nachher-Vergleiche prüfen nun neben dem BIN-Hash auch Referenzhash, Softwarestand, Rolle, Datenart,
Familie und Referenzvollständigkeit. Ein Wechsel macht die Messungen nicht vergleichbar. Neue Berichte speichern
außerdem die exakten Layoutschlüssel; sind sie in beiden Läufen vorhanden, werden hinzugewonnene und verlorene
exakte Kennfelder einzeln ausgewiesen. Alte Baselines ohne Referenzbindung müssen mit den unveränderten Eingaben
neu erzeugt werden; sie werden nicht still als gleichwertig behandelt.

Für EDC17CP09 (6P8KB574), EDC16C35 (4M702389), EDC16C31 (6m661411), MSD85 (791I200S) und MSD80
(37IIAFAA bis 37IIANAA) fehlen lokal weiterhin die passenden BIN-/vollständigen Definitionspaare mit erlaubter
Nutzung. Benötigt werden passende Speichersegmente/EPK, Quellnachweis, Hashes und bei Transferprüfungen mindestens
zwei tatsächlich verschiedene Softwarestände. Eine EDC17C69-BIN ohne passende Definition ersetzt diese Paare nicht.
