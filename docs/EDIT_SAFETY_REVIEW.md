# Schreibsicherheit – Prüfung aller Schreibpfade (Qualitätsphase 6)

Stand: 25.11.2026, Branch `feat/post-rc1-recognition-nextgen`. Alle Schreibtests verwenden ausschließlich
synthetische Dateien; kein Test verändert eine echte Firmware.

## 1. Grundsatz

Jede Änderung an Firmware-Bytes läuft über **eine** Stelle: `BinaryImage.commit` (`core/model.py`).
`write`, `write_physical`, Stapelbearbeitung, Rezepte, Smart Transfer, Versionswiederherstellung und alle
Prüfsummenkorrekturen rufen `commit` auf. Seit Qualitätsphase 6 hängt an jedem im Programm geöffneten
Abbild eine zentrale Schutzschicht (`core/edit_guard.WritePolicy`, gesetzt mit `guarded()`), die **unmittelbar
vor dem Schreiben** erneut prüft – auch dann, wenn ein Dialog die Prüfung vorher schon gemacht hat.

Ablauf einer Bearbeitung:

1. **Vorschau** – der Dialog berechnet die Änderung (Zellen, Bytes, vorher/nachher), ohne zu schreiben.
2. **Freigabe** – `MainWindow.edit_allowed` → `WritePolicy.approve`: ermittelt alle betroffenen Objekte
   (andere Kennfelder, gespeicherte Achsen mit allen Nutzern, ungeprüfte Erkennungen).
   - Nichts anderes betroffen → Freigabe ohne Rückfrage.
   - Andere Objekte betroffen → Rückfrage mit vollständiger Liste (Name, Adresse, Art; ab 30 Einträgen
     „… und N weitere Objekte“). Bei gespeicherten Achsen der Hinweis: *„Eine gespeicherte Achse ist ein
     physischer Speicherbereich: Die Änderung gilt für jedes Kennfeld, das diese Bytes liest. Es wird nichts
     auf andere Adressen kopiert.“*
   - Achse mit **unbekannter** gemeinsamer Identität → **abgelehnt**. Eine zweite Bestätigung hebt das nicht
     auf (Entscheidung 4). Freigabe nur nach technischer Klärung (Abschnitt 4).
3. **Freigabeobjekt** (`Approval`) – bindet Positionen, Revision des Abbilds, eigene Kennfelder und die
   bestätigten Konflikte.
4. **Erneute Prüfung in `commit`** (`WritePolicy.check`) direkt vor `_apply`:
   - ohne Freigabe: jeder Konflikt → `EditRefused` („Schreiben ohne Freigabe abgelehnt“);
   - Revision geändert → „Freigabe veraltet“;
   - Bytes außerhalb der freigegebenen Positionen → abgelehnt;
   - Konflikte werden mit den **aktuellen** Kennfeldern neu berechnet: abgelehnte Achse → Ablehnung;
     neuer, nicht bestätigter Konflikt (z. B. geänderte Achsreferenz) → „Freigabe veraltet“.
5. **Eine Transaktion** – alle Bytes in einem Undo-Schritt; bei einem Fehler wird nichts geschrieben.

## 2. Schreibpfade

