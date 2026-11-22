# field2table-r3 — 使用与方法说明

文献结论与数据提取 Skill（week3 littrack challenge-105b70ee 重做版）。按
`/input/target-fields.json` 的 field_id 清单逐字段抽取研究结论、实验条件、关键指标与
数据点；值逐字回挂 paragraph_id+quote；每个 field_id 强制一行、每行强制一条对应
claim、每行记录五源检索日志（search_log）。

## 相比 r2（64.33 分版本）的关键改进

| 改进 | 说明 |
|---|---|
| 覆盖密度门禁 | target-fields 每个 field_id 必须在 result.fields 各有一行（哪怕 not_reported/null），check.py 漏行=FAIL |
| 每行一条 claim | 每个字段行（含未报告/冲突/失败行）在顶层 claims 有 `claim-<field_id>` 条目，check.py 缺 claim=FAIL |
| 逐字段 search_log | 每行登记五类来源（表格/结果段/图注/摘要/补充材料）的检索记录；not_reported 判定因此有据 |
| 骨架+段落收割合一 | skeleton.py 一次调用同时产出全字段骨架与 /app/work/paragraphs.json（供逐字校验） |
| 范围值校验修正 | `2.8-4.3` 类正数范围不再被误判为负数 |

## 调用步骤（评测时，Agent 按 SKILL.md 执行）

1. 读 `/input/target-fields.json`、`/input/case.json`、task.md，抄下全部 field_id（数总数）。
2. 落骨架（第一个写盘动作）：
   ```bash
   python /skills/weekly-skill/scripts/skeleton.py --fields /input/target-fields.json \
     --case /input/case.json --out /app/output/result.json --paras /app/work/paragraphs.json
   ```
3. 逐字段全源定位（正文/表格/图注/补充材料 sweep，记 search_log）。
4. 逐字段成行 + 逐字段成 claim（`claim-<field_id>`）。
5. 校验交付：
   ```bash
   python /skills/weekly-skill/scripts/check.py --result /app/output/result.json \
     --case /input/case.json --fields /input/target-fields.json \
     --paras /app/work/paragraphs.json --out /app/work/check-report.json
   ```
   退出码非 0 按报告修复直到 PASS。

## 输入 / 输出

- 输入：`/input/case.json`（案例、材料段落、output_contract）、`/input/target-fields.json`
  （field_id 清单，兼容 fields/targets/items 包装或纯数组）、task.md。PDF 材料用环境 pdf
  工具取文本，证据用页码+段/表行/图注号定位。
- 输出：`/app/output/result.json`，顶层五键（case_id/status/result/claims/uncertainties）
  + output_contract 附加键 + changelog；主产物为 result.fields 的结构化字段表（完整内嵌）。

## 最小示例（合成数据，非正式案例答案）

`examples/` 三件套：`example-fields.json`（5 个字段）、`example-input.json`（3 段合成
论文材料）、`example-result.json`（示意输出）。本地自测：

```bash
python scripts/skeleton.py --fields examples/example-fields.json --case examples/example-input.json \
  --out /tmp/skel.json --paras /tmp/paras.json
python scripts/check.py --result examples/example-result.json --case examples/example-input.json \
  --fields examples/example-fields.json --paras /tmp/paras.json --out /tmp/check.json
```

标注示意（result.fields 单行 + 对应 claim，截取自 example-result.json）：

```json
{"field_id": "capacity_retention_doped", "status": "reported",
 "value": {"scalar": 84.3, "range": null, "text": null},
 "units": "%", "statistic": "value",
 "conditions": ["1C 倍率", "200 次循环", "2.8-4.3 V"], "comparator": "undoped baseline",
 "evidence": [{"paragraph_id": "p02", "quote": "the discharge capacity retention was 84.3% for the doped sample", "locator": "§Results"}],
 "verbatim_number": "84.3", "claim_layer": "n/a",
 "search_log": ["表格: 材料未提供", "结果段 p02: 查到", "图注: 无", "摘要: 无", "补充材料: 材料未提供"]}
```

```json
{"claim_id": "claim-capacity_retention_doped", "text": "掺杂样品在 1C、2.8-4.3 V 下循环 200 次后放电容量保持率为 84.3%",
 "layer": "n/a", "kind": "reported", "source_id": "paper", "location": "p02 §Results",
 "evidence": [{"paragraph_id": "p02", "quote": "the discharge capacity retention was 84.3% for the doped sample"}]}
```

## 依赖

仅 Python 3 标准库（json/re/argparse/os），无第三方包；脚本不可用时 SKILL.md 第2步
允许手写等价骨架，绝不空盘。

## 异常处置与限制

- 扫描件无文本层 → extraction_failed + 如实降级；表格跨页断裂不拼接猜数；
  单位缺失写 `unit_not_reported`；未报告≠0；数值冲突 conflicts 双方引文并列；
  预算触顶（>48 次请求或 >700 秒）立即收尾交付 partial。
- 机械校验兜底字面正确性与覆盖密度，不能替代语义抽查；不做单位换算与跨行合并推断。
