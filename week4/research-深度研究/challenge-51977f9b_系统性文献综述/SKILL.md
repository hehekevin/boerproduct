---
name: sysrev-screening
description: Systematic review screening skill (focused). Registers a versioned protocol (research question + inclusion/exclusion criteria) BEFORE any judgment, then screens every record with a decision (included/excluded/pending_review), a reason-code, a cited criteria id and a verbatim evidence quote with source location. Produces a reproducible PRISMA-style funnel count with closure check and a short evidence-grounded synthesis. Only the screening-and-traceability loop is in scope; quality appraisal and full data extraction are one-line summaries, not per-item audits. Use when the task asks for a reproducible systematic-review screening with auditable inclusion/exclusion decisions and traceable reasons.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 后第一个动作运行 `build_skeleton.py`，写出含 output_contract 全字段 + case_id 的 `/app/output/result.json`。此后任何时刻 result.json 必须存在且 JSON 可解析。
2. **先声明后判定**：纳入/排除标准（criteria）必须在任何逐条判定之前写定版本号与 declared_at；之后不改判据，确需修改则新增版本并回溯重判。
3. **失败也交付**：任何中断/失败仍写 result.json（status=partial，写明截断位置）。所有脚本退出码恒 0，判据只看 result 里的 verdict 字段。
4. **预算保护**：模型请求已用超 32 次或 450 秒就停止新增判定，用现有结果定稿收尾。

## 定位与约定
锁定子场景：给定研究问题与 9 篇真实题录（含摘要），完成「协议声明 → 逐条纳排 → 漏斗计数 → 简短综合」。**只做筛选与可追溯闭环**，不全文精读、不做质量量表逐维评价、不做结构化效应量提取（这三者各一句话概括即可）。检索无结果、材料缺失照实登记，不补造文献。
- 输入：`/input/case.json`（research_question + criteria_draft + records[9篇] + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅 Python 标准库。
- 线性 3 步，禁止分支回环。脚本定位以 `/app/work/skill_marker.json` 标志文件校验为准。

## 三步流程

### Step 0 — 落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动提取 output_contract 全字段与 records 清单写骨架；脚本失败则手工抄字段与记录手写骨架（键一个不缺）。

### Step 1 — 声明协议 + 逐条纳排（核心，1-2 次响应）
- 先填 `result.criteria`：从 case.json 的 `criteria_draft` 提炼编号化纳排标准（inclusion 3-5 条 / exclusion 3-5 条），声明 `version` + `declared_at`。**之后不改判据。**
- 再对 `result.records[]` 逐条给：
  - `decision` ∈ `included` / `excluded` / `pending_review`
  - `reason_code`：included 用标准 id 前缀（IN-xx）；excluded 给排除理由（如 `EX-not_rct`、`EX-wrong_population`、`EX-wrong_outcome`）；pending 标 `PD-insufficient_info` + pending_reason
  - `criteria_ref`：命中哪条标准 id
  - `evidence_quote`：从该 records[i].abstract 逐字摘录一句支撑判定的原文
  - `evidence_location`：如 `records[3].abstract`
  - `rationale`：一句话判定理由
- 每条都判，不跳不脑补；摘要不足 → pending + 登记 uncertainties。

### Step 2 — 漏斗计数 + 简短综合 + 自检（脚本 + 1 次响应）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.funnel`：identified=records 总数、screened、included、excluded、pending_review，closure=closed（逐级可加）。
- `result.synthesis`：2-3 条简短综合结论，每条带 strength（按支持记录数粗判 strong/moderate/weak）与 supporting_records 引用，**不逐篇提取效应量**。
- `result.run_status` + `result.verdict`（screened/partially_screened/cannot_verify）如实填。
- verify_check 判据看 `validator_verdict`：FAIL 则按 problems 逐条修复再重跑，直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心业务键）
```json
{
  "case_id": "…", "status": "answered|partial|input_error",
  "result": {
    "research_question": {"question":"…","pico":{}},
    "criteria": {"version":"v1.0","declared_at":"…","inclusion":[{"criterion_id":"IN-01","text":"…"}],"exclusion":[{"criterion_id":"EX-01","text":"…"}]},
    "records": [{"record_id":"R01","title":"…","year":2024,"doi":"…","decision":"included","reason_code":null,"criteria_ref":["IN-01"],"evidence_quote":"…","evidence_location":"records[0].abstract","rationale":"…","judged":true}],
    "funnel": {"identified":9,"screened":9,"included":5,"excluded":2,"pending_review":1,"closure":"closed"},
    "synthesis": {"conclusions":[{"text":"…","strength":"strong","supporting_records":["R01"]}],"gaps":[]},
    "run_status": {"state":"success","reason":null},
    "verdict": "screened", "verdict_basis":"…"
  },
  "claims": [{"claim_id":"c-01","text":"…","kind":"reported","source_id":"R01","location":"records[0].abstract","evidence":[{"quote":"…"}]}],
  "uncertainties": {"summary":"…","human_review":[]},
  "changelog": []
}
```

## 校验器会抓的错（verify_check.py）
1. criteria 缺 version/declared_at；判定引用的 criteria_ref 不存在或在标准声明后才补（协议漂移）。
2. decision 枚举非法；excluded 无 reason_code；pending 无 pending_reason；included 无 criteria_ref；judged 记录缺 evidence_quote 或 claims 无回证。
3. funnel 数字与 records 判定计数不一致；closure != closed。
4. verdict 与判定进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 题录为空 | funnel.identified=0、verdict=cannot_verify，不补造 |
| 摘要不足/缺 DOI | 判 pending + 登记 uncertainties，不脑补 |
| 标准冲突 | uncertainties 登记 + 声明优先序；改协议新增版本回溯重判 |
| 预算不足 | 保留已完成部分，status=partial，changelog 注明截断 |
| 校验脚本失败 | 退出码恒 0，结论记 verdict，不中断交付 |

## 已知限制
- 只做筛选与可追溯闭环，不做质量量表逐维评价、不做全文精读与效应量合并。
- 增益对照非平台白板对照；白板由平台生成。`examples/` 为合成示意（非正式答案，9 条题录为虚构）。