| Pfad | Ort | Vor QP6 | Nach QP6 |
|---|---|---|---|
| Tabellenzelle | `ui/views.py` `MapTableModel.setData` | geprüft (Dialog) | Freigabe → `write_physical(approval=)` → `commit`-Prüfung |
| Hex-Editor | `ui/views.py` `HexTableModel.setData` | **ungeprüft** | geprüft: Byte in Kennfeld/Achse → Rückfrage bzw. Ablehnung |
| Auswahl bearbeiten | `ui/next_dialogs.py` `SurfaceEditDialog.apply` | geprüft (Dialog) | zusätzlich `commit`-Prüfung |
| Stapelbearbeitung | `ui/tools_dialogs.py` `BatchEditDialog.do_apply` | geprüft (Dialog) | zusätzlich `commit`-Prüfung |
| Bearbeitungsrezept | `ui/main_window.py` `execute_recipe` | geprüft (Dialog) | zusätzlich: widersprüchliche Schritte (gleiche Bytes) werden abgelehnt |
| Smart Map Transfer | `ui/next_dialogs.py` `SmartTransferDialog` | geprüft (Dialog) | zusätzlich `commit`-Prüfung |
| Version wiederherstellen | `core/versioning.apply_restore` | **ungeprüft** | geprüft (alle betroffenen Kennfelder) |
| Prüfsummenkorrektur (Sitzung) | `core/integrity.apply_correction` | **ungeprüft** | geprüft |
| Prüffeld-Korrektur (Profil) | `core/checksum_audit.apply_checksum_correction` | mehrere Schreibvorgänge, Rücknahme durch Schreiben | **eine** Transaktion mit Freigabe, Rücknahme per Undo |
| Prüfsummen-Tabellen | `core/checksum_tables.apply_table_correction` | wie oben | wie oben |
| EDC16 / EDC17 | `core/edc16_checksum`, `core/edc17_checksum` `apply_correction` | eine Transaktion | Freigabe wird durchgereicht |
| Dialog ohne Wächter | alle obigen Dialoge, wenn kein `guard` übergeben wird | schrieb ungeprüft | `silent_approval`: nur ohne Fremdbetroffenheit, sonst Ablehnung |
| Undo / Redo | `BinaryImage.undo/redo` | – | bewusst ohne Freigabe (nimmt eigene, bereits geprüfte Transaktion exakt zurück) |
| Projekt laden | `BinaryImage.restore_patches` | – | bewusst ohne Freigabe (stellt gespeicherten Stand her; Bereich und Bytewerte werden geprüft) |
| Achsdefinition / Map-Pack / Definitionsimport | `AxisDialog`, `commit_metadata` | – | ändern nur Definitionen, keine Bytes |
| Werkzeuge ohne Kennfelder | `tools/gui_smoke`, `feature_clips`, `next_workflows`, `calibration_v18` | – | arbeiten auf eigenen synthetischen Abbildern ohne Schutzschicht (keine Kennfelder bekannt) |

Es gibt keine Einfügen-Funktion für Zellen, und die ORI/MOD-Ansicht ist nur lesend.

## 3. Geprüfte Bedingungen

| Bedingung | Wo |
|---|---|
| Gültige Position, Bytewert 0–255, keine doppelten Positionen, Vorher-Wert stimmt | `commit` |
| Wertebereich der Zellbreite, endliche Zahl, keine nichtlineare Formel ohne Umkehrung | `write_physical`, `plan_surface_edit` |
| Schreiben außerhalb des Abbilds, teilweise ungültige Transaktion | `write`, `apply_batch`, `commit` (nichts wird geschrieben) |
| Überlappende Kennfelder | `edit_guard.conflicts` |
| Gespeicherte Achsen mit allen Nutzern; Identität sicher / plausibel / unbekannt | `edit_guard.conflicts` (aus `axis_refs`) |
| Ungeprüfte Nutzer werden gezählt und genannt | `Conflict.unverified` |
| Revision, Positionen, bestätigte Konflikte | `WritePolicy.check` |
| Widersprüchliche Rezeptschritte | `editing.plan_recipe` |
| Gleiche Rohwerte begründen nie eine gemeinsame Achse | `axis_refs` (getrennte Objekte, beide geschützt) |

## 4. Technische Klärung einer Achse unbekannter Identität

Dialog „Gemeinsame Achse technisch klären“ (Schaltfläche in der Ablehnung). Nichts ist vorausgefüllt:

- Speicherbereich (Anfang, Ende), Punktzahl, Zellbreite – müssen zusammenpassen (`Ende − Anfang + 1 =
  Punkte × Breite`) und zur gespeicherten Achse passen;
- Zuordnung: alle Kennfelder, die diese Bytes als Achse lesen – muss **genau** der ermittelten Nutzerliste
  entsprechen;
- Herkunft der Prüfung: mindestens 20 Zeichen, keine Floskel (z. B. geprüfte Definition, Adress- und
  Layoutprüfung im Programmcode).

