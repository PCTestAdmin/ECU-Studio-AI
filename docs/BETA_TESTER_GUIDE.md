# Beta tester guide: local test report

*German version: [BETA_TESTER_ANLEITUNG.md](BETA_TESTER_ANLEITUNG.md).*

This guide is for people who want to measure how well ECU Studio detects tables in **their own** ECU file. They need no programming knowledge. The measurement runs completely on your computer. Nothing is sent anywhere.

## What you need

- A test build of ECU Studio that contains the tester report (not yet included in 1.21.0-rc1; you get the test build from the developers).
- An original read of your ECU (`.bin`) that you may lawfully use.
- The definition that belongs to **exactly this** file: A2L, XDF or CSV. If the definition belongs to a different software version, the result is meaningless.

Use only files you are allowed to use. Do not pass on firmware or definitions. The report contains neither.

## How it works (guided mode)

1. Open the Windows command prompt: press the Windows key, type `cmd` and press Enter.
2. Paste this line and press Enter. If you installed ECU Studio somewhere else, adjust the folder.

   ```
   "%LOCALAPPDATA%\Programs\ECU-Studio-AI\_internal\python\python.exe" -m ecu_studio.tools.tester_report --assistent
   ```

3. The assistant asks three questions:
   1. **Path to the original file.** Tip: drag the file from Explorer into the window; this inserts the path.
   2. **Path to the definition**, the same way.
   3. **ECU line**, for example `Bosch MEVD17.2` or `Siemens MSD80`. Give manufacturer and line only. Do not enter a software number, part number, VIN or file name: the assistant refuses them.
4. The measurement takes a few seconds to several minutes.
5. You then see the **complete content** that would be saved. Nothing else is in it.
6. Type `ja` ("yes") and the report is saved as a `.json` file. Any other answer saves nothing. An existing file is never overwritten.

Press Ctrl+C at any time to cancel. Nothing is saved then.

## What the report contains and what it does not

| Contained | Never contained |
|---|---|
| Counts: tables in the definition, tables found, exact hits, axes, function identification | Firmware bytes, definition contents |
| Program version, the ECU line you typed, type of definition (A2L/XDF/CSV) | Table, axis or function names |
| Run time in whole seconds | Addresses, file names, paths, file sizes, hashes, time stamps |

**Counts can still be recognisable.** Exact totals, such as "1,158 tables in the definition", together with the ECU line and version can point to one particular software version, and through it to you. This is especially true when only a few people send reports. That is why all values from 100 upwards are **rounded to two significant digits** by default (1,158 → 1,200). The option `--exakt` turns off rounding. Use it only if you accept the higher risk.

## Passing on the report

Whether, how and to whom you pass on the report is your decision. ECU Studio transmits nothing automatically. The tool contains no network code. Before passing it on, open the `.json` file in a text editor and check that it shows exactly what the preview showed.

## What the report means and what it does not

- The report measures ECU Studio against **your** definition. The tool marks it as a tester's own measurement.
- A single report is **not an independent validation** of ECU Studio. Independent validation needs several files, testers and definitions that the developers do not know, plus an agreed evaluation.
- The results depend on the quality of the definition. Missing or wrong entries in the definition appear as "misses" or "false detections".

## If something goes wrong

- **"Linie: ..."**: the ECU line contains a number, path or special character. Enter only manufacturer and line.
- **"Die Messung ist fehlgeschlagen (...)"** ("the measurement failed"): often the definition does not belong to the file. Only the error type is shown, because full error messages can contain file paths. The option `--details` shows the full message, on your screen only. Do not pass that on.
- **"Die Zieldatei existiert bereits"** ("the target file already exists"): choose another file name.

## For experienced users (without the assistant)

```
python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l --line "Bosch MEVD17.2"
python -m ecu_studio.tools.tester_report ORIGINAL.bin DEFINITION.a2l --line "Bosch MEVD17.2" --export report.json --consent CODE
```

1. The first call only shows the preview and a consent code.
2. The second call saves only if the code matches exactly this content.
