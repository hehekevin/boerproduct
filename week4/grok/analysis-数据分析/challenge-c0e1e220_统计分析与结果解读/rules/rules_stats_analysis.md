# Domain rules — stats_analysis (统计分析与结果解读)

Goal: numbers that are recomputable from the real table, with the right method for the
design, effect size + CI, explicit assumptions, and an interpretation a researcher can act on.

## 1. Read the dictionary first
- Confirm outcome column, group/design factor, units, missing codes, pairing/independence.
- Register the real table in datasets[]; never assume column meaning from a label.
- If the source is a SQLite export, query it read-only first (sibling db skill) or read
  the exported table; record the actual columns.

## 2. Descriptive statistics — state the caliber
- Report n, mean, sd, variance, median, quartiles, min, max, missing count, skew/kurtosis.
- Missing/non-numeric cells are excluded PAIRWISE and counted — never treated as 0, never
  silently row-deleted without saying how many. No imputation of source values.
- Give the unit and the population/sample caliber; add the mean's 95% CI (t-based).

## 3. Inferential method selection (avoid misuse)
- 2 independent groups → Welch t (does not assume equal variance). Screen normality via
  skewness/excess-kurtosis (|skew|>1 or |kurt|>2 flags concern) and variance ratio F-test;
  when non-normal or requested, also report Mann-Whitney U (normal approximation with tie
  correction — exact small-sample distribution is NOT available in stdlib; say so).
- >2 groups → one-way ANOVA (F, p, eta²). NEVER run a two-sample t-test on three groups.
  Post-hoc pairwise comparisons are not performed by the engine — state this limit.
- Paired/repeated design → note it in assumptions; the engine's independent-sample tests
  are not valid for paired data without a paired analysis (flag human_confirm).
- Correlation → Pearson r (linearity + interval scale) with t-test p and Fisher-z CI;
  Spearman (rank) when monotonic-but-nonlinear or ordinal. Regression → OLS slope/intercept/
  R², slope SE/t/p/CI, residual sd; state linear/independent/homoscedastic error assumptions.

## 4. Effect size + confidence interval (not just p)
- Group difference: Cohen's d (pooled sd) + 95% CI of the mean difference (Welch df).
- ANOVA: eta² (explained proportion). Correlation: r + Fisher-z CI. Regression: slope CI.
- A CI is a range for the ESTIMATE, not for individual values — interpret it correctly.
- p alone is never "proof of effectiveness"; report magnitude + direction + uncertainty.

## 5. Multiplicity
- Declare a `family` string on analyses that belong to one comparison family; the engine
  applies Holm adjustment and reports p_adjusted_holm. Do not fish across methods.

## 6. Interpretation discipline (required per analysis)
- Tie every claim to the computed number (auto_summary provides the exact values).
- Distinguish statistical significance from practical/scientific importance.
- Correlation/regression ≠ causation; note confounding and design limits.
- Mark remaining uncertainty and human_confirm items; never overstate.

## 7. Honest gaps & stdlib limits
- n<2 per group, <3 complete pairs, or zero variance → insufficient_evidence with reason.
- Formal Shapiro-Wilk / Levene and exact Mann-Whitney are not in stdlib; the engine uses
  documented screens/approximations and labels them. Do not fabricate a test you cannot run.
- Every result carries evidence {source_id, dataset_id, column(s), n_rows_used}; status
  computed | insufficient_evidence | failed. Result status success/partial/failed honest.