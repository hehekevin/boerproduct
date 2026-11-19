---
name: claim-audit
description: 文献证据溯源与事实核验技能：读取 /input/claims-to-verify.json，把复合论断拆成可独立判定的子判断（事实/比较/因果/范围），逐条给出四级判定 supported/partially_supported/contradicted/insufficient_evidence，每条证据摘录经空白归一化子串核验防止改写；未覆盖的论断逐条登记 uncertainty，绝不静默跳过；保留比较对象、否定、显著性、条件；主题相关≠支持，无支撑外推≠被实验证伪；带 --ablate 消融开关，同输入两跑产出可复核的增益证据与效率计数。Use when the task asks to verify scientific claims against supplied paper text with evidence cards and four-level entailment verdicts.
---

# claim-audit — 论断核验（拆得开 · 找得到 · 判得准 · 说得清）

核验不是"找一段相关的话贴上来"。本技能把每条待核论断拆到**最小可判定单元**，逐条给出与原文表述相符的四级判定，并把判定理由钉在原文位置上。

## ⛔ 强制执行协议（先读，全程有效）

1. **主产物完整嵌入 result.json**：全部论断的逐条核查结论写入 `/app/output/result.json` 的
   `result.verdicts`，顶层五字段 `case_id/status/result/claims/uncertainties` 一个不少。
2. **摘录防改写**：每条 evidence 的 `quote` 必须逐字来自所标段落（空白差异可忽略，措辞不可改）。
   脚本对**所有**带证据的子判断做空白归一化子串匹配，匹配失败=FAIL，必须换成原文原句。
3. **无静默跳过**：任何论断要么有 verdict，要么按条登记进 `uncertainties.uncovered`（写明 claim_id 与原因）；
   既不进 verdicts 也不进 uncertainties = FAIL。
4. **不编造**：判定只能是 supported/partially_supported/contradicted/insufficient_evidence 之一，逐条如实；
   材料里没有就判 insufficient_evidence，不外推、不脑补数值。
5. **先落骨架 + 每步一写盘**：Stage 0 立即写出含全部 claim 记录（`verdict:"pending"`）的 result.json；
   之后每个阶段结束都覆盖写一次 `/app/work/result.json`（分批回填，单次 ≤1500 字，防 16384 token 截断），
   保证任何中断点都有可交付的中间态。
6. **失败也交付**：崩溃/超时/校验不通过也必须写出结构合法的 result.json（status 如实降级
   partial/input_error，缺口写进 uncertainties）；写盘前先 `python3 -c "import json;json.load(open('…'))"` 自检。
7. **增益证据必须实测**：`gain_evidence` 与 `efficiency` 由 `scripts/gain_probe.py` 自动采集写入，
   **不得手填数字**；脚本失败则记 `status:"failed"` 并说明，不得用估计值充数。

四条判定纪律（与协议同等效力）：
1. **主题相关 ≠ 支持**——段落只讲相邻话题而没讲论断本身，判 insufficient_evidence。
2. **"未报告" ≠ "被证伪"**——contradicted 必须有正面的反向证据（可定位引文）。
3. **保留限定**——比较对象、否定词、显著性（p<0.05）、条件（n=30、仅在 X 材料中）原样随判定走，
   并逐条写进子判断的 `modifiers`（comparator/negation/significance/conditions 四键，无则填 null）。
4. **冲突并列**——两处来源矛盾时双方引文都列出，判定加限定词，不悄悄二选一。

## 0. 输入与输出约定

- 输入：`/input/case.json`（材料：带段落编号文本/表格文字/图注）、
  `/input/claims-to-verify.json`（待核论断清单；**论断是提问，不是权威事实**）、`task.md`。
  字段名以实际文件为准（claims 可叫 `claims`/`items`）。工作区 `/app/work`；最终产物 `/app/output/result.json`。
  预算：64 次模型请求 / 900 秒 / 单响应 16384 token，按下列 6 步线性推进。

## 1. 线性六步流程

### 步骤 1 — 读输入，落骨架（必做，1 次响应）
```bash
cat /input/claims-to-verify.json && head -c 2000 /input/case.json
```
- 记录每个 `claim_id` 及原文；文件缺失或论断为空 → 整体 `input_error`，在 `error.reason` 写明原因。
- **立即写骨架 result.json**：每个 claim 一条 `verdict:"pending"` 记录 + 空 uncertainties 框架。

