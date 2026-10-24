# Offenes ECU-Studio-Kennfeldpaket, Version 2

Das bestehende Format `ecu-studio-map-pack` wird erweitert, kein zweites Paketformat eingeführt.
Dateiendung: `.ecupack.json`, UTF-8-JSON ohne ausführbaren Code oder Firmwarebytes.
Version 1 bleibt lesbar. Die Version 2 ist ab ECU Studio AI 1.17.0 verfügbar.

## Inhalt

| Feld | Bedeutung |
|---|---|
| `format`, `version` | `ecu-studio-map-pack`, Ganzzahl `2` |
| `source_sha256`, `source_size` | Hash des unveränderten Originals und Länge in Bytes |
| `identity` | `family` als Text, `hardware` und `software` als Listen der in der BIN erkannten Kennungen; leer bedeutet unbekannt |
| `maps` | Liste der `MapDefinition`-Datensätze; Adressen sind **Dateioffsets**, `ecu_address` ist nur ergänzende symbolische ECU-Adresse |
| `axis_groups` | Abgeleitete Gruppen aus `axis_groups.shared_axis_groups`; Mitglieder als `[map_index, "X"/"Y"]`, gespeicherte Achsadressen, Punktzahl, Quelle und Unsicherheiten |
| `provenance` | Beschreibung des Pakets und Vertrauensmodell; Herkunft pro Definition in `source`, optionale Beschreibung in `notes`, Beleg in `label_evidence` |
| `integrity_sha256` | SHA-256 der kanonischen JSON-Darstellung aller anderen Felder (`core.storage.canonical_digest`) |

Ein Kennfelddatensatz enthält Name, Start, Zeilen/Spalten, Typ (`u8/s8/u16/s16/u32/s32/f32`), Endianness,
Skalierung `factor/bias`, Einheit, Funktion, X-/Y-Stützstellen, deren Einheiten und Rollen, gespeicherte
Achsadressen/-referenzen, Speicherordnung/Strides und den vom Autor angegebenen Prüfstatus.
Alle Felder und Standardwerte stehen in `core.model.MapDefinition`; das Paket behält sie als JSON-Werte.
Es enthält **keine** Werteblöcke der Kennfelder, ORI/MOD-Patches oder Firmwareabbilder. Der Ursprungssoftwarestand
steht in `identity.software`. Wenn die BIN keine Softwarekennung enthält, wird keine erfunden.

Die Integritätsprüfsumme erkennt Beschädigungen. Sie ist weder digitale Signatur noch unabhängiger OEM-Nachweis.
Auch ein vom Autor als `verified` markierter Eintrag wird bei der Übernahme zunächst `verified=false`.
Der Prüfstatus der Quelle bleibt im Beleg sichtbar; die fachliche Bestätigung am Ziel bleibt erforderlich.

## Export und Datenschutz

Die bisherigen Menübefehle **Datei → Eigenes ECU-Map-Pack exportieren/importieren …** bleiben die Einstiegspunkte.
Der Exportdialog bietet alle, nur bestätigte oder ausgewählte Definitionen sowie optional gespeicherte
Achsadressen/Gruppen. Stützstellenwerte und Einheiten bleiben beim Abwählen der Adressen erhalten.
Eine Vorschau zeigt die gewählten Definitionen.

Freie Notizen, Belege, Achsenhinweise, Ordner und lokale Pfade werden standardmäßig nicht weitergegeben.
Beschreibungen/Belege können ausdrücklich eingeschlossen werden. Kennfeldnamen und eingeschlossene Texte
müssen vor der Weitergabe auf Kundeninformationen geprüft werden. Absolute Dateipfade in exportierten
Definitionsfeldern werden abgelehnt. Unbekannte Projektfelder bleiben im Projekt verlustfrei erhalten;
zum Export solcher Definitionen wird eine Version benötigt, die ihre Bedeutung kennt.

## Import und Vergleich

1. Parser prüft Version, Größen-/Geometriegrenzen, Achsadressen und Integrität. Doppelte JSON-Schlüssel und
   nichtendliche Zahlen werden abgewiesen. Gruppen müssen mit den Definitionsadressen übereinstimmen.
2. Inhalt, Herkunft und Konflikte erscheinen vor der Übernahme. Unbekannte künftige Felder werden benannt;
   ein solches Paket kann verlustfrei gelesen/geschrieben, aber nicht übernommen werden.
3. Direkte Übernahme nur bei identischem Original-Hash **und** identischer Größe. Angegebene ECU-/HW-/SW-Kennungen
   müssen zu den am Original erkannten Kennungen passen. Unbekannt ist keine bestätigte ECU-Identität.
4. Doppelte oder überlappende Definitionen innerhalb des Pakets oder mit dem Zielkatalog blockieren die gesamte
   direkte Übernahme. Vorhandene Definitionen werden niemals überschrieben oder still entfernt.
5. Andere Originale: lokale Quell-BIN wählen, deren Hash exakt zum Paket passt. Danach arbeitet der vorhandene
   Softwarestand-Vergleich (`version_compare`, `name_transfer`). **Keine** ungeprüfte Kopie an gleiche Offsets.
6. Explizite Bestätigung erzeugt eine atomare Katalogtransaktion samt Projektversionsstand und Audit-Eintrag.
   Firmwarebytes ändern sich nicht. Strg+Z/Strg+Y nutzen denselben Undo-Stapel wie Byte-Edits und halten die
   Reihenfolge ein. Nach späteren, nicht transaktionalen Definitionsänderungen wird eine veraltete Rücknahme
   abgelehnt, statt diese Änderungen zu verlieren. Der Undo-Stapel ist wie bisher sitzungsbezogen;
   gespeicherte Versionsstände und Journal bleiben im Projekt erhalten.

Das aktuelle Datenmodell enthält keinen separaten Speicher-Datentyp für Achsen. Der Import prüft daher
Achsadressen und minimale Bereichslängen, aber behauptet keine unabhängige Dekodierung aller Achsbytes.
Ungeprüfte Zielachsen bleiben auch im bestehenden Werte-Transfer gesperrt.

## Grenzen und lokale Vorschläge

Maximal 16 MiB JSON, 5000 Definitionen, 5 Millionen beschriebene Zellen, 512 Punkte pro Dimension,
4096 Zeichen pro Text und 12 Verschachtelungsebenen. Die Prüfung von Kennfeldgrenzen folgt dem bestehenden
strided/row-major/column-major-Modell. Überlappungen werden konservativ über Bytehüllen erkannt.

**Paket lokal merken** und der Export ergänzen den vorhandenen Projektindex um eine additive Cache-Tabelle.
Beim Laden einer BIN erscheinen bekannte Pakete/Projekte mit gleichem Hash oder gleicher erkannter Familie.
Es werden keine Verzeichnisse ungefragt durchsucht und keine Definitionen/Werte automatisch übernommen.
Der Import liest die Datei erneut; ein Cache-Eintrag ist kein Vertrauensnachweis.

## Reproduzieren

`python -m pytest -q tests/test_map_pack.py tests/test_map_pack_workflow.py`

Die Tests erzeugen die Daten selbst: sieben Datentypen × zwei Byte-Reihenfolgen, geteilte Achsen,
Identitätskonflikte, beschädigte/future Pakete, doppelte Einträge, Überlappungen, Abbruch, Undo/Redo,
Projektversionen und Speichern/erneutes Öffnen. Der Integrationstest verwendet den bestehenden Scanner
und den bestehenden Softwarestand-Abgleich. Keine privaten ECU-Dateien werden für CI benötigt.
