# DOMAIN RULES — 文献数据清洗与标准化 (kind=data_cleaning)

## Focus
- 规得齐: same metric → same field name/type/allowed-value set.
- 换得准: unit/format conversion keeps original + formula + precision; compound/prefix/interval correct.
- 合得对: dedup/synonym merge by explainable key; no wrong merges.
- 追得回: every normalized value traceable to source.

## Rules
1. Define field_mapping/allowed_values/target_unit/dedup_keys; normalize fields.
2. Convert units via clean.py preserving original+formula+precision; flag unconvertible (keep original+pending).
3. Merge duplicates only by explainable key; record merged_with + both sources; never merge distinct experiments.
4. Emit cleaned records + anomalies + pending; every record keeps source.

## Self-check
- [ ] fields/types/allowed unified
- [ ] conversion keeps original+formula+precision
- [ ] dedup by explainable key; no wrong merge
- [ ] anomalies+pending+source traceable
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
