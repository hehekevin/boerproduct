# Domain rules — protocol_design (实验方案生成与优化)

Goal: turn the research objective into a protocol an experimenter can schedule,
execute and peer-review — or know exactly what is missing. Cover the six rubric
elements: hypothesis & variables, controls, equipment & materials, time & cost,
parameter ranges, risks & anomalies.

1. **Hypothesis & variables.** Restate the objective as a testable hypothesis.
   Each variable: role (independent/dependent/confounder/controlled), operational
   definition, measurement method, unit, allowed range. A variable with only a name
   is incomplete. Cite the material that defines each measurement.
2. **Controls.** Design blank AND positive/negative/dose-gradient controls as the
   objective demands. For each control state which confounder it excludes. A single
   blank control triggers a warning. Controls must match the research goal.
3. **Equipment & materials.** Bind every step to equipment (model, range/spec) and
   reagents (spec, grade). Mark substitutable vs non-substitutable items. If the
   material gives no model/spec, record not_reported + human_confirm — never invent
   a model number.
4. **Time & cost.** duration_min per step; use parallel_group for steps that run
   concurrently (engine takes max per group, sums the rest). cost per step when
   price material exists; engine sums and compares with objective.budget_cap.
   Sample size and scheduling must be quantified when material allows.
5. **Parameter ranges.** Every key parameter: value + unit + allowed range [lo,hi].
   The range basis must be cited: device manual, pilot experiment or literature
   (evidence locator). A value outside its range is surfaced as range_violations
   (partial) — fix the value or widen the range with evidence, do not hide it.
6. **Risks & anomalies.** Predefine failure modes (contamination, no signal, poor
   reproducibility, insufficient sample), each with a judgement criterion, a
   stop-loss point and an alternative path. "注意安全" alone is not a risk plan.
7. **Optimizations.** status=reported when quoted from material (evidence required);
   status=inferred for agent suggestions (rationale + evidence + uncertainty; routed
   to confirmations). Never write an unconfirmed suggestion as an executable fact.
8. **Confirmations.** Safety, ethics, equipment availability and expert judgement go
   to confirmations[] with handling=human_confirm. Planning scenarios are not claimed
   actual labs, vendor quotes or safety approvals.
9. **Versioned plans.** If the organizer provides 3 versioned candidate plans,
   register them in protocols[] and base the design on the actual latest version;
   record which version each step/parameter comes from (evidence + provenance.changes).