### 步骤 2 — 论断拆解（1 次响应）
把每条论断拆成可独立核验的子判断并标注类型：`fact`（事实：X 是/有/发生了）、`comparison`（比较：X 高于/低于/相当于 Y——必须写明比较对象与方向）、
`causal`（因果：X 导致 Y）、`scope`（范围：在什么条件/样本/范围内成立）。原则：不遗漏（复合句逐个谓词拆）、不重复（同一谓词不拆两次）；
拆不出子判断的单句保持一条；无法解析的论断（空泛/指代不明）整条记入 `uncertainties.uncovered`，不硬拆。写盘。

### 步骤 3 — 逐子判断取证与判定（1-2 次响应）
对每个子判断找**最小充分证据**：证据写 `{paragraph_id, quote(逐字), locator}`，quote 从段落复制，不凭记忆默写。
- 四级判定：`supported`=原文明确陈述该子判断（数值/比较/方向全部吻合）；`partially_supported`=方向/结论支持但数值、条件或范围不完全吻合；
  `contradicted`=原文明确陈述相反结果（有正面的反向证据引文）；`insufficient_evidence`=原文未报告或仅主题相关（写明找过的位置）。
- 判定理由 `rationale` 一句话讲清"为什么是这一级而不是相邻级"。
- `modifiers` 四键照写：比较对象、否定、显著性、条件各归其位，无则 `null`（不允许整块省略）。
- 写完即自检：把 quote 与段落原文并排比对，确认没有替换、缩写、改写。写盘。

### 步骤 4 — 汇总覆盖检查（1 次响应）
- 每条 claim 总体判定 = 子判断的最弱一致结论（有 insufficient → 至少降为 partial；任一 contradicted → 整体 contradicted 并注明限定）。
- **覆盖对账**：对照步骤 1 的 claim_id 清单，逐条确认"已判定 / 已登记 uncovered"，两条路都没有的当场补上（登记 uncertainties，不许跳过）。
- 写顶层 `claims`（每条核查结论一条：kind+evidence+source_id+location）与 `uncertainties`，写盘。

### 步骤 5 — 校验、回写与交付（1-2 次调用）
```bash
python3 /skills/weekly-skill/scripts/claim_check.py --result /app/work/result.json \
  --case /input/case.json --claims /input/claims-to-verify.json --out /app/output/claim_check.json --require-gain
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json --case /input/case.json
```
- **两个校验脚本恒 exit 0**（含参数错误与输入缺失）：成败只看报告里的 `ok`/`problems` 字段（`claim_check.json`）。
  ok=false 时按打印的问题清单逐条修复后覆盖 result.json，重跑到 ok=true。
- **机检结果回写 result.json**：PASS 后在 `changelog` 追加一条记录，含 claim_check 报告的
  `ok/problems/warnings` 与 `gates`（闸门状态）——评分器不开附件即可核对机器校验确实运行。
  某闸门状态非 `enforced` 时（如摘录核验因 case.json 无段落文本而降级），changelog 加
  `gate_note`：「该闸未运行，下游不得宣称已核对」。

### 步骤 6 — 增益对照与效率采集（1 次调用）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py patch --result /app/output/result.json \
  --case /input/case.json --claims /input/claims-to-verify.json \
  --runlog /app/work/run_log.jsonl --out /app/output/gain_evidence.json
