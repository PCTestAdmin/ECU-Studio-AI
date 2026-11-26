# Anleitung für Beta-Tester: lokaler Testbericht

*English version: [BETA_TESTER_GUIDE.md](BETA_TESTER_GUIDE.md).*

Diese Anleitung ist für Menschen, die messen möchten, wie gut ECU Studio Kennfelder in **ihrer eigenen** Steuergerätedatei erkennt. Programmierkenntnisse sind nicht nötig. Die Messung läuft vollständig auf deinem Rechner. Es wird nichts gesendet.

## Was du brauchst

- Ein Testbuild von ECU Studio mit dem Testbericht (in 1.21.0-rc1 noch nicht enthalten; den Testbuild bekommst du von den Entwicklern).
- Eine Originalauslesung deines Steuergeräts (`.bin`), die du rechtmäßig nutzen darfst.
- Die Definition zu **genau dieser** Datei: A2L, XDF oder CSV. Gehört die Definition zu einem anderen Softwarestand, ist das Ergebnis wertlos.

Verwende nur Dateien, die du nutzen darfst. Gib keine Firmware oder Definitionen weiter. Der Bericht enthält beides nicht.

## Am einfachsten: im Programm (ab dem Testbuild nach Qualitätsphase 6)

Menü **Werkzeuge → Kennfelderkennung überprüfen (lokaler Test) …** öffnet einen Assistenten mit sieben Schritten:

1. **Einführung** – was gemessen wird und was nicht.
2. **Firmware wählen** – die Datei wird nur gelesen und geprüft. Abgelehnt werden z. B. leere Dateien, Textdateien, Intel-HEX/S-Record, ZIP, WinOLS-Projekte, Definitionen und Programmdateien, jeweils mit Grund.
3. **Definition wählen** (A2L, XDF oder CSV) und **Steuergerätelinie** eingeben, dann **Passung prüfen**. Passt die Definition nicht zur Firmware (z. B. andere Software), geht es nicht weiter.
4. **Analyse** – läuft im Hintergrund. Die Kennfeldsuche bekommt nur die Firmware, nicht die Definition. **Analyse abbrechen** oder das Fenster schließen stoppt sie; nichts wird gespeichert.
5. **Ergebnis** – Trefferquote (wie viele Kennfelder der Definition genau gefunden wurden), Datentyp und Achsen der Treffer, Funktionszuordnung. Eine Präzision wird nicht berechnet, weil eine eigene Definition selten vollständig ist; Kandidaten, die nicht in der Definition stehen, gelten als „nicht bewertbar“, nicht als falsch.
6. **Export** – Vorschau genau des Dateiinhalts. Werte ab 100 sind gerundet (umschaltbar auf exakte Werte, höheres Wiedererkennungsrisiko). Gespeichert wird nur nach Häkchen „Ich habe den Inhalt geprüft …“ und Wahl eines Dateinamens; vorhandene Dateien werden nie überschrieben.
7. **Feedback** (freiwillig) – nur feste Antworten, keine freie Texteingabe; ebenfalls nur nach Vorschau und Zustimmung gespeichert.

Der Bericht ist derselbe wie beim Kommandozeilen-Assistenten unten. ECU Studio sendet nichts; ob und wem du die Datei gibst, entscheidest du.

## So geht's (geführter Ablauf in der Eingabeaufforderung)

1. Öffne die Windows-Eingabeaufforderung: Windows-Taste drücken, `cmd` eingeben, Enter.
2. Füge diese Zeile ein und drücke Enter. Hast du ECU Studio woanders installiert, passe den Ordner an.

   ```
   "%LOCALAPPDATA%\Programs\ECU-Studio-AI\_internal\python\python.exe" -m ecu_studio.tools.tester_report --assistent
   ```