Die Klärung (`AxisClearance`) gilt nur für diese Firmware (Hash des Originals) und für das Layout aller
Nutzer (Name, Adresse, Größe, Datentyp, Byteordnung, Achsbezug). Ändert sich die Firmware, das Layout oder
die Zuordnung, verfällt sie automatisch. Bearbeitungen der Achswerte selbst lassen sie bestehen. Auch nach
der Klärung bleibt die Rückfrage mit allen Nutzern; die Klärung hebt nur die Ablehnung auf.

## 5. Tests (synthetisch)

`tests/test_write_policy.py` (18) und `tests/test_axis_identity_edit_safety.py` (12):

| Gegenbeispiel | Test |
|---|---|
| Unbekannte gemeinsame Achse, zweite Bestätigung | `test_unknown_shared_axis_is_refused_and_a_second_confirmation_does_not_help` |
| Plausible gemeinsame Achse, einmal geschrieben für alle Nutzer | `test_plausible_shared_axis_needs_confirmation_and_writes_once_for_all_users` |
| Definitionsachse: physische Wirkung auf alle Nutzer | `test_definition_shared_axis_shows_physical_effect_on_all_users` |
| Gleiche Rohwerte, zwei Objekte | `test_axes_with_identical_raw_values_stay_two_objects_and_both_are_guarded` |
| Überlappende Tabellen, Schreiben ohne Freigabe | `test_overlapping_tables_need_confirmation_and_unapproved_writes_are_refused` |
| Freie Bytes | `test_free_bytes_outside_every_object_need_no_approval` |
| Manipulierte Achsreferenz nach Freigabe | `test_manipulated_axis_reference_after_approval_is_stale` |
| Falsche Breite, NaN, Überlauf | `test_wrong_width_and_out_of_range_values_are_rejected_before_writing` |
| Außerhalb des Abbilds, teilweise ungültig | `test_writes_outside_the_image_and_partly_invalid_transactions_change_nothing` |
| Gemischte Transaktion mit abgelehntem Teil | `test_transaction_with_one_refused_part_writes_nothing` |
| Veraltete Freigabe, andere Positionen | `test_stale_approval_after_another_edit_or_for_other_positions` |
| Abbruch und Fehler, Verlauf bleibt nutzbar | `test_cancelled_confirmation_and_errors_leave_a_working_history` |
| Undo/Redo auf gemeinsamer Achse exakt | `test_undo_redo_of_an_approved_shared_axis_edit_is_exact` |
| Stapel, Wiederherstellung und andere Wege ohne Freigabe | `test_batch_restore_and_unapproved_alternative_paths_are_refused` |
| Widersprüchliches Rezept | `test_recipe_with_contradictory_steps_is_refused` |
| Fehlerhafte Definitionen und Projekt-Patches | `test_faulty_definitions_and_project_patches_are_rejected` |
| Klärung: Angaben müssen passen, hebt nur die Ablehnung auf, verfällt bei Layoutänderung | `test_clearance_needs_matching_statements_and_lifts_only_the_refusal` |
| Klärung an Firmware gebunden | `test_clearance_is_bound_to_the_firmware` |

Außerdem: `tests/test_next_integration.py` (Hex-Schreiben in einem Kennfeld fragt nach),
`tests/test_next_core.py` (Rezept, atomare Stapelbearbeitung).

## 6. Bekannte Grenzen

- Undo/Redo und das Laden eines Projekts laufen bewusst ohne Freigabe (siehe Tabelle).
- Werkzeuge und Skripte, die ein Abbild ohne Kennfelder bearbeiten, haben keine Schutzschicht, weil nichts
  bekannt ist, das geschützt werden könnte. Wer ein Abbild mit Kennfeldern per Skript bearbeitet, setzt
  `guarded(image, lambda: maps)`.
- Die Schutzschicht prüft, **welche bekannten Objekte** betroffen sind. Sie kann nicht beurteilen, ob eine
  Änderung fachlich sinnvoll oder für ein Fahrzeug zulässig ist. Keine Flashfreigabe.
