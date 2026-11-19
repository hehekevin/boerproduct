---
name: acwrite-transfer
description: 科研成果转化写作技能：按目标读者画像做受众适配改写（论文→科普/新闻稿/申报材料），内容取舍三档清单（必须保留/可压缩/可删除+理由），术语表锁定与首次展开，关键结论/数据/限定条件完整保留，论断强度与源文匹配。Use when the case asks to adapt research output for a different audience (public science article, press release, project material), preserving facts, data and limitations with an auditable content-triage list.
---

# acwrite-transfer — 成果转化改写（受众画像 · 取舍留痕 · 事实不丢）

转化的难点是**读得懂但不写丢**：改写给外行时证据和限定条件最容易被一起删掉。本技能用**取舍清单**管住每一处删改。交付三件套：

1. **改写稿**：transfer.docx + transfer.md（按目标体裁组织）
2. **取舍与溯源**：triage.jsonl（三档取舍清单）+ evidence_map.jsonl（关键结论/数据/限定条件 → 源文逐字证据）
3. **版本与边界**：术语对照表 + 待确认项 + changelog


## 主路径收敛令（P0，覆盖其他流程指令）

1. **交付优先序**：骨架落盘 → 主字段/主内容补全 → result.json 完整可解析（此步完成即达到可交付状态）→ 校验器 → 增益层。
2. **增益层降级为可选**：gain_probe 的消融双跑与污染反例自测只在剩余预算（请求+时间）≥40% 时执行；预算不足直接跳过，在 result.json 的 gain_evidence 写 {"available": false, "reason": "budget_exhausted"}，**禁止**为增益证据挤占交付预算。
3. **预算告急即定稿**：任一时刻请求次数或时间过半仍未完成校验，立即以当前 result.json 定稿交付，缺失键如实登记，禁止继续展开任何支线。
4. 主线禁止执行污染反例自测（那是离线取证工具，非交付必需）。
## 0. 强制执行协议（7 条，先于一切）
1. **抄契约**：读 `/input/case.json`，把 `output_contract` 全部字段名逐字抄下（含 `case_id`）——result.json 字段与契约一一对应，一个不缺。
2. **立即落骨架**：开跑第一步就用 build_result.py 写 `/app/output/result.json` 骨架（status=partial，契约字段全为 null），此后每阶段结束回填。
3. **每步一个写盘动作**：每次响应只做一个阶段 + 一次写盘；先写盘再继续，广度优先（先全链路跑通再加深），不许在一个阶段内反复打磨。
4. **熔断**：预算 64 请求 / 900 秒；**48 次请求或 700 秒即进入收尾**——停止新内容，只做回填、校验、result.json 收口。
5. **写盘前 JSON 自检**：任何 json/jsonl 落盘前确认可解析、字段完整；result.json 每次写盘前做 load 校验。
6. **失败也交付**：任何阶段崩溃/超时，也要保证 /app/output/result.json 是合法 JSON（status=partial 或 failed，缺什么在 uncertainty 写明）。
7. **嵌入完整性**：主产物全文必须结构化嵌入 result.json（build_result.py --embed-md 自动分块），评分器不开附件即可核对。

## 1. 阶段流程

### Stage 0 — 定契约与骨架
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial
python3 scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
- constraints.json 记：目标体裁（科普文章/新闻稿/申报材料/内参）、读者画像、字数、术语表。**status 只许四级：complete/partial/failed/blocked**，如实降级不扣分，嵌入完整性才是得分主体。

### Stage 1 — 读者画像与解释策略（1 次响应，产出 /app/work/audience.json）
`{"reader":"城市大众读者","prior_knowledge":…,"reading_purpose":…,"needs":[…],"strategy":{"term_density":"每千字≤3个术语","analogy_style":"生活类比","depth":"结论+原因，不展开方法细节","examples":"取1-2个贴近读者的例子"}}`
- 体裁规范：新闻稿=倒金字塔（结论先行）；科普=问题引入→发现→意义→边界；申报材料=成果-指标-应用价值。

