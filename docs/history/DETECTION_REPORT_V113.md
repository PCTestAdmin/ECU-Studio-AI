# Erkennung und Prüfung 1.13

Softwaregebundene Definitionen ergänzen die generische Struktursuche. Das neue Preset-Modell sortiert deren Kandidaten vorsichtig, ohne allein anhand seines Werts Kandidaten zu entfernen. Der bisherige synthetische Strukturhinweis bleibt erhalten. Beide liefern keine Kennfeldnamen, Einheiten oder bestätigten Wahrscheinlichkeiten.

Neue Korrekturen: einsbasierte CATEGORYMEM-Zuordnung, mehrere MS43-Versionen mit festem Headerfeld und widerspruchsfreier .DAT-Kennung, MS42-Fenster 0x48000..0x50000, manifestgebundene Quellen und Regionen, RomRaider-Vererbung und exakte ID/Größe. Fließkommazahlen werden in Tabellen, Kurven, Qualitätsprüfung, ORI/MOD und Bearbeitungsvorschauen ohne Ganzzahlrundung dekodiert. Der allgemeine Rohdaten-Trace behält seine Ganzzahlformate.

Die private MS43-Datei blieb unverändert: SHA-256 76010474fe2e3a4896724b6d0244173e49464e7b38758ccc6dc1bcaa53650421. Die ursprüngliche Fehlerstelle wird weiterhin als ip_cur_igc_sp__n__maf bei 0x76503, 6×6 u8, mit 91,91921591 mA angezeigt. GUI-Tests prüfen den Austausch alter u32-Vorschläge, Erhalt manueller Definitionen und Wiederholung des Scans.

Ein separates öffentliches MS42-Abbild liefert 592 quellenbasierte Zuordnungen. Voll- und Teilabbild stimmen mit Adressverschiebung überein. SHA-256: 010d6bf17bcfe46a9f436ba8e11dff375466ee948aaaf10d43a1d8325757b2cc. [Unveränderliche Quelle](https://github.com/ms4x-net/ms42/blob/4b3f591ccb96399f06dd8bb13a2a9dcb9ca56c17/firmware/Siemens_MS42_0110C6_E46_M52TUB28_EU3_LHD.bin). Diese BIN liegt nur lokal zur Prüfung vor und ist kein Trainings- oder Lieferbestandteil.

Die öffentliche RomRaider-XML enthält 334 ROM-Definitionen. Drei synthetische Abbilder mit ROM-ID, in Größen 192/512/1024 KiB, prüfen das Format mit 167/157/158 importierbaren numerischen Tabellen. Das ist keine Prüfung echter Denso-Firmwaredaten. Die externe XML wird weder weiterverteilt noch trainiert. Details: ROMRAIDER_FORMAT_AUDIT_V113.json. Gezielte Tests prüfen falsche IDs, Größen, Adressen, Formeln, nichtendliche Werte, mehrdeutige Zuordnungen und zyklische Vererbung.

16 Standard-XDFs sind mit festgeschriebenen Git-Blob-Hashes unverändert enthalten. Für MS41 kommt die Vollabbild-Adresskopplung aus BASEOFFSET der Quelle; ein realer MS41-Nachweis fehlt. Fünf weitere MS43-Stände haben Identitäts- und Quellenintegritätstests, aber keine eigenen realen BIN-Regressionen. Für Bosch, Delphi und Continental werden keine automatischen Abdeckungsquoten behauptet.

Das neue JSON-Modell wurde aus offenen Presets trainiert und byteidentisch reproduziert. Trainings-, Validierungs- und Testquellgruppen überschneiden sich nicht; fast gleiche normalisierte Flächen werden entfernt. 320 Testbeispiele stammen aus acht Preset-Tabellen und sind keine 320 unabhängigen Steuergeräte. Erzeugte Negativbeispiele ersetzen keinen repräsentativen OEM-Code-Korpus. Vollständige Metriken und Einschränkungen: TRAINING_REPORT_V113.json.

Alle Community-Zuordnungen bleiben unverified. Keine Checksum-Korrektur, Flash-Freigabe oder universelle automatische ECU-Erkennung. Windows-Paket und Testergebnisse: QA_REPORT_V113.json. Laufzeit und Quellen werden ohne private BIN, VIN oder privaten Dateipfad ausgeliefert.
