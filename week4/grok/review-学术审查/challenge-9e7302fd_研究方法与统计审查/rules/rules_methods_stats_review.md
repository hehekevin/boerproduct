# Domain rules — methods_stats_review (研究方法与统计审查)

Goal: every methods/statistics opinion lands on a specific manuscript location;
severity matches the defect nature; a reviewer can re-run and get the same sheet.

## 1. Design audit (dimension: design)
- Design type vs the research question it claims to answer.
- Controls present and appropriate? Grouping/allocation described? Blinding and
  bias control stated? Primary endpoint and hypothesis pre-specified?
- Missing design element that threatens validity → major confirmed (quote the
  methods text showing the gap). Acceptable design with thin description →
  minor (reporting), not major.

## 2. Variables (dimension: variables)
- Exposure/outcome/covariate/group definitions, measurement instruments, coding.
- Cut-points justified? Unit conversions correct? Missing-value handling stated?
- Variable type (continuous/ordinal/categorical/count) must fit the model used.

## 3. Statistical tests (dimension: statistical_test / assumptions)
- Test matches data structure, distribution assumptions, sample independence.
- Multiple comparisons corrected? Repeated measures handled? Interactions and
  sensitivity analyses addressed where needed?
- Assumptions unreported ≠ violated: use suspected or a reporting finding,
  never confirmed violation without evidence.

## 4. Sample size & power (dimension: sample_size_power)
- Estimation basis, effect-size source, alpha and power settings reported?
- Actual enrollment vs estimated; dropout/exclusions and how handled.
- No justification at all → major if it undermines the main claim, else minor.

## 5. Results reporting (dimension: effect_size / p_ci_interpretation / reporting)
- Effect size with CI, exact p (not just "p<0.05"), statistic + df.
- p-value interpretation: significance ≠ effect importance; CI interpretation
  must match the interval; "no difference" ≠ equivalence.
- Figure/table vs text numeric consistency.

## 6. Recomputation (stats_checks[]) — the core discipline
- For EVERY reported statistic that the provided data can check, create a
  stats_check: describe (mean/sd/n/quartiles of a field), correlation (r),
  linreg (slope/intercept/r2), or expr (AST-safe arithmetic, e.g. CI bounds,
  t-statistic from mean/sd/n, percentage checks).
- Point data.source_id at the REGISTERED real data file and name the exact
  fields; alternatively transcribe the actual series into values/xs/ys and say
  so. Never type numbers from memory.
- reported{} must carry an evidence locator to the manuscript sentence/table
  cell where the value appears.
- Tolerance: default rel 5% / abs 1e-9; tighten (e.g. rel 0.005) for values
  reported to few decimals, and state why in the description.
- mismatch → a confirmed reporting/consistency finding with BOTH values.
- not_recomputable (missing file/field, n<2, zero variance) → honest gap +
  uncertainty; keep the reported value labeled "reported", never "verified".

## 7. Honesty
- reported = printed in the manuscript; computed = engine output from real data;
  inferred = your methodological judgment (bind it to quotes).
- Missing protocol/data → insufficient_evidence + human_confirm, not guesses.
- Record IR edits in provenance.changes; the same IR + data must replay identically.