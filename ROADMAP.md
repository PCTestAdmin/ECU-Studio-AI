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

## ![Neu in 1.16.0](https://img.shields.io/badge/🎉_NEU_IN_1.16.0-veröffentlicht_22.10.2026-1a7f37?style=for-the-badge)

[Jetzt herunterladen](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/latest) – installierte Versionen bieten das Update automatisch an.
Die Clips sind echte Aufnahmen der App
mit einer synthetischen Vorführdatei (keine Herstellerdaten).

<table>
<tr><th align="left">Neu</th><th>Version</th></tr>
<tr><td>

**Doppelt so viele Treffer** – Ein Klick auf <i>Scan</i>: Die Suche findet Kennfelder über ihre Achsen im Kopf, jede Fundstelle bekommt eine gemessene Konfidenz. Anklicken zeigt sofort die Heatmap.<br><img src="docs/clips/scan.gif" width="720" alt="Doppelt so viele Treffer">

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Konfidenz-Filter** – Nur gesicherte, nur wahrscheinliche oder nur geprüfte Kennfelder anzeigen – die Prozentwerte sind auf echten Referenzdaten gemessen.<br><img src="docs/clips/filter.gif" width="720" alt="Konfidenz-Filter">

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**ORI/MOD-Vergleich** – Zweite Datei wählen: Liste aller betroffenen Kennfelder und eine Differenz-Heatmap je Zelle (rot = höher, blau = niedriger).<br><img src="docs/clips/compare.gif" width="720" alt="ORI/MOD-Vergleich">

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Unterstützte Steuergeräte** – Für jede Familie ehrlich angezeigt: validiert, teilweise, experimentell oder nicht validiert – mit Messwerten.<br><img src="docs/clips/support.gif" width="720" alt="Unterstützte Steuergeräte">

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Englische Oberfläche** – <i>Einstellungen → Sprache / Language</i>. Standard ist die Systemsprache, Projekte bleiben sprachunabhängig.<br><img src="docs/clips/english.gif" width="720" alt="Englische Oberfläche">

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**2–4× schneller** – Alle CPU-Kerne arbeiten mit – große Dateien in ~10 statt ~33 Sekunden.

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Kennlinien** – Fast doppelt so viele Kennlinien und Achsen werden erkannt.

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Steuergerät erkannt** – Nach dem Öffnen: Familie, Softwarestand und ob sie getestet ist.

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Namen übernehmen** – Kennfeldnamen aus einem verwandten Softwarestand mit Definition übertragen.

</td><td align="center"><b>1.16.0</b></td></tr>
<tr><td>

**Prüfsummen ME7 · MED9 · ME9** – Prüfen und korrigieren – nur wenn das Verfahren am Original bewiesen ist.

</td><td align="center"><b>1.16.0</b></td></tr>
</table>

<br>

## ![In Arbeit](https://img.shields.io/badge/🔨_IN_ARBEIT-läuft_gerade-bf8700?style=for-the-badge)

| | Thema | Stand |
|:--:|---|---|
| 🔐 | **Signierte Updates** | Eingebaut – aktiv, sobald der Schlüssel eingerichtet ist ([Anleitung](docs/RELEASE.md)) |
| 🧮 | **Prüfsummen EDC16 · EDC17** | Rechnerische Prüfung eingebaut; OEM-Nachweise für sichere Korrektur fehlen noch |

<br>

## ![Als Nächstes](https://img.shields.io/badge/📋_ALS_NÄCHSTES-geplant-8250df?style=for-the-badge)

| | Thema | Warum |
|:--:|---|---|
| 🧩 | **TunerStudio-Abstimmungen öffnen** | Speeduino, rusEFI, MegaSquirt – die Definition ist dort öffentlich |
| 🧠 | **Kennfelder aus dem Programmcode** | Größter Hebel für EDC17 und MED17 (TriCore, PowerPC) |
| 🔗 | **Gruppenkennfelder** | Viele Bosch-Kennfelder teilen sich ihre Achsen |
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
<summary><b>✅ Frühere Versionen</b></summary>
<br>

**1.16.2** · 22.10.2026 – EDC16/EDC17-Prüfung, vollständige Struktur-Sperre und kryptografisch abgesicherte OEM-Nachweise

**1.16.1** · 22.10.2026 – Update aus der App repariert (einmal von Hand installieren), Update-Suche bei jedem Start

**1.15.0** · 21.10.2026
- Kennfeldsuche ohne Raster, mit Code-Verweisen für ältere Prozessoren
- A2L mit gespeicherten Achsen, Prüfung der Software-Kennung (EPK)
- Messung gegen Hersteller-Definitionen
- Flash-Vorabprüfung, Prüfsummen-Suche und -Korrektur mit Vorschau
- Windows-Paket ohne Python, Installer, automatische Updates mit Rücksicherung

**1.10.0** · 16.10.2026 – 3D-Ansicht mit Drehen, Neigen und ORI/MOD-Drahtgitter

<img src="docs/clips/view3d.gif" width="720" alt="3D-Ansicht">

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
