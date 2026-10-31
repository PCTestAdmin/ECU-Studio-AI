# Mitmachen bei ECU Studio AI

Danke für dein Interesse! Hier steht, wie Beiträge am besten ankommen.

## Grundregeln

1. **Keine Original-Firmware hochladen.** BIN-, ORI- oder OLS-Dateien von Herstellern sind urheberrechtlich
   geschützt – weder in Issues noch in Pull Requests. Teile stattdessen Prüfsumme (SHA-256), Größe,
   Steuergeräte-/Softwarekennung und Messergebnisse.
2. **Messen statt behaupten.** Änderungen an der Erkennung brauchen eine Vorher/Nachher-Messung mit
   `python -m ecu_studio.tools.benchmark_suite MANIFEST.json --baseline ALT.json` auf mindestens einem
   Referenzpaar (Manifest und Rollen: [docs/REFERENCE_VALIDATION.md](docs/REFERENCE_VALIDATION.md));
   `python -m ecu_studio.tools.miss_analysis MANIFEST.json` zeigt, warum Kennfelder fehlen. Eine Verbesserung
   auf einer Familie darf andere Familien und die Negativkontrollen nicht messbar verschlechtern.
3. **Keine Scheingenauigkeit.** Automatische Funde bleiben Geometrie-Hypothesen. Namen, Einheiten oder
   Funktionen nur aus Definitionen oder bestätigter Prüfung – nie aus Rohdaten erraten.
4. **Kein Code fremder Tuning-Software.** Nur eigene Implementierungen oder Quellen mit kompatibler Lizenz (GPL-3.0).

## Entwicklungsumgebung

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -e .[dev,train]
python -m pytest -q
```

## Pull Requests

- Ein Thema pro Pull Request, mit kurzer Begründung und Messwerten.
- Neue Funktionen bekommen Tests; synthetische Testdaten bitte im Test erzeugen statt Dateien einzuchecken.
- Code-Stil wie im umgebenden Code; Oberflächentexte auf Deutsch.
- Die Tests müssen unter Python 3.11 und 3.12 grün sein (läuft automatisch über GitHub Actions).

## Neue Steuergerätefamilie messen

Am wertvollsten sind öffentliche BIN/Definitions-Paare einer noch nicht gemessenen Familie:

1. `benchmark_suite` mit einem lokalen Manifest ausführen und das Ergebnis (JSON, enthält nur Zahlen und Hashes)
   im Issue „Erkennungsbericht“ posten.
2. Quelle der Definition und ihre Lizenz angeben.
3. Falls die Definition vollständig ist: `tools/calibrate_confidence.py` mit dem Paar ausführen und das
   Ergebnis beilegen.
