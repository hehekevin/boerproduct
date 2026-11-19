# ERROR HANDLING — library track

Principle: never fabricate, never silent-skip, never write未完成 as完成.

| Situation | Handling | Status signal |
|-|-|-|
| Metadata field absent in all sources | metadata.status=not_reported, value=null | coverage.missing |
| Field derived, not stated | status=inferred + uncertainty note | partial |
| Two sources disagree on a field | status=source_conflict + both evidences | partial |
| Field present but unparseable | status=extraction_failed + reason | partial |
| File unreadable / no permission | recorded in index.unreadable[]; op skipped + reason | partial |
| Duplicate file (same content hash) | grouped in duplicates.content_hash_groups; not overwritten | n_hash_duplicate_groups |
| Same alias claimed by two docs | alias_conflicts surfaced with attribution | partial |
| Version supersedes unknown id | validation error; fix chain | partial |
| Search query has no matching passage | search status=no_hits (not invented hits) | partial |
| Classification: no rule matches | abstain (unclassified), not force-fit | partial |
| Question unsupported by material | insufficient_evidence + human_confirm | partial |
| Annotation locator wrong / quote mismatch | locator_issues reported | partial |
| IR unreadable / build exception | failed/partial; validation + partial artifacts saved | failed/partial |

Always save validation.json + whatever artifacts exist early, then fix and re-run.
result.json carries honest status + sources + uncertainty + change_log + limits.
