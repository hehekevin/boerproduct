---
name: academic-integrity-check
description: Academic integrity and compliance check skill (focused on citation verification). Scans the manuscript text for in-text citation markers (如 [1]、[3]), verifies each against the reference list (existence, metadata, claim-reference alignment), and flags citation_gap / wrong_attribution / formatting_inconsistency with a verbatim quote and section location. Only citation-norm verification is in scope; privacy/copyright/ethics/journal-requirements are out-of-scope notes. Use when the task asks to check academic norm compliance with per-item evidence and severity.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **只核引用规范**：聚焦引用真实性/对应性/格式一致性，不查隐私/版权/伦理（各一句话兜底）。读不到的被引文献标"待复核"不脑补。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定一篇分章节稿件（含参考文献列表），完成「引文标号核验 → 逐条问题清单（quote+定位+severity）→ 结论」。只做引用规范核验，报出的问题必须能指回原文位置、有可核对依据。公开引用编号在文献表不存在的、论断与所引主题不对应的、引用格式不统一的都要报；风格差异不算不端。
- 输入：`/input/case.json`（manuscript{sections[]+references} + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 引文核验（核心，1-2 次响应）
扫正文各章节里的引用标号（如 [1]、[3]）：
- 每个标号 `citation_checks[]`：`cite_marker`（[1]）+ `claim_quote`（正文带该标号的论断句逐字）+ `location`（如 sections[1].text）+ `status` ∈ `ok` / `not_in_refs` / `mismatch` / `uncertain`（读不到文献内容时）+ `basis`（一句话判定依据）+ `severity` ∈ `critical`/`major`/`minor`
- 标号不在参考文献表 → `not_in_refs`（critical）
- 标号存在但引用文献主题与论断明显不符 → `mismatch`（major）
- 同一文献多次引用的格式/编号不一致 → `minor`
- 每案例 6-10 条封顶，宁少勿滥

### Step 2 — 综合 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：问题计数 + 最严重问题；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "manuscript_title":"…",
    "citation_checks":[{"cite_marker":"[1]","claim_quote":"…","location":"sections[1].text","status":"ok|not_in_refs|mismatch|uncertain","basis":"…","severity":"critical|major|minor"}],
    "summary":{"total":"…","critical":"…","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"audited|partially_audited|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"[1]","location":"sections[1].text","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. citation_checks 空且稿件有引用标号。
2. status/severity 枚举非法；not_in_refs 无 basis；claim_quote 缺。
3. 报出的 critical/major 无 basis（可核对依据）。
4. verdict 与核验进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 无参考文献表 | 全部标号 not_in_refs，或 verdict=cannot_verify 不脑补 |
| 被引文献内容读不到 | status=uncertain + 注明，不脑补主题对应 |
| 题目材料只有摘要无全文 | 只核已有章节，material_gaps 登记 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只核引用规范，不提供法务/伦理委员会正式意见；隐私/版权/伦理/投稿要求为 out-of-scope 一句话提示。
- examples/ 为合成示意（虚构）非正式答案。