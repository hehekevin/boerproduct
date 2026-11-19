# 基金申请书写作资源包（可复用 · 可直接套用于自己的申请）

> 本文件是 acwrite-grant 的配套资源，供他人**独立用于自己的申请书**。不含任何正式案例答案。
> 用法：把本文档复制到自己的工作目录，按需裁剪；机检脚本见 `scripts/`。

## 一、七要素清单（逐条写实，禁止"口号堆叠"）

| 要素 | 写什么 | 不写什么 | 自检问题 |
|---|---|---|---|
| 立项依据 | 别人做到哪一步→还差什么→为什么是申请人→为什么是现在 | "意义重大""符合国家战略" | 每段能否指到具体文献/前期成果？ |
| 科学问题 | 收敛到 1–3 个可回答、可分解、有边界的问题 + 判断标准 | "如何实现突破" | 什么问题算回答？什么结果算没回答？ |
| 研究目标 | 与科学问题一一对应，数量适度、可考核 | "全面提升研究水平" | 目标数与路线条数、指标条数是否对得上？ |
| 研究内容 | 目标对应的具体展开 + 输入输出 | 罗列方法名 | 每条内容能挂到哪个目标？ |
| 技术路线 | 按内容组织步骤、方法、关键节点、风险与备选 | "采用先进方法" | 每步的输入/输出/风险/备选是否写全？ |
| 创新点 | 与**具体**已有工作的差别 + 凭什么做得成 | "首次""国际领先""填补空白" | 每条创新点能否指名道姓说清"与谁比、差在哪"？ |
| 研究基础与可行性 | 能力—证据—与本研究的关系的证据链 | 罗列平台设备 | 每条前期成果是否有逐字摘录 + 定位？ |

**二态纪律**：前期成果必须分「已完成」「拟开展」。已完成需逐字摘录 + 文件页/段定位；拟开展不得写成已有成果。

## 二、四向对齐检查表（目标 ↔ 内容 ↔ 路线 ↔ 指标）

逐格打勾，任一格为空即为孤儿项，必须补齐或删掉对应行：

| 目标 ID | 目标陈述 | 对应内容 ID | 对应路线 ID | 对应考核指标 | 指标可考核？ | 内容↔路线↔指标是否同一件事 |
|---|---|---|---|---|---|---|
| G1 | | C1 | R1 | | 是/否 | 是/否 |
| G2 | | C2 | R2 | | 是/否 | 是/否 |

对齐表落盘格式（`alignment.jsonl`，一行一目标）：
```json
{"goal":"G1","contents":["C1"],"routes":["R1"],"metrics":["完成 1 套因果验证实验"]}
```

路线表落盘格式（`routes.jsonl`，一行一路线，步骤必须含输入输出）：
```json
{"rid":"R1","steps":[{"in":"…","out":"…","node":"关键节点","risk":"风险","backup":"备选方案"}]}
```

## 三、事实与来源映射表（`evidence_map.jsonl`）

**四字段齐全，缺一不可**：`kind`（论断类型）/ `evidence`（≤40 字逐字摘录）/ `source_id`（材料 ID）/ `location`（页/段定位）。

```json
{"kind":"prior_work","evidence":"覆盖 42 例样本","source_id":"M01","location":"M01:p3"}
{"kind":"claim","evidence":"缺失率低于 3%","source_id":"M01","location":"M01:p4"}
```

`kind` 建议取值：`claim`（关键论断）/ `prior_work`（前期成果）/ `number`（数字）/ `citation`（引用）/ `policy`（政策口径）。

**逐字回证**：`evidence` 必须是材料原文的连续片段，空白归一后应能在对应 `location` 找到；不允许改写、不允许拼接。

## 四、预算数字-来源核对表（`budget_ledger.jsonl`）

每条预算**必须**带 `status` 与 `source_locator`，二者缺一即被机检判为疑似编造。

| status | 含义 | 正文怎么写 |
|---|---|---|
| `sourced` | 材料中有明确出处 | 写具体金额，并注明来源 |
| `assumed` | 无直接出处但有明确估算依据 | 写"按 X 估算"，并写明估算口径 |
| `missing` | 材料无依据 | **不写金额**，写占位符并列入待人工确认 |

