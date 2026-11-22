# clean2table-r3 — 文献数据清洗与标准化 Skill（README）

对应赛道：week3 文献阅读「文献数据清洗与标准化」（challenge-f4bca185）。
在 69 分版 clean2table-r2 全部机制之上做**最小化保底增强**，补齐三件可核验能力。

## 1. 文件清单

| 文件 | 作用 |
|------|------|
| `SKILL.md` | Skill 本体：强制协议置顶 + 五步主流程 + 输出 schema + 异常处置表 + 限制与维护 |
| `scripts/clean_run.py` | 清洗引擎（skeleton / profile / run / check 四模式，零第三方依赖，异常全捕获不裸崩） |
| `resources/rules-template.json` | 六类编号规则模板（FM 字段映射 / UC 单位换算 / SN 同义归一 / MM 缺失 / AF 异常 / DD 去重）+ 字段字典 + 冲突策略 |
| `resources/units-table.md` | 单位换算表：SI 前缀、常见线性换算、trace 中间值字段说明、不猜边界 |
| `README.md` | 本文件：使用说明 + 标注示意最小示例 |
| `worklog.md` | 重做记录：相对 r2 的改动与理由 |

## 2. 快速使用

```bash
# 第2步 落骨架（保证任意时刻 result.json 存在且可解析）
python /skills/weekly-skill/scripts/clean_run.py skeleton --case /input/case.json --outdir /app/output
# 第3步 画像（看真实列名/单位/疑似重复）
python /skills/weekly-skill/scripts/clean_run.py profile --case /input/case.json --out /app/work/profile.json
# 据 profile 实例化规则（参照 resources/rules-template.json 改列名/单位/同义组）
# 第4步 跑清洗
python /skills/weekly-skill/scripts/clean_run.py run --case /input/case.json --rules /app/work/rules.json --outdir /app/output
# 第5步 校验（非零退出逐条修复后重跑）
python /skills/weekly-skill/scripts/clean_run.py check --result /app/output/result.json --case /input/case.json
```

换一批表/换列名：只改 `/app/work/rules.json` 的 `condition.column` 与字段字典即可重跑，无需改代码；
重复运行结果一致（规则按 `(priority, rule_id)` 稳定排序，无随机性）。

## 3. 相对 r2 的三项增强（保底路线）

1. **清洗台账逐条嵌入**：每个被改格在 `__raw__[field].ledger` 内嵌
   `{change_id, kind, original, new, rule_id}`，每行带 `__changes__` 变更号索引；
   审阅单行即可核对全部改动，`result.changelog` 仍保留全量台账。
2. **单位换算中间值留痕（可复算）**：每条 convert 变更带 `trace`——
   `factor_source`（si_prefix/rule/identity）、前后缀因子、`net_factor`、`offset`、
   `value_in`/`value_out`、`precision`/`value_final`、`recompute` 公式串；
   复核式：`value_final == round(value_in × net_factor + offset, precision)`。
3. **脏值逐条登记不静默丢弃**：无法清洗的值（未知单位/不可解析格式/去重未判定行）
   逐条进 `uncertainties.dirty_values`（row_id/field/value/reason/pending_id），
   原值保留在表中，与 pending_review 同号关联；check 校验
   `dirty_values == summary.unknown_units` 且 pending 脏值必须逐条登记。

## 4. 标注示意最小示例（示意数据，非正式案例结果）

输入 `demo-case.json`：

```json
{"case_id": "demo-001", "records": [
  {"row_id": "r1", "source": "PaperA", "cap_ug_g": "250 ug/g", "condition": "25C pH7"},
  {"row_id": "r4", "source": "PaperA", "cap_ug_g": "250 ug/g", "condition": "25C pH7"},
  {"row_id": "r5", "source": "PaperB", "cap_ug_g": "12 xyz", "condition": "25C pH7"}]}
```

调用（示意）：

```bash
python scripts/clean_run.py run --case demo-case.json --rules resources/rules-template.json --outdir /tmp/demo
python scripts/clean_run.py check --result /tmp/demo/result.json --case demo-case.json
```

示意输出（**示意，仅标注接口形态**；真实结果以平台 3 个固定案例实际运行为准）：

```jsonc
{
  "case_id": "demo-001",
  "status": "answered",                       // 待确认清单是交付物，不是缺口
  "result": {
    "cleaned_table": {"rows": [{
      "row_id": "r1", "value": 0.25, "__units__": {"value": "mg/g"},
      "__changes__": ["C0001"],               // 增强①：行级台账索引
      "__raw__": {"value": {
        "value_raw": "250 ug/g", "to_unit": "mg/g",
        "trace": {                            // 增强②：中间值留痕，可复算
          "factor_source": "si_prefix",
          "src_prefix_factor": 1e-6, "dst_prefix_factor": 0.001,
          "net_factor": 0.001, "offset": 0,
          "value_in": 250, "value_out": 0.25,
          "precision": 4, "value_final": 0.25,
          "recompute": "250 x (1e-06/0.001) +0 = 0.25"},
        "ledger": {"change_id": "C0001", "kind": "convert",
                   "original": "250 ug/g", "new": 0.25, "rule_id": "UC01"}}}},
      // r4 与 r1 判定键全同且值相容 → merge 进 changelog，判定键含条件指纹
    ],
    "summary": {"rows_in": 3, "rows_out": 2, "changed_cells": 2,
                "merged_groups": 1, "unknown_units": 1, "dirty_values": 1}}
  },
  "claims": [{"claim_id": "CL001", "kind": "inferred", "source_id": "UC01",
              "location": "changelog:C0001", "text": "UC01 换算 1 格，trace 可复算",
              "evidence": [{"paragraph_id": "r1", "quote": "value: 250 ug/g -> 0.25"}]},
             {"claim_id": "CL002", "kind": "reported", "source_id": "r5",
              "location": "uncertainties.dirty_values[P0001]",
              "text": "行 r5 存在无法清洗的脏值 '12 xyz'，原值保留并登记",
              "evidence": [{"paragraph_id": "r5", "quote": "12 xyz"}]}],
  "uncertainties": {
    "dirty_values": [                          // 增强③：脏值逐条登记，不静默丢弃
      {"row_id": "r5", "field": "value", "value": "12 xyz",
       "reason": "无法解析数值/单位，原值保留", "pending_id": "P0001"}],
    "human_review": ["[P0001] 无法解析数值/单位：'12 xyz'（r5）"],
    "summary": "清洗完成：rows_in=3 rows_out=2 changed=2 merged=1 pending=1 dirty=1；改动逐条内嵌行级台账；换算 trace 可复算；脏值逐条登记不丢弃。"}
}
```

## 5. 异常与限制速览

- 单位无法识别/不可解析 → 原值保留 + pending_review + `dirty_values` 逐条登记，不猜。
- 缺失保持空缺不编造；越界只标记不改值；科学冲突只登记不裁决。
- 温标/仿射换算须规则显式给 `factor+offset`；ppm↔mg/L 须规则显式声明近似系数。
- 空表 → `insufficient_evidence`；输入不可解析 → `input_error`；中断 → `partial` 且仍交付。
- `dirty_values` 是登记不是豁免：登记后的值仍留在表中，统计时由使用者决定排除。
