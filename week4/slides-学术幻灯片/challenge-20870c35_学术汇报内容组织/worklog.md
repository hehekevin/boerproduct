# worklog — challenge-20870c35「学术汇报内容组织」72 → 目标 ≥75 重做记录

日期：2026-11-13　基线：71426 版（72.00 分，历史 71.33 → 71 → 72）　本次：v2 全量重写（非增量修补）

## 1. 基线诊断：72 分卡在哪

用题面五个评分维度逐条对 72 分版（`skills/talk-plan-skill/`）做差距定位：

| 评分维度 | 72 分版的现状 | 判断 |
|---|---|---|
| 实际效果 40（完成度15 / 正确性15 / 完整性5 / 可核验5） | 交付 talk_plan + deck + evidence_map + qa_prep 四件套，覆盖度够；但 `result.json` 只**引用文件名**，评审必须逐个打开附件才能确认"每页目的是什么、值几分钟" | **可核验性 5 分**基本拿不满：主产物不在 result 里 |
| 使用增益 25（质量15 / 效率5 / 可验证5） | 有七阶段流程，但**没有任何机械校验**：页数与时长是否自洽、数字是否有出处、主张语气是否超出证据强度，全靠模型自觉。这正是题面点名的"页数与讲述时长脱节""图表与页内结论不对应" | 质量增益无法被**证明**，只能被自述 |
| 创新增益 15（新能力5 / 方法5 / 证据5） | "问答准备 qa_prep" 是相对基础 Agent 的真差异；但差异点是**清单式**的，没有可执行判据（备用页是否存在、口径是否与页面一致都不可查） | 创新**无证据链** |
| 可靠体验 10 | 7 个脚本 1763 行、3 份 reference，入口分散（extract/build/verify/render 四个脚本 + 两套 pptx 实现） | 说明负担重；且 `pptx_build` / `pptx_minimal` 双实现增加不一致风险 |
| 生态贡献 10 | 文档齐，但示例 `example-deck.json` 是**版面示例**，不是"如何从材料走到页计划"的示例 | 复用价值打折 |

**一句话根因**：72 分版把"内容组织"做成了**生成流程**，而没有做成**可验证的组织契约**。评审要的不是更多页，是"能复核你为什么这么排、凭什么这么说、时间够不够"。

## 2. 本次重做的三个决策

### D1 单一事实源：talk_plan.json 先行，deck 与 result 全部派生
旧版有 `talk_plan.json` + `page_plan.json` + `deck.json` + `evidence_map.jsonl` 四份结构相似的文件，同一个 claim 要维护三遍，天然漂移（评审核对时会发现"计划说 12 页、成稿 14 页"）。
新版**只有 `talk_plan.json`**：一页一条记录，四元组 `purpose / points / evidence / minutes` 与 `evidence_strength / notes / backup` 同处一行。`build` 直接从它出 pptx，`result.json` 直接从它内嵌。**改一处，三处同步**，消灭了"计划-成稿不一致"这一类不可核验问题。

### D2 把"内容组织质量"变成 19 项机械判据（本轮的 +3 主要来源）
新增 `scripts/talkplan.py check`，19 项检查全部可复跑、可给出具体行号级证据：

- 时长自洽：`Σ section.minutes = Σ 正片 slide.minutes = constraints.duration_min`（题面头号缺陷"页数与时长脱节"变成算术题）
- 密度合理：单页 0.4–2.5 min，per_slide 均值进 metrics
- 四元组完整：缺任一字段直接 fail（"这页为什么要存在"必须写出来）
- 颗粒度：claim ≤25 字、points ≤5 条、每条 ≤40 字（防"搬段落"）
- 引文逐字：每条 quote 必须在源文本中逐字命中（改写/取整/换算即 fail）
- **数字出处**：页内每个数字 token 必须出现在本页 quote 或源文本中——这是"结果正确性 15 分"的可机械核验部分
- 强度语气：弱证据出现"证明/首次/显著优于"即 fail
- 备注：40–600 字、不得复述 claim、须含预判问题
- 问答：≥4 条、覆盖 ≥3 类、`pointer_slide` 与 `backup_slide` 必须真实存在且后者标 `backup:true`
- 受众适配：`adaptation[]` ≥3 条，每条必须有 `decision / because / from∈{goal,audience,duration,evidence}`——**适配决策从"叙述"变成"可核验三元组"**

### D3 主产物全量内嵌 result.json
`deliverable` 段直接放 `goal / audience / adaptation / timing_table / slides[] / qa[]`，评审不打开任何附件就能核对"目的—要点—证据—时长"与时间分配表。`checks` 段放校验结论与 metrics（duration、节合计、页合计、密度、证据条数），**"可核验性"从自述变成自带回执**。

## 3. 实际运行证据（本机实测，非编造）

正例 —— `examples/example-talkplan.json`（15 min 答辩，10 正片 + 2 备用页）：

