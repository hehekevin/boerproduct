---
name: query-plan-keywords
description: Academic literature search planning skill (focused). Decomposes a research question into a structured query plan: for each core concept, expands keywords (terms, synonyms, abbreviations, cross-language) and builds an executable search string with boolean logic and field limits, each annotated with its intent. Only keyword-expansion and query-string construction are in scope; multi-round retrieval orchestration and dedup are one-line notes. Use when the task asks to plan academic search queries for a research question.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **检索式要有意图说明**：每组查询写清布尔逻辑+字段+意图，检索式不可退化成关键词串。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定研究问题 + 范围 + 材料，完成「概念拆解 → 关键词扩展 → 检索式构建（3-5 组）」。只做查询规划与关键词扩展，不真实调库检索、不做结果去重。材料里的术语按材料为准。
- 输入：`/input/case.json`（research_question + scope + materials[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 关键词扩展 + 检索式构建（核心，1-2 次响应）
- `concepts[]`：把研究问题拆 3-5 个核心概念，每个概念给 term + 同义词 + 缩写 + 跨语言表达
- `query_plan[]`：3-5 组检索式，每组 query_string（布尔逻辑，如 `("graph neural network" OR GNN) AND ("molecular property" OR ADMET)`）+ field（title/abstract/all）+ intent（这段检索式想命中什么）

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：概念数/检索式数；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_question":"…",
    "concepts":[{"concept_id":"C1","term":"graph neural network","synonyms":["GNN","message passing"],"abbreviations":["GNN"],"cross_language":[]}],
    "query_plan":[{"query_id":"Q1","query_string":"(\"graph neural network\" OR GNN) AND \"molecular property\"","field":"title,abstract","intent":"…"}],
    "summary":{"concepts":"3-5","queries":"3-5","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"planned|partially_planned|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"inferred","source_id":"Q1","location":"concepts[0]","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. concepts 空或 <3；query_plan 空。
2. query_string 无布尔逻辑（退化成关键词串）或空。
3. 每条 query 缺 intent（意图）。
4. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 研究问题模糊 | 先拆可检索结构，模糊处登记 uncertainties，不硬编术语 |
| 材料术语冲突 | 以材料为准 + 登记冲突 |
| 范围过宽 | 检索式加时间/字段限制 + 注明 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只做查询规划，不真实检索；检索式为给定问题+材料的推导，不声称命中结果。
- examples/ 为合成示意非正式答案。