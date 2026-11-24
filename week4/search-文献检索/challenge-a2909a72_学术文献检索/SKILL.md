---
name: lit-search-resultset
description: Academic literature search skill (focused on delivering a usable result set). Given a research question and provided multi-database response snippets, extracts real bibliographic records from the material (not fabricating), deduplicates near-duplicate records (e.g. same paper from two databases), normalizes fields (title/authors/year/doi/venue), and produces a ranked, source-traceable result set with coverage note (which relevant works are present). Emits BOTH a structured result set AND a prose search report (search_report) embedded into result.json. Only extraction/dedup/normalization from provided material is in scope; no live database query is claimed. Use when the task asks to deliver a usable literature result set for a research question.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **只从给定材料提取**：结果集每条记录必须来自 case.json 的 materials（真实响应 snippet），不编造文献；材料里没有的标"未覆盖"。
3. **去重 + 标准化 + 来源回溯**：同一文献多库出现要去重合并，字段标准化，每条保留来源库。
4. **成文报告必嵌入**：除结果集外，必须写 `result.search_report`（≥200 字），说明检索范围、结果集规模、去重情况、覆盖缺口。
5. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
6. **预算保护**：模型请求超 40 次或 600 秒即停止，用现有结果写 search_report 收尾。

## 定位与约定
锁定子场景：给定研究问题 + 范围（年份/数据库）+ 多库响应材料，完成「真实记录提取 → 去重 → 字段标准化 → 排序 → 来源回溯 → 覆盖说明」。评分看"是否交付可用的文献结果集、是否覆盖关键文献、Recall@k 与关键文献命中率"。不声称实时检索、不编造材料外的文献。
- 输入：`/input/case.json`（research_question + scope + materials[] + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以 skill_marker.json 校验。

## 四步流程

### Step 0 — 落骨架（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 记录提取 + 去重 + 标准化（核心，1-2 次响应）
- 从 materials[] 逐条提取书目记录：`title`/`authors`/`year`/`doi`/`venue`/`source_db`
- `result.records[]`：去重后的结果集，每条带 title/year/doi/source_db/venue/abstract_snippet
- 识别关键文献（直接相关，如 GNN 预训练、分子性质预测），标注 relevance ∈ high/medium/low
- 材料里 DOI 缺失的重复记录（如 m4 是 m3 的 duplicate），按标题相似合并，保留有 DOI 的那条，记入 dedup

### Step 2 — 排序 + 覆盖说明（1 次响应）
- `result.ranked_records[]`：按相关性 + 年份排序
- `result.coverage_note`：说明覆盖了哪些关键研究方向、哪些缺口（如材料里没有的年份/主题）

### Step 3 — 写成文报告 + 自检（1 次响应 + 1 脚本）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.search_report`（≥200 字）：检索问题、范围、结果集规模、去重数、覆盖缺口、来源可追溯性
- 判据看 validator_verdict；FAIL 则修复→重跑直到 PASS。

## 输出 schema（result.json 顶层契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_question":"…",
    "scope":{"years":"2019-2024","databases":["Crossref","EuropePMC","OpenAlex"]},
    "records":[{"record_id":"R01","title":"…","authors":"…","year":2019,"doi":"…","venue":"…","source_db":"Crossref","relevance":"high","abstract_snippet":"…","duplicate_of":null}],
    "dedup":[{"kept":"R03","merged":"R04","basis":"title_similar_no_doi"}],
    "ranked_records":["R01","R02","R03"],
    "coverage_note":"覆盖 GNN 预训练、分子表征学习；缺口：2022-2023 应用类文献未在材料中",
    "search_report":"## 检索结果\n……（≥200字成文）",
    "run_status":{"state":"success","reason":null},
    "verdict":"delivered|partially_delivered|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"R01","location":"materials[0].snippet","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…"},"changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. records 为空；每条记录 title 缺或不在 materials 里（编造）。
2. dedup 里 merged 记录无对应；同一论文两库出现未合并。
3. search_report 缺失或 <200 字。
4. ranked_records 与 records 不一致。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| materials 为空 | records 空 + verdict=cannot_verify，不编造 |
| DOI 缺失重复 | 标题相似合并，保留有 DOI 的，记 dedup |
| 材料只覆盖部分方向 | coverage_note 说明缺口，不补造 |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 只从给定材料提取，不声称实时检索/全域召回；结果集是材料快照的整理。
- 相关性判断是语义判断，机械校验只保证记录来自材料、去重与计数一致。
- examples/ 为合成示意（虚构），非正式答案。