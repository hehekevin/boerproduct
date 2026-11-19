# Domain rules — compliance_check (学术规范与合规检查)

Goal: every compliance judgment is double-anchored (norm clause + manuscript
locator), reproducible on the same material, and separates norm problems from
substantive scientific problems. Missing a real risk and inventing a fake one
are equally bad.

## 1. Checklist construction
- Identify the applicable norms from task.md / the manuscript: study type
  (RCT → CONSORT; systematic review → PRISMA; animal study → ARRIVE), target
  journal guide (record version/date if provided), plus universal norms
  (ethics, COI, data availability, authorship, copyright, privacy).
- Decompose each norm into checkable items; cite the item number/section in
  `guideline` (e.g., "CONSORT 2010 item 23"). If the guideline text is not
  provided, use the named standard checklist and add an uncertainty entry
  (agent knowledge of the checklist, human_confirm) — never quote clause text
  you cannot see.
- Register provided guideline files in sources[]/documents[] (role=guideline)
  and guidelines[] with version.

## 2. Grading (status)
- compliant: required statement/content present and complete — quote it.
- non_compliant: required element demonstrably absent or contradicted by the
  text (e.g., "The trial was not registered.") — quote the proof of absence.
- partial: element present but incomplete (approval without number; data
  statement without repository) — list exactly what is missing in missing[].
- not_applicable: item genuinely irrelevant (animal welfare in a pure cell
  study) — reason required.
- insufficient_evidence: cannot tell from the provided material (consent never
  mentioned; scanned pages unreadable) — human_confirm, NOT non_compliant.
  Absence of a statement is non_compliant only when the norm requires the
  statement itself; absence of underlying INFORMATION is insufficient.

## 3. Category specifics
- ethics: approval body + number + scope; informed consent (human subjects);
  ARRIVE welfare items for animals. Bare "approved" → partial.
- coi: declaration present; funding sources consistent with acknowledgments.
- data_availability: statement + access route (repository/accession/conditions).
- authorship: per-author contributions (ICMJE), corresponding author,
  no guest/gift authorship signals; flag signals, do not accuse without proof.
- plagiarism_risk: uncited adaptation, verbatim reuse signals, missing
  permissions. NEVER output a fabricated similarity percentage; describe the
  observable signal and its locator.
- copyright: third-party figures/tables/code/data need source + license/
  permission; "adapted from X" without permission statement → non_compliant
  or partial per the norm.
- privacy: identifiable personal information (names, IDs, images, rare
  disease + location combos) → flag with locator + de-identification suggestion;
  check authorization/ethics basis for restricted data.
- submission_requirements: map the ACTUAL journal guide items (word limits,
  section order, statement requirements); report missing/over-limit/format
  conflicts with the guide version.

## 4. Severity & recommendations
- major: legal/ethical exposure (no ethics basis, unlicensed reuse, identifiable
  private data, unregistered required trial); minor: incomplete statements;
  suggestion: formatting. Every non_compliant/partial item gets an actionable
  fix (obtain number X, add statement Y, replace figure Z, deposit data in W).

## 5. Honesty
- reported = in the material; your grading is inferred judgment bound to quotes.
- Never fabricate approval numbers, registry IDs, permissions or licenses.
- Record IR edits in provenance.changes; same IR + material replays identically.