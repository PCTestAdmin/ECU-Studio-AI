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
  92 → 99 % correct. A detection with other axes there does not count as confirmation. Axis values are no longer
  carried over when the axis is not confirmed at the target place; before, 296 of 941 such axes showed wrong values.
  When adopted, a proposal replaces an unchecked, unnamed detection at the same place. Until now exactly the
  confirmed proposals were skipped.
- **Reproducible training:** data set with provenance, family hold-out, seed, log and replacement gate. Role
  *training* requires an explicit clearance of the data (`training_allowed`). Retraining was not better (the
  difference is within chance); the shipped model stays.
- **Scan:** named stages in the status bar, steadily rising progress, faster axis search with identical results.
  With a large XDF loaded, the window used to freeze for 35–43 s after a scan (MED17 with 3446 definitions); taking
  over the findings now takes less than 0.3 s with the same result.
- **Known limits:** the precision of program-code findings is not measured. Bosch EDC17 sets table pointers at run
  time through `a9`, which cannot be resolved statically. EDC17, MG1, MD1, Simos and SID remain not validated. The
  earlier manufacturer-A2L measurements (MSD80, MSD85, EDC16, EDC17CP09) cannot be repeated locally and are marked
  as historical.

**No flash approval:** ECU Studio AI does not release modified files for flashing. Checksums, signatures, emissions
and safety functions remain the user's responsibility.
