# Domain rules — data_cleaning (科研数据清洗与处理)

Goal: turn a fault-injected real table into a downstream-ready cleaned table where
every field treatment has an explicit rule + evidence, and the quality report numbers
are provably identical to the cleaned result.

## 0. Read the dictionary before touching data
- Register EVERY actual input file in sources[] (table, dictionary, workorder, QC rules).
- Extract: field semantics, sentinel codes and their meaning, what a true 0 means,
  the real primary key, target units, physical/QC bounds, encoding notes.
- The organizer material (revision2) is published aggregate transcriptions with injected
  storage/encoding faults — NOT raw experiments. Do not infer population statistics.

## 1. Missing values — classify, NEVER impute
- Distinguish: not_detected (ND), below_detection_limit (<LOD), missing_entry (blank),
  storage_fault_sentinel (-999 etc.), and true zero (0). Map each via params.sentinel_map.
- DO NOT impute missing/invalid source values (no mean/median/0 fill). Flag them: the
  cleaned cell becomes empty, the original value + label + rule stay in cleaning_log.json.
- "0" is a valid detected value when the dictionary says so — never reclassify it as missing.
- Report per-column missing rate computed from the cleaned table.

## 2. Duplicates — real primary key, full provenance
- Key = the dictionary's real identifier (sample_id + timestamp, subject_id + visit...),
  NOT whole-row equality. Normalize case/whitespace before comparing (engine does this).
- Decide keep=first|last with a stated reason (e.g., first export is authoritative).
- Every removed row is logged in full (key, dropped record, kept row index, rule, reason).
- Near-duplicates with conflicting fields: surface the conflict in uncertainty, do not
  silently merge values.

## 3. Units & formats — reversible, no silent precision loss
- Harmonize to the dictionary target unit. factor_expr is evaluated by the AST-whitelist
  safe_eval (e.g., "1000", "1/1000"); the inverse expression is logged so the conversion
  is reversible. Original values remain in the snapshot + log.
- Convert only rows whose unit_column matches from_unit; unknown unit labels → do not
  guess a factor; flag human_confirm.
- type_cast for numeric-text mixing (commas, scientific notation); cast failures are
  logged as extraction_failed, original kept. rename_column aligns abbreviations to the
  dictionary; keep the mapping in the log.

## 4. Outliers — diagnose, justify, default to flag
- Combine physical/QC bounds (dictionary) with distribution diagnostics (IQR k=1.5 or
  z-score threshold 3). State which rule fired and the computed bounds.
- Default action=flag: an extreme value may be a real high value or a pipetting error —
  keep it, flag it, and add uncertainty + human_confirm. action=remove requires an
  explicit reason and is logged row-by-row.
- Note when a diagnostic flags a dictionary-valid value (e.g., true zero below the lower
  IQR fence): retain it and explain in uncertainty.

## 5. Quality report — numbers must equal the result table
- The engine recomputes per-column missing counts/rates, flagged outliers, conversions,
  duplicate removals and row counts FROM the cleaned rows and compares with the log
  (consistency_check). Any mismatch → status partial, never paper over it.
- Report field-level issue list + treatment actions + impact scope (rows before/after).

## 6. Replayability & safety
- Original file is NEVER overwritten; an original_<dataset> snapshot is exported.
- Operations apply in IR order; the log is the replay record (op_id, row locator,
  original → new, rule, evidence). Another person must reproduce the cleaned table.
- Record input sha256 (engine does at load), rules, and run status in result.json.
- Empty table / all-missing column / unreadable file → honest dataset status + failed op
  with reason; partial result early, improve incrementally.