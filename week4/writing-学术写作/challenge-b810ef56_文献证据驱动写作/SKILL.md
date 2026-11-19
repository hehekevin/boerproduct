---
name: eviwrite-claimbind
description: 文献证据驱动写作技能：把成稿拆成可判定论断单元，逐条绑定来源与逐字引文（章节/页码/段落定位），按 A-D 证据等级审计措辞相称性（相关不写成因果、弱证据不写成强结论、冲突不隐藏），统一校验器机检 fail_count 逐项可回查，消融双跑+污染反例机器判定增益。Use when the case asks to complete or revise evidence-based academic writing, keeping every substantive claim traceable to a specific source passage with verbatim quotes, strength grading and honest uncertainty.
---

# eviwrite-claimbind — 文献证据驱动写作（论断—证据—成稿 三段交付）

核心思想：写作是**可指认的断言**——每句有依据的话都能指出依据在哪、依据多强。
交付三件套：① 论断清单 claims.jsonl；② 证据表 evidence_table.jsonl（逐字引文+定位+等级）；
③ 成稿 draft.md + result.json（含强度审计、校验报告、增益证据、uncertainty 如实）。

### 增益证据与效率计数（回填 result.json，必须真跑）
```bash
python3 scripts/gain_probe.py --result /app/output/result.json \
  --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl \
  --sources /app/work/sources --draft /app/output/draft.md --ablate --write
```
- 同一校验器对三臂各跑一遍：技能臂 vs 基础臂（剥离证据绑定的同文本副本）的
  fail_count 差 = 机器判定的质量增益；副本注入 2 条污染反例（编造 quote/相关写因果），
  校验器必须 FAIL 才证明判据灵敏。`--write` 只写 result.json 的 gain_evidence 与 efficiency。
- 机检 FAIL **一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过如实登记并继续交付，
  禁止以非零退出码结束。

## ⚠️ 强制执行协议（每次运行先读完本节再动手，顺序不可调换）

1. **抄契约**：第一动作 `cat /input/case.json`，逐字抄下 `output_contract` 全部字段名与
   `case_id`。result.json 必须包含全部字段，一个不缺（无值先置 null，只增不删）。
2. **立即落骨架**：读完契约立刻写出骨架 result.json（status=in_progress）。此后任何时刻
   中断，result.json 都完整可解析。
3. **读真实材料**：来源文献逐个打开读原文，不按文件名/标签猜内容；材料不足、冲突、
   仅摘要、原文矛盾一律如实标注，不补造。
4. **写盘自检**：每次写 JSON 后 `python3 -c "import json;json.load(open(...));print('ok')"`。
   失败重写一次；再失败改纯文本兜底并在 uncertainty 记录。
5. **熔断**：累计约 48 次模型请求或 700 秒即停止新增工作，直接收尾（校验→组装），status 如实。
6. **失败也交付**：任何异常不允许空手退出。partial/failed 也要有 result.json + 已完成部分。

## 线性流程（5 步，按序执行）

### Step 1 — 契约与骨架
```bash
ls -la /input/ && cat /input/case.json && cat /input/task.md 2>/dev/null || true
python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --status in_progress
```
- 从 case.json/task.md 提炼 `/app/work/constraints.json`：体裁、受众、引用风格、字数范围。
- 把每个 output_contract 字段映射到「由哪个产物回填」，记入 constraints 的 field_plan。
- 材料文件复制/整理到 `/app/work/sources/`（M01.txt…），manifest.jsonl 逐行登记
  `{"id":"M01","type":"原始研究|综述|指南|预印本"}`；PDF 若能读取文本则落 txt 并在原文
  保留 `[SRC:M01:p3|line12]` 定位锚点，不能读则如实记 uncertainty（不得伪造页码）。

### Step 2 — 写成稿（初稿）
- 按 constraints 与案例要求写 `/app/output/draft.md`：先全篇各段各写一版（短但有据），
  再充实；单响应只写 1-2 节，写完自检。
- 写作规则：**数值/样本量/统计量**与来源逐字一致（不取整不换算），来源没有的不写或标
  [待核]；**引用**只引材料中的文献条目，作者/年份/DOI 照抄，不堆装饰性引用；
  **措辞按证据强度选词**（A 级可用"证实"，B 级"结果表明"，C 级"综述提示"，D 级必带限定语）；
  相关≠因果；单篇小样本不写成领域共识；冲突证据并列注明，不择边隐藏。

### Step 3 — 论断切分与证据绑定
```bash
python3 scripts/claim_split.py --draft /app/output/draft.md --out /app/work/claims.jsonl
python3 scripts/evidence_bind.py --claims /app/work/claims.jsonl --sources /app/work/sources --out /app/work/evidence_table.jsonl
```
- claim_split 自动分类（numeric/citation/factual/interpretive）并预标 hedged/strong/universal。
- evidence_bind 按「数字一致优先 + 字面覆盖排序」匹配来源句，quote 为逐字子串（去空白比对）。
- match=none 的论断：回读来源找正确出处改稿，或删断言，或标 [待核] 记 uncertainty；
  **禁止保留来源不明的实质性论断**。

