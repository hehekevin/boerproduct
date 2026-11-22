---
name: question-drive-retrieval
description: Question-driven retrieval planning skill (focused). Decomposes a complex research question into a structured sub-question list (object / mechanism / method / time-range / comparison / evidence-requirement) and expands keywords (terms, synonyms, abbreviations) for each sub-question. Only question-decomposition and keyword-expansion are in scope; multi-round retrieval iteration and stop-condition are one-line notes. Use when the task asks to structure a research question into retrievable sub-questions.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **子问题要结构化**：拆成 对象/机制/方法/时间范围/比较关系/证据要求 等维度，配关键词，不写模糊长问句。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定研究问题 + 材料片段，完成「问题拆成结构化子问题 + 每子问题关键词扩展」。只做问题拆解与关键词扩展；多轮检索/停止条件是一句话兜底。材料里的术语按材料为准。
- 输入：`/input/case.json`（task + research_question_raw + records[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 问题拆解 + 关键词扩展（核心，1-2 次响应）
- `sub_questions[]`：把研究问题拆 3-5 个子问题，每个给 `question`（一句话）+ `aspects[]`（对象/机制/方法/时间/比较/证据要求 等维度）+ `keywords[]`（每个核心术语 + 同义 + 缩写）
- 子问题之间标注可并行/依赖关系（简要）

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：子问题数/覆盖维度；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_question":"…",
    "sub_questions":[{"sq_id":"SQ1","question":"…","aspects":{"object":"…","mechanism":"…","comparison":"…","evidence":"…"},"keywords":[{"term":"…","synonyms":["…"],"abbreviations":["…"]}],"dependencies":"independent|after_SQ1"}],
    "summary":{"sub_questions":"3-5","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"decomposed|partially_decomposed|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"inferred","source_id":"SQ1","location":"records[0].abstract_excerpt","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. sub_questions 空或 <3；question 空。
2. keywords 空；aspects 缺关键维度。
3. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 问题过于笼统 | 先拆可检索结构，模糊处登记 uncertainties |
| 材料术语与问题不符 | 以材料为准 + 登记 |
| 子问题不明显 | 至少按对象/机制/比较三维拆，不硬凑 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只做问题拆解与关键词扩展，不真实检索；为问题+材料的推导。
- examples/ 为合成示意非正式答案。