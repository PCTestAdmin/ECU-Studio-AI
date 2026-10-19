# Diagnose und Umsetzung 1.12

## Reproduzierter Fehler

Der Screenshot wurde mit der vom Benutzer lokal bereitgestellten 512-KiB-MS43-Datei reproduziert. SHA-256: `76010474fe2e3a4896724b6d0244173e49464e7b38758ccc6dc1bcaa53650421`. Die Originaldatei wurde ausschließlich gelesen.

Bei `0x76520` interpretierte der Scanner jeweils vier Bytes als `u32` big endian. `A3 A3 A3 A3` wird arithmetisch korrekt zu 2.745.410.467; die Annahme eines 32-Bit-Kennfelds war falsch. Eine Änderung des Anzeigefaktors hätte diesen Fehler verdeckt.

Die passende öffentliche MS4X-Standard-XDF definiert an dieser Stelle `ip_cur_igc_sp__n__maf`: Beginn `0x76503`, Ende exklusiv `0x76527`, 6×6, u8, Formel `0.56392157*X`, Einheit mA, Drehzahl-/Lastachsen. Die Tabelle enthält in der Probe durchgehend Rohwert 163. Die alte Heuristik setzte mitten in dieser Tabelle an und umfasste mehrere folgende Tabellen. Ihre vorgegebenen Raster erkannten weder diese ungerade Startadresse noch ihre konstante Fläche als eigenständige Tabelle.

Zusätzlich ignorierte der XDF-Importer verknüpfte Achsen, sobald auch eine eingebettete Adresse vorhanden war. Solche alten Platzhalter stehen tatsächlich in der MS4X-XDF, etwa bei der VANOS-Tabelle ab `0x7652F`. Bei `embedinfo type="3"` hat nun das verknüpfte Objekt Vorrang. Dessen Datentyp, Adresse und Formel werden verwendet. Achseneinheiten und Kategorien bleiben erhalten.

## Öffentliche Editor-Dokumentation

