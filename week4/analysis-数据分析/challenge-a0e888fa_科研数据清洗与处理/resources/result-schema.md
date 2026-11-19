# result.json 完整形态（sciclean-r1）

顶层契约字段：`case_id` / `status`（answered|partial|insufficient_evidence|input_error）
/ `result` / `claims` / `uncertainties`。case.json 的 `output_contract` 声明的额外键
按名补齐（无法产出的填 unknown/空数组，绝不删键）。以下为 `result` 内层结构。

```jsonc
{
  "engine": "sciclean-r1/1.0",
  "cleaned_table": {
    "columns": ["row_id", "sample_id", "concentration", "..."],
    "rows": [{
      "row_id": "s01",
      "concentration": 0.25,                    // 清洗后值（数值型定型）
      "__units__": {"concentration": "mg/L"},   // 每字段当前单位
      "__changes__": ["C0001"],                 // 该行全部变更号（行级台账索引）
      "__raw__": {                              // 原值影子：审计链载体
        "concentration": {
          "source_column": "concentration", "value_raw": "250 ug/L",
          "unit_raw": "ug/L", "to_unit": "mg/L",
          "trace": {                            // 换算中间值，可逐步复算
            "factor_source": "si_prefix", "net_factor": 0.001, "offset": 0,
            "value_in": 250, "value_out": 0.25, "precision": 4,
            "value_final": 0.25, "recompute": "250 x (1e-06/0.001) +0 = 0.25"},
          "ledger": {                           // 行级台账（改前/改后/规则）
            "change_id": "C0001", "kind": "convert",
            "original": "250 ug/L", "new": 0.25, "rule_id": "UC01"}
        }
      }
    }]
  },
  "changelog": [{       // 全量逐格台账：每处修改一条，row_id+rule_id 可回放
    "change_id": "C0001", "row_id": "s01", "field": "concentration",
    "original": "250 ug/L", "new": 0.25, "rule_id": "UC01", "kind": "convert",
    "formula": "...", "precision": 4, "trace": {"...": "..."}
  }],
  "pending_review": [{  // 待人工确认清单：不可修复项登记而非静默丢弃
    "pending_id": "P0001", "kind": "unknown_unit_or_format",
    "row_id": "s03", "field": "concentration", "value": "12 xyz",
    "issue": "无法解析数值/单位", "suggest": "人工确认后补规则"
  }],
  "field_mapping": {"map": [{"source_column", "target_field", "rule_id", "rationale"}],
                    "notes": [], "unmapped_fields": []},
  "rules_applied": [{"rule_id", "kind", "priority", "rationale"}],  // 规则事前声明留痕
  "dedup_report": {"merged_groups": [{"kept_row_id", "merged_row_ids", "key", "rule_id"}],
                   "suspected_pairs": []},
  "missing_report": {"fields": {"concentration": 1}, "cells": [{"row_id", "field", "value"}]},
  "anomalies": [{"row_id", "field", "value", "rule_id", "issue"}],   // 异常只标记不改动
  "conflicts": [],      // 同键异值只登记不裁决
  "summary": {"rows_in": 6, "rows_out": 5, "changed_cells": 11, "merged_groups": 1,
              "missing_marked": 1, "unknown_units": 1, "dirty_values": 1,
              "synonyms_normalized": 0, "anomalies": 2, "conflicts": 0,
              "pending_items": 3},
  "artifacts": {"cleaned_csv": "...", "changelog_jsonl": "...", "pending_review_json": "..."},
  "check_standard": ["...算对标准逐条清单..."],
  "efficiency": {"wall_seconds", "rows_in", "rows_out", "rules_evaluated",
                 "changed_cells", "evidence_variants", "reproduce": ["...命令..."]},
  "gain_evidence": {"design", "mechanism_to_metric", "variants": [
                      {"variant": "normal|ablate_<机制>", "ablate": [], "wall_seconds",
                       "metrics": {...}, "fault_injection": {"injected", "injected_by_type",
                       "caught", "missed", "note"}}],
                    "comparison": [{"variant", "metric_deltas", "fault_injection"}],
                    "boundaries": [], "failure_conditions": [], "reproduce": [],
                    "rules_source": "rules_file|auto_derived"},
  "machine_checks": {   // 全量机检三元组，评分器不开附件即可核对
    "checks": [{"item": "...", "template_value": "...", "applied": "...", "match": true}],
    "convert_spot_checks": [{"item", "template_value", "applied", "match"}],
    "gates": [{"gate": "case_read|contract_fields|rules_file|machine_verify",
               "state": "enforced|skipped_not_provided|not_found|unreadable"}],
    "problems": [],     // 非空 ⇒ all_pass=false（verdict 照实嵌入）
    "all_pass": true, "gate_note": ""
  }
}
```

`claims` 每条含 `claim_id/text/kind(reported|inferred)/source_id/location/evidence`
（evidence 为逐字 quote 数组）。`uncertainties` 六键固定：`unreported / unverifiable /
conflicts / human_review / dirty_values / summary`；`dirty_values` 每条含
`row_id/field/value/reason/pending_id`（与 pending_review 同号关联）。

## 机检复核式（评分器可逐条验算）

1. `changed_cells == len(changelog)`；`rows_out == cleaned_table 行数 == cleaned.csv 数据行数`。
2. 行数守恒：`rows_in == rows_out + sum(len(merged_row_ids))`（防静默删行）。
3. 换算汇总守恒：`sum(new) == sum(trace.value_final)`（防篡改或复算失真，仅计双端数值型条目）。
4. 每条 convert 变更：`value_final == round(value_in × net_factor + offset, precision)`，
   区间双端各算不取中点；`formula`/`precision`/`trace` 缺一即 FAIL。
5. 每行 `__changes__` 条数 == 该行 changelog 条数；换算/归一/缺失格内嵌 `ledger`
   且变更号在 `__changes__` 内（审计链逐条可回放）。
6. `pending_review` 非空 ⇒ `uncertainties.human_review` 非空；脏值逐条登记且
   `len(dirty_values) == summary.unknown_units`。
7. 闸门四态显式枚举，非 enforced 即写 gate_note「下游不得宣称已核对」。
