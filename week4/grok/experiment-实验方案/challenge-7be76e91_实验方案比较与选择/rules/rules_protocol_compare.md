# Domain rules — protocol_compare (实验方案比较与选择)

Goal: multiple candidates on ONE comparable matrix, a completed comparison, and a
defensible, independently re-computable choice.

1. **Common matrix.** Identical criteria, units and measurement口径 for every
   candidate. Convert units explicitly and record the conversion. Cover the seven
   required fields plus the key comparison dimensions (cost, time, yield, safety,
   reproducibility, ...).
2. **Per-cell provenance.** Each cell {criterion_id, candidate_id, value, status,
   evidence} quotes the actual plan figure (source_id + paragraph_id + quote). A
   figure the material does not state → status=not_reported, value=null; it is
   excluded from weighting and counted in coverage. Never impute a missing number.
3. **Criteria.** direction = higher_better (yield/safety/reproducibility) or
   lower_better (cost/time/risk). weight ≥ 0. The engine renormalizes weights to sum 1
   and warns if the raw sum ≠ 1. Cite the task/material basis for each weight.
4. **Method (engine).** Min-max normalize each criterion across candidates with
   reported/inferred numeric values; invert lower_better; all-equal → 0.5. Score =
   Σ w_i·norm_i; rank descending; margin = top − second. Coverage = covered criteria /
   total criteria per candidate.
5. **Defensibility.** Report per-criterion tradeoffs (winner + value + evidence) and
   ±20% weight sensitivity (winner flips). If margin < 0.05 or any candidate coverage
   < 60%, the choice is fragile → human_confirm; state this, do not overclaim.
6. **Qualitative criteria.** Supply a justified 0–1 score (status=inferred + rationale
   + evidence) or leave not_reported. Never silently convert prose into a number.
7. **Conflicts.** Two sources give different figures for one cell → source_conflict
   with both locators; do not average silently.
8. **Versioned plans.** Register each candidate version in protocols[]; candidates
   reference protocol_id + version; cite the actual version text. The recommendation
   must name the chosen version explicitly.