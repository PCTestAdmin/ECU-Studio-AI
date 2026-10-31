# Nächster Sprint: Prioritäten und Abnahmekriterien

Stand: 31.10.2026, nach Branch `feature/firmware-guard` (`b504f2d`). Reihenfolge = Priorität.

## Regeln für jede Änderung

- **Schneller und zuverlässiger, messbar:** Jede Änderung bringt eine Vorher/Nachher-Messung unter gleichen
  Bedingungen mit (`library_benchmark` für Datenbank und Suche, `benchmark_suite --baseline` für die Erkennung).
  Eine Verschlechterung wird nur mit dokumentierter Begründung übernommen.
- **Nichts Unbestätigtes als sicher:** Automatische Funde und Vorschläge bleiben „ungeprüft“; „geprüft“ setzt nur
  der Nutzer ausdrücklich. Stufen und Gründe (nachgewiesen / wahrscheinlich / mehrdeutig) stehen sichtbar daneben.
  Nur eine identische Datei oder eine passende vollständige Definition ist ein Nachweis.
- **Firmware bleibt lokal:** Tests nur mit synthetischen Daten; echte Daten nur über Opt-in-Tests und lokale
  Manifeste; Firmware-Schutz vor jedem Commit und Push ([FIRMWARE_PROTECTION.md](FIRMWARE_PROTECTION.md)).

## 1. Vollständig lokale, intelligente ECU-Referenzsuche

**Heute:** Beim Öffnen einer BIN werden Projekte und Kennfeldpakete über Hash, Hardware-/Softwarenummer und Familie
gefunden, mit Stufe und Grund. Referenzdateien außerhalb von Projekten (A2L/XDF/Map-Packs im lokalen Datenordner)
werden nicht indiziert; der konfigurierbare Ordner (`ecu-studio.localdata`) kennt bisher nur der Firmware-Schutz.

**Aufgaben**
- Lokalen Referenzordner in der App einstellbar machen und dessen Definitionen (A2L-EPK, XDF-Titel, Map-Pack-Identität)
  in den Index aufnehmen; nur Metadaten und Hashes, keine Firmwarebytes in der Datenbank.
- Strukturelle Treffer: verwandte Softwarestände über den vorhandenen Softwarestand-Vergleich (verschobene
  Kennfelder) als eigene Stufe anbieten, immer mit Vorschau und Bestätigung.
- Fahrzeug-/Motorangaben nur aus belegten Quellen (Definition, Nutzerangabe) und mit Herkunft anzeigen.

**Abnahme:** Synthetische Bibliothek mit bekannten Beziehungen: jede Beziehung landet in der richtigen Stufe, keine
falsche „nachgewiesen“-Einstufung; Suche bei 20 000 Projekten + 2 000 Paketen ≤ 50 ms Median.

## 2. Hintergrund-Indizierung ohne blockierende Oberfläche

**Heute:** `ProjectStore.index_many` schreibt stapelweise mit Fortschritt und Abbruch, läuft aber im UI-Thread
(`processEvents`). Die Vorschläge beim Öffnen laufen synchron (≈ 28 ms bei 20 000 Projekten).

**Aufgaben**
- Indizierung und Referenzsuche in einen Worker-Thread mit eigener SQLite-Verbindung; Ergebnisse per Signal.
- Abbruch, Fortschritt, Fehlerliste wie bisher; laufende Suche wird beim Öffnen einer anderen BIN verworfen.
- Gleichzeitiges Schreiben aus zwei Instanzen absichern (Timeout/Retry), ohne Schemaänderung für ältere Versionen.

**Abnahme:** UI-Test, der während einer Indizierung von 500 synthetischen Projekten Ereignisse verarbeitet (keine
Blockade > 100 ms); identische Indexinhalte wie die synchrone Variante.

## 3. XDF-Export mit dynamischen Achsen und unabhängigen Kompatibilitätstests

**Heute:** Achsen werden als feste Stützstellen (`LABEL`) exportiert, weil das Modell Datentyp und Skalierung einer
Achse nicht speichert. Der Export ist atomar und wird mit dem eigenen Importer zurückgelesen.

**Aufgaben**
- `MapDefinition` um Achsendatentyp, Byte-Reihenfolge und Skalierung erweitern (Projekte bleiben in beiden Richtungen
  lesbar; unbekannte Felder bleiben erhalten).
- Achsen mit Adresse als `XDFAXIS` mit `EMBEDDEDDATA` und eigener `MATH` exportieren; ohne bekannte Adresse wie bisher.
- Unabhängige Prüfung: Struktur gegen die mitgelieferten, von TunerPro erzeugten GPL-XDFs vergleichen und mit einem
  zweiten, nicht eigenen XDF-Parser mit kompatibler Lizenz lokal gegenlesen; ein Test in TunerPro selbst wird von Hand
  durchgeführt und nur dann als solcher dokumentiert.

**Abnahme:** Rundreise ohne Abweichung für 8/16/32 Bit, signed, little/big endian, Spalten- und Zeilenachsen; der
zweite Parser liest dieselben Adressen und Werte; Bericht nennt genau, womit geprüft wurde.

## 4. Automatische Kennfelderkennung: TriCore, Datentypen, gemeinsame Achsen

**Heute:** MSD80 I8A0S (Entwicklungsdaten, unvollständige Community-XDF): 73 von 99 exakt, Typ richtig 62, 37 Paare
gemeinsamer Achsen, 0 Widersprüche. Bosch EDC17C69 liefert mit dieser Aufrufkonvention 0 Deskriptoren.

**Aufgaben**
- Datentyp: Vorzeichen und Breite der Achsen ebenfalls aus den Ladebefehlen der Achsensuche ableiten, nur bei
  übereinstimmenden Zugriffen; sonst „ungeprüft“.
- Gemeinsame Achsen: Achsen, die über mehrere Routinen oder Codepfade denselben Zeiger erhalten, zusammenführen; reine
  Wertegleichheit zählt nicht.
- Bosch-TriCore (EDC17/MED17): Übergabe der Kennfelder untersuchen, sobald ein rechtmäßiges Referenzpaar vorliegt.

**Abnahme:** keine Verschlechterung auf MS42/MS43, den Negativkontrollen und MSD80; jede Verbesserung mit
`benchmark_suite --baseline` belegt; neue Evidenzklassen bleiben unkalibriert, bis eine vollständige Referenz misst.

## 5. Unabhängige Benchmarks auf weiteren Softwareständen

**Heute:** Kein zweiter unabhängiger Datensatz; alle TriCore-Zahlen stammen aus einem Softwarestand.

**Aufgaben**
- Lokales Manifest mit Unabhängigkeitsgruppen um weitere, rechtmäßig nutzbare Paare (anderer Softwarestand derselben
  Familie, z. B. MSD80/MSD81, sowie ME7, EDC16, EDC17) erweitern; Rollen *training* und *holdout* strikt trennen.
- Ergebnisse nur als Zahlen und Hashes im Repository; Firmware und Definitionen bleiben im lokalen Ordner.

**Abnahme:** Mindestens ein Holdout-Paar je bearbeiteter Familie, bevor dort von „unabhängig validiert“ die Rede ist;
ohne solches Paar bleibt die Angabe „Entwicklungsdaten“.
