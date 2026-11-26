# Schreibsicherheit – Prüfung aller Schreibpfade (Qualitätsphase 6, rc2-Release-Fix)

Stand: 26.11.2026, Branch `feat/post-rc1-recognition-nextgen`, Release-Fix `edd926c` (Zellbreite gespeicherter
Achsen, § 4a). Alle Schreibtests verwenden ausschließlich synthetische Dateien; kein Test verändert eine echte
Firmware.

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
| Tatsächlicher Speicherbereich einer Achse: größte Punktzahl × Zellbreite (bzw. mit Abstand der Stützstellen); unbekannte Breite = 4 Byte je Punkt; widersprüchliche Breite = die größte, gemeinsame Achse abgelehnt | `axis_refs.objects`, `edit_guard.axis_range` (§ 4a) |
| Werte eines Kennfelds mit offenem Datentyp: die breiteste mögliche Lesart | `edit_guard.value_length` |
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
Nutzer (Name, Adresse, Größe, Datentyp, Byteordnung, Achsbezug, **Zelltyp, Herkunft und Stützstellenabstand
der Achse**). Ändert sich die Firmware, das Layout, die Zellbreite oder die Zuordnung, verfällt sie automatisch.
Bearbeitungen der Achswerte selbst lassen sie bestehen. Auch nach der Klärung bleibt die Rückfrage mit allen
Nutzern; die Klärung hebt nur die Ablehnung auf.

Seit dem rc2-Release-Fix gilt zusätzlich:

- Die angegebene Zellbreite **wird in der Bereichsprüfung verwendet** (vorher nur gespeichert). Die Klärung
  wirkt nur auf einen Konflikt mit genau diesem Bereich (`AxisClearance.covers`).
- Eine Klärung kann eine **belegte Zellbreite nicht verkleinern** („eine Klärung ändert keine belegte
  Zellbreite“); sie kann nur eine unbekannte Breite festlegen.
- Eine festgelegte Breite darf die Achse nicht in die Werte eines ihrer Nutzer reichen lassen.
- **Widersprüche** (Punktzahl, Zellbreite, Stützstellenabstand, Datentypen der Definitionen) werden nicht
  per Klärung aufgehoben: „Widerspruch zuerst in den Definitionen klären“.
- Achsen mit Abstand zwischen den Stützstellen (XDF-Stride) sind nur über die Definition klärbar.
- Eine zweite Bestätigung hebt eine Ablehnung weiterhin nie auf.

## 4a. Zellbreite gespeicherter Achsen (rc2-Release-Fix)

**Befund (M1 der Release-Bereitschaft):** Die Schreibprüfung nahm für jede gespeicherte Achse fest 2 Byte je
Stützstelle an (`AXIS_POINT_BYTES`). Folgen: Bei 32-Bit- und Float-Achsen war die obere Hälfte ungeschützt, bei
8-Bit-Achsen wurde ein zu großer Bereich beansprucht (bis in die Werte der eigenen Tabelle), die Kopiensuche
verglich 2 Byte je Punkt, und eine technische Klärung speicherte eine Zellbreite, ohne sie zu verwenden.

**Behebung:**

