---
name: recall-coverage-audit
description: Search recall coverage and miss analysis skill (focused). Compares the reference set against retrieved records using deterministic identifier matching (DOI/PMID exact) plus title+author+year fuzzy match, outputs coverage/recall/miss-rate and classifies each miss by actionable reason (synonym_not_covered / field_too_narrow / time_window / source_not_indexed / identifier_anomaly). Only coverage measurement and miss classification are in scope; supplementary re-search is a one-line note. Use when the task asks to measure search recall against a frozen reference set.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **命中判定用脚本机械做**：标识符精确匹配 + 标题作者年份近似，覆盖率/遗漏率由脚本计算，不手填。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定冻结参考集（reference_set，4 篇）+ 检索结果（retrieved_records），完成「命中判定 → 覆盖率/遗漏率 → 漏检归类」。只做覆盖测量与漏检分类；补充检索是收尾一句话。命中判定规则事前声明，逐条可复核。
- 输入：`/input/case.json`（research_question + reference_set + queries + retrieved_records + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 覆盖测量与漏检分类（核心，1 脚本 + 1 次响应）
```bash
python3 /skills/weekly-skill/scripts/coverage_measure.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/coverage.json --emit-into
```
- 脚本机械做：对每条 reference 判 `hit`（DOI 精确相等，或标题归一化后相同）vs `miss`，计算 `coverage_rate` / `miss_rate`
- 模型对每条 miss 归类 `miss_reason` ∈ `synonym_not_covered` / `field_too_narrow` / `time_window` / `source_not_indexed` / `identifier_anomaly`，给 `evidence`（一句话判定依据）
- 逐条命中状态写 `matches[]`

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：覆盖率 + 主要漏检原因分布；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_question":"…",
    "match_rule":{"identifier":"doi|pmid exact","fuzzy":"title+author+year normalized","declared_at":"…"},
    "matches":[{"ref_id":"K01","hit":true,"matched_record":"R01","basis":"doi_equal"}],
    "misses":[{"ref_id":"K03","miss_reason":"synonym_not_covered","evidence":"…"}],
    "coverage_metrics":{"reference_total":4,"hit":2,"miss":2,"coverage_rate":0.5,"miss_rate":0.5},
    "summary":{"note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"measured|partially_measured|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"K01","location":"reference_set.items[0]","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. coverage_metrics 与 matches/misses 计数不一致。
2. miss_reason 枚举非法；miss 无 evidence。
3. match_rule 缺 declared_at（判定规则未事前声明）。
4. verdict 与测量进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 参考集为空 | coverage_rate=NaN 填 null，verdict=cannot_verify |
| 标识符缺失 | 退回标题作者年份近似匹配 + 注明 |
| 检索结果为空 | 全 miss + 归类 source_not_indexed/其他，不补造 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只测覆盖与漏检分类，不做补检搜索；命中判定为给定快照内匹配，不声称实时全域召回。
- examples/ 为合成示意非正式答案。