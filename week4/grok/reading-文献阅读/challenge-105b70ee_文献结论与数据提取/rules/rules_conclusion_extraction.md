# DOMAIN RULES — 文献结论与数据提取 (kind=conclusion_extraction)

## Focus
- Read /input/target-fields.json; emit one result per field_id.
- Preserve scalar/units/statistic/experimental condition/comparator + exact paragraph_id/quote.
- Distinguish author conclusion / limitation / speculation; no '可能'→fact.
- Every field traceable to original location.

## Rules
1. Iterate requested field_ids; extract value+units+statistic+condition+comparator with quote locator.
2. Tag reported vs inferred; speculation kept as speculation; attach condition to every number.
3. Handle cross-page tables/supplement; flag missing fields as insufficient_evidence.
4. Emit per-field results + evidence map; result.json honest.

## Self-check
- [ ] one result per field_id
- [ ] units/condition/comparator preserved
- [ ] reported vs inferred; speculation not factored
- [ ] paragraph_id/quote traceable
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
