# Sicherheit

ECU Studio AI liest fremde Dateien (BIN, XDF, A2L, XML, ZIP). Fehler beim Einlesen manipulierter
Dateien können ein Sicherheitsproblem sein.

## Schwachstelle melden

Bitte **nicht** als öffentliches Issue, sondern über
[GitHub Security Advisories](https://github.com/PCTestAdmin/ECU-Studio-AI/security/advisories/new).
Beschreibe, welche Datei bzw. welcher Ablauf das Problem auslöst – ohne Original-Firmware anzuhängen;
eine minimale, selbst erzeugte Beispieldatei reicht.

## Bereits umgesetzt

- XML wird mit `defusedxml` gelesen (keine externen Entitäten, keine Netzwerkzugriffe).
- Umrechnungsformeln werden geparst, nie mit `eval` ausgeführt.
- Modelle werden als JSON gespeichert, nicht als Pickle.
- Die Originaldatei wird nie überschrieben; Exporte schreiben atomar mit Sicherung.
- Updates: nur von den offiziellen Release-Adressen, SHA-256 gegen `.sha256`-Datei **und** GitHub-Angabe,
  Build-Herkunft (`gh attestation verify`), optional Ed25519-Signatur (RFC 8032, siehe `docs/RELEASE.md`) –
  ist ein öffentlicher Schlüssel eingebaut, wird ohne gültige Signatur nichts geladen.

## Nicht im Umfang

Ob eine geänderte Kalibrierung für ein Fahrzeug sicher ist, kann die Software nicht beurteilen.
Der Flash-Preflight prüft nur die dokumentierten Punkte und ist keine Freigabe.
