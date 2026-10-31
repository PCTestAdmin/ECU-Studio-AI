# Firmware-Schutz: Firmware und private Referenzen bleiben lokal

Stand: 31.10.2026. ECU Studio AI ist Open Source, die Firmware seiner Nutzer nicht. Diese Seite beschreibt, wie das
Repository verhindert, dass Firmware oder private Referenzdaten in einem Commit, Push oder Release landen, und was
trotzdem noch von Hand geprüft werden muss.

## 1. Was nie ins Repository darf

Firmware (`.bin`, `.ori`, `.mod`, `.frf`, `.sgo`, `.hex`, `.s19`, `.srec` …), Voll- und Teilabzüge, EEPROM- und
TCU-Dumps, private A2L-/DAMOS-/XDF-Dateien und Map-Packs, Projektdatenbanken mit Kundendaten und jeder Ausschnitt
daraus. Das gilt auch umbenannt, komprimiert, als Hex/Base64 kodiert oder in Tests eingebettet, und auch über Git
LFS, Release-Assets oder Workflow-Artefakte.

Öffentlich sind Quellcode, Tests mit **synthetischen** Daten, Dokumentation, leere Vorlagen und Benchmark-Summen
ohne private Inhalte (nur Zahlen und Hashes).

## 2. Lokale Ablage außerhalb des Repositorys

```text
D:/ECU-Studio-Local/          (frei wählbar)
  firmware/originals/  firmware/modified/  firmware/ecu/  firmware/tcu/
  references/a2l/  references/damos/  references/xdf/  references/mappacks/
  projects/  databases/  benchmarks/  private-reports/
```

Den Ordner einmal bekannt machen, damit der Schutz ihn kennt (mehrere Ordner möglich):

```bat
git config --add ecu-studio.localdata "D:/ECU-Studio-Local"
:: oder für die Sitzung:  set ECU_STUDIO_LOCAL_DATA=D:\ECU-Studio-Local
```

Liegt ein so konfigurierter Ordner **innerhalb** des Repositorys, blockiert der Schutz jeden Commit und Push.
Der bisher genutzte `.qa/`-Ordner im Repository ist git-ignoriert und als privater Ordner gesperrt; für neue Daten
ist der Ordner außerhalb vorzuziehen.

## 3. Schutzschichten

| Schicht | Wo | Was sie leistet | Grenze |
|---|---|---|---|
| A. `.gitignore` | Repository | Firmware-, Definitions- und Datenbank-Endungen, lokale Datenordner | wirkt nicht bei `git add -f` und bereits getrackten Dateien |
| B. Pre-Commit | `.githooks/pre-commit` | prüft den **Index** (genau das, was committet wird), also auch selektives Staging über `git add -p` oder `update-index` | lässt sich mit `--no-verify` umgehen |
| C. Pre-Push | `.githooks/pre-push` | prüft **jeden ausgehenden Commit** (auch umbenannte Dateien und Commit-Nachrichten) und den vollständigen Baum der gepushten Spitze, also auch alte getrackte Dateien | lässt sich mit `--no-verify` umgehen |
| D. CI | `.github/workflows/tests.yml` | prüft den gepushten Baum erneut; Tests prüfen die Regeln | wirkt erst **nach** dem Push, also nur als Alarm |
| E. Manuelle Prüfung | vor jedem Push | siehe Abschnitt 6 | – |

Aktivieren (einmal je Klon):

```bat
python src\ecu_studio\tools\firmware_guard.py install
```

Das setzt `core.hooksPath=.githooks`. Die Hooks nutzen nur die Standardbibliothek und lesen Dateien aus Git, nicht
aus dem Arbeitsverzeichnis. Findet ein Hook kein lauffähiges Python, blockiert er.

## 4. Regeln

