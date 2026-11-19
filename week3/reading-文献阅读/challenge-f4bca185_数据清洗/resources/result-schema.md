# result.json 输出契约（clean2table-r5）

本文件是 SKILL.md 第 2 节的完整展开版。SKILL.md 只给必背字段清单；本文件给完整 JSON 形态与逐字段语义，
供 Agent 与使用者对照核对。**本文件是格式说明，不是正式案例答案**；真实结果以平台 3 个固定案例实际运行为准。

## 顶层结构

平台通用契约五字段（一个不缺，extra 键按 case.json 的 output_contract 补）：

| 键 | 语义 | 失败/无法产出时 |
|---|---|---|
| `case_id` | 取自 case.json，与输入逐字一致 | 填 "unknown"，并写入 uncertainties |
| `status` | `answered` / `partial` / `insufficient_evidence` / `input_error` | 如实降级，不省略键 |
| `result` | 主产物（全量内嵌，不只给附件路径） | 保留键，填 {} 并说明 |
| `claims` | 关键结论，每条带证据定位与逐字摘录 | 空数组 |
| `uncertainties` | 未报告/无法判断/冲突/待人工/脏值/摘要 | 六键齐全 |

## result 字段清单

| 字段 | 内容 | 对应评分六方面 |
|---|---|---|
| `cleaned_table` | columns + rows；每行带 row_id、__raw__ 原值影子、__changes__ 台账索引、__units__ | 主产物 |
| `changelog` | 逐格变更：change_id/row_id/field/original/new/rule_id/kind/formula/precision/trace | 来源与变更记录 |
| `pending_review` | 待人工确认清单：pending_id/kind/row_id/field/value/issue/suggest | 缺失与异常 |
| `field_mapping` | map（源列→规范字段+rule_id+rationale）、unmapped_fields、notes | 字段规范 |
| `rules_applied` | 生效规则：rule_id/kind/priority/rationale | 规则库 |
| `dedup_report` | merged_groups（kept_row_id/merged_row_ids/key/rule_id）、suspected_pairs | 重复记录 |
| `missing_report` | fields（各字段缺失数）+ cells（row_id/field 清单） | 缺失与异常 |
| `anomalies` | 越界/异常：row_id/field/value/rule_id/issue（原值保留） | 缺失与异常 |
| `conflicts` | 科学冲突登记：what/where/field/values/rule_id（只登记不裁决） | 缺失与异常 |
| `summary` | rows_in/rows_out/changed_cells/merged_groups/missing_marked/unknown_units/dirty_values/synonyms_normalized/anomalies/conflicts/pending_items | 汇总 |
| `artifacts` | cleaned_csv / changelog_jsonl / pending_review_json 路径 | 交付物 |
| `check_standard` | 预先定义的"算对"标准清单（与第5步校验点一致） | 可核验性 |
| `efficiency` | 可自动采集的效率计数 + 复现命令 | 效率增益 |
| `gain_evidence` | 同输入双跑对照（机制→指标映射/逐项对照/边界/失效条件） | 增益可验证性 |
| `machine_checks` | 全量三元组 + 换算抽检 + 闸门四态 | 可核验性 |

## 关键子结构示例（示意，非正式答案）

