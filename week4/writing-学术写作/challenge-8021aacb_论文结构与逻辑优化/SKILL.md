---
name: struct-diag-paper
description: 论文结构与逻辑诊断技能：对给定稿件做六类结构机检（章节结构/研究问题对齐/论证链/段落关系/重复内容/结论边界）+ 模型语义诊断，合并为定位到章节/段落/句子并附逐字引文的可执行编辑方案（move/merge/split/narrow/insert/delete），同输入消融两臂+污染反例注入产出机器判定增益证据。Use when the case asks to diagnose/optimize paper structure, logic, argument chain, redundancy, conclusion boundary, or produce an actionable revision plan.
---

# struct-diag-paper — 论文结构与逻辑诊断（诊得准 · 改得动 · 链得通 · 说得清）

核心思想：诊断是**有定位、有依据、有动作**的判断，不是写作原则罗列。每条问题必须：
① 定位到章节/段落（诊得准）；② 给出 move/merge/split/narrow/insert/delete 可执行动作（改得动）；
③ 论点—论据映射支撑跨章呼应检查（链得通）；④ 附逐字引文供作者复核采纳/部分采纳/驳回（说得清）。
交付四件套：findings.json（合并问题清单）+ edit_actions.jsonl（有序动作）+ report.md（可编辑诊断报告）+ result.json（契约全字段+增益证据）。

### 增益证据与效率（必须本次真跑，禁止文字声明冒充数字）
```bash
python3 scripts/gain_evidence.py --manuscript /app/work/manuscript.json --result /app/output/result.json
```
- 同一校验器 structure_check 对同输入**消融两臂各跑一遍**：完整臂（六类机检）vs 消融臂
  `--ablate`（六类全关，仅表层规则，模拟无结构能力的基础检查）。逐类 FAIL 数差为机器判定。
- 污染反例：向稿件副本注入 3 处植入缺陷（跨章节重复段/绝对化结论句/无证据论断），完整臂
  重跑副本验证检测器非空转（命中数与未命中类别均如实记录）。
- 写入 result.json 的 `gain_evidence` 与 `efficiency`（这两个键由本脚本独占，其他脚本不碰）。
- **机检/闸门失败一律 verdict 照实记录、退出码恒 0**；修一轮仍不过则如实登记并继续交付。

## ⚠️ 强制执行协议（每次运行先读完本节再动手，顺序不可调换）

1. **抄契约**：第一动作 `cat /input/case.json`，逐字抄下 `output_contract` 全部字段名与 `case_id`。result.json 必须含全部字段，一个不缺（无值先置 null，不删键）。
2. **立即落骨架**：`build_result.py --status in_progress`。此后任何时刻中断，result.json 完整可解析。
3. **读真实文件**：稿件内容从实际文件提取，不按文件名/标签猜内容；领域标签错误不补造数据。
4. **广度优先**：六类语义诊断各至少一条或明确登记「该类经复核无问题」，再逐条充实。
5. **熔断**：累计约 48 次模型请求或 700 秒即停止新增诊断，直接收尾，status 如实。
6. **写盘自检**：每次写 JSON/文本后自检可解析；失败重写一次，再失败在 uncertainty 记录。
7. **失败也交付**：任何异常不空手退出；blocked/partial/failed 也要有 result.json 与已完成部分。

## 线性流程（7 步，按序执行）

### Step 1 — 契约与骨架
```bash
ls -la /input/ && cat /input/case.json && cat /input/task.md 2>/dev/null || true
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status in_progress
```

### Step 2 — 稿件提取与切章
```bash
python3 scripts/extract_input.py --input /input --case /input/case.json --task /input/task.md --outdir /app/work
```
- 产出 `/app/work/manuscript.json`（章节/段落结构 + stats + notes）与 constraints.json。
- 稿件为 PDF 且脚本无 PyMuPDF 时：用 Harness 的 pdf-text-tool 转出文本存 /app/work/raw.txt，
  再把该文件放回 /input 重跑本步；仍失败则 notes 记录缺口，**status 置 blocked 并交付说明**。
- `sections==[]` 时不得编造结构，status=blocked。

### Step 3 — 论点—论据映射（链得通的底座）
```bash
python3 scripts/claim_extractor.py --manuscript /app/work/manuscript.json --out /app/work/claim_evidence_map.jsonl
```
- 逐句抽取论断与证据标记（数值/引用[n]/图表），support 分 same_sentence/same_paragraph/none。
- 用一次响应复核 `support==none` 的条目：同段确无证据→进入论证链 findings；机检漏判（跨段
  有据）→登记为机检误报，在 changelog 记录口径。

