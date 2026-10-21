<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/roadmap-dark.svg">
  <img alt="ECU Studio AI Roadmap: veröffentlicht, nächstes Update, in Arbeit, als Nächstes" src="docs/images/roadmap-light.svg" width="100%">
</picture>

<br><br>

[![Aktuelle Version](https://img.shields.io/github/v/release/PCTestAdmin/ECU-Studio-AI?label=aktuelle%20Version&style=for-the-badge&color=1a7f37)](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/latest)
&nbsp;
[![Änderungen](https://img.shields.io/badge/📝_Alle_Änderungen-CHANGELOG-0969da?style=for-the-badge)](CHANGELOG.md)
&nbsp;
[![Steuergeräte](https://img.shields.io/badge/🚗_Getestete_Steuergeräte-Übersicht-bf8700?style=for-the-badge)](docs/ECU_SUPPORT.md)

</div>

<br>

## ![Nächstes Update](https://img.shields.io/badge/🚀_NÄCHSTES_UPDATE-fertig_·_kommt_bald-0969da?style=for-the-badge)

Bereits entwickelt und getestet – erscheint mit der nächsten Version.

| | Neu | Was du davon hast |
|:--:|---|---|
| 🎯 | **Doppelt so viele Treffer** | Deutlich mehr Kennfelder werden exakt erkannt – bei weniger Fehlfunden |
| 📈 | **Kennlinien** | Fast doppelt so viele Kennlinien und Achsen |
| ⚡ | **2–4× schneller** | Große Dateien in ~10 statt ~33 Sekunden – alle CPU-Kerne arbeiten mit |
| 🏷️ | **Steuergerät erkannt** | Nach dem Öffnen: welche Familie, welche Software, ob sie getestet ist |
| 🔁 | **Namen übernehmen** | Kennfeldnamen aus einem verwandten Softwarestand mit Definition |
| 🧮 | **Prüfsummen ME7 · MED9 · ME9** | Prüfen und korrigieren – nur wenn das Verfahren am Original bewiesen ist |
| 🔍 | **ORI/MOD-Vergleich** | Differenz-Heatmap und Liste aller Änderungen außerhalb bekannter Kennfelder |

<br>

## ![In Arbeit](https://img.shields.io/badge/🔨_IN_ARBEIT-läuft_gerade-bf8700?style=for-the-badge)

| | Thema | Stand |
|:--:|---|---|
| 🔐 | **Signierte Updates** | Eingebaut – aktiv, sobald der Schlüssel eingerichtet ist ([Anleitung](docs/RELEASE.md)) |
| 🧮 | **Prüfsummen EDC16 · EDC17** | Bekannte Verfahren passen nicht – weitere werden untersucht |

<br>

## ![Als Nächstes](https://img.shields.io/badge/📋_ALS_NÄCHSTES-geplant-8250df?style=for-the-badge)

| | Thema | Warum |
|:--:|---|---|
| 🧩 | **TunerStudio-Abstimmungen öffnen** | Speeduino, rusEFI, MegaSquirt – die Definition ist dort öffentlich |
| 🧠 | **Kennfelder aus dem Programmcode** | Größter Hebel für EDC17 und MED17 (TriCore, PowerPC) |
| 🔗 | **Gruppenkennfelder** | Viele Bosch-Kennfelder teilen sich ihre Achsen |
| 🌍 | **Englische Oberfläche** | Für Nutzer außerhalb des deutschsprachigen Raums |
| ✍️ | **Code-Signatur** | Keine SmartScreen-Warnung mehr (braucht ein Zertifikat) |

<br>

## ![Wartet auf Testdaten](https://img.shields.io/badge/📦_WARTET_AUF_TESTDATEN-ungetestet-6e7781?style=for-the-badge)

Die App öffnet und durchsucht diese Steuergeräte – ihre Erkennungsgüte ist aber **noch nicht mit echten Daten
gemessen**. Rechtlich sichere Testdateien gibt es dafür öffentlich nicht.

> **Bosch** MD1 · MG1 · MED17.5 · MED17.7 · EDC17 (außer CP09)<br>
> **Continental** Simos · SID<br>
> **Siemens** MSD81 · MSV70 · MSV80

💡 **Du kannst helfen:** Hast du eine Originaldatei **und** die passende A2L, die du nutzen darfst? Ein einziger Befehl
misst sie und zeigt das Ergebnis – [so geht's](docs/ECU_SUPPORT.md#was-für-die-offenen-varianten-gebraucht-wird).
Bitte keine Firmware hochladen.

<br>

<details>
<summary><b>✅ Bereits veröffentlicht</b></summary>
<br>

**1.15.0** · 21.10.2026
- Kennfeldsuche ohne Raster, mit Code-Verweisen für ältere Prozessoren
- A2L mit gespeicherten Achsen, Prüfung der Software-Kennung (EPK)
- Messung gegen Hersteller-Definitionen
- Flash-Vorabprüfung, Prüfsummen-Suche und -Korrektur mit Vorschau
- Windows-Paket ohne Python, Installer, automatische Updates mit Rücksicherung

**1.14 und früher**
- Editor mit Hex-, Tabellen- und 3D-Ansicht, Versionsstände
- XDF-, A2L-, RomRaider- und CSV-Import
- Projekte mit Schutz der Originaldatei

</details>

<details>
<summary><b>🚫 Bewusst nicht geplant</b></summary>
<br>

- **Automatische Leistungssteigerung** (Stage 1) – braucht fachliches Urteil am Fahrzeug
- **Flashfreigabe** – die App ersetzt keine Prüfung mit einem geeigneten Werkzeug
- **Umgehen von Schutzfunktionen** (Wegfahrsperre, Abgas, Plausibilitätsprüfungen)
- **Zerlegen kommerzieller Programme** wie WinOLS – Vergleiche nur von außen
- **Firmware im Repository** – Originaldateien bleiben bei dir

</details>

<div align="center">
<br>
<sub>Termine gibt es bewusst nicht: Ein Punkt gilt erst als fertig, wenn er an echten Daten gemessen ist.</sub><br>
<sub><a href="README.md">← README</a> · <a href="CHANGELOG.md">CHANGELOG</a> · <a href="docs/PROGRESS.md">Fortschritt</a> · <a href="docs/ECU_SUPPORT.md">Steuergeräte</a> · <a href="CONTRIBUTING.md">Mitmachen</a></sub>
</div>