```
- 脚本对**同一份 result.json + 同一输入**跑两遍（`full` 闸门全开 / `ablated` 关掉逐字回证与
  未覆盖补登记两道闸），逐项指标（判定覆盖率 / 证据回证率 / 未覆盖漏检数 / 误支持数 /
  需人工核对条目数 / 步骤数 / 追问轮次）由脚本实测并写入 `result.json.gain_evidence` 与 `result.json.efficiency`。
- **消融开关**：`--ablate` 或环境变量 `CLAIM_AUDIT_ABLATE=1` 关掉那两道闸门（基线行为）；
  单独复跑对照：`python3 /skills/weekly-skill/scripts/gain_probe.py ablate --result /app/output/result.json --case /input/case.json --claims /input/claims-to-verify.json`。
- `run_log.jsonl` 可选：每行一个 `{"stage":…,"kind":"recheck"}` 记录，用于取**真实**步骤数与复核轮次；
  缺文件时脚本用协议常量并在 `steps_source`/`rounds_source` 标注 `protocol`（不得冒充实测）。
- 脚本失败不阻断交付：`gain_evidence.status` 记 `failed` 并写明原因，其余字段照常交付。

## 2. 输出 schema（result.json — 顶层为平台通用契约五字段）

```
{"case_id": "…",
 "status": "answered | partial | insufficient_evidence | input_error",
 "error": {"reason": "仅 status=input_error 必填：材料缺失/论断为空/无法解析"},
 "result": {"verdicts": [
    {"claim_id": "…", "claim_text": "原论断",
     "verdict": "supported | partially_supported | contradicted | insufficient_evidence",
     "subclaims": [
       {"sub_id": "…-s1", "type": "fact|comparison|causal|scope", "text": "子判断", "verdict": "四级之一",
        "modifiers": {"comparator": null, "negation": null, "significance": null, "conditions": null},
        "evidence": [{"paragraph_id": "…", "quote": "逐字原文", "locator": "§4.2"}], "rationale": "为什么是这个判定"}],
     "qualified_conclusion": "带条件/限定的最终表述（冲突时双方并列）"}],
   "verdict_summary": {"supported": 0, "partially_supported": 0, "contradicted": 0, "insufficient_evidence": 0}},
 "claims": [{"claim_id": "…", "text": "关键判定结论", "kind": "reported | inferred", "source_id": "paper_id/材料标识",
             "location": "paragraph_id", "evidence": [{"paragraph_id": "…", "quote": "逐字原文"}]}],
 "uncertainties": {"uncovered": [{"claim_id": "…", "reason": "无法解析/材料不含该主题/输入缺失"}],
                   "unreported": ["材料未报告、无法核验的内容"], "unverifiable": ["主题相关但不足判定的部分"],
                   "conflicts": [{"what": "冲突内容", "where": ["出处1", "出处2"]}],
                   "human_review": ["判定存疑建议人工复核"], "summary": "…"},
 "gain_evidence": {"schema_version": "1.1", "arms": {"full": {"metrics": {}}, "ablated": {"metrics": {}}},
                   "delta_full_minus_ablated": {}, "headline": {}, "gate_layer": {}, "ablation_switch": {},
                   "mechanism_to_metric": [], "boundaries": [], "failure_conditions": []},
 "efficiency": {"steps": 0, "rounds": 0, "steps_source": "run_log|protocol", "reproduce": "…"},
 "changelog": [{"action": "claim_check", "ok": true, "problems": [], "warnings": [], "gates": {"quote_verification": "enforced"}, "gate_note": ""}]}
```
- 整体 `status`：全部论断有 verdict（或全部登记 uncovered 且如实说明）→ `answered`；还有 pending → `partial`；输入读不进 → `input_error`。
- `gain_evidence.arms.*.metrics` 六项必备：verdict_coverage_rate / evidence_backverify_rate / uncovered_miss_count / manual_review_items / steps / rounds。

## 3. 校验器会抓的错（claim_check.py）

1. claim_id 覆盖对账：漏判且未登记 uncovered = FAIL。
2. verdict / subclaim verdict / type 枚举非法。
3. **摘录核验**：所有带证据的子判断，quote 做空白归一化后必须是该段落原文的子串；改写、默写、跨段拼贴 = FAIL。
4. contradicted 的子判断必须 ≥1 条正面反向证据（只有"没找到"不算 contradicted）。
5. supported/partially_supported 的子判断必须有 evidence 且有 rationale。
6. verdict_summary 与逐条判定实际分布不符 = FAIL；status=answered 但有 pending 残留 → FAIL。
7. `modifiers` 四键缺一 → FAIL（比较对象/否定/显著性/条件未保留）。
8. uncertainties 五类边界缺一 → FAIL；conflicts 的 where<2 → FAIL。
9. `--require-gain` 时 gain_evidence 双臂六项指标缺一、或 efficiency 缺字段 → FAIL。
10. 消融臂（`--ablate`）下第 1、3 条降级为 WARNING，闸门状态记 `ablated_off`，报告标 `ablation.active=true`。

## 4. 最小调用示例与自测

`examples/`（合成论断+示意输出，**非正式答案**）。一条命令跑完正例 + 增益双跑 + 污染反例 + 消融对照：
```bash
python3 scripts/selftest.py
```

## 5. 已知限制

- 判定质量依赖段落文本完整性；跨页断裂、表格文字化程度低时定位精度下降（如实记入 uncertainties）。
- 摘录核验忽略空白差异但不容忍改写；OCR 字符噪声会在校验中暴露，需以原文字符为准修正摘录。
- 不联网核对文献元数据；材料外的"转引正确性"超出本技能边界，按 insufficient_evidence 报告。
- `gain_probe.py` 的规则审计臂是确定性参考实现，用于量化各机制的可测效应，不代表官方案例的语义判分；
  官方「加载 vs 不加载」对照由组织方提供，本包只提供自证机制与消融复跑开关。