### Step 4 — 模型语义诊断（诊得准的主判层）
通读 manuscript.json，写 `/app/work/model_findings.json`（JSON 数组，schema 同机检 finding）：
```json
[{"finding_id":"M001","source":"model","category":"claim_boundary","category_zh":"结论边界",
  "severity":"high","location":{"section":"4 结论","paragraph":2},"quote":"逐字原文≤80字",
  "problem":"结论称『全面解决』，但方法仅在该数据集两类任务上验证",
  "basis":"模型语义判断（结构级，机检无法覆盖）",
  "suggested_action":{"type":"narrow","instruction":"收窄为『在该数据集上优于基线』"},
  "status":"pending_author"}]
```
- category 六选一：section_structure/question_alignment/claim_evidence/paragraph_flow/repetition/claim_boundary。
- 每条必须有 location+quote+动作类型；机检已覆盖的类别优先补充机检盲区（如语义层面的循环论证、跨章节呼应断裂）。
- 材料不足/需人工确认的判断写入 `--gaps`（Step 6），不编造。

### Step 5 — 机检与合并
```bash
python3 scripts/structure_check.py --manuscript /app/work/manuscript.json --out /app/work/findings_machine.json
python3 scripts/edit_plan.py --machine /app/work/findings_machine.json --model /app/work/model_findings.json \
  --manuscript /app/work/manuscript.json --out-actions /app/work/edit_actions.jsonl \
  --out-findings /app/output/findings.json --out-report /app/output/report.md \
  --gaps '["人工确认项/材料缺口（JSON 数组）"]'
```
- 机检六类：章节功能与顺序 / 研究问题与贡献对齐 / 论证链断点 / 段落衔接 / 跨章节重复 / 结论边界。
- 合并键 = 类别+引文+位置：同位同文去重，不同位置同文各留一条；model 条目带 model_echo 留痕。

### Step 6 — 增益证据（消融两臂 + 污染反例，真跑）
```bash
python3 scripts/gain_evidence.py --manuscript /app/work/manuscript.json --result /app/output/result.json
```

### Step 7 — 收尾组装
```bash
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status complete \
  --findings /app/output/findings.json --actions /app/work/edit_actions.jsonl \
  --report /app/output/report.md --claim-map /app/work/claim_evidence_map.jsonl \
  --manuscript /app/work/manuscript.json --notes '缺口; 待核项' --changelog '关键决策; 机检误报口径'
```
- status 四级：六类全出+报告完整=complete；部分环节失败=partial（写明环节）；无法产出=failed；
  无稿件/依赖缺失无法开工=blocked（notes 说明缺什么）。
- gain_evidence/efficiency 由 Step 6 写入，本步只回填其余键（不覆盖、不删键）。

## 异常处置表

| 情形 | 处置 |
|---|---|
| 稿件缺失/PDF 无法提取 | status=blocked；notes 记录缺口与已尝试路径（pdf-text-tool 等）；不编造结构 |
| 模型诊断（Step 4）未完成 | edit_plan 仅机检结论运行，gaps 登记「语义层未覆盖，六类可能有遗漏」 |
| 机检误报（如描述性方法名） | 修规则一轮；仍误报则在 changelog 记录口径，不硬凑 |
| 稿件被截断/格式混乱 | extract notes 记录；已提取部分照常诊断，uncertainty 注明覆盖范围 |
| 无参考文献/图表缺失 | 属 section_structure 正常检出项；若体裁不需要，作者可驳回 |
| gain_evidence 计算失败 | error 如实写入 gain_evidence 键，退出码仍 0，不冒充数字 |
| 预算将尽（≥48 次或 ≥700 秒） | 立即 Step 7 收尾，status 如实 |

## 最小调用示例（示意，非正式案例结果）

```bash
python3 scripts/extract_input.py --input /input --outdir /app/work
# → {"ok":true,"case_id":"...","source":"file:manuscript.txt(text)","sections":6}
python3 scripts/structure_check.py --manuscript /app/work/manuscript.json --out /app/work/findings_machine.json
# → {"ok":true,"arm":"skill_full","fail_count":10}
python3 scripts/gain_evidence.py --manuscript /app/work/manuscript.json --result /app/output/result.json
# → {"ok":true,"written":true,"fail_diff":10,"pollution":"pass"}
```
输入结构示例见 `examples/example_input.json`（示意结构，非正式案例）。

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部字段；任何时刻可解析（先骨架后回填）
- [ ] 每条 finding 有 location+quote+可执行动作类型；作者可按 report.md 逐条采纳/部分采纳/驳回
- [ ] claim_evidence_map 覆盖全部论断句；support=none 条目已复核并进入 findings 或登记误报
- [ ] gain_evidence 含同输入两臂逐项差 + 污染反例命中数，全部为本次真跑数字
- [ ] status/uncertainty/changelog 如实；未编造结构问题、来源或增益数字
