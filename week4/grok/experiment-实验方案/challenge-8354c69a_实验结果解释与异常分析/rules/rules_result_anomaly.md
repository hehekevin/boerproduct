# Domain rules — result_anomaly (实验结果解释与异常分析)

Goal: five checkable conclusion segments — trend, anomaly points, possible causes,
verification steps, follow-up suggestions — each re-computable from the raw data.

1. **Expected vs observed.** Per metric: expected value + unit + tolerance (absolute
   number, or {abs, pct}). The engine computes deviation = mean(observed) − expected
   and within_tolerance (every provided tolerance must hold). Missing expected or
   tolerance → within=null + an explicit note; never guess a pass/fail.
2. **Replicates & outliers.** Transcribe the actual replicate readings. The engine
   computes describe (n/mean/sd/min/quartiles/max). Outlier flags use the IQR rule
   (outside [Q25−1.5·IQR, Q75+1.5·IQR], applied only when n≥4) and are labelled
   inferred flags, not confirmed measurement errors. n<4 → state insufficient
   replicates rather than forcing a flag.
3. **Trend.** When readings form a series {x,y}, the engine runs linreg
   (slope/intercept/r2) and labels increasing/decreasing/flat. Any claimed trend,
   inflection or magnitude must match the raw readings; cite the data field.
4. **Candidate causes — never facts.** Each anomaly lists candidate_causes with a
   support level: supported / partially_supported / contradicted / unknown. The engine
   ranks by support weight (3/1/−1/0). A cause marked supported, partially_supported
   or contradicted REQUIRES an evidence locator (calibration record, run log, control,
   literature). Without evidence it is insufficient_evidence + human_confirm. Do not
   assert a single cause as the confirmed truth.
5. **Actions & follow-up.** Every anomaly gets a corrective action. Add follow_up
   experiments that discriminate between the top candidate causes (e.g. re-calibrate
   and re-measure; repeat with immediate measurement to remove a delay confounder).
6. **Coverage & honesty.** Cover all metrics, controls, replicates and edge cases; do
   not cherry-pick. State the unexplained part explicitly. Distinguish reported
   (quoted) from inferred (diagnosed) conclusions. Conflicting records →
   source_conflict with both locators. Never fabricate a reading, expected value,
   tolerance or cause.