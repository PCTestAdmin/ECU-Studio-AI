# ECU Studio AI 1.19.0 – Release Notes (Entwurf / draft)

**Noch nicht veröffentlicht. Not released yet.** Die deutsche Fassung ist der Abschnitt „Unveröffentlicht“ in
[CHANGELOG.md](../CHANGELOG.md); der Release-Workflow übernimmt ihn, sobald er im freigegebenen Release-Schritt zu
`## 1.19.0 (Datum)` wird. Die englische Fassung unten kann dann angehängt werden. Messungen und Grenzen:
[Validierungsbericht](VALIDIERUNG_1.19.0.md).

---

## English

Map recognition without a definition, backed by a final validation round. Status per feature: *validated* = proven
on independent references, *experimental* = present but not independently checked.

- **TriCore program code (experimental):** interpolation calls that pass a record header (count and breakpoints of
  both axes in front of the data, also mixed 8/16 bit) are recognised. The cell width comes from the routine's load
  instructions, without the count reads. Conditional branches are followed. Where a routine expects its arguments
  in other registers than `a4`/`a5`/`a6`, the assignment is derived from its call behaviour. Measured only on the
  MSD80 full flash I8A0S, which was also used during development (partial XDF): 73 → 84 of 99 maps exact, curves
  164 → 173. There is no independent reference for other TriCore versions. All other comparison pairs give the
  same results as 1.18.2.
- **Three recognition layers:** definitions stay unchanged. Findings from code and structure fill gaps before data
  patterns and AI do. If code/structure detection finds the same table as a definition, the definition is marked
  "independently confirmed" (not "checked"). A data-pattern match only supports the position and is counted
  separately. Contradictions (start, size, cell width, byte order, proven sign) are listed in the scan report. A
  finding that partly overlaps a definition is no longer added to the list as well.
- **Wrong definition detected:** if the axis values change direction in more than 10 % of the checkable maps, XDF
  import and scan warn that the definition probably belongs to another software version or family. Measured on
  local pairs: fitting definitions 0.1–0.8 %, wrong ones 87–97 %. Empty or erased table areas are now a hint, not a
  warning (they are common for unused functions).
- **No invented data types:** if the sign is not proven by program code and the bytes decide it, the inspector shows
  the other possible reading.
- **Identification with a level:** unique, probable, ambiguous or unknown, each with its reason.
- **Review checklist** (Tools): detected maps ordered by need for review, with reasons and shared axes. Confirm and
  reject are saved in the project and apply only to the original file they were made on. Every decision can be
  withdrawn under "Decisions …". A new scan does not offer a rejected table again unless it is now found with
  stronger evidence; then it appears with a note.
- **Name transfer between software versions:** proposals that the target's own detection finds at the same place
  with the same size, cell width and byte order are marked. Measured on MED17 (development data): "similar values"
  92 → 99 % correct (not independently validated; the app does not show these rates). A detection with other axes there does not count as confirmation. Axis values are no longer
  carried over when the axis is not confirmed at the target place; before, 296 of 941 such axes showed wrong values.
  When adopted, a proposal replaces an unchecked, unnamed detection at the same place. Until now exactly the
  confirmed proposals were skipped.
- **Learned models without provable clearance removed:** the learned model for data-pattern finds, shipped since
  1.15.0, was trained, among others, on a file whose provenance note excludes training and on data without
  documented clearance. It is removed from the program, ZIP, installer and source code. The same applies to the
  MS43 structure model (no training clearance) and the table of measured hit rates (measured on files without
  clarified provenance). Git history is unchanged; checksums and provenance are in the model card, section 2e
  (German). The build stops if one of these files, even renamed, gets into a package again. A new model is applied
  only with documented clearance of its training data.
- **Effect on detection:** exact maps, data types, axes and axis addresses stay the same on all 15 comparison pairs.
  Without the model, more unconfirmed data-pattern finds appear (e.g. ME9: precision 62 → 42 %, MS45: 66 → 38 %).
  The MS43 model's shape hints are gone; they only concerned maps the bundled MS43 definition already contains.
- **Kind of evidence instead of a percentage:** every automatic find shows *code evidence*, *structure evidence* or
  *data-pattern guess*. This is not a probability and not independently validated; the tooltip says so. TriCore
  code evidence is marked experimental. The catalogue filter uses the same levels. Rates saved in projects by
  1.15.0–1.18.2 are removed on loading; your own notes stay. The historical values and their provenance are in the
  model card.
- **Review checklist:** pure data-pattern guesses without contradictions are a separate group, collapsed by default
  ("Show data-pattern guesses"). They stay in the project, the catalogue and the filter; finds with code or
  structure evidence and all contradictions stay on top.
- **Reproducible training:** data set with provenance, family hold-out, seed, log and replacement gate. Only data
  with a recorded clearance (`training_allowed`) is trained on, and only such a model is applied in scans. No
  cleared data set with a complete reference is available at the moment.
- **Scan:** named stages in the status bar, steadily rising progress, faster axis search with identical results.
  With a large XDF loaded, the window used to freeze for 35–43 s after a scan (MED17 with 3446 definitions); taking
  over the findings now takes less than 0.3 s with the same result. If the window had to repaint during a scan
  (first display of a file, closing the checklist), it stood still until the scan ended (MS43: 4.7-5.1 s, also in
  1.18.2); now the longest pause is 0.11 s with the same scan time. Finished background tasks are waited for
  before they are released and when the window closes.
- **Known limits:**
  - The precision of program-code findings is not measured. TriCore code detection stays experimental.
  - Bosch EDC17 sets table pointers at run time through `a9`, which cannot be resolved statically.
  - EDC17, MG1, MD1, Simos and SID remain not validated. The earlier manufacturer-A2L measurements (MSD80, MSD85,
    EDC16, EDC17CP09) cannot be repeated locally and are marked as historical.
  - A one-time crash (access violation) on 1 Nov 2026 did not recur in the later stress runs. Its cause is unknown.
  - If the program folder is nested deeper than about 200 characters, the program does not start (Windows path
    length).
  - On MS43, cancelling takes effect only after 3–5 s, because reading the bundled definition cannot be
    interrupted. Finds of a cancelled scan are not taken over.

**No flash approval:** ECU Studio AI does not release modified files for flashing. Checksums, signatures, emissions
and safety functions remain the user's responsibility.
