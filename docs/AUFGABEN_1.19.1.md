# Aufgaben für 1.19.1

Stand: 03.11.2026, nach der Veröffentlichung von 1.19.0. Messungen und Hintergrund:
[Validierungsbericht § 13–14](VALIDIERUNG_1.19.0.md), [Modellkarte § 2e](MODELLKARTE.md).

Jede Änderung an der Erkennung wird mit `benchmark_suite` gegen 1.19.0 gemessen. Die Aufgaben sind erst erledigt,
wenn kein bisher exaktes Kennfeld verloren geht, Datentypen, Achsen und Achsadressen gleich bleiben oder besser
werden und die synthetischen Negativkontrollen nicht schlechter werden.

## Priorität hoch

### 1. Zwei verlorene MSD80-Kennfelder untersuchen (bekannte Regression aus 1.19.0)

MSD80 I8A0S (Teil-XDF, Entwicklungsdatei): 1.18.2 fand beide Tabellen exakt als Datenmuster-Funde, 1.19.0 nicht mehr.
Die Erkennung kam netto auf 73 → 84 exakt (13 neu, 2 verloren).

| Tabelle laut XDF | 1.19.0 findet dort |
|---|---|
| `0x4FB18`, 6 × 7, u16 | überlappende Zeilenabstands-Funde `0x4FADE` 4 × 9 und `0x4FB26` 4 × 7; dahinter ein Fund aus einem Interpolationsaufruf `0x4FB6C` 7 × 6 |
| `0x5604C`, 6 × 8, u16 | direkt davor einen Fund aus einem Interpolationsaufruf `0x55FEC` 6 × 8, der genau bei `0x5604C` endet; dahinter `0x560AC` 1 × 16 |

Vorgehen:

1. Für beide Adressen protokollieren, welche Stufe den 1.18.2-Fund verwirft bzw. ersetzt (Budget der Datenmuster,
   Überlappung mit Code-Funden, Zusammenführung).
2. Prüfen, ob `0x5604C` selbst von einem Aufruf übergeben wird, der nicht erkannt ist.
3. Nur eine gezielte Korrektur; Abnahme siehe oben.

Erledigt ist die Aufgabe, wenn beide Tabellen wieder exakt gefunden werden oder der Grund belegt dokumentiert ist und
kein anderes Paar schlechter wird.

### 2. Datenmuster-Falschfunde reduzieren, ohne echte Kennfelder zu verlieren

Ohne Lernmodell sinkt die Präzision gemessen an den Paaren mit vollständiger Referenz: MS43 79 → 75 %,
MS42 72 → 66 %, ME9 62 → 42 %, ME9.2.1 72 → 64 %, MS45 66 → 38 %. In der Vermutungsgruppe der Prüfliste sind
1–13 % exakt, darunter aber alle 22 exakten MS42-Funde und 21 von 30 bei MS45.

- Regeln (kein Training) für typische Fehlfunde suchen: Wiederholungen, Code-ähnliche Bereiche, Überlappung mit
  belegten Tabellen.
- Ein neues Lernmodell nur mit freigegebenen Trainingsdaten (`training_allowed`, Modellkarte § 2a/§ 2e). Kein
  Training mit MS42-, MS43-, SIM2K-, MSS54- oder TunerPro-Daten ohne Freigabe.
- Messung je Familie: Präzision und exakte Funde. Abnahme: kein exakter Fund verloren.

### 3. Zuordnung von X- und Y-Achsen verbessern

- Fälle sammeln, in denen Achsen vertauscht, falsch oder nicht zugeordnet sind (`axes_correct`, `with_axes` und
  `axis_address_*` im Benchmark).
- Achsen aus Code-Belegen (TriCore `a5`/`a6`, C16x) vor Achsen aus Datensuche bevorzugen.
- Abnahme: `axes_correct` und `axis_address_correct_2d` steigen, keine Verschlechterung auf einem Paar.

### 4. Kennfelder und Achsen gemeinsam darstellen

- Katalog und Inspektor zeigen ein Kennfeld mit seinen Achsen als Einheit (Adresse, Länge, Werte, Herkunft der
  Zuordnung).
- Gemeinsame Achsen mehrerer Kennfelder bleiben sichtbar.
- Keine Änderung an der Erkennung.

## Weitere Aufgaben

### 5. Scan-Abbruch bei MS43 beschleunigen

Ein Abbruch wirkt bei MS43 erst nach 3–5 s, weil das Einlesen der mitgelieferten Definition nicht unterbrechbar ist
(Validierung § 12.2). Ziel: Abbruchprüfung während des Einlesens; Ergebnis eines vollständigen Scans unverändert.

### 6. Sehr lange Windows-Installationspfade

Liegt der Programmordner tiefer als rund 200 Zeichen, scheitert das Laden der Qt-Bibliothek. Mögliche Wege:

- Hinweis im Installer bzw. beim Start;
- kürzere interne Pfade im Paket;
- Long-Path-Manifest prüfen.

### 7. Nicht reproduzierbaren GUI-Absturz beobachten

Die einmalige Zugriffsverletzung vom 01.11.2026 trat in 3000 Scans, 160 Neustartzyklen und über 100 EXE-Läufen nicht
wieder auf; die Ursache ist unbekannt.

- Auf einem Rechner mit Administratorrechten Absturzabbilder einschalten (Befehle in Validierung § 12.2).
- Belastungsläufe bei jeder Änderung an Workern oder Signalen wiederholen.