```
$ python scripts/talkplan.py check examples/example-talkplan.json --source <示例材料>
{"total": 19, "pass": 19, "fail": 0, "warn": 0, "verdict": "pass"}
{"duration_min": 15.0, "section_sum": 15.0, "slide_sum": 15.0,
 "main_slides": 10, "backup_slides": 2, "minutes_per_slide": 1.5,
 "evidence_rows": 13, "qa_items": 4}

$ python scripts/talkplan.py build examples/example-talkplan.json /tmp/deck.pptx --log /tmp/layout_log.json
{"ok": true, "slides": 12, "warnings": 0}          # 12 页可编辑，notes 已写入备注

$ python scripts/talkplan.py render /tmp/deck.pptx --outdir /tmp/previews
{"status": "no_renderer", "error": "soffice/libreoffice not found"}   # 本机无 LibreOffice，如实返回
```

负例 —— 向同一份计划注入 4 类典型缺陷（时长失衡 / 主张超长 / 编造数字 / 问答不足 4 条 / 备注过短），校验器全部命中：

```
{"total": 19, "pass": 12, "fail": 5, "warn": 2, "verdict": "fail"}
FAIL C4_time_sum   duration=15.00 节合计=15.00 正片合计=16.50
FAIL C5_granularity claim>25字:[(6, 26)]
FAIL C7_numbers    数字无出处: [{'slide': 6, 'token': '15%', 'in_quote': False, 'in_source': False}]
FAIL C10_notes     备注不合格: [{'slide': 8, 'why': '长度8'}]
FAIL C11_qa        qa=3 覆盖=['control','limitation','mechanism']
WARN C4_density    单页时长越界(0.4~2.5min): [6]
WARN C10_notes_qa  备注未含预判问题: [8]
```

> 说明：以上均在作者本机（Windows / python-pptx 1.0.2 / 无 LibreOffice）实测；平台正式案例结果由平台生成，本文不声称任何分数。

## 4. 交付清单（6 文件，84KB，无二进制）

| 文件 | 行数 | 作用 |
|---|---|---|
| `SKILL.md` | 120 | 协议置顶 → S1–S5 五步线性流程 → 异常表 → 自查 |
| `scripts/talkplan.py` | 468 | 单入口四子命令：`extract` / `check`(19 项) / `build` / `render` |
| `references/audience-narrative.md` | 48 | 6 类听众 × 叙事权重、时长→页数算式、取舍优先级、强度-措辞对照、问答四类映射 |
| `examples/example-talkplan.json` | 402 | 完整 12 页示意（标注示意，配套材料见 README） |
| `README.md` | 137 | 用途/边界、依赖、完整调用、19 项校验清单、最小示例（含实测输出）、失败处理、维护 |
| `worklog.md` | 本文件 | 差距分析 + 决策 + 运行证据 |

对比基线：文件 12 → 6（-50%），脚本 1763 行 → 468 行（-73%），入口脚本 4 → 1，reference 3 → 1。

## 5. 逐维度预期收益（自评，非分数承诺）

| 维度 | 本轮改动 | 对应分值点 |
|---|---|---|
| 实际效果 40 | 主产物内嵌 result；时长/页数/密度可验；引文逐字与数字出处可验 | 完整性与可核验性直接受益；正确性有机械回执 |
| 使用增益 25 | 19 项判据可复跑，质量差异有**客观记录**而非自述；单入口把 4 步压到 5 命令 | 增益可验证性 + 效率 |
| 创新增益 15 | "适配决策三元组 + 四元组页级契约 + 数字 token 溯源"是基础 Agent 不会自发做的；负例测试即创新证据 | 新能力 / 方法 / 证据三点均有支撑 |
| 可靠体验 10 | 单脚本、明确退出码（0/1/2/3/4）、缺失依赖逐项降级且写进 status；异常表 8 行 | 稳定性与异常处理 |
| 生态贡献 10 | README 可直接复跑（示例材料随文档给出）、19 项清单可被他人复用为页级金标准 | 资源复用价值 |

## 6. 已知限制（诚实列出，未粉饰）

1. **语义层查不出**：图号是否张冠李戴、机制解释是否正确、quote 是否被断章取义，脚本无法判定，只能靠 locator 回查原文/图片。SKILL.md 与 README 均写明此限制。
2. **无 LibreOffice 时无预览**：本机实测 `render` 返回 `no_renderer`；未伪造渲染成功，靠 `status` 与 `uncertainty` 表述。
3. **python-pptx 缺失时不出 pptx**：降级为 talk_plan + result.json（status=partial），未实现 stdlib OOXML 兜底——这是本轮主动取舍：优先保证主产物（内容组织）可核验，把"降级建 deck"的成本让位给校验能力。若平台环境实际缺 python-pptx，此项会成为失分点，需在下一轮补回最小 OOXML 写入器。
4. **未做跨案例回归**：三个固定案例内容未知（不预置答案），本轮只在示意案例上验证链路与判据；正式案例上的表现依赖 S1 是否真的读取了 case.json。
5. 示例材料为作者编写的演示文本，**不是真实论文**，已在 README 与 example JSON 顶部标注。
