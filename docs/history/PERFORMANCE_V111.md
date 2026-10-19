# Performance-Nachweis 1.10 → 1.11

Windows 11, CPython 3.13.2 x64; NumPy/PySide6-Versionen in `requirements-lock-windows.txt`. Deterministische synthetische Zufallsbytes (Seed 20261017) plus eine bekannte Oberfläche. **Keine echten Firmware-Trefferraten.** Analysezeiten: Median aus drei vollständigen Läufen pro Größe; vollständige Einzelwerte in `baseline-performance.json` und `next-performance.json`.

| Datei (MiB) | v1.10 Analyse (s) | v1.11 Analyse (s) | v1.10 RAM (MiB) | v1.11 RAM (MiB) | v1.10 max. Qt-Intervall (ms) | v1.11 max. Qt-Intervall (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7,389 | 3,165 | 77,1 | 76,3 | 13,01 | 12,44 |
| 4 | 19,821 | 8,860 | 91,6 | 90,1 | 12,55 | 12,46 |
| 8 | 27,818 | 15,497 | 113,3 | 110,6 | 12,81 | 12,62 |
| 16 | 26,317 | 15,906 | 142,9 | 145,9 | 13,12 | 12,52 |

RAM ist das größte durch den Timer abgetastete Prozess-RSS über die Wiederholungen, kein exakt erfasster Allocator-Peak. Qt-Intervalle messen einen 10-ms-Ereignistimer während QThread-Analyse, keine Windows-Eingabelatenz oder Bildrate. OS-Dateicache war warm; andere Systemlast und Laufzeitschwankungen beeinflussen Zahlen. Lade-Mediane aus drei Reads der ersten Wiederholung (ms): v1.10 1,21 / 4,86 / 10,50 / 16,73; v1.11 1,02 / 3,63 / 6,75 / 13,63. Keine gezielte Ladezeit-/RAM-Verbesserung behauptet.

Die Scanner behalten ihre bisherigen Suchgrenzen: generisch u16 bis 8 MiB, zusätzliche Datentypen bis 2 MiB; bekannte Profile können Datenfenster einschränken. Eine 16-MiB-Analyse ist deshalb **keine Vollsuche aller Bytes**. Das erklärt auch, weshalb v1.10 bei 16 MiB nicht doppelt so lange wie bei 8 MiB benötigt. Zufallsinhalte und Speicher-/Cachezustand unterscheiden die Größenläufe.

Profiling eines synthetischen 1-MiB-Images zeigte die meiste CPU-Zeit in `discover_maps`, `scan_u8`, `scan_32` und `scan_s16`, besonders NumPy-Differenzen und Reduktionen. In 1.11 werden vorhandene notwendige Spannweiten-/Horizontalbedingungen vor aufwendigen vertikalen/statistischen Berechnungen ausgewertet. Keine zusätzliche Ablehnungsregel wurde eingeführt. Die serialisierte Ausgabe auf fünf synthetischen Fällen ist exakt gleich: `baseline-detections.json` / `next-detections.json` (Demo 2 Karten, Multi-Map 14, die übrigen 0). Das beweist Regressionserhalt auf diesem Korpus, nicht auf jeder echten Firmware.

Die separate Qt-Flächendekodierung stürzte in v1.10 wegen des fehlenden `FORMATS`-Imports ab. Der Benchmark erfasst diesen Fehler ausdrücklich statt eine Laufzeit zu erfinden. In 1.11 beträgt der erste gemessene Dekodierungsaufruf der 12/16-Bit-Testoberfläche etwa 0,06–0,10 ms; kein Vorher/Nachher-Faktor für einen zuvor defekten Pfad.

## Wiederholen

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\benchmark_compare.ps1
```

Das Skript verwendet das unveränderte Originalarchiv neben dem Projekt und denselben Benchmark-Harness für beide Quellstände. Der Harness wurde erst für diese Messung ergänzt und ist keine Änderung der archivierten Detektoren. Für nur den aktuellen Stand:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:OPENBLAS_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m ecu_studio.tools.benchmark_next --out next-performance.json --repeats 3
```

GUI-Darstellung wird zusätzlich in `qa-artifacts/source-gui/` und `qa-artifacts/exe-gui/` geprüft. Diese Smoke-Tests sind von der Qt-Heartbeat-Messung getrennt.
