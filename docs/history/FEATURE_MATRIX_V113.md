# Funktionsstand 1.13

| Funktion | Implementierung und Grenze |
|---|---|
| Offline-Definitionen | 16 vollständige GPL-XDFs, MS41/MS42/MS43; Version, Größe und Achsenquorum |
| XDF-Achsen/Kategorien | Verknüpfte Achsen, einsbasierte Kategorien; reine Achsen bei Automatik ausgelassen |
| MS43-Versionen | 430037, 430055, 430056, 430064, 430066, 430069; Standard Full/Partial |
| MS42 | 0110C6 Full/Partial; separates öffentliches reales Regressionsexemplar |
| MS41 | 1429861 XDFs; Identität nur Hinweis, reale Regression fehlt |
| RomRaider | Exakte ID/Größe, Vererbung, u8/s8/u16/s16/u32/s32/f32, Achsen, Formeln; kein OEM-Paket enthalten |
| Nichtlineare Formeln | Eingeschränkte AST-Auswertung; ohne geprüfte Umkehrfunktion schreibgeschützt |
| Float-Bearbeitung | Einzelzellen, Flächenvorschau und Transaktionen mit IEEE-f32-Quantisierung; nicht im allgemeinen Rohdaten-Trace |
| Struktur-KI | 32 Bäume, Preset-Training, getrennte Quellgruppen, reproduzierbare JSON-Inferenz; Sortierhilfe ohne Semantik |
| Andere Hersteller | Lokaler XDF/A2L-Import; keine automatische Bosch-/Denso-/Delphi-Abdeckung behauptet |
| Trainingsdaten | Offene Quellen und vollständige Lizenzen enthalten; keine privaten oder OEM-BINs trainiert |
| Ausgabe | Original bleibt erhalten, Änderungen als Overlay, keine Flash-Freigabe |

Weitere bestehende Editorfunktionen: FEATURE_MATRIX_V112.md und FEATURE_MATRIX_V111.md.