[EVC beschreibt für WinOLS](https://www.evc.de/en/product/ols/software/) die Unterscheidung von Programm-/Datenbereichen, automatische Kennfeldsuche und eine räumliche Vorschau. Die interne proprietäre Suchformel ist dort nicht offengelegt. Die Umsetzung übernimmt dokumentierte Arbeitsprinzipien, keinen WinOLS-Code und keine behauptete identische Erkennungsleistung.

Die [MS4X-Dokumentation](https://www.ms4x.net/index.php?title=Siemens_MS43) beschreibt den MS43-Kalibrierbereich `0x70000–0x7FFFF`. Der [MS4X-Quellbestand](https://github.com/ms4x-net/ms43) beschreibt die Verwendung zur Software-/Dateigröße passender XDFs mit TunerPro. [Extended Load](https://www.ms4x.net/index.php?title=Siemens_MS43_Extended_Load_Limit) benötigt ausdrücklich eine eigene passende Definition; identische Softwarekennung reicht für diese Variante nicht aus.

Für die offline mitgelieferten **Standard**-Definitionen wurde deshalb ein fest gepinnter älterer Repository-Stand verwendet: [Commit 72feadb3…](https://github.com/ms4x-net/ms43/tree/72feadb3e965743fb1c16b36a79b14e98d0c684e/definitions). Der aktuelle Hauptzweig enthält Extended-Load-Dateien. Deren Lastskalierung wird nicht automatisch auf die Benutzerdatei angewendet. Autoren: MS4x Dev Team, GPL-3.0; Originaldateien unverändert und vollständig beigefügt.

## Implementierte Änderungen

| Bereich | Verhalten in 1.12 |
|---|---|
| Softwaregebundene Erkennung | Offline-XDFs für Standard-MS43 430069 in 64/512 KiB; Hashprüfung und verteiltes Achsenquorum |
| Tabellenabgrenzung | Adresse, Dimensionen, Datentyp, Speicherlayout und Formel aus vollständiger Definition; auch konstante 6×6-Flächen |
| XDF-Achsen | Verknüpfte Objekte schlagen alte eingebettete Adressen; skalierte Achswerte, Einheiten, Kategorien erhalten |
| Generische Suche | Zusätzlich Count-/Axis-Record-Hypothesen; unabhängige Dimensionen statt ausschließlich fester Raster |
| Breitenprüfung | Derselbe physische Bereich wird als u8/u16 gegengeprüft, bevor ein u16/u32-Vorschlag akzeptiert wird |
| Ergebnispriorität | Manuelle/geprüfte Definitionen bleiben erhalten, alte ungeprüfte Heuristik wird beim erneuten Scan ersetzt; benannte Quellalias-Ansichten bleiben erhalten |
| Zahlenanzeige | Unskalierte Ganzzahlen vollständig; Editierdarstellung mit Rundlaufpräzision statt acht signifikanter Stellen |
| Herkunft | XDF-Zuordnung als ungeprüft sichtbar, vollständiger Quellen-/Lizenzdialog, kein automatisches Training |

## Reale Stichprobe und Grenzen

Der neue Scan benötigt in dieser Umgebung rund 4,2 Sekunden und schlägt **403 zweidimensionale Tabellen sowie 453 Kennlinien** vor. Der alte Scanner lieferte 36 generische Bereiche, davon 16 u32. Nur einer der alten Vorschläge stimmt in Adresse, Dimensionen und Datentyp mit den neuen Quellzuordnungen überein.

Dies misst **Übereinstimmung mit Community-Definitionsdaten**, keine unabhängige Kennfeldpräzision oder Vollständigkeit. Die 856 Einträge sind keine 856 einzeln vom Hersteller oder Benutzer geprüften Kennfelder. Zwei definierte 2D-Tabellen ohne passende kontinuierliche Achsen werden nicht automatisch vorgeschlagen. Weitere Skalare und separate Achsobjekte sind beim vollständigen XDF-Import verfügbar. Andere Softwarestände/Steuergeräte erhalten durch diese Änderung keine erfundenen Kennfeldnamen. Die bestehenden Modelle wurden nicht auf diese Benutzerdatei trainiert.

Die Tests prüfen Breitenmehrdeutigkeit, echte große u32-Werte, ungewöhnliche Raster/ungerade Adressen, Rauschen, Abbruch, verknüpfte Achsen, Quellenintegrität, Marker ohne passende Achsen, Erhalt manueller/geprüfter Definitionen, Alias-Ansichten, Zahlenpräzision, automatischen Start beim BIN-Öffnen sowie Full-/Partial-Read an der tatsächlichen lokalen Probe. Quelloberfläche und verpackte Windows-EXE durchlaufen zusätzlich dieselbe reale Worker-/Rescan-Prüfung. Endgültige Zahlen und EXE-Hash stehen im QA-Bericht.

## Windows-Ausgabe

Der erste PyInstaller-Build wurde von Windows Defender beim Start blockiert (WinError 225) und wird nicht ausgeliefert. Das endgültige portable Paket enthält stattdessen unveränderte CPython-Binärdateien, offen liegende Anwendungsquellen, dynamisch geladene Qt-/NumPy-Bibliotheken und einen kleinen C#-Starter. Seine komplette Quelle liegt bei. Der Starter nutzt einen isolierten Python-Suchpfad und schreibt keine Bytecode-Caches neben die Anwendung. Damit kann das Programmverzeichnis schreibgeschützt bleiben.

Der hier aktive überwachte Ordnerzugriff blockiert Schreibzugriffe neu bereitgestellter Anwendungen in geschützte Dokumentenordner. Deshalb schreibt der Integrationstest seine Artefakte in ein normales temporäres Testverzeichnis; der Buildprozess kopiert die Prüfberichte anschließend ins Projekt. Das Paket wurde tatsächlich von seinem Windows-Starter aus ausgeführt. Keine Defender-Ausnahme oder geänderte Sicherheitsrichtlinie wurde verwendet. Die normale Betriebssystemprüfung von Speicherzielen bleibt bestehen. Der Starter ist nicht digital signiert; die mitgelieferten Python-EXE/DLLs sind unveränderte Laufzeitdateien mit ihren ursprünglichen Signaturen.
