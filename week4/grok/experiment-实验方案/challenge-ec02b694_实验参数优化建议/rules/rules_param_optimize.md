# Domain rules — param_optimize (实验参数优化建议)

Goal: an executable parameter plan — key parameters, recommended values, feasible
intervals, response-metric definition and verification, search strategy and cost.

1. **Per parameter.** name + current value (if known) + recommended value + unit +
   feasible range [lo,hi] + rationale + evidence. Cover the parameters the research
   question actually depends on (temperature, time, concentration, pH, ...).
2. **Reported vs inferred.** A literature/data optimum quoted verbatim →
   source_optimum + status=reported (evidence required). An agent suggestion →
   status=inferred + rationale + uncertainty + human_confirm. Never blur the two.
3. **Bounds.** The feasible range comes from literature/pilot data; device/material
   limits[] come from manuals/specs (cite them). The engine checks recommended ∈
   range AND ∈ limits; violations are surfaced as partial, not hidden. Safety
   thresholds are hard limits.
4. **Response metric.** Define measurement + unit + direction (higher_better /
   lower_better). Transcribe actual data rows as observations[] {param, value,
   response, evidence(row locator)}; the engine recomputes observed_best and
   descriptive stats. If the data contradicts the recommendation, explain or revise.
5. **Numeric checks.** Express arithmetic as numeric_checks[] {expr, env, min/max/
   equals}; the engine evaluates with safe_eval (AST whitelist). Use it for yield
   gain, dilution/dose, unit conversion, budget/trial counts. Failures are reported.
6. **Search strategy & cost.** State the method (e.g. one-factor-at-a-time around the
   reported optimum, or a bounded grid over the finite parameter domain), n_trials,
   and a stop criterion (e.g. improvement < 2%). cost = per_trial × n_trials vs budget.
7. **Gaps.** Missing limit/data/optimum → not_reported + human_confirm. Conflicting
   reported optima → source_conflict with both locators. Never fabricate a number.
8. **Versioned plans / finite domains.** If the organizer provides versioned candidate
   plans and finite parameter domains, optimize within the stated domain; record the
   plan version and domain bounds with evidence.