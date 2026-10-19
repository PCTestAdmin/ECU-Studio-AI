# ECU Studio AI 1.12 – Kennfelderkennung korrigiert

Die 1.12 behebt die am MS43-Screenshot reproduzierte Fehlinterpretation benachbarter Bytes als 32-Bit-Kennfeld sowie falsche Rastergrenzen und fehlerhaft gelesene XDF-Achsen. Die Funktionen der 1.11 bleiben erhalten; deren übriger Entwicklungsstand steht in `README_V1_11.md` und `DELIVERY_REPORT_V111.md`.

## Start

`ECU-Studio-AI-1.12-windows-x64.zip` vollständig entpacken. `ECU-Studio-AI-1.12.exe` starten; den Ordner `_internal` daneben behalten. Python und Internet sind zum Betrieb nicht erforderlich.

Die MS43-BIN mit Softwarestand 430069 öffnen. Für 64- und 512-KiB-Dateien startet die Definitionsprüfung automatisch im Hintergrund. Beim erneuten Prüfen eines bestehenden Projekts **Strg+K** verwenden. Ungeprüfte alte Strukturvorschläge werden dabei ersetzt; manuell gepflegte und als geprüft markierte Definitionen behalten Vorrang. Die BIN-Änderungen bleiben unverändert. Den aktualisierten Kennfeldkatalog als Projekt speichern.

Das Windows-Paket verwendet einen kleinen C#-Starter mit einsehbarer Quelle und eine unveränderte, mitgelieferte CPython-Laufzeit. Programmcode, austauschbare Qt-DLLs, Paketlizenzen und XDFs liegen als normale Dateien unter `_internal`. Der zuvor lokal erzeugte PyInstaller-Build wurde von Windows Defender blockiert und ist nicht Bestandteil dieser Ausgabe. Es wurden keine Sicherheitsausnahmen eingerichtet. Die Ausgabe ist nicht digital signiert.

Die Katalogsuche findet beispielsweise `ip_cur_igc_sp__n__maf`. Dieser Eintrag beginnt bei `0x76503`, enthält 6×6 `u8`-Werte und verwendet die XDF-Formel `0.56392157*X` in mA. `0x76520` aus dem Screenshot liegt innerhalb dieser Tabelle. Rohwert 163 ergibt rund 91,9192 mA; vier `A3`-Bytes dürfen hier nicht zu 2.745.410.467 zusammengefasst werden.

## Erkennung

1. Vorhandene manuelle/CSV/XDF/A2L-Zuordnungen und exakte persönliche Referenzen haben Vorrang.
2. Für MS43 430069 liegen vollständige MS4X-**Standard**-XDFs v1.14 mit verknüpften Achsen offline bei. Softwarekennung, Dateigröße, mindestens zwölf verschiedene plausible Achsenpaare und verteilte Tabellenpositionen werden geprüft. Ein Softwaremarker allein reicht nicht.
3. Vorgeschlagen werden Tabellen und Kennlinien mit lesbaren, streng monotonen kontinuierlichen Achsen. Konstante Tabellen bleiben erkennbar. Separate Achsobjekte und Skalare stehen über den ausdrücklichen Import der mitgelieferten XDF zur Verfügung.
4. Ohne passenden Definitionsabgleich sucht die generische Heuristik zusätzlich nach Dimensionsheadern und zwei benachbarten Achsen. Unterstützte Hypothese: `nx,ny,X[nx],Y[ny],Z[ny,nx]`; 8-/16-Bit-Zähler und Achsen, gepackte Daten, auch ungerade Adressen. Andere ECU-Layouts sind damit nicht allgemein entschlüsselt.
5. Mehrbyte-Kandidaten werden gegen schmalere Interpretationen desselben Speicherbereichs geprüft. Bei mindestens gleich plausiblen Unterwörtern wird der breite Kandidat verworfen. Große echte 32-Bit-Werte bleiben unterstützt; es gibt keine pauschale Werteobergrenze als Reparatur.

Die Zuordnungen bleiben ausdrücklich **ungeprüft**. Achsenplausibilität und eine Community-XDF sind kein unabhängiger Nachweis aller Funktionen oder der Patchvariante. Extended Load und MS43X benötigen eigene passende Definitionen. Keine Trainingsfreigabe, Checksum-Korrektur oder Flashbarkeitszusage entsteht durch den Scan.

## Quellen und Prüfung

Die vollständigen unveränderten XDF-Quellen, Autorenhinweise, Lizenz und feste Git-Blob-Kennungen liegen unter `_internal/app/ecu_studio/recognition/data/definitions/`. In der Oberfläche: **Hilfe → Definitionsquellen und Lizenzen**.

`DETECTION_REPORT_V112.md` erläutert Diagnose, öffentliche Editor-Dokumentation und Umsetzung. `REAL_MS43_AUDIT_V112.json` dokumentiert die lokale reale Stichprobe ohne Dateinamen/VIN oder Firmwarekopie. `QA_REPORT_V112.json` enthält die abschließenden Testergebnisse und den geprüften EXE-Hash.

Aus dem Quellpaket: `build_release.ps1`. Optional lässt sich eine private lokale MS43-Regressionsdatei über `ECU_STUDIO_MS43_REGRESSION_BIN` einbinden. Ohne vorhandene lokale Probe werden die betreffenden Realdatentests übersprungen. Keine private Firmware wird mitgeliefert oder hochgeladen.