| Bestandteil | Umsetzung |
|---|---|
| Eigenes Merkmal statt Werte-Datentyp | je Kennfeld `axis_x/y_dtype` ('' = unbekannt), `axis_x/y_type_source`, `axis_x/y_step` (Byteabstand der Stützstellen, 0 = dicht). Der Datentyp der Werte wird nie für die Achse übernommen. |
| Herkunft | A2L: `AXIS_PTS` mit seinem `RECORD_LAYOUT` (gemeinsame Achsen) bzw. das `RECORD_LAYOUT` der Kennlinie/des Kennfelds (eingebettete Achsen); XDF: `EMBEDDEDDATA` der Achse einschließlich Stride; Datensatz-, Kennlinien- und Anzahl-Kopf-Erkennung: die Breite, mit der die Achse gelesen wurde; Definitionsdialog: Zelltyp muss ausdrücklich gewählt werden. |
| Unterstützte Typen | u8/s8 (1 Byte), u16/s16 (2), u32/s32/f32 (4). Float64 wird nicht unterstützt (kein Typ im Programm; ungültige Typen lehnt `validate` ab). |
| Achsobjekt | Breite, Typstatus (*bestätigt*, *belegt*, *unbekannt*, *widersprüchlich*), Quellen, größte Punktzahl aller Nutzer, Stützstellenabstand; geschützter Bereich `Adresse … Adresse + (Punkte − 1) × max(Abstand, Breite) + Breite`. |
| Unbekannte Breite | geschützt mit der größten darstellbaren Zelle (4 Byte je Punkt); im Konflikt benannt („Zellbreite der Achse unbekannt: geschützt mit 4 Byte je Punkt“). Alte Projekte und Map-Packs ohne Achstyp laden mit „unbekannt“, **nicht** als 16 Bit. |
| Widersprüchliche Breiten oder Abstände | die größte wird geschützt, der Widerspruch wird angezeigt; eine gemeinsame Achse erhält die Identität „unbekannt“ und wird abgelehnt. Keine stille Wahl, keine Identität aus gleichen Rohwerten. |
| Unterschiedliche Punktzahlen | geschützt wird die größte (vorher: die der Mehrheit). |
| Feste Achse ohne Adresse | beansprucht keinen Speicherbereich. |
| Kopiensuche | vergleicht Punkte × Zellbreite; bei unbekannter Breite oder Abstand 1 Byte je Punkt (findet mehr Kopien, die Identität bleibt offen). |
| Klärung | siehe § 4. |
| Freigabe | Ein bestätigter Konflikt ist an seinen Bereich gebunden; ändert sich die Breite nach der Rückfrage, ist die Freigabe veraltet. |

**Verbleibende 16-Bit-Annahmen (bewusst, keine Schreibprüfung):** Die Datensatz- und Kennliniensuche
(`axis_records`, `curve_records`) prüft 16-Bit-Kandidaten mit 16-Bit-Lesungen; `scoped_scan._axis_ranges`
schätzt die Breite der Achsen eines Strukturfunds aus den Werten (≤ 255 → 1 Byte), um Zeigertabellen
auszusortieren. Beides sind Erkennungsheuristiken; sie beanspruchen keinen geschützten Bereich und wurden nicht
geändert, damit die Erkennung unverändert bleibt.

**Echte Definitionen (Entwicklungsdaten, nur Zählwerte):** In einer MEVD17.2-Definition mit rund 19 500
Kennfeldern haben 618 der 3 177 gespeicherten Achsobjekte 1 Byte, 2 553 haben 2 Byte und 6 haben 4 Byte je Punkt;
alle tragen einen belegten Typ. Die 6 32-Bit-Achsen waren vorher nur zur Hälfte geschützt. Die bisher gemeldeten
„Konflikte“ beim Schreiben der ersten Zelle von 8-Bit-Achs-Kennfeldern waren Fehlmeldungen der 2-Byte-Annahme
(beanspruchter Bereich bis zu 12 Byte in die eigenen Werte); sie entfallen.

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

`tests/test_axis_cell_width.py` (39, rc2-Release-Fix), alle synthetisch:

