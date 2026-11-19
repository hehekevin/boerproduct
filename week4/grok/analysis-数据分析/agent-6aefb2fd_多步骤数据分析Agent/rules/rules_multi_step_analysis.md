# Domain rules — multi_step_analysis (多步骤数据分析Agent)

Goal: an end-to-end pipeline where each step consumes the previous step's real output, every
step is independently verifiable, and the final report's numbers are same-source and recomputable.

## 1. Decompose with explicit boundaries
- Read the dictionary + task; decide which tables/columns to read and how far to compute.
- Steps: load → clean → stats → viz → (query) → interpret. Each step: step_id, kind,
  depends_on (earlier steps only), payload (same schema as the sibling single-kind skill).
- Keep steps small and checkable; one responsibility per step.

## 2. Load & field alignment
- Register every real table; record sha256 + row count + status at load.
- Multi-table/multi-source: align field names/types/units/keys explicitly; output a checkable
  field mapping; flag cross-table key misalignment (human_confirm), never silently join.

## 3. Clean — record impact, no silent loss
- State missing/outlier/duplicate rules + priority; the clean step replaces the shared data
  context so downstream steps use CLEANED rows.
- Record rows before/after and distribution impact (quality report); preserve originals + log.
- Do not impute missing/invalid source values; flag them.

## 4. Stats — assumptions before tests
- Choose method by design (2 groups Welch, >2 ANOVA, etc.); check distribution/independence/
  sample size/multiplicity; state the basis in assumptions. Effect size + CI, not just p.
- Expose computed metrics so the interpret step can reference them ("<analysis_id>.<key>").

## 5. Viz — consistent with the data
- Chart type fits the data + conclusion intent; axes/aggregation/error bars match the underlying
  (cleaned) data; every glyph data-bound. Do not let a figure exaggerate or hide a difference.

## 6. Report — numbers back-filled and cross-checked
- The interpret step writes the narrative AND declares claims {metric, value, tolerance}.
- The engine compares each claimed value to the computed metric (back-fill check). A mismatch
  means the report is not same-source → partial; fix the text or the analysis, never fudge.
- Report text, tables, and figures must all trace to the same computed results; keep version/caliber.

## 7. Dependency cascade & recovery (honest)
- Steps run in order; a step whose dependency failed/is absent is SKIPPED with a reason.
- Step status done|partial|failed|skipped; any non-done propagates to overall partial.
- Failure is locatable per step (provenance: inputs → outputs → status); recover by fixing that
  step's payload and rerunning — downstream recomputes from the shared context.
- Never fabricate a downstream result from a failed upstream step. Save partial early.