```json
{"item":"材料费","amount":12.0,"source_locator":"M02:p2","status":"sourced"}
{"item":"劳务费","amount":15.0,"source_locator":"","status":"assumed"}
{"item":"数据处理费","amount":null,"source_locator":"","status":"missing"}
```

## 五、创新点 vs_existing 对照表（`innovation_vs_existing.jsonl`）

每条创新点五行缺一不可：**claim**（我声称什么）/ **vs_existing_who**（与谁比，必须具体到工作）/ **difference**（差在哪）/ **why_can_win**（凭什么做得成）/ **evidence_locator**（依据在材料哪里）。

```json
{"claim":"低氧作为可控扰动做因果拆解","vs_existing_who":"Zhang 2021 method A",
 "difference":"仅单点相关性 vs 时间梯度+位点级分辨率",
 "why_can_win":"已有 1200 例队列(M01:p4)","evidence_locator":"M01:p4"}
```

写不出 `vs_existing_who` 和 `difference` 的创新点，通常说明它还没有被证成——删掉或改写，不要用修饰词掩盖。

## 六、禁用修辞词表

`国际领先` `国际首创` `填补空白` `世界首创` `重大突破` —— 出现即机检 fail（`banned_claims`），除非上下文明确是"与已有工作对照"的语境。

`首次` 属软禁用：可以出现在"首次在该体系中观察到…"这类**有对照依据**的句子里，但必须能指到对照表里的一行。

## 七、待人工确认项清单（`notes_for_human.json`）

凡是无法从材料机械判定、必须由申请人拍板的事，逐条列出并给出"缺什么"：

```json
["待补：申请人第一作者论文原件编号（材料仅给检索结果）",
 "待核：设备费 20 万元是否含税（指南未说明口径）"]
```

## 八、章节落盘与回填

一个章节 = 一个文件 `chNN_<短名>.md`，写完立即回填 `result.json`（`--append`），中断也有半成品可交付。

| 文件 | 章节 | 关键约束 |
|---|---|---|
| ch01 | 立项依据 | 四字段证据挂账 |
| ch02 | 科学问题与研究目标 | 判断标准 + 目标与 alignment 一一对应 |
| ch03 | 研究内容 | 无来源数字标"拟" |
| ch04 | 技术路线 | 输入/输出/节点/风险/备选 |
| ch05 | 创新点 | 先写对照表再成文 |
| ch06 | 研究基础与可行性 | 逐字摘录 + 二态分清 |
| ch07 | 预算 | 逐条 status + locator |

## 九、自查评分表（提交前逐项打勾）

| # | 检查项 | 通过标准 | ✓ |
|---|---|---|---|
| 1 | 契约字段齐全 | output_contract 全部键存在且非空 | |
| 2 | 章节完整 | 7 章 embed_gate 全 embedded | |
| 3 | 对齐无孤儿 | goals_no_orphan / metrics_measurable / routes_used_and_io 全 match | |
| 4 | 无裸用修辞 | no_banned_claims match=True | |
| 5 | 创新点有对照 | innovation_vs_existing match=True，且对照表已嵌入 | |
| 6 | 预算有来源 | budget_sourced match=True，无来源金额未落数字 | |
| 7 | 前期成果可回证 | 每条 kind=prior_work 有 ≤40 字摘录 + location | |
| 8 | 二态分清 | 已完成/拟开展无混淆 | |
| 9 | 增益证据真实 | gain_evidence 两档齐全，数字由脚本实跑产生 | |
| 10 | 状态诚实 | status 为 complete/partial/failed/blocked 之一且与实际相符 | |
| 11 | 待确认项明确 | notes_for_human 非空且每条可执行 | |
| 12 | 渲染真实 | 无渲染器时如实标 no_renderer | |

## 十、维护与扩展

- 新增材料格式 → 扩展 `scripts/extract_materials.py` 的解析函数（当前支持 docx/pdf/txt/md/csv/tsv/xlsx/json/html/rtf/bib/tex/pptx，缺库时逐格式降级）。
- 预算科目变化 → 只改 `budget_ledger.jsonl` 内容，脚本无需改动。
- 新增检查项 → 在 `scripts/align_check_grant.py` 的 `checks` 列表追加 `{item, template_value, applied, match}`，并同步本文件的第八节。
- 脚本失败路径退出码恒为 0；判定一律看报告里的 `verdict`/`fail`/`problems`，不要用退出码判断成败。
