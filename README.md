<div align="center">

<img src="docs/images/social-preview.png" alt="ECU Studio AI – Kennfelder finden, verstehen und nachvollziehbar bearbeiten" width="860">

<br>

[![Version](https://img.shields.io/github/v/release/PCTestAdmin/ECU-Studio-AI?label=Version&sort=semver&color=2f81f7)](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/PCTestAdmin/ECU-Studio-AI/total?label=Downloads&color=2f81f7)](https://github.com/PCTestAdmin/ECU-Studio-AI/releases)
[![Tests](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/workflows/tests.yml/badge.svg)](https://github.com/PCTestAdmin/ECU-Studio-AI/actions/workflows/tests.yml)
[![Lizenz: GPL-3.0](https://img.shields.io/badge/Lizenz-GPL--3.0-2f81f7)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)](#installation)

**Open-Source-Kalibrier-Workbench für Motor- und Getriebesteuergeräte.**<br>
Findet Kennfelder auch ohne Definition, zeigt nachvollziehbar, *warum* – und schützt vor Fehlern beim Bearbeiten.

<br>

[![Herunterladen](https://img.shields.io/badge/⬇_Herunterladen-Windows_x64-2ea043?style=for-the-badge)](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/latest)
&nbsp;
[![Fortschritt](https://img.shields.io/badge/📈_Fortschritt-je_Version-8957e5?style=for-the-badge)](docs/PROGRESS.md)
&nbsp;
[![Steuergeräte](https://img.shields.io/badge/🚗_Steuergeräte-gemessen-d29922?style=for-the-badge)](docs/ECU_SUPPORT.md)
&nbsp;
[![Roadmap](https://img.shields.io/badge/🗺️_Roadmap-fertig_%C2%B7_in_Arbeit_%C2%B7_geplant-0969da?style=for-the-badge)](ROADMAP.md)

<sub>Kein Python nötig · Updates mit Prüfsumme, Sicherung und Rollback · Originaldatei bleibt immer unverändert</sub>

</div>

---

## Inhalt

| | |
|---|---|
| [🚀 Installation](#installation) | Herunterladen, starten, aktualisieren |
| [✨ Funktionen](#funktionen) | Erkennen, prüfen, bearbeiten |
| [📊 Erkennungsgüte](#erkennung) | Gemessen gegen Hersteller-Definitionen |
| [🚗 Steuergeräte](#steuergeraete) | Was unterstützt und was gemessen ist |
| [⚙️ So funktioniert es](#funktionsweise) | Vom Byte zum Kennfeld |
| [🛡️ Sicherheit](#sicherheit) | Preflight, Prüfsummen, Grenzen |
| [🧑‍💻 Entwicklung](#entwicklung) | Quellcode, Tests, Releases |

---

<a id="installation"></a>

## 🚀 Installation

> **Drei Schritte, ohne Python oder Terminal.**

1. **[Neueste Version herunterladen](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/latest)**
   - `ECU-Studio-AI-<version>-windows-x64.zip` – **portabel**: entpacken, fertig
   - `ECU-Studio-AI-<version>-setup.exe` – **Installer**: Startmenü-Eintrag und Deinstallation, ohne Administratorrechte
2. `ECU-Studio-AI.exe` starten.
3. **Datei → BIN öffnen …** – zum Ausprobieren liegt unter [`examples/demo`](examples/README.md) eine synthetische Demo-Datei.

<details>
<summary><b>⚠️ Windows meldet „Der Computer wurde durch Windows geschützt“?</b></summary>
<br>

ECU Studio AI ist noch **nicht code-signiert**, deshalb warnt Windows SmartScreen beim ersten Start.

- Im Fenster **„Weitere Informationen“** → **„Trotzdem ausführen“**, oder
- **vor dem Entpacken**: Rechtsklick auf die ZIP → **Eigenschaften** → **„Zulassen“** anhaken → OK.

Echtheit prüfen: Die SHA-256 der Datei (`Get-FileHash <datei>`) muss mit der `.sha256`-Datei des Releases
übereinstimmen; die Build-Herkunft belegt `gh attestation verify <datei> --repo PCTestAdmin/ECU-Studio-AI`.
</details>

<details>
<summary><b>🔄 Wie funktionieren die automatischen Updates?</b></summary>
<br>

| Schritt | Was passiert |
|---|---|
| Prüfen | Beim Start und höchstens einmal täglich über die GitHub-Releases-API – nur **stabile** Versionen. Abschaltbar unter **Einstellungen**. Ohne Internet passiert still nichts. |
| Fragen | Fenster mit Version und Änderungen: **Jetzt aktualisieren** · **Später erinnern** · **Diese Version überspringen**. |
| Laden | Nur von den Releases dieses Repositorys; SHA-256 gegen die veröffentlichte Prüfsumme **und** GitHubs eigene Angabe. |
| Installieren | Erst nach dem Schließen (ungespeicherte Arbeit wird abgefragt) durch einen separaten Updater: jede Datei geprüft, eigene Dateien übernommen, alte Version gesichert. |
| Absichern | Selbsttest der neuen Version – bei einem Fehler automatisch zurück zur alten. **Einstellungen → Vorherige Version wiederherstellen …** holt sie jederzeit zurück. |

Projekte (`%USERPROFILE%\.ecu_studio_ai`) und Einstellungen liegen außerhalb des Programmordners und bleiben
unberührt. Protokoll: `%LOCALAPPDATA%\ECUStudioAI\updates\update.log`. Vor jeder Veröffentlichung wird genau dieser
Weg automatisch auf Windows Server 2022 und 2025 durchgespielt.
</details>

---

<a id="funktionen"></a>

## ✨ Funktionen

<table>
<tr>
<td width="33%" valign="top">

### 🔍 Erkennen
- **Kennfelder ohne Definition** – über Programmcode-Verweise, Datensätze mit Achsen und Datenmuster
- **Achsen** erkannt und zugeordnet, Skalierungsvorschläge
- **Gemessene Konfidenz** je Fund: *gesichert*, *wahrscheinlich* oder *Vermutung*
- **Dubletten** und Überwachungskopien markiert
- Funktionsgraph und Signal-Tracing

</td>
<td width="33%" valign="top">

### 🛡️ Prüfen
- **Flash-Preflight** für jede geänderte Byteposition
- **Zwillingskennfelder** auf gleiche Änderung geprüft
- **Checksummen** mit geprüften Profilen, Korrektur mit Byte-Vorschau, Suche unbekannter Layouts
- Software-Kennung (EPK) gegen die Definition
- Drei getrennte Stufen: Prüfsummen · Preflight · Flashvalidierung

</td>
<td width="33%" valign="top">

### ✏️ Bearbeiten
- **Definitionen**: XDF, A2L/DAMOS, RomRaider, CSV, HEX/S19
- Tabelle, Heatmap, 2D, **3D**, Hex-Editor, Speicheratlas
- **ORI/MOD-Vergleich** zellgenau
- Undo/Redo, Projektstände, Batch mit Vorschau
- Original bleibt **immer** unverändert

</td>
</tr>
</table>

<div align="center">

| Kennfeldtabelle (hell) | Heatmap (dunkel) | 3D-Ansicht (dunkel) |
|:---:|:---:|:---:|
| <img src="docs/images/light-table.png" width="280"> | <img src="docs/images/dark-heatmap.png" width="280"> | <img src="docs/images/dark-3d.png" width="280"> |

<sub>Screenshots mit der synthetischen Demo-Datei <code>examples/demo/demo_multi_map.bin</code>.</sub>

</div>

---

<a id="erkennung"></a>

## 📊 Erkennungsgüte

Blind gemessen: Die Definition des Herstellers dient **nur als Referenz**, nie als Eingabe. Die Präzision ist nur dort
angegeben, wo die Referenz vollständig ist. **Test** = Daten, die nie zum Einstellen der Erkennung verwendet wurden.

| Steuergerät | Referenz | exakt erkannte Kennfelder | Präzision |
|---|---|---:|---:|
| Bosch EDC17CP09 | Hersteller-A2L | **463** von 703 | **85 %** |
| Siemens MSD85 · *Test* | Hersteller-A2L | **279** von 1026 | **81 %** |
| Siemens MSD80 · *Test* (6 Stände) | Hersteller-A2L | **217–224** von 864 | **81–82 %** |
| Bosch EDC16C35 | Hersteller-A2L | **283** von 387 | **81 %** |
| Bosch EDC16C31 | Hersteller-A2L | **272** von 364 | **82 %** |
| Siemens MS43 | Community-XDF | **197** von 379 | **79 %** |
| BMW ME9.2.1 | Hersteller-A2L | **170** von 460 | **72 %** |
| Denso SH-2 (Subaru) | RomRaider (Auswahl) | **147–178** | – |

Stand: nächste Version (Werte von 1.15.0 in [docs/PROGRESS.md](docs/PROGRESS.md)). Welche Steuergeräte validiert,
teilweise oder noch gar nicht gemessen sind, zeigt [docs/ECU_SUPPORT.md](docs/ECU_SUPPORT.md) und in der App
**Hilfe → Unterstützte Steuergeräte …**.

**Fehlalarme** auf Daten ohne Kennfelder (9 Zufallsdateien bis 2 MB, komprimiert, gelöschter Flash, Nullen): **0** Kandidaten.
Auf Programmcode ohne Kalibrierdaten (Windows-DLLs) entstehen Kandidaten, alle mit der Stufe *Vermutung*.

> 📈 **Wie sich die Erkennung von Version zu Version verbessert hat: [docs/PROGRESS.md](docs/PROGRESS.md)**<br>
> 🔬 Alle Messwerte je Variante: [docs/ECU_SUPPORT.md](docs/ECU_SUPPORT.md) · reproduzierbar mit `python -m ecu_studio.tools.benchmark_suite`

<details>
<summary><b>Trefferquote je Beweisart und Lernmodell</b></summary>
<br>

Anteil der Funde, die exakt an einem echten Objekt beginnen (gemessen auf MS43, MS42, Hyundai ×2, MSS54 und den
Hersteller-A2L von ME9, ME9.2.1, EDC17CP09, EDC16C35/C31; MSD80/85 bleiben als Testdaten außen vor):

| Beweisart | Anzahl | Trefferquote |
|---|---:|---:|
| Code-Verweis + zwei Achsen | 227 | 100 % |
| Code-Verweis + Achse (Kennlinie) | 159 | 99 % |
| Code-Verweis ohne Achsen | 35 | 97 % |
| Achse aus Kopf-Datensatz | 1383 | 88 % |
| Kopf-Datensatz (nx, ny, X, Y, Kennfeld) | 694 | 87 % |
| Achsen-Arrays mit Anzahl-Präfix (MS4x allein 97–100 %) | 2374 | 54 % |
| nur Datenmuster | 1321 | 22 % |

Für reine Datenmuster-Funde ordnet ein Lernmodell nach; geprüft jeweils auf einer beim Training ausgelassenen Familie
(Präzision bei 80 % Trefferquote): Hyundai SIM2K 14 → 34 %, BMW MSS54 7 → 32 %, alte 8-Bit-Motronic 5 → 35 %,
Siemens MS4x 29 → 50 %. Details: [docs/MODELLKARTE.md](docs/MODELLKARTE.md).
</details>

---

<a id="steuergeraete"></a>

## 🚗 Steuergeräte

| Familie | Prozessor | Code-Verweise | Achsen | Status |
|---|---|:---:|:---:|---|
| Siemens MS43 (BMW) | C167 | ✅ | ✅ | ✅ validiert · Standard-XDFs inklusive |
| Siemens MS41 / MS42 (BMW) | C167 | ✅ | ✅ | 🟡 gemessen, Erkennung gering (MS42: 22 von 213 exakt) |
| Bosch ME7 / ME7.5 (Volvo, VAG) | C167 | ✅ | ✅ | ✅ gemessen |
| Bosch EDC17CP09 (BMW) | TriCore | – | ✅ | ✅ gemessen · Hersteller-A2L |
| Siemens MSD80 / MSD85 (BMW) | PowerPC | – | ✅ | ✅ unabhängig gemessen · Hersteller-A2L |
| Bosch EDC16C31 / C35 (BMW) | PowerPC | – | ✅ | ✅ gemessen · Hersteller-A2L |
| BMW ME9 / ME9.2.1 | PowerPC | – | ✅ | ✅ validiert · Hersteller-A2L |
| Siemens MS45 | C167 | – | ✅ | 🟡 gemessen, Erkennung gering (30 von 472 exakt) |
| Denso SH-2 (Subaru) | SH-2 | ✅ | ✅ | ✅ gemessen |
| GM P01 | 68k | ✅ | – | ✅ gemessen |
| Bosch MED17.1.62 · MED9 | TriCore · PowerPC | – | ✅ | 🟡 nur Teil-Referenz |
| Bosch M4.4 · Motronic · Renault Fenix | 8051 · 68HC11 | 🟡 | – | ✅ gemessen |
| BMW MSS54 | CPU32 | – | ✅ | ✅ gemessen · vollständige XDF |
| Continental SIM2K (Hyundai) | TriCore | – | 🟡 | 🟡 gemessen, Erkennung unzureichend |
| Speeduino (Open Source) | AVR / ARM | – | – | 🟡 gemessen (14 Abstimmungen), ohne Definition schwach – `.ini` ist öffentlich |
| EDC17 (weitere) · MED17.5/17.7 · MG1 · MD1 · Simos · SID | – | – | – | ⚪ nicht validiert – keine rechtlich sicheren Referenzdaten öffentlich |

<sub>✅ gemessen · 🟡 teilweise · ⚪ noch keine Referenzdaten. Code-Verweise = Kennfeldadressen aus dem Programmcode.
Konkrete Softwarestände und alle Zahlen: <a href="docs/ECU_SUPPORT.md">docs/ECU_SUPPORT.md</a>.</sub>

---

<a id="funktionsweise"></a>

## ⚙️ So funktioniert es

```mermaid
flowchart LR
    BIN[BIN-Datei] --> P{Profil<br/>bekannt?}
    P -- ja --> W[Kalibrierfenster]
    P -- nein --> M[Code/Daten-<br/>Trennung]
    W --> E
    M --> E
    subgraph E[Beweise sammeln]
        C[Code-Verweise<br/>C16x · 68k · SH-2 · HC11 · 8051]
        H[Datensätze mit<br/>Anzahl und Achsen]
        A[Achsen-Arrays]
        D[Datenmuster]
    end
    E --> R[Lesarten<br/>abwägen]
    R --> K[Konfidenz aus<br/>gemessenen Quoten]
    K --> UI[Katalog · Graph<br/>Signal-Tracing]
```

Wo der Programmcode auf ein Kennfeld zeigt, stimmt der Start praktisch immer; wo nur Datenmuster sprechen, ist es eine
Vermutung – und wird auch so angezeigt. Alle Funde sind **Geometrie-Hypothesen**: Name, Einheit und Funktion kommen
nur aus einer passenden Definition oder deiner Prüfung, nie aus einer Vermutung.

---

<a id="sicherheit"></a>

## 🛡️ Sicherheit

> [!WARNING]
> **ECU Studio AI gibt keine Flashfreigabe.** Checksummen werden nur mit einem geprüften, an die Original-Firmware
> gebundenen Profil verifiziert – Signaturen und weitere Prüfungen des Steuergeräts bleiben ungeprüft. Geänderte
> Dateien vor dem Flashen mit einem geeigneten Werkzeug prüfen. Eingriffe können Typgenehmigung, Abgasverhalten und
> Versicherungsschutz betreffen.

- **Original bleibt unverändert** – alle Änderungen liegen als nachvollziehbare Ebene darüber.
- **Keine Firmware im Repository** – Tests verhindern Programmdateien, Archive und Firmware außerhalb von `examples/`.
- **Fremddaten:** mitgelieferte MS4x-XDFs (MS4x Dev Team) und rusEFI-Presets unter GPL-3.0, Herkunft in den `NOTICE.txt`
  unter `src/ecu_studio/recognition/data/`.
- Sicherheitslücken bitte vertraulich melden: [SECURITY.md](SECURITY.md).

---

<a id="entwicklung"></a>

## 🧑‍💻 Entwicklung

```bat
start_windows.bat                         :: Umgebung anlegen und Oberfläche starten (Python 3.10–3.13)
python -m pytest -q                       :: alle Tests
build_exe_windows.bat                     :: Windows-Paket bauen (ZIP + Installer, mit Tests)
```

| | |
|---|---|
| 📚 [Dokumentation](docs/README.md) | Aufbau des Quellcodes, Werkzeuge, Benchmarks |
| 🚢 [Release-Ablauf](docs/RELEASE.md) | Version, CHANGELOG, Tag – Build, Update-Test und Veröffentlichung laufen automatisch |
| 🧪 [Beispiele](examples/README.md) | Synthetische Demo-Dateien und Vorlagen |
| 📝 [CHANGELOG](CHANGELOG.md) | Alle Änderungen |
| 🗺️ [Roadmap](ROADMAP.md) | Was fertig ist, was in Arbeit ist und was als Nächstes kommt |
| 🤝 [Mitmachen](CONTRIBUTING.md) | Besonders willkommen: **Messungen an weiteren Steuergeräten** – bitte **keine Original-Firmware** hochladen |

### 🗺️ Roadmap

<a href="ROADMAP.md"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/roadmap-dark.svg">
  <img alt="Roadmap: veröffentlicht, nächstes Update, in Arbeit, als Nächstes" src="docs/images/roadmap-light.svg" width="100%">
</picture></a>

**→ [Ganze Roadmap](ROADMAP.md)**

<div align="center">
<br>
<sub>ECU Studio AI · <a href="LICENSE">GPL-3.0</a> · Kalibrierwerkzeug ohne Herstellerbezug – kein Ersatz für eine fachliche Prüfung</sub>
</div>