3. Der Assistent stellt drei Fragen:
   1. **Pfad zur Originaldatei.** Tipp: Datei aus dem Explorer in das Fenster ziehen, dann steht der Pfad da.
   2. **Pfad zur Definition**, genauso.
   3. **Steuergerätelinie**, z. B. `Bosch MEVD17.2` oder `Siemens MSD80`. Gib nur Hersteller und Linie an. Software-, Teile- oder Fahrgestellnummern und Dateinamen lehnt der Assistent ab.
4. Die Messung dauert einige Sekunden bis Minuten.
5. Danach siehst du den **vollständigen Inhalt**, der gespeichert würde. Sonst nichts.
6. Tippe `ja`, dann wird der Bericht als `.json`-Datei gespeichert. Jede andere Antwort speichert nichts. Eine bestehende Datei wird nie überschrieben.

Mit Strg+C brichst du jederzeit ab. Dann wird nichts gespeichert.

## Was im Bericht steht und was nicht

| Enthalten | Nie enthalten |
|---|---|
| Zählwerte: Kennfelder der Definition, gefundene, exakt getroffene, Achsen, Funktionszuordnung | Firmware-Bytes, Inhalte der Definition |
| Programmversion, die eingegebene Steuergerätelinie, Art der Definition (A2L/XDF/CSV) | Kennfeld-, Achsen- oder Funktionsnamen |
| Laufzeit in ganzen Sekunden | Adressen, Dateinamen, Pfade, Dateigrößen, Hashes, Zeitstempel |

**Auch Zählwerte können wiedererkennbar sein.** Exakte Gesamtzahlen wie „1.158 Kennfelder in der Definition“ können zusammen mit Linie und Version auf einen bestimmten Softwarestand hindeuten und damit auf dich. Das gilt besonders, wenn nur wenige Personen Berichte abgeben. Deshalb sind alle Werte ab 100 standardmäßig **auf zwei Stellen gerundet** (1.158 → 1.200). Mit der Option `--exakt` entfällt die Rundung. Nutze sie nur, wenn du das höhere Risiko bewusst in Kauf nimmst.

## Weitergabe

Ob, wie und an wen du den Bericht weitergibst, entscheidest allein du. ECU Studio überträgt nichts automatisch. Das Werkzeug enthält keinen Netzwerkcode. Öffne die `.json`-Datei vor der Weitergabe in einem Texteditor und prüfe, dass dort genau das steht, was die Vorschau gezeigt hat.

## Was der Bericht aussagt und was nicht

- Der Bericht misst ECU Studio an **deiner** Definition. Das Werkzeug kennzeichnet ihn als eigene Messung eines Testers.
- Ein einzelner Bericht ist **keine unabhängige Validierung** von ECU Studio. Dafür braucht es mehrere, den Entwicklern unbekannte Dateien, Tester und Definitionen sowie eine vereinbarte Auswertung.
- Die Ergebnisse hängen von der Qualität der Definition ab. Fehlende oder falsche Einträge der Definition erscheinen als „nicht gefunden“ oder „Fehlerkennung“.

## Wenn etwas schiefgeht

- **„Linie: …“**: Die Steuergerätelinie enthält eine Nummer, einen Pfad oder Sonderzeichen. Gib nur Hersteller und Linie ein.
- **„Die Messung ist fehlgeschlagen (…)“**: Oft gehört die Definition nicht zur Datei. Angezeigt wird nur die Fehlerart, weil vollständige Fehlermeldungen Dateipfade enthalten können. Die Option `--details` zeigt die ganze Meldung, nur auf deinem Bildschirm. Gib sie nicht weiter.
- **„Die Zieldatei existiert bereits“**: Wähle einen anderen Dateinamen.

## Für Geübte (ohne Assistent)

```
python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l --line "Bosch MEVD17.2"
python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l --line "Bosch MEVD17.2" --export bericht.json --consent CODE
```

1. Der erste Aufruf zeigt nur die Vorschau und einen Zustimmungscode.
2. Der zweite Aufruf speichert nur, wenn der Code zu genau diesem Inhalt passt.
