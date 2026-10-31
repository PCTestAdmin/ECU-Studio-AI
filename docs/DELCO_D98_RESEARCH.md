# Delco „D98“: Recherche nach Firmware und Definitionen (30.10.2026)

**Ergebnis:** Es wurde **kein rechtmäßig nutzbares Delco-D98-Firmwareabbild** gefunden, und erst recht kein Paar aus
BIN und passender Definition. Es gibt deshalb **keine Erkennungsmetrik** für D98. Dieser Bericht hält fest, was
„D98“ ist, welche Quellen geprüft wurden und welche Daten für eine Messung fehlen.

## 1. Was „D98“ bezeichnet

| Aussage | Beleg | Belegqualität |
|---|---|---|
| „D98xxx“ ist die **D-Nummer (Kalibrierkennung)** im Kennungsblock von **Delphi/Delco Multec S**, Offset 0x3026 (6 ASCII-Zeichen), Beispiel „D98003“. Es ist keine eigene Steuergerätefamilie. | openremap-core, `openremap/core/manufacturers/delphi/multec_s/patterns.py` ([Commit `6c6ba85`](https://github.com/v-arapidis/openremap-core/tree/6c6ba8526b9f8040916b3a617035a085eabfccab), MIT, abgerufen 30.10.2026) | Strukturbeschreibung aus einem Open-Source-Extractor; an keiner echten Datei selbst geprüft |
| Multec S: genau 131 072 Byte, **Motorola HC12/HCS12**, zwei gespiegelte 64-KiB-Bänke, Boot-Block 0x0000–0x1FFF gelöscht (0xFF), HC12-Pointer-Tabellen ab 0x2000 (`00 00 7E`), Kennungsblock bei 0x3000 (Spiegel 0x13000) mit SW-Nummer (0x3009), Sendercode (0x3011), GM-Teilenummer (0x3015), Variante (0x3020), D-Nummer (0x3026), Motorkennung (0x302C) | ebenda | wie oben |
| Einsatz: Opel/Vauxhall 1996–2003, Astra G, Corsa B/C, Vectra B, Zafira A; Motoren u. a. X16SZR, X14XE, Z16SE, Z14XE | ebenda; Werkstatthandbuch-Seiten zu „Multec S“ (workshop-manuals.com, Vectra B) | Zweitquellen; Motor-Zuordnung plausibel |
| **X16XEL** (Vectra B / Astra F, 1.6 16V, 74 kW) läuft mit **Multec S** | [Vectra-B-Werkstatthandbuch, Abschnitt Multec S / X16XEL](https://workshop-manuals.com/vauxhall/vectra-b/j__engine_and_engine_aggregates/fuel_injection_systems/multec_s/component_locator/illustration_air_ducts_(x16xel_with_secondary_air_system)/sticky-ezoic.php?id=3767) | Handbuchauszug; kein Kalibrierstand genannt |
| **D98003** ↔ Opel-Steuergerät **16227049 MF**, Astra G 1.6, X16SZR | Zwei Händlerseiten ([ecu-espana.es](https://ecu-espana.es/opel/unidad-de-control-de-motor/multec-f-v2-gris-azul/opel-16227049mf-delco-d98003-104328.html), [ecuscb.com](https://ecuscb.com/fabricante/gm/ecu-gm-opel-delco-16227049mf-16227049-mf-16-227-049mf-16-227-049-mf-d98003/)); dieselben Werte als Beispiele im openremap-Kommentar | Händlerangaben, keine Herstellerdokumentation |
| D98005, D98007 | Keine belastbaren Treffer (nur unpassende bzw. Spam-Seiten) | – |

**Abgrenzung:** Delco **E98** ist eine andere GM-Steuergerätegeneration und hat mit der D-Nummer „D98…“ nichts
zu tun. „Multec“ (ohne S, z. B. Multec 700/MPFI) und „Multec HSFI-2.x“ sind andere Systeme. Ein Dateiname mit
„D98“ allein genügt nicht: Maßgeblich sind Größe, Layout und Kennungsblock.

## 2. Geprüfte Quellen

| Runde | Suche / Quelle | Ergebnis | Nutzbar? |
|---|---|---|---|
| 1 | Websuche EN „Delco D98 ECU Multec S Opel D98005 bin xdf“ (erweitert) | OldSkullTuning-Artikel zu Delco Multec mit TunerPro; Händler; Foren | Nein: keine Dateien mit Nutzungsrecht |
| 1 | Websuche DE „Multec S Steuergerät D98 Opel X16XEL Kennfeld TunerPro“ | Nur allgemeine TunerPro-/Holley-Treffer | Nein |
| 1 | GitHub-Repo-Suche: `multec`, `multec s`, `D98005`, `x16xel`, `delco ecu`, `opel ecu xdf`, `multec xdf`, `delco d98` | Kein Repository mit Multec-S-Firmware oder -Definition. Delco-Treffer betreffen Holden/68HC11 (VN–VY). | Nein |
| 1 | openremap-core (lokal geklont, MIT) | Multec-S-Extractor mit Layoutbeschreibung. `_dev/contrib/corpus/delphi-multec-s-128k.mimic` ist laut README des Projekts **synthetisch** („proves nothing about real ECUs“): 0xFF plus vier eingesetzte Kennungsfelder, **keine Kalibrierdaten**. | Nur als Strukturbeschreibung und synthetische Negativkontrolle |
| 2 | Websuche „"Multec S" xdf TunerPro X16SZR/Z16SE/X14XE“ (erweitert) | OldSkullTuning verkauft Delco-Multec-XDFs (40 €, laut AGB passwortgeschützt, „race use only“, ohne BIN) | Nein: kostenpflichtig, geschützt, ohne Firmware |
| 2 | OldSkullTuning „Free Resources“ (Seite und AGB gelesen) | Nur drei freie Bosch-Dateien (M30B34 Motronic, ML3.1, M2.9), nichts zu Delco/Multec; keine Lizenzangabe | Nein |
| 2 | Websuche Multec S HC12 Reverse Engineering | Keine veröffentlichten Kennfelddefinitionen oder Disassemblierungen; IDA unterstützt 68HC12 | Nein |
| 2 | Websuche DE „Multec S Kennfelder XDF Z14XE“ | Nur Werkstattdaten (Multec S (F) bei Z14XEP) | Nein |
| 3 | Exakte D-Nummern „D98003/D98005/D98007“ | D98003 ↔ 16227049 MF (Händler) | Identifikation, keine Datei |
| 3 | Websuche „X16XEL Multec S ECU bin file xdf“ | Ein einzelner Forumsanhang, laut Suchtext Export eines Tuning-Werkzeugs | Nicht verwendet: keine Definition, D-Nummer unbekannt |
| 3 | GitHub-Repo-Suche: `tunerpro opel`, `astra g ecu`, `opel tuning xdf`, `vauxhall ecu`, `hc12 ecu disassembly`, `corsa ecu bin` | Keine Treffer | – |
| 3 | Lokaler, nur lesender Scan von Downloads, Dokumente, Desktop und D:\ nach 128-KiB-Dateien mit Multec-S-Layout | 1 Datei mit 128 KiB, kein Multec-S-Layout | Keine lokalen Daten |

Nicht durchsucht wurden zugangsgeschützte Foren und Dateiarchive sowie Tuning-Datenbanken mit Bezahlschranke.
Firmware aus solchen Quellen wäre ohne Nutzungsrecht ohnehin nicht verwendbar.

## 3. Was für eine Messung gebraucht wird

1. Mindestens ein **unverändertes Multec-S-Original** (128 KiB) mit lesbarem Kennungsblock (SW-Nummer,
   GM-Teilenummer, D-Nummer, Motorkennung), aus eigenem Steuergerät oder mit ausdrücklichem Nutzungsrecht.
2. Eine **passende Definition** zu genau dieser Kalibrierung (D-Nummer/SW-Nummer gleich), möglichst vollständig.
   Eine Teil-XDF erlaubt nur Recall auf ihren Einträgen, keine Präzision.
3. Für einen unabhängigen Test ein **zweiter Stand** (andere D-Nummer oder anderer Motor) mit eigener Definition,
   in einer eigenen Unabhängigkeitsgruppe.

Mit diesen Daten lässt sich die Messung wie bei MSD80 über ein lokales Manifest (`.qa/`, git-ignoriert) mit
`benchmark_suite` und `miss_analysis` durchführen.

## 4. Hypothesen für eine spätere Multec-S-Erkennung (ungeprüft)

- **Familienerkennung** über das dokumentierte Layout (Größe, gelöschter Boot-Block, `00 00 7E` bei 0x2000,
  Kennungsblock bei 0x3000 mit Spiegel bei 0x13000). Nicht umgesetzt, weil es an keiner echten Datei geprüft ist.
- **Kennfelder:** HC12 ist big-endian. Die vorhandenen Scanner für Achsen (`axis_arrays`), Kopfdatensätze und
  Zeilenabstand sowie die 68HC11/HC12-nahe Codeverweis-Suche (`cpu_refs`) wären der Ausgangspunkt. Ob Multec S
  Achsen mit Zählerpräfix oder Pointer-Tabellen nutzt („HC12 pointer tables ab 0x2000“), ist unbekannt.
- **Spiegelbank:** Bank 2 ist laut Beschreibung ein Spiegel von Bank 1. Eine Erkennung müsste doppelte Kandidaten
  zusammenführen, statt sie zweimal zu melden.
