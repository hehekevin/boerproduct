---
name: literature-screen-rank
description: Literature screening and ranking skill (focused). For each candidate paper, judges relevance into three tiers (directly_relevant / indirectly_relevant / irrelevant) with a one-line basis citing the abstract, then produces a stable, explainable priority ordering (direct > method-reference > background) with a break-tie rule. Only relevance judgment and ranking are in scope; label taxonomy and conflict-handling are one-line notes. Use when the task asks to screen and rank a candidate set against a research question.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **排序规则事前声明**：相关性三分 + 排序规则 + 平局处理在判定前声明，之后不改。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定研究问题 + 纳排标准 + 6 篇候选文献，完成「相关性三分判定 → 稳定排序」。只做相关性判断与排序；标签体系/冲突处理是一句话兜底。摘要不足判间接相关+降置信度，不脑补。
- 输入：`/input/case.json`（research_question + criteria + candidates[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 相关性判定 + 排序（核心，1-2 次响应）
- 声明 `relevance_rule`（三档判据）+ `rank_rule`（direct > method-reference > background，同级按年份新→旧）+ `declared_at`
- 对每篇 candidate：`relevance` ∈ `directly_relevant`/`indirectly_relevant`/`irrelevant` + `basis`（引用 abstract 依据一句话）+ `confidence`
- `ranked_order[]`：按规则输出排序后的 id 序列，同分并列记录 ties

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：相关/间接/无关分布 + 排序；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_question":"…",
    "relevance_rule":{"directly_relevant":"…","indirectly_relevant":"…","irrelevant":"…","declared_at":"…"},
    "rank_rule":{"primary":"direct > method-reference > background","tie":"year desc","declared_at":"…"},
    "screening":[{"paper_id":"P01","relevance":"directly_relevant","basis":"…","confidence":"high"}],
    "ranked_order":["P01","P03","P02",{"ties":[["P02","P04"]]}],
    "summary":{"direct":"…","indirect":"…","irrelevant":"…","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"screened|partially_screened|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"P01","location":"candidates[0].abstract","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. screening 未覆盖全部 candidates。
2. relevance 枚举非法；每条缺 basis。
3. ranked_order 与 screening 的相关性分布不一致；rank_rule 缺 declared_at。
4. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 摘要不足 | relevance=indirectly_relevant + confidence=low + 注明 |
| 多篇并列 | rank_rule 的 tie 规则 + ties 登记 |
| 候选为空 | verdict=cannot_verify |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只做相关性判定与排序，不做标签体系/去重/冲突合并；排序为给定候选集内判定。
- examples/ 为合成示意非正式答案。