### Step 4 — 强度审计与双重校验（fail 必须修复一轮）
```bash
python3 scripts/strength_gate.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --out /app/output/strength_report.json
python3 scripts/verify_check.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --out /app/output/verify_report.json
```
- strength_gate 5 规则：R1 强断言×C/D证据=overclaim；R2 相关×因果词=causal_overreach；
  R3 全称词=overgeneralization；R4 未限定=needs_hedge；R5 强证据过度弱化=underclaim（双向把关）。
- verify_check 逐条机检 5 项：bound / verbatim / locator_format / in_draft / wording。
- FAIL 处置：只改对应论断/引文后重跑，不重写全文；修一轮仍 FAIL 照实登记继续交付。

### Step 5 — 增益探针与组装收尾
```bash
python3 scripts/gain_probe.py --result /app/output/result.json --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --ablate --write
python3 scripts/schema_guard.py --result /app/output/result.json --case /input/case.json --out /app/output/guard_report.json
python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --assemble \
  --draft /app/output/draft.md --claims /app/work/claims.jsonl \
  --evidence-table /app/work/evidence_table.jsonl --strength /app/output/strength_report.json \
  --verify /app/output/verify_report.json --status complete \
  --changelog '关键决策; 降级事实' --notes '材料缺口; 待核项'
```
- 先 gain_probe（--ablate 真跑出 gain_evidence/efficiency）再 --assemble 回填主产物；
  最后 schema_guard 终检（契约字段齐全、case_id 在位）。
- status 四级：全链路=complete；部分失败=partial（写明环节）；无法产出=failed；
  材料缺失无法开工=blocked（result.json 写明缺什么）。
- uncertainty 必含：材料缺口、[待核] 条目、证据冲突、仅摘要来源、降级事实。

## 异常处置表

| 情形 | 处置 |
|---|---|
| 来源文献不可得/仅摘要 | source_type 如实登记，等级记 D，正文加限定语；uncertainty 注明 |
| PDF 无法读取文本 | 不伪造页码；locator 置 p?（校验器 FAIL 如实），uncertainty 记录 |
| 两份来源数值冲突 | 并列注明两个口径与各自来源；不擅自取舍 |
| 论断找不到证据 | match=none → 改稿/删断言/标 [待核]；不得保留来源不明论断 |
| 响应被截断/中断 | 已写盘文件不受影响；从下一节继续；骨架 result.json 保证可解析 |
| claim_split 切分过碎 | 长句拆分后弱片段（<6 字）自动丢弃；关键论断可手工补入 claims.jsonl |
| 引用编号与文献表不一致 | 以材料文献条目为准逐条改号；对不上标 [待核] |
| 校验器异常/依赖缺失 | 脚本打印 error 后退出码仍 0；结论按 fail_count 照实写入 result.json |
| 预算将尽（≥48 次或 ≥700 秒） | 立即 Step 5 收尾，status 如实 |

## 最小调用示例（示意，非正式案例结果）

```bash
python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --status in_progress
# → {"ok":true,"mode":"skeleton","contract_fields":8}
# 写 /app/output/draft.md（示例内容见 examples/example_case.json）
python3 scripts/claim_split.py --draft /app/output/draft.md --out /app/work/claims.jsonl
# → {"ok":true,"claims_total":14,"by_type":{"numeric":5,"citation":6,"factual":2,"interpretive":1}}
python3 scripts/evidence_bind.py --claims /app/work/claims.jsonl --sources /app/work/sources --out /app/work/evidence_table.jsonl
# → {"ok":true,"claims":14,"bound_exact":12,"bound_none":2}
python3 scripts/strength_gate.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --out /app/output/strength_report.json
# → {"ok":true,"violations":3,"verdict":"fail"}   ← 修复一轮后
# → {"ok":true,"violations":0,"verdict":"pass"}
python3 scripts/verify_check.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --out /app/output/verify_report.json
# → {"ok":true,"verdict":"PASS","fail_count":0}
python3 scripts/gain_probe.py --result /app/output/result.json --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --ablate --write
# → fail_count_diff_base_minus_skill>0 且 sensitivity_check=PASS
python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --assemble --draft /app/output/draft.md --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --strength /app/output/strength_report.json --verify /app/output/verify_report.json --status complete
python3 scripts/schema_guard.py --result /app/output/result.json --case /input/case.json --out /app/output/guard_report.json
# → {"verdict":"PASS"}
```

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部字段（只增不删），任何时刻可解析
- [ ] 全部实质性论断在 claims.jsonl 且逐条绑定证据表；quote 逐字、locator 可回查
- [ ] 措辞与证据等级相称：无 overclaim/causal_overreach/overgeneralization；D 级有限定语
- [ ] 引用全部来自材料文献条目；冲突证据并列注明；[待核] 项在 uncertainty 显式列出
- [ ] draft.md 与论断清单一致（in_draft 全过）；成稿可继续编辑
- [ ] gain_probe --ablate 真跑：fail_count 差>0 且污染反例 sensitivity_check=PASS
- [ ] status/uncertainty/changelog 如实；未编造数据、文献或渲染状态
