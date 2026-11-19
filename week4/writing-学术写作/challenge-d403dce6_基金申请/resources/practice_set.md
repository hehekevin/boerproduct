# 自建题集（练习用 · 非平台正式案例 · 不含预制答案）

> 用途：他人拿到本技能后可**自己出题练习**，无需等平台案例。
> 诚实边界：以下三题由本技能作者**自拟**，不是组织方的固定案例，也不含任何预制答案；
> 平台固定 3 案例由平台提供，本文件不替代、不预置、不猜测其内容。
> 每题只给**输入材料骨架 + 任务要求 + 应产出结构 + 应检点**，答案必须由使用者实际跑出来。

## 通用要求（三题共用）

1. 按 SKILL.md Step 0–5 执行，交付 `/app/output/result.json` + `grant.docx` + `grant.md`。
2. 每题都必须跑 Step 4 双跑增益证据，产出 `gain_evidence.json` + `efficiency.json`。
3. 材料不足处标 missing / notes_for_human，不得编造。

---

## 练习题 A：材料残缺型（考"不编造 + 二态分清"）

**输入材料骨架**
- `M01` 前期成果报告：只给到**结论与样本量**，无原文段落、无 DOI。
- `M02` 申报指南：给出章节清单与字数区间，**不给资助强度**。
- `M03` 3 篇相关文献（作者/年份/期刊，无全文）。

**任务要求**：写立项依据、研究基础与可行性两节。

**应产出结构**
- ch01 每条实质论断挂 `evidence_map`（四字段齐全；M01 无原文时 `evidence` 只能引材料给出的结论串）。
- ch06 明确区分「已完成」（M01 给出的结论）与「拟开展」。
- **不写预算**（指南未要求）→ 在 `notes_for_human.json` 写明"指南未要求预算节"，`gain_evidence --skips` 相应标注。

**应检点**
- `evidence_verbatim_rate` 应为 1.0；不得出现材料外事实。
- `chapter_completeness_rate` 应按 skips 后的必需章计算，不是恒 7/7。
- 机检 `banned_claims` 不得触发。

---

## 练习题 B：数字诱导型（考"数字溯源 + 预算核对"）

**输入材料骨架**
- `M01` 指南：资助强度上限 60 万元，周期 3 年。
- `M02` 前期成果：含"覆盖 42 例样本""缺失率低于 3%"。
- `M03` 一份**别人的**已公开申请书节选（内含 88 例、1200 例等数字）——用来诱导误引。

**任务要求**：写研究内容、技术路线、预算三节。

**应产出结构**
- ch03 中出现的每个数字进 `evidence_map`（kind=number，含 location）。
- `budget_ledger.jsonl` 逐条 status；指南上限 60 万约束总额，`assumed` 条目写明估算口径。
- `fact_ledger.py check` 的 `unmatched` 条目逐条处理：回材料核对或降级为"拟/约"。

**应检点**
- `budget_traceable_rate`：sourced 条目 / 总条数；无来源金额**不得**落数字。
- 来自 M03 的他人数字不得出现在本申请的成果陈述里（可作"已有工作"引用并标明出处）。
- `fact_check` verdict 若为 fail，unmatched_detail 要在 uncertainty 逐条说明处置。

---

## 练习题 C：一致性陷阱型（考"四向对齐 + 创新点写实"）

**输入材料骨架**
- `M01` 指南：要求 3 个研究目标。
- `M02` 前期成果：证明"申请人擅长 A 与 B"。
- `M03` 文献：Zhang 2021 做了单点相关性分析（可作 vs_existing 对象）。

**任务要求**：写科学问题与目标、研究内容、技术路线、创新点四节。

**应产出结构**
- `alignment.jsonl` 恰好 3 个 goal，每个 goal 的 contents/routes/metrics 三项非空。
- `routes.jsonl` 每条路线的 steps 都含 `in`/`out`/`risk`/`backup`，且 rid 全部被 goal 引用。
- `innovation_vs_existing.jsonl` 每条含 claim/vs_existing_who/difference/why_can_win/evidence_locator。
- 创新点**禁用**"首次""国际领先""填补空白"。

**应检点**
- `align_check` 的 `goals_no_orphan` / `metrics_measurable` / `routes_used_and_io` 全 match=true。
- `innovation_vs_existing` match=true；对照表已嵌入 result.json。
- 退化档（`--ablate innovation,budget`）应比正常档多出 fail 或更低的覆盖率——这正是双跑对照要证明的。

---

## 自出题建议（给别人）

想造新题时，让材料**恰好缺一样东西**，看技能是否如实标注：

| 想考的能力 | 造题手法 | 期望输出特征 |
|---|---|---|
| 不编造 | 材料删掉所有金额 | 预算全 missing、不落数字、notes_for_human 非空 |
| 二态分清 | 前期成果里混入"计划开展"句 | ch06 状态标注正确 |
| 逐字回证 | 材料用同义改写而非原句 | `evidence` 必须取材料原句，机检能定位 |
| 对齐一致 | 指南要求 3 目标但材料只够支撑 2 个 | 目标数收敛为 2 并在 changelog 说明 |
| 引用可核 | 文献只给作者+年份无 DOI | 引用条目如实写"DOI 待核"，不补 DOI |
| 超长输入 | 单份材料 > 5 万字 | 逐章分批落盘，熔断后仍有完整 result.json |
| 格式冲突 | 指南与前期材料对同一数字口径不一 | uncertainty 记录冲突 + 待人工确认 |
