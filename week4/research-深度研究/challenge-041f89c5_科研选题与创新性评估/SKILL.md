---
name: proposal-novelty-assess
description: Research proposal novelty and innovativeness assessment skill (focused). For each candidate proposal, deconstructs the research question into a testable statement, classifies each innovation claim into one of four types (method / data / scenario / theory) and checks whether it is covered by the provided known-works list, then verifies feasibility across four elements (data / method / resource / time) with per-element status and basis. Only question-definition, innovation-classification and feasibility-check are in scope; full literature comparison matrices are one-line summaries. Use when the task asks to assess research topics and novelty against a bounded known-work list.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后任何时刻 result.json 必须存在且可解析。
2. **只对照已知工作清单**：创新点判定只与 case.json 的 known_works 对照，不自己新增检索。已知工作读不到的标"无法判定"。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定 4 个选题 proposal + 5 篇已知工作 + 评价标准，完成「问题可检验化 → 创新点四类判定 → 可行性四要素核查」。只做问题定义+创新分类+可行性，不做完整比较矩阵、不做长篇综述式评估。已知工作只引用清单内文献，读不到标"无法判定"，不把"检索不到"说成"无人研究"。
- 输入：`/input/case.json`（research_context + criteria + proposals[] + known_works[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 逐 proposal 评估（核心，1-2 次响应）
对每个 proposal：
- `research_question`：拆成 对象+关键变量+比较基线+预期结论+可证伪条件 五要素
- `innovation_claims[]`：每条创新陈述判 `type` ∈ `method`/`data`/`scenario`/`theory`，并对照 known_works 判 `coverage` ∈ `novel`/`overlapped`/`partially_overlapped`，给 `basis`（引用 known_works[i].title 或 abstract 摘要）+ `source_ref`
- `feasibility`：四要素 data/method/resource/time，每要素给 `status`（satisfied/conditional/missing）+ `basis`
- 每个 proposal 给一句结论 + `confidence`

### Step 2 — 综合 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：哪个 proposal 创新边界最清晰 + 可行性最强；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "proposals":[{
      "proposal_id":"T01","title":"…",
      "research_question":{"object":"…","variables":"…","baseline":"…","expected":"…","falsifiable_condition":"…"},
      "innovation_claims":[{"claim":"…","type":"method|data|scenario|theory","coverage":"novel|overlapped|partially_overlapped","basis":"…","source_ref":"known_works[0]"}],
      "feasibility":{"data":{"status":"satisfied|conditional|missing","basis":"…"},"method":{},"resource":{},"time":{}},
      "conclusion":"…","confidence":"high|medium|low"
    }],
    "summary":{"top_proposal":"…","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"assessed|partially_assessed|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"inferred","source_id":"T01","location":"known_works[0].abstract","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. proposals 未全评估；research_question 五要素缺。
2. innovation_claims 空；type 枚举非法；overlapped 无 basis/source_ref 指向 known_works。
3. feasibility 四要素缺；status 枚举非法；conditional/missing 无 basis。
4. verdict 与评估进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| known_works 为空 | 创新点 coverage 均标 novel 但 confidence 降级 + uncertainties 登记"无对照基准" |
| 已知工作摘要不足 | coverage 标 partially_overlapped + 注明依据不足，不脑补 |
| 可行性材料缺失 | status=missing + basis 注明，不补造数据/算力 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只对照清单内已知工作，不做真实全网检索；"未检索到"不等同"无人研究"。
- examples/ 为合成示意非正式答案。