### Stage 2 — 内容取舍三档清单（1 次响应，产出 /app/work/triage.jsonl）
逐段盘点源文：`{"sid":"S05","src_locator":"M01:p2|para4","tier":"keep|compress|drop","content":…,"reason":…,"keep_priority":"关键结论|限定条件|数据支撑|方法要点|背景"}`
- **必须保留（keep）**：核心结论及其限定条件、关键数据（数值/样本量/口径）、图表引用、安全/伦理相关声明。
- **可压缩（compress）**：方法细节（一句话概括）、次要结果。**可删除（drop）**：文献综述细节、重复背景、行话套话——drop 一律给理由。
- 同步产出 /app/work/evidence_map.jsonl：每条 `{"claim_id":"C01","kind":"conclusion|number|limitation|term|figure|citation","claim":"一句话论断","evidence":"源文逐字摘录≤40字（空白归一化后必须能在源文子串匹配）","source_id":"M01","location":"p2|para4"}`。不编造；材料不足标 uncertainty，不硬凑。

### Stage 3 — 改写（1-2 次响应，产出 draft.json）
- **术语**：terminology.jsonl 锁定（术语↔通俗表达对照）；缩写首次出现展开；同一概念全文一个说法。
- **数字**：数值/单位/比较基准/样本量与源文一致；换算留痕；百分比不换口径。
- **强度匹配**：逐句对照 triage 的 keep 条目——限定语（"在X条件下""初步"）必须跟着结论走；机制推测标"研究者推测"。
- **类比**：只用帮助理解的类比，不把类比写成事实（"类似于"句式）。
- **引用**：数据出处不丢；新闻稿注明研究来源与机构。

### Stage 4 — 组稿与校验（1 + 3 次脚本）
```bash
python3 scripts/docx_build.py /app/work/draft.json --out-docx /app/output/transfer.docx --out-md /app/output/transfer.md
python3 scripts/fact_ledger.py check --draft /app/output/transfer.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python3 scripts/triage_audit.py --triage /app/work/triage.jsonl --source /app/work/extracted --transfer /app/output/transfer.md --out /app/output/triage_audit.json
python3 scripts/consistency_check.py --draft /app/output/transfer.md --constraints /app/work/constraints.json --out /app/output/check_report.json
```
- 任一校验 exit≠0 必须修复重跑（数字回台账核对、补回 keep 落点、降级强度词），不许打印了事。
- 证据回证（Stage 6 由 build_result.py 代跑）：evidence_map 每条 evidence 空白归一化后逐字子串匹配源文；unbacked 逐条列出计入 fail。

### Stage 5 — 渲染
```bash
python3 scripts/render_preview.py --src /app/output/transfer.docx --outdir /app/output/previews
```

### Stage 6 — result.json（嵌入 + 闸门收口）
```bash
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact transfer.docx --artifact-md transfer.md \
  --embed-md /app/output/transfer.md --evidence /app/work/evidence_map.jsonl \
  --source /app/work/extracted --fact-check /app/output/fact_check.json \
  --triage /app/work/triage.jsonl --consistency /app/output/triage_audit.json \
  --render /app/output/previews/render_log.json --status complete
```
- build_result.py 自动产出 **gates 区**：每个可核验点一条 `{item, template_value, applied, match}` 三元组 + 闸门状态显式枚举 `enforced / skipped_not_provided / not_found / unreadable`。**没跑 ≠ 通过**：未运行的闸门标 skipped_not_provided 或 not_found 并写 gate_note「下游不得宣称已核对」。
- 主产物全文分块嵌入 `main_artifact_text`（每块 ≤1500 字，嵌入后回验字符数一致）。

## 2. 异常处置表

| 情形 | 处置 |
|---|---|
| 源文含大量统计细节 | 压缩为"研究跟踪了X人、持续Y年"；具体数值保留关键项，其余指向原文 |
| 术语无法通俗化 | 保留术语+一句话定义；uncertainty 列出 |
| 源文结论限定条件多 | 逐条保留；宁可句子长不丢边界 |
| 目标体裁要求标题党/夸张 | 拒绝升级词；用具体数字与对比制造张力；changelog 说明 |
| 源文是预印本 | 改写稿注明"预印本/未经同行评审" |
| 读者画像未指定 | 按体裁默认画像并在 audience.json 标 assumed |
| 校验脚本崩溃/缺依赖 | gate 标 unreadable + gate_note；改用人工核对清单并在 uncertainty 声明，不静默跳过 |

