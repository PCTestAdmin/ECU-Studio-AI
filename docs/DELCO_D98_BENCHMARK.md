# Delco D98 / Multec S: Benchmark (30.10.2026)

**Status: keine Erkennungsmessung möglich.** Es gibt kein rechtmäßig nutzbares D98-Firmwareabbild, weder lokal
noch in den geprüften öffentlichen Quellen (siehe [DELCO_D98_RESEARCH.md](DELCO_D98_RESEARCH.md)). Deshalb gibt
es hier weder Precision noch Recall, keine Teilreferenzmessung und keine Aussage zur Erkennungsqualität.

## Einzige durchführbare Messung: synthetische Negativkontrolle

| Feld | Wert |
|---|---|
| Datei | `_dev/contrib/corpus/delphi-multec-s-128k.mimic` aus [openremap-core `6c6ba85`](https://github.com/v-arapidis/openremap-core/tree/6c6ba8526b9f8040916b3a617035a085eabfccab) (MIT) |
| SHA-256 | `b31700988164166a5a077bfd86da02ed0e49bfe855fb18dbc52adef1a4381033` |
| Art | **synthetisch**: 131 072 Byte 0xFF mit `00 00 7E` bei 0x2000, SW-Nummer „12345678“ + „AB“ bei 0x3009, GM-Nummer „87654321“ bei 0x3015; **keine Kalibrierdaten, keine D-Nummer** |
| Rolle | Negativkontrolle (Struktur ohne Kennfelder) |
| Erkannte Familie | „Unbekannt“: ECU Studio AI hat kein Multec-S-Profil |
| Kandidaten | **0** (alle Klassen) |
| Laufzeit / Python-Allokationspeak | 0,66 s / 9,2 MiB |

Das zeigt nur, dass der Scanner auf diesem leeren Layout keine Fehlalarme erzeugt. Über echte Multec-S-Dateien
sagt es nichts.

## Reproduktion

```text
python -c "from ecu_studio.core.model import BinaryImage; from ecu_studio.core.scoped_scan import scan_calibration_candidates as s; print(len(s(BinaryImage.from_file('delphi-multec-s-128k.mimic'))))"
```

## Sobald echte Daten vorliegen

Lokales Manifest unter `.qa/` (git-ignoriert) nach [REFERENCE_VALIDATION.md](REFERENCE_VALIDATION.md) anlegen,
mit Hash, D-Nummer, SW-Nummer, Herkunft, Lizenz, Rolle und `complete`. Danach:

```text
python -m ecu_studio.tools.benchmark_suite .qa/multec-manifest.json --out .qa/multec.json --markdown .qa/multec.md
python -m ecu_studio.tools.miss_analysis  .qa/multec-manifest.json --out .qa/multec-miss.json
```

Eine unvollständige XDF wird als **Teilreferenzmessung** gekennzeichnet: Sie liefert nur Recall auf den dort
definierten Kennfeldern.
