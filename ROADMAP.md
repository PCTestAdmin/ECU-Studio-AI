<div align="center">

# 🗺️ Roadmap

**Was ist fertig? Woran wird gearbeitet? Was kommt als Nächstes?**

[![Stabil](https://img.shields.io/github/v/release/PCTestAdmin/ECU-Studio-AI?label=aktuelle%20Version&style=flat-square&color=2ea043)](https://github.com/PCTestAdmin/ECU-Studio-AI/releases/latest)

</div>

| ✅ Veröffentlicht | 🚀 Fertig, kommt mit dem nächsten Update | 🔨 In Arbeit | 📋 Als Nächstes |
|---|---|---|---|
| Kennfeldsuche ohne Definition | Deutlich mehr erkannte Kennfelder | Signierte Updates aktivieren | TunerStudio-Abstimmungen öffnen |
| A2L-, XDF-, RomRaider-Import | Kennlinien werden erkannt | Prüfsummen für EDC16 / EDC17 | Kennfelder direkt aus dem Programmcode |
| Prüfsummen mit Vorschau | 2–4× schneller (mehrere CPU-Kerne) | | Gruppenkennfelder (gemeinsame Achsen) |
| Windows-Installer + Auto-Update | Steuergerät wird erkannt + Status angezeigt | | Englische Oberfläche |
| | Namen aus Schwester-Softwareständen | | |
| | Prüfsummen ME7 / MED9 / ME9 | | |
| | ORI/MOD: Heatmap + unbekannte Änderungen | | |

<sub>Alle Messwerte stehen im [CHANGELOG](CHANGELOG.md) und unter [Steuergeräte](docs/ECU_SUPPORT.md). Termine gibt es bewusst nicht.</sub>

---

## 🚀 Fertig – kommt mit dem nächsten Update

| | Was | Was du davon hast |
|:---:|---|---|
| 🎯 | **Genauere Kennfeldsuche** | Rund doppelt so viele Kennfelder exakt erkannt, weniger Fehlfunde |
| 📈 | **Kennlinien (1D)** | Fast doppelt so viele Kennlinien und Achsen gefunden |
| ⚡ | **Schneller** | Große Dateien in ~10 statt ~33 Sekunden |
| 🏷️ | **Steuergerät erkennen** | Hinweisbalken zeigt Familie, Software und ob das Gerät getestet ist |
| 🔁 | **Namen übernehmen** | Kennfeldnamen aus einem verwandten Softwarestand mit Definition übertragen |
| 🧮 | **Prüfsummen ME7 / MED9 / ME9** | Prüfen und korrigieren – nur wenn das Verfahren am Original bewiesen ist |
| 🔍 | **ORI/MOD-Vergleich** | Differenz-Heatmap und Liste der Änderungen außerhalb bekannter Kennfelder |
| 🧭 | **Unterstützte Steuergeräte** | Übersicht in der App: *Hilfe → Unterstützte Steuergeräte* |

## 🔨 In Arbeit

- **Signierte Updates** – eingebaut; aktiv, sobald der Signaturschlüssel eingerichtet ist ([Anleitung](docs/RELEASE.md))
- **Prüfsummen EDC16 / EDC17** – bekannte Verfahren passen nicht, weitere werden untersucht

## 📋 Als Nächstes

- **TunerStudio-Abstimmungen öffnen** (Speeduino, rusEFI, MegaSquirt) – die Definition ist dort öffentlich
- **Kennfelder aus dem Programmcode** finden (TriCore, PowerPC) – größter Hebel für EDC17 und MED17
- **Gruppenkennfelder** mit gemeinsamen Achsen erkennen
- **Englische Oberfläche**
- **Code-Signatur** der Windows-Dateien (entfernt die SmartScreen-Warnung, braucht ein Zertifikat)

## 📦 Wartet auf Testdaten

Diese Steuergeräte funktionieren in der App, sind aber **noch nicht mit echten Daten geprüft** – es gibt öffentlich
keine rechtlich sicheren Testdateien:

**Bosch** MD1 · MG1 · MED17.5 / 17.7 · EDC17 (außer CP09) &nbsp;·&nbsp; **Continental** Simos · SID &nbsp;·&nbsp; **Siemens** MSD81 · MSV70 / 80

> 💡 Du hast eine Originaldatei **und** die passende A2L, die du nutzen darfst? Ein Befehl misst sie – siehe
> [Steuergeräte → Selbst messen](docs/ECU_SUPPORT.md#was-für-die-offenen-varianten-gebraucht-wird). Bitte keine Firmware hochladen.

---

<details>
<summary><b>✅ Bereits veröffentlicht</b></summary>
<br>

**1.15.0** (21.10.2026)
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
<sub><a href="README.md">← README</a> · <a href="CHANGELOG.md">CHANGELOG</a> · <a href="docs/PROGRESS.md">Fortschritt</a> · <a href="docs/ECU_SUPPORT.md">Steuergeräte</a> · <a href="CONTRIBUTING.md">Mitmachen</a></sub>
</div>