## 3. 最小调用示例（示意）
```bash
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial  # 骨架先行
# （模型响应：audience.json 画像 / triage.jsonl+evidence_map.jsonl 逐段挂账 / draft.json）
python3 scripts/docx_build.py /app/work/draft.json --out-docx /app/output/transfer.docx --out-md /app/output/transfer.md
python3 scripts/fact_ledger.py check --draft /app/output/transfer.md --ledger /app/work/fact_ledger.jsonl
python3 scripts/triage_audit.py --triage /app/work/triage.jsonl --source /app/work/extracted --transfer /app/output/transfer.md
# → {"keep_missed":0,"strength_violations":0,"verdict":"pass"}
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --artifact transfer.docx \
  --embed-md /app/output/transfer.md --source /app/work/extracted --status complete
# → result.json 含 gates（每闸门 enforced/pass）+ main_artifact_text 全文嵌入
```

## 4. 增益证据与效率计数（可选自证，不阻塞主交付）
同输入跑完整模式与消融模式各一遍，产出可核验的增益数字；正式案例预算紧张时可跳过，不影响主流程。
```bash
# 1) 从源文派生必须保留项清单（rubric 两臂共用，与 A/B 无关）
python3 scripts/align_audit.py rubric --source /app/work/extracted --limit 40 --out /app/work/rubric.jsonl
# 2) 完整模式计分（--transfer 指向完整改写稿）
python3 scripts/align_audit.py table --triage /app/work/rubric.jsonl --source /app/work/extracted \
  --transfer /app/output/transfer.md --audience /app/work/audience.json \
  --terminology /app/work/terminology.jsonl --seed examples/terminology_seed.jsonl \
  --condition A_full_skill --out /app/output/gain_table_full.json
# 3) 消融模式计分（--ablate：同一输入忽略完整稿，改用同源机械派生的机制关闭退化稿计分）
python3 scripts/align_audit.py table --ablate --triage /app/work/rubric.jsonl --source /app/work/extracted \
  --transfer /app/output/transfer.md --audience /app/work/audience.json \
  --terminology /app/work/terminology.jsonl --seed examples/terminology_seed.jsonl \
  --condition B_degraded --out /app/output/gain_table_ablated.json
```
- 两份 table JSON 的 `metrics` 即真实对照数字：事实漂移数、受众错配数、术语不一致数、关键结论保留占比（key_conclusion_retention.ratio）、需人工编辑条目数（manual_edit_items）、返工轮次（rework_rounds）。示例结构与量级见 `examples/ablation_gain_example.json`（示意，非正式案例）。
- **键互补不覆盖**：增益证据写入 result.json 的独立辅助键（如 `gain_evidence`、`efficiency`），与 output_contract 契约字段互补，不覆盖、不改动任何既有键；若主控流程另有 `registry_evidence` 等独立键，同样只增不改，与 `gain_evidence` 互为补充。
- 效率计数口径：manual_edit_items = 校验问题 + 事实漂移 + 受众错配 + 术语不一致 + 强度升级词 + 待确认项之和；rework_rounds 优先取 repair_log 实测（每行一轮），无记录时用 estimate_rework_rounds 机械估算并在 `rework_rounds_source` 标明。
- 诚实边界：消融 B 臂是脚本确定性派生的机制关闭基线，用于同输入同口径对照，不等价于组织方正式基础 Agent，不替代官方对照。

## 5. 交付自查清单
- [ ] 读者画像明确；解释策略落实（术语密度/类比/深度）
- [ ] triage 三档清单逐段登记；keep 项全部落稿（triage_audit pass）
- [ ] 关键数据/限定条件/样本信息零丢失；换算留痕
- [ ] 术语锁定；缩写首现展开；同一概念一个说法
- [ ] 无强度升级词；类比不当事实
- [ ] evidence_map 每条逐字≤40字且子串可回证；fact_check pass
- [ ] result.json：契约字段无缺、main_artifact_text 全文嵌入、gates 全枚举、fail 已冒泡修复、status 如实四级
- [ ] （可选）增益对照已实测：完整 vs --ablate 两份 table 的 metrics 真实数字写入 result.json 独立辅助键
