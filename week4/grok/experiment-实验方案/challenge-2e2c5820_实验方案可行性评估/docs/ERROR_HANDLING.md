# ERROR HANDLING — experiment track

Principle: never fabricate, never silent-skip, never write 未完成 as 完成.
Finding a blocker/anomaly is task completion (success); a *gap in evidence* is partial.

| Situation | Handling | Status signal |
|-|-|-|
| Required info absent in all sources | status=not_reported, value=null + human_confirm | partial |
| Value derived/suggested, not stated | status=inferred + rationale + uncertainty | confirmation |
| Two sources disagree | status=source_conflict + both evidences | partial |
| Present but unparseable | status=extraction_failed + reason | partial |
| File unreadable / not found | provenance.file_status=file_not_found/read_failed | partial |
| Parameter value outside its range | range_violations surfaced (fix value or widen range with evidence) | partial |
| Recommended outside device/material limit | checks.in_limits=false + human_confirm | partial |
| Feasibility: need > available | verdict=blocker + shortfall arithmetic (a finding, not a gap) | success if traceable |
| Feasibility: no inventory evidence | verdict=not_reported + human_confirm | partial |
| Compare: missing matrix cell | not_reported, excluded from weighting; coverage reported | partial |
| Compare: weight-sensitive choice | margin<0.05 or coverage<60% → human_confirm | partial |
| Anomaly cause without evidence | insufficient_evidence; never asserted as fact | partial |
| Expected/tolerance not reported | within_tolerance=null + note (not guessed) | partial |
| Quote mismatch / bad paragraph id | locator_issues reported | partial |
| IR unreadable / build exception | failed/partial; validation + partial artifacts saved | failed/partial |

Always save validation.json + whatever artifacts exist early, then fix and re-run.
result.json carries honest status + sources + uncertainty + change_log + limits.