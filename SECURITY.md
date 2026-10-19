# Sicherheit

ECU Studio AI liest fremde Dateien (BIN, XDF, A2L, XML, ZIP). Fehler beim Einlesen manipulierter
Dateien können ein Sicherheitsproblem sein.

## Schwachstelle melden

Bitte **nicht** als öffentliches Issue, sondern über
[GitHub Security Advisories](https://github.com/PCTestAdmin/ecu-studio-ai/security/advisories/new).
Beschreibe, welche Datei bzw. welcher Ablauf das Problem auslöst – ohne Original-Firmware anzuhängen;
eine minimale, selbst erzeugte Beispieldatei reicht.

## Bereits umgesetzt

- XML wird mit `defusedxml` gelesen (keine externen Entitäten, keine Netzwerkzugriffe).
- Umrechnungsformeln werden geparst, nie mit `eval` ausgeführt.
- Modelle werden als JSON gespeichert, nicht als Pickle.
- Die Originaldatei wird nie überschrieben; Exporte schreiben atomar mit Sicherung.

## Nicht im Umfang

Ob eine geänderte Kalibrierung für ein Fahrzeug sicher ist, kann die Software nicht beurteilen.
Der Flash-Preflight prüft nur die dokumentierten Punkte und ist keine Freigabe.