| Fall | Erwartung | Test |
|---|---|---|
| 8-, 16-, 32-Bit- und Float32-Achse (u8, s8, u16, s16, u32, s32, f32) | genau der gespeicherte Bereich geschützt, erstes Byte dahinter frei | `test_every_cell_type_protects_exactly_its_stored_bytes`, `test_sixteen_bit_axis_protection_is_unchanged` |
| Schreiben in die bisher ungeschützte zweite Hälfte einer 32-Bit-Achse | Konflikt; ohne Freigabe abgelehnt | `test_write_into_the_formerly_unprotected_upper_half_of_a_32_bit_axis_is_a_conflict` |
| Unbekannte Breite | konservativ 4 Byte, im Konflikt benannt; mit Kopie abgelehnt | `test_unknown_width_is_protected_with_the_widest_cell_and_named`, `test_unknown_width_of_a_shared_axis_with_a_copy_is_refused_until_clarified` |
| Widersprüchliche Breiten | angezeigt, breit geschützt, abgelehnt, nicht klärbar | `test_contradicting_widths_are_shown_protected_widely_and_never_cleared` |
| Widersprüchliche Punktzahlen | größte geschützt | `test_contradicting_point_counts_protect_the_largest_one` |
| Gemeinsame Achse mit mehreren Nutzern | alle Nutzer im Konflikt | `test_shared_axis_lists_every_user` |
| Wertgleiche Achsen an verschiedenen Adressen | getrennte Objekte; volle Zellbreite verglichen | `test_value_equal_axes_at_different_addresses_stay_separate`, `test_copy_search_compares_the_whole_cell_width` |
| Falsche manuelle Breite | belegte Breite nicht verkleinerbar; keine Breite bis in die Werte | `test_a_stated_width_cannot_be_narrowed_by_a_clarification`, `test_a_clarified_unknown_width_must_not_reach_into_the_users_values` |
| Layout, Breite oder Firmware geändert | Klärung verfällt | `test_clarification_expires_with_layout_width_or_firmware` |
| Freigabe, danach Breite geändert | Freigabe veraltet | `test_an_approval_does_not_survive_a_changed_axis_width` |
| Feste Achse ohne Adresse | kein fiktiver Konflikt | `test_fixed_axis_without_address_claims_no_bytes` |
| Achse am Dateiende | geschützt bis zum letzten Byte; zu lange Achse abgelehnt | `test_axis_at_the_end_of_the_image` |
| Ungültige Adresse, Typ (u64, f64), Abstand, Klärungsangaben | kontrollierte Ablehnung | `test_invalid_axis_address_type_or_step_is_refused`, `test_invalid_clarification_statements_are_refused` |
| Überlappende Achse und Tabelle; offener breiterer Werte-Typ | beide gemeldet; breiteste Lesart geschützt | `test_overlapping_axis_and_table_are_both_reported`, `test_open_wider_value_type_of_a_table_is_protected` |
| Transaktion mit ungeschütztem Teil; Undo/Redo; Original | nichts geschrieben; exakt; Original unverändert | `test_transaction_with_one_unprotected_part_writes_nothing_and_undo_redo_is_exact` |
| Fläche/Stapel und Hex | gleicher Bereich, ohne Freigabe abgelehnt | `test_batch_area_and_hex_paths_use_the_same_range` |
| Alte Projekte und Map-Packs ohne Achstyp | laden, Typ unbekannt (nicht 16 Bit); neuer Pack behält den Typ | `test_projects_and_map_packs_without_axis_type_load_as_unknown` |
| A2L ULONG-/FLOAT32-Achsen, eingebettete UBYTE/UWORD-Achsen | Typ aus dem Achs-Layout, nicht aus den Werten | `test_a2l_axis_cell_type_comes_from_the_axis_record_layout_not_the_values` |
| XDF 32-Bit-Achse, 8-Bit-Achse mit Stride | Typ und Abstand übernommen, Bereich exakt | `test_xdf_axis_cell_type_and_point_distance` |
| Optimierte Prüfung gegen Brute-Force mit gemischten Breiten und Abständen | identisch | `test_optimised_check_equals_a_brute_force_range_check_with_mixed_widths` |

Die übrigen Schreibwege (Rezept, Smart Transfer, Wiederherstellung, Prüfsummenkorrekturen) laufen über dieselbe
`commit`-Prüfung und damit über dieselbe Bereichsberechnung; ihre bestehenden Tests (oben) bestehen unverändert.
Der Definitionsdialog verlangt für eine neu angegebene Achsadresse einen ausdrücklich gewählten Zelltyp
(`tests/test_definition_dialog_ui.py`).

## 6. Bekannte Grenzen

- Undo/Redo und das Laden eines Projekts laufen bewusst ohne Freigabe (siehe Tabelle).
- Werkzeuge und Skripte, die ein Abbild ohne Kennfelder bearbeiten, haben keine Schutzschicht, weil nichts
  bekannt ist, das geschützt werden könnte. Wer ein Abbild mit Kennfeldern per Skript bearbeitet, setzt
  `guarded(image, lambda: maps)`.
- Achsen mit unbekannter Zellbreite werden mit 4 Byte je Punkt geschützt. Bei 8- und 16-Bit-Achsen ohne
  Typangabe (z. B. Projekte aus rc1 oder älter) kann das zusätzliche Rückfragen oder Ablehnungen auslösen
  (sichere Richtung); Abhilfe: Definition neu importieren oder den Zelltyp im Definitionsdialog angeben.
- Die Schutzschicht prüft, **welche bekannten Objekte** betroffen sind. Sie kann nicht beurteilen, ob eine
  Änderung fachlich sinnvoll oder für ein Fahrzeug zulässig ist. Keine Flashfreigabe.
