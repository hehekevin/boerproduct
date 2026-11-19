# worklog — xling-lit-recall（challenge-802a7115）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期同周交付包（challenge-2dd1f64c / lit-screen-rank，其源自第 3 周
  冠军包 repro-verify）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新，逐条对应题面五个突破方向与四个机检点：
  - **术语映射有据**（方向1 术语扩展）：term_map 每条带 evidence_quote，校验器机械
    回证到案例材料位置（candidates[i].title/abstract）；
  - **逐语种检索式**（方向2/3）：build_queries.py 从映射机械派生，built_from 可回溯；
  - **跨语言版本归并**（方向4 语言识别/版本）：clusters + duplicate_of（正本=原文版），
    同题同版精确重复机械捕获；
  - **语言覆盖矩阵一致**：coverage_matrix 与 queries/items 机械对账，行集合=目标语种∪
    已判定语种，"静默新增语种"与"漏语种"都被判违规；
  - **翻译歧义登记**（方向5 误译复核）：ambiguities（readings + resolved/needs_review），
    needs_review 强制进 pending_review。

### 文件清单
| 文件 | 行数 | 说明 |
|------|------|------|
| SKILL.md | 150 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 223 | 落骨架 + 候选清单 + rubric 模板 |
| scripts/build_queries.py | 140 | 术语表机械派生逐语种检索式（键归属：result.queries） |
| scripts/lang_detect.py | 145 | 显式字符类语言判定（不用 isalpha，中文安全） |
| scripts/score_rank.py | 183 | 机械打分 + 确定性排序（键归属：ranking/fused_score/rank） |
| scripts/verify_check.py | 578 | 五组可消融校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 157 | 结构守卫 |
| scripts/gain_probe.py | 588 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 3 works/6 views 虚构记录 | 标注"非正式答案" |

脚本数 7（≤8 ✓）、文件数 10（≤50 ✓）、整包约 180 KB（<2MB ✓）、零外部依赖 ✓。

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- build_queries.py：`result.queries`
- score_rank.py：`result.ranking`、`items[].fused_score`、`items[].rank`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 数字回证规则（题面约束的落地）
- keep/pending 条目的 fused_score 必须出现在 claim text/quote 中；
- **标识符内嵌数字排除回证**：边界正则 `(?<![0-9A-Za-z_.])数(?![0-9A-Za-z])`，
  "V01" 里的 "01"、"W1" 里的 "1" 不作为回证命中；
- **区间端点保留**："0.91-0.95" 两端都算命中（连字符不属于排除字符类）。
- 中文处理全部用显式字符类/字符串方法，无一处 isalpha（lang_detect.py 用 Unicode
  区间表，score_rank 平局破序用字符串序）。

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-xling-001）

**全链路自测（干净输入）**：
- build_skeleton ✓（case_id=demo-xling-001，contract 6 字段，候选 6 条）
- lang_detect ✓（ja/zh/latin 判定 + 诚实 multi 降级）
- build_queries ✓（5 条映射 → 4 语种检索式：en/ja/pt/zh 各 1 条）
- score_rank ✓（V01 0.96 > V04 0.92 > V06 0.79 > V03 0.41，无平局）
- verify_check PASS（24 检查项全 applied，0 problems，unbacked_numbers=[]）
- schema_guard PASS
- gain_probe ✓（wall_clock≈0.0131s，result.json≈26.5KB）
- 干净输入上 normal vs degraded 五类漏检均为 0（无违规可漏，符合预期）；
  steps_count normal=32 / degraded=20（delta=+12：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 7 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | FAIL | — |
| problems | 12 | 1（仅恒开的排序复算） | −11 |
| 术语映射漏检 | 0 | 1 | +1 |
| 归并漏检 | 0 | 1 | +1 |
| 覆盖矩阵漏检 | 0 | 1 | +1 |
| 证据漏检 | 0 | 10 | +10 |
| 待复核漏检 | 0 | 1 | +1 |

注入的 7 项污染：T01 清空 evidence_quote（映射无据）；V02 清空 duplicate_of（版本
未归并重复计数）；V01 清空 criteria_hit/evidence_quote 并篡改 fused_score=9.9999；
coverage_matrix en 行 records_found+1（矩阵被篡改）；歧义 A02 needs_review 改
resolved（歧义登记丢失）；清空 pending_review；清空 claims。
正常模式抓全 12 处（caught_by_normal_mode=true）；退化模式 14 处客观违规漏掉 13 处
（仅剩恒开的排序复算抓到 1 处分数篡改）——"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**消融子集冒烟**：`--ablate termmap` 与 `--ablate all` 均退出码 0、报告照实降级
（degraded 执行检查项 12 条 / normal 24 条，disabled=5）。

**效率计数**：gain_probe 全链路 wall_clock≈0.0131s，result.json≈26.5KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上五类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. crosslang/recency 归一化口径是本技能在 rubric 事前声明的设定，不是外部标准。
4. examples 全部为合成案例（标题/摘要/DOI 虚构），非正式答案；正式结果只能来自平台
   3 个固定案例的实际运行。平台案例边界（3 works/6 views：葡/英原文、出版方全文译本、
   仅英文摘要、精确重复）已按题面在示例结构中对齐，但**不预置任何正式答案**。
5. lang_detect 只做字形判定，pt/es 等同字形语种区分靠停用词辅助且证据不足时诚实
   返回 multi；最终语种判定由 Agent 结合元数据（DOI/刊名）完成。
6. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
7. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与同周姊妹包（challenge-2dd1f64c）的差异（防同质化说明）
- 领域 schema 全换：纳排三层标签 → term_map/queries/clusters/ambiguities/coverage_matrix。
- 新增两个领域脚本：build_queries.py（映射→检索式机械派生）与 lang_detect.py
  （显式字符类语言判定，中文安全）。
- 校验组全换：纳排一致性 → 术语映射有据 + 跨语言归并 + 覆盖矩阵对账 + 证据回证 +
  歧义待复核五组；新增恒开的"语种登记"校验（静默新增语种判违规）。
- 数字回证规则按题面细化：标识符内嵌数字排除回证、区间端点保留。
- 污染注入改为领域化污染（映射删证据 / 清 duplicate_of / 篡改矩阵计数 / 歧义改
  resolved / 清空待复核 / 清空证据链）。
