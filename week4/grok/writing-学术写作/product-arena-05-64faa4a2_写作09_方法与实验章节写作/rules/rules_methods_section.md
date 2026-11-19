# Domain rules — methods_section (方法与实验章节写作)

## 1. Extract elements from real material (写得全 / 写得准)
- Read protocol/config/log/code/data-description; register each in `sources[]`.
- Build ordered, executable `sections[]` (Methods + Experiments): each step's input,
  operation, output, decision condition. Do not compress multi-step operations into one sentence.
- Separate train/validation/test flows; hardware, software versions, environment, seed,
  replicates. Do not mix conditions.

## 2. Parameters with source + status (engine-checked)
- `parameters[]`: name, value, unit, target (what it acts on), source, locator, status.
- Every parameter MUST have a source (config/log/author-confirm) — no source = error.
- status: reported (in material) / inferred (computed — show derivation) / not_reported
  (absent → human_confirm) / source_conflict / extraction_failed / insufficient_evidence.
- Align prose numbers with the parameter table; engine runs number-consistency.
- Never invent a value to make a paragraph flow; absent → not_reported + flag.

## 3. Dataset, controls, statistics
- `datasets[]`: name, version, size, preprocessing, split ratio + randomization, subset use.
- Controls: baseline object + version, same-budget condition, evaluation metric +
  statistical method → "compared to baseline" is a comparable conclusion, not an assertion.
- `statistical_methods[]`: test name, alpha, n, variability (SD vs SEM) — state explicitly.

## 4. Reproducibility & limits (做得着 / 说得住)
- `reproducibility`: code_version, environment, seed, commands, data_access. Missing
  fields → not_reported (human_confirm), rendered as "not_reported" in reproducibility.md.
- Limitations point to concrete failure scenarios + applicable scope, not boilerplate.

## 5. Equipment/reagents & honesty
- `equipment[]` (name, count), `reagents[]` (name, vendor, lot) with source locators.
- Distinguish reported vs inferred everywhere; gaps flagged, never fabricated.
- Editable md+docx+csv; traceable revisions; honest status/uncertainty/change_log.