```json
{
  "case_id": "demo-001",
  "status": "answered",
  "result": {
    "cleaned_table": {"columns": ["row_id", "value"], "rows": [
      {"row_id": "r1", "value": 0.25, "__units__": {"value": "mg/g"},
       "__changes__": ["C0001"],
       "__raw__": {"value": {"source_column": "cap_ug_g", "value_raw": "250 ug/g",
                             "unit_raw": "ug/g", "to_unit": "mg/g",
                             "trace": {"factor_source": "si_prefix", "src_prefix": "u",
                                       "src_prefix_factor": 1e-6, "dst_prefix": "m",
                                       "dst_prefix_factor": 1e-3, "net_factor": 0.001,
                                       "offset": 0, "src_unit": "ug/g", "dst_unit": "mg/g",
                                       "value_in": 250, "value_out": 0.25, "precision": 4,
                                       "value_final": 0.25,
                                       "recompute": "250 x (1e-06/0.001) +0 = 0.25"},
                             "ledger": {"change_id": "C0001", "kind": "convert",
                                        "original": "250 ug/g", "new": 0.25, "rule_id": "UC01"}}}
    ]},
    "changelog": [{"change_id": "C0001", "row_id": "r1", "field": "value",
                   "original": "250 ug/g", "new": 0.25, "rule_id": "UC01", "kind": "convert",
                   "formula": "250 ug/g x 0.001 +0 = 0.25 mg/g", "precision": 4,
                   "trace": {"factor_source": "si_prefix", "net_factor": 0.001,
                             "value_in": 250, "value_out": 0.25, "precision": 4,
                             "recompute": "250 x (1e-06/0.001) +0 = 0.25"}}],
    "pending_review": [{"pending_id": "P0001", "kind": "unknown_unit",
                        "row_id": "r5", "field": "value", "value": "12 xyz",
                        "issue": "无法解析数值/单位", "suggest": "人工确认后补规则"}],
    "field_mapping": {"map": [{"source_column": "cap_ug_g", "target_field": "value",
                               "rule_id": "FM02", "rationale": "字段字典别名匹配"}],
                      "unmapped_fields": ["…"], "notes": ["…"]},
    "rules_applied": [{"rule_id": "UC01", "kind": "unit_convert", "priority": 20,
                       "rationale": "1 ug/g = 0.001 mg/g"}],
    "dedup_report": {"merged_groups": [{"kept_row_id": "r1", "merged_row_ids": ["r4"],
                                        "key": ["pb2+", "adsorption_capacity", "25c ph7|papera"],
                                        "rule_id": "DD01"}],
                     "suspected_pairs": [{"row_a": "r2", "row_b": "r5",
                                          "reason": "条件指纹不同"}]},
    "missing_report": {"fields": {"value": 1}, "cells": [{"row_id": "r3", "field": "value"}]},
    "anomalies": [{"row_id": "…", "field": "value", "value": "…", "rule_id": "AF01", "issue": "…"}],
    "conflicts": [{"what": "同判定键行值不一致（疑似科学冲突，不裁决）",
                   "where": ["r2", "r5"], "field": "value", "values": ["0.25", "0.41"],
                   "rule_id": "DD01"}],
    "summary": {"rows_in": 4, "rows_out": 3, "changed_cells": 3, "merged_groups": 1,
                "missing_marked": 1, "unknown_units": 1, "dirty_values": 1,
                "synonyms_normalized": 2, "anomalies": 0, "conflicts": 0, "pending_items": 1},
    "artifacts": {"cleaned_csv": "/app/output/cleaned.csv",
                  "changelog_jsonl": "/app/output/changelog.jsonl",
                  "pending_review_json": "/app/output/pending_review.json"},
    "check_standard": ["output_contract 键一个不缺", "…"],
    "efficiency": {"wall_seconds": 0.02, "rows_in": 4, "rows_out": 3, "rules_evaluated": 12,
                   "changed_cells": 3, "pending_items": 1, "dirty_values": 1,
                   "reproduce": ["python3 …/clean_run.py run --case … --outdir …"],
                   "note": "wall_seconds 为引擎单趟耗时；模型请求数由平台统计，引擎不臆造。"},
    "gain_evidence": {
      "design": "同输入同规则多档真实执行对照：normal 全机制 vs ablate_<机制> 单变量退化",
      "mechanism_to_metric": {"unit_convert": "机制=单位换算规则 → 指标=convert_cells",
                              "machine_verify": "机制=换算抽检机检 → 指标=fault_injection.missed"},
      "variants": [{"variant": "normal", "ablate": [], "wall_seconds": 0.01,
                    "metrics": {"convert_cells": 3, "pending_items": 1, "dirty_values": 1},
                    "fault_injection": {"injected": 2, "caught": 2, "missed": 0}}],
      "comparison": [{"variant": "ablate_spot", "ablate": ["spot"],
                      "metric_deltas": {"convert_cells": {"normal": 3, "variant": 3, "delta": 0}},
                      "fault_injection": {"injected": 2, "caught": 0, "missed": 2}}],
      "boundaries": ["对照只在同一输入、同一规则集下成立", "…"],
      "failure_conditions": ["输入无可识别行数据→对照无意义", "…"],
      "reproduce": ["python3 …/clean_run.py evidence --case … --outdir …"]},
    "machine_checks": {
      "triple_format": "{item, template_value, applied, match}",
      "checks": [{"item": "changed_cells == changelog 条数", "template_value": 3,
                  "applied": 3, "match": true}],
      "convert_spot_checks": [{"item": "changelog[C0001] 复算 round(value_in x net_factor + offset, precision)",
                               "template_value": "round(250 x 0.001 + 0, 4) == 0.25",
                               "applied": 0.25, "match": true}],
      "gates": [{"gate": "case_read", "state": "enforced", "note": ""},
                {"gate": "contract_fields", "state": "enforced", "note": ""},
                {"gate": "rules_file", "state": "enforced", "note": ""},
                {"gate": "machine_verify", "state": "enforced",
                 "note": "全量三元组校验 + 换算抽检机检"}],
      "problems": [], "all_pass": true,
      "gate_note": "闸门未全部 enforced 时下游不得宣称已核对"}
  },
  "claims": [{"claim_id": "CL001", "text": "行 r1 与 r4 判定为重复记录并合并（规则 DD01）",
              "kind": "inferred", "source_id": "r1", "location": "rows:r1",
              "evidence": [{"paragraph_id": "r1", "quote": "value='250 ug/g'"}]}],
  "uncertainties": {"unreported": [{"row_id": "r3", "field": "value"}],
                    "unverifiable": ["无法清洗的脏值 1 处，已逐条登记 dirty_values"],
                    "conflicts": [{"what": "…", "where": ["r2", "r5"]}],
                    "human_review": ["[P0001] 无法解析数值/单位（r5）"],
                    "dirty_values": [{"row_id": "r5", "field": "value", "value": "12 xyz",
                                      "reason": "无法解析数值/单位，原值保留", "pending_id": "P0001"}],
                    "summary": "清洗完成：rows_in=4 rows_out=3 changed=3 …"}
}
```

## 字段语义要点

- `__raw__[field]`：原值影子，含 source_column / value_raw / unit_raw / to_unit / trace / ledger。**原值永不删除**。
- `__changes__`：该行全部 change_id 索引；`__raw__[field].ledger`：被改格的逐条台账。两者必须一致（机检会查）。
- `trace`：换算中间值，复核式 `value_final == round(value_in × net_factor + offset, precision)`；区间换算双端各算、不取中点。
- `dirty_values`：无法清洗的值逐条登记（row_id/field/value/reason/pending_id），与 `pending_review` 同号关联；`summary.dirty_values == summary.unknown_units`。
- `machine_checks.problems` 非空 ⇒ `all_pass=false`：**verdict 照实记录，进程退出码恒 0**，禁止以非零码中断交付。
- `gates[].state` 取值 `enforced` / `skipped_not_provided` / `not_found` / `unreadable`；没跑 ≠ 通过。
