# Domain rules — quality_appraisal (文献研究质量评价)

Challenge `challenge-bace1c46`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Define the scale FIRST (appraisal_tool.dimensions): design/allocation, sampling & power, measurement/outcomes, statistics, reporting completeness — each with what evidence decides it and when it is not assessable. Restrict applicability via applies_to + record study_type; judge every APPLICABLE dimension (missing ones are flagged, not fabricated).
2. Every judgment yes/partial/no needs an evidence locator at sentence or table level in the ACTUAL document: paragraph_id/page/table + the original quote. A grade without a locator is not reviewable; a locator without a real quote is not evidence.
3. If the document does not report what the dimension needs, judgment = insufficient_evidence (abstain) with grade unclear/not_assessable or none — NEVER a plausible-looking guess. Abstaining on a critical dimension forces overall unclear.
4. Grades: low / some_concerns / high / unclear per dimension; overall = worst_domain over judged dimensions (engine), with the abstain policy stated. Distinguish 'clearly present', 'possibly present', 'no sign' and 'insufficient evidence' for bias domains.
5. Read the actual methods/results, not the abstract's self-praise: 'reasonable design, adequate sample' without locators is exactly the failure mode this skill prevents.
6. Applicability mismatches (e.g. an RCT-only dimension on a cohort) are recorded as not applicable with basis, not silently skipped.
7. Output is appraisal assistance for a human reviewer — not peer review, not a clinical recommendation; a second person must be able to re-derive every grade from the locators.

## IR fields enforced by validate_ir (kind-specific)

```
appraisal_tool: {name, aggregation?: worst_domain,
  critical_dimensions?: [dim_id],
  dimensions: [{id, name, applies_to?: [study_type]}]}   # REQUIRED scale
records[] extras: study_type? (rct/cohort/...),
  dimensions: [{dimension_id, judgment: yes|partial|no|insufficient_evidence,
    grade?: low|some_concerns|high|unclear, rationale?,
    evidence: [{source_id, paragraph_id?|page?|table?, quote?}]}]
# non-abstain judgment REQUIRES evidence + grade;
# abstain MUST NOT carry a confident grade
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] scale defined with applicability; every applicable dimension judged or flagged
- [ ] every non-abstain judgment has sentence/table locator + quote + grade + rationale
- [ ] unreported -> abstain (unclear), never fabricated; critical abstain -> overall unclear
- [ ] aggregation rule stated; second reviewer can re-derive grades from locators
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