| Regel | blockiert |
|---|---|
| `extension` | Firmware-, Dump-, Definitions-, Archiv- und Datenbankendungen (`.bin .ori .mod .frf .sgo .hex .s19 .srec .a2l .dam .xdf .kp .ols .zip .7z .sqlite .db …`) |
| `private-dir` | Pfade mit Ordnern wie `.qa`, `firmware`, `references`, `private-reports`, `mappacks`, `damos`, `a2l`, `originals`, `dumps` |
| `size` | Dateien über 1 MiB |
| `binary` | jede Binärdatei ohne Bild-Endung; erkannte Steuergerätekennungen (EDC17, MED17, MSD80, Bosch-Nummern …) werden mit genannt. Fängt **umbenannte** Firmware ab. |
| `media` | PNG/GIF/JPG/ICO/WEBP, deren Inhalt kein Bild ist oder hinter dem Bildende Daten tragen |
| `payload` | in Text eingebettete Bytes: Hex-Folgen, `\x..`-Escapes, `0x..`-Listen und Hexdumps ab 1 KiB (auch über viele Zeilen oder Strings verteilt; 2 KiB in Summe je Datei), Base64-Blöcke ab 768 dekodierten Binärbytes, ab 8 Intel-HEX-/S-Record-Zeilen. Einzelne Hashwerte (32/40/64/128 Hex-Zeichen) zählen nicht. |
| `local-path` | Text, der den konfigurierten lokalen Datenordner nennt; lokaler Datenordner im Repository |

Meldungen nennen nur Pfad, Regel und Größe, nie Dateiinhalte.

**Öffentliche Ausnahmen** stehen in `.firmware-guard.json` unter `allow`, jeweils **Pfad + SHA-256 des Inhalts**:
die synthetischen Beispiele in `examples/` und die mitgelieferten GPL-XDFs der MS4x-Community. Eine Ausnahme gilt
nur für genau diese Bytes an genau diesem Pfad; jede Änderung oder Umbenennung wird wieder geprüft. Neue öffentliche
Dateien (z. B. ein neues synthetisches Beispiel) werden so freigegeben:

```bat
git add -f examples\neu\demo.bin
python src\ecu_studio\tools\firmware_guard.py allow examples\neu\demo.bin
git add .firmware-guard.json
```

Die Änderung an `.firmware-guard.json` ist im Diff sichtbar und gehört in die Prüfung vor dem Push.

## 5. Befehle

```bat
python src\ecu_studio\tools\firmware_guard.py staged                        :: Index prüfen
python src\ecu_studio\tools\firmware_guard.py push --range origin/main..HEAD :: ausgehende Commits prüfen
python src\ecu_studio\tools\firmware_guard.py tree HEAD                      :: alle getrackten Dateien
python src\ecu_studio\tools\firmware_guard.py history                        :: jeder erreichbare Blob aller Refs
```

## 6. Pflicht vor jedem Push

1. `git status` und `git log --stat origin/main..HEAD`: nur erwartete Dateien?
2. `git diff origin/main..HEAD` lesen, besonders Tests, JSON-Daten und `.firmware-guard.json`.
3. `firmware_guard.py push --range origin/main..HEAD` muss `OK` melden (der Pre-Push-Hook macht das zusätzlich).
4. Wenn sich nicht sicher ausschließen lässt, dass private Daten enthalten sind: **nicht pushen.**

## 7. Wenn der Schutz anschlägt

- **Beim Commit:** Datei aus dem Index nehmen (`git restore --staged PFAD`), Ursache klären.
- **Beim Push:** Die Daten stecken in einem Commit. **Kein Lösch-Commit**: der frühere Commit enthielte die Datei
  weiterhin und würde mit veröffentlicht. Die nicht veröffentlichten Commits neu aufbauen (Branch vor die Commits
  zurücksetzen und ohne die Datei neu committen), erneut prüfen und erst dann pushen.
- **Schon gepushte Daten** gelten als veröffentlicht. Dann sofort den Repository-Inhaber informieren; eine
  Bereinigung der Historie ist ein eigener, ausdrücklich freizugebender Schritt.

## 8. Restrisiken

Ein Scanner ist keine Garantie. Nicht erkannt werden insbesondere:

- verschlüsselte oder mit eigenen Verfahren kodierte Daten, Daten in Bildpixeln,
- kleine Fragmente unter den Schwellen (z. B. einzelne Kennfeldwerte als Zahlenlisten in Tests),
- Kennfeldwerte als Dezimalzahlen in JSON/CSV,
- private Definitionen, die als Text ohne Firmware-Endung abgelegt sind (z. B. eine XDF als `.txt` mit unauffälligem Inhalt),
- alles, was mit `--no-verify` oder ohne aktivierte Hooks committet und gepusht wird,
- Daten, die vor Einführung des Schutzes veröffentlicht wurden.

Die Historie wurde am 31.10.2026 vollständig geprüft (`history`): kein Firmware-Fund. Gemeldet wurden nur ältere
Versionen der mitgelieferten GPL-XDFs, eine früh entfernte Metadaten-Datenbank ohne Firmwarebytes und ein defektes
Test-GIF; sie stehen mit Begründung unter `reviewed_history` in `.firmware-guard.json`.
