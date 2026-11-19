# worklog — cite-fact-verify（challenge-cbe96f01）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期已交付同类包（challenge-0999879e / paper-review-audit，同赛道
  首个交付）复用：① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict
  照实写 JSON；③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门
  四态；④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新，对应本题四个机检点：
  1. **引用逐字回证**：confirmed 的 quote 空白归一化后逐字回证于稿件原文（verify_check A 组）；
  2. **数值一致性复算**：numeric_audit.py 机械复算"同标签+单位跨节数值漂移"与
     "显著性表述矛盾（p<阈值 vs p=值逐条复算）"两类确定性模式；findings 的
     numeric_claims 逐字回证原文（verify_check F 组）；
  3. **编造引用识别**：citation_audit.py 提取正文标记（[n] 与 Author-Year）与
     参考文献表机械比对 → fabricated_markers / uncited_refs；citation_fabrication
     发现的 cite_marker 须命中候选清单，反向矛盾（标记实际在文献表）也判 FAIL
     （verify_check E 组）；
  4. **pending 登记完备**：citation_state=cannot_determine ⇒ status 必须 pending
     （读不到被引文献不冒充已核对）+ pending_review 含 reason/needed_action
     （verify_check D+E 组）。
- 新增领域字段：findings[].cite_marker / citation_state（四态）/ over_inference /
  numeric_claims；新增两个机械审计键 result.citation_audit / result.numeric_audit。

### 文件清单
| 文件 | 行数 | 说明 |
|------|------|------|
| SKILL.md | 150（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 252 | 落骨架 + 稿件结构/参考文献数 + severity_rubric 模板 + 挂载标志校验 |
| scripts/citation_audit.py | 189 | 引用标记 vs 参考文献表机械比对（键归属：citation_audit） |
| scripts/numeric_audit.py | 213 | 数值漂移候选 + 显著性复算底账（键归属：numeric_audit） |
| scripts/coverage_audit.py | 196 | 六分面×章节覆盖机械审计（键归属：coverage/unchecked） |
| scripts/verify_check.py | 497 | 六组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 157 | 结构守卫（新增 citation_audit/numeric_audit/领域 finding 字段必填） |
| scripts/gain_probe.py | 529 | 双跑增益对照 + 领域化污染反例（键归属：gain_evidence/efficiency） |
| examples/example-case.json | 合成 5 章节虚构稿件（含编造引用 [9]、48/36 数值矛盾、p<0.01 vs p=0.04、[4] 全文未获取） | 标注"非正式答案" |
| examples/example-result.json | 示意输出（全链路实跑回写后落盘） | 标注"示意" |

共 10 个文件、约 160 KB（平台上限 50 文件 / 2MB）；脚本 7 个（上限 8）。

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- citation_audit.py：`result.citation_audit`
- numeric_audit.py：`result.numeric_audit`
- coverage_audit.py：`result.coverage`、`result.unchecked`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-citefact-001）

**机械审计命中（干净合成案例）**：
- citation_audit：正文标记 4 个（[1][2][4][9]）vs 参考文献表 4 条 → 编造候选
  `['[9]']`、未引用文献 `['[3]']` ✓
- numeric_audit：扫描数字 13 个 → 标签冲突候选 1（受试者名：48[S1,S4] vs 36[S3]）、
  p 表述违规候选 1（p<0.01[S1] vs p=0.04[S4]，复算 0.04 不满足 <0.01）✓
- coverage_audit：9 findings（confirmed=7 pending=1 suppressed=1），章节 4/5 有
  发现，S3 登记豁免，unchecked=0 ✓

**全链路自测（干净输入）**：verify_check PASS（44 检查项全 applied）/
schema_guard PASS（含 output_contract 全字段）/ gain_probe 两跑均 PASS、六类漏检
全 0（无违规可漏，符合预期）、steps_count normal=51 / degraded=7（delta=+44）/
单组消融 `--ablate citation,numeric` 仍 PASS 且 44 项 applied。

**同一校验器、同一污染输入（副本注入 7 项领域化污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 13 | 0 | −13 |
| 引用定位失据漏检 | 0 | 1 | +1 |
| 分级口径漏检 | 0 | 0 | 0 |
| 证据缺失漏检 | 0 | 7 | +7 |
| 待复核漏登记 | 1 | 2 | +1 |
| 编造引用漏检 | 0 | 1 | +1 |
| 数值漂移漏检 | 0 | 1 | +1 |

注入的 7 项污染：F01 清空 quote/location；F01 篡改 cite_marker 为 [99]（文献表
不存在的编造引用）；F04 篡改 numeric_claims 数值为原文不存在的 999（数值漂移）；
F03 标 pending 但清空 pending_reason；F01（fact_error）清空对照依据 evidence；
清空 pending_review；清空 claims。
正常模式抓全（caught_by_normal_mode=true；13 处问题含逐条列出），退化模式 11 处
客观违规全部漏检且 verdict 翻成 PASS。待复核漏登记 normal=1 是因为真值含两条
（F03 pending_reason 被清 + pending_review 被清）而捕获项按 finding 粒度计 1 条，
漏 1 条属真值口径差，如实记录不修饰。分级口径漏检 delta=0 是因为本次未注入
severity 违规（见诚实边界 3）。

**失败路径实测**：7 个脚本对缺失 result.json / 缺失 case.json 全部 **exit 0**
（build_skeleton 降级写骨架到备用路径），不中断交付。

**效率计数**：gain_probe 全链路 wall_clock≈0.0095s；example-result.json 回写
增益证据后约 60KB；`efficiency.model_requests` 保持 null（不可脚本采集，由
Agent 侧回填）。

### 防陷阱落实
- **isalpha 汉字陷阱**：numeric_audit / coverage_audit 统计英文词数一律用正则
  `[A-Za-z]+`（`en_words()`），并在 stats.note 写明原因——汉字
  `"字".isalpha()==True` 会把中文全部误计为英文词。
- **引文回证**：空白归一化子串匹配（`re.sub(r"\s+","",s)`），不做大小写折叠，
  保持中文逐字语义。
- **编造引用双锁**：发现须命中机械候选（防凭空指认），confirmed 引用的标记须
  回证文献表（防冒充引用）；探针侧另用同源函数独立复算真值（防校验层单点失灵）。
- **挂载标志**：build_skeleton 校验技能根 SKILL.md 存在（校验式命中），
  未命中时 WARN 进 problems，不中断。
- **脚本互导容错**：verify_check / gain_probe 对 citation_audit 的导入包在
  try/except，导入失败退化为闸门 warn，不崩溃。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上六类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例
   副本，已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 污染注入未覆盖 severity 违规维度，severity 组增益由口径映射规则与
   verify_check --ablate 间接支撑，未单独实测出非零 delta（与第 4 期前作相同的
   已知边界）。
4. 编造引用识别是"正文标记 vs 参考文献表"机械下界：脚注式/作者-年份变体样式
   可能漏检，Author-Year 匹配键为"首作者大写姓_年份"，重名同年不计入（候选须人工复核）。
5. 数值复算只覆盖"同标签漂移 + 显著性矛盾"两类确定性模式；前置标签取数字前
   紧邻中文/字母串末 3 字符，窗口选择是启发式，跨节同义不同词（如"纳入/招募"
   前缀不同）依赖末 3 字符恰好一致——本例"受试者"命中属设计使然，真实案例可能
   需调窗口；机械候选一律须 Agent 复核，不冒充终审结论。
6. 引文回证是"逐字出现于稿件原文"的机械下界，不能替代被引文献主张的语义核对；
   读不到文献时标 pending，不冒充已核对。
7. severity_rubric 与 suppression_rules 口径是本技能事前声明的设定，不是外部标准。
8. examples 全部为合成案例（论文/数据/文献虚构），非正式答案；正式结果只能来自
   平台 3 个固定案例的实际运行。
9. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
10. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与同赛道前作（challenge-0999879e / paper-review-audit）的差异（防同质化说明）
- 领域 schema 全换：通用六分面（含方法设计/统计报告/论证链）→ 引用核验专用
  六分面（citation_support/citation_fabrication/fact_consistency/numeric_consistency/
  source_reliability/evidence_locus）；新增 cite_marker / citation_state 四态 /
  over_inference / numeric_claims 字段。
- 校验组从四组扩到六组：新增引用规则组（四态枚举、不可判定⇒pending、标记回证
  文献表、编造候选对齐）与数值回证组（numeric_claims 逐字回证），消融开关同步扩。
- 新增两台领域机械引擎：citation_audit.py（标记比对）与 numeric_audit.py
  （漂移扫描 + p 值复算），替换前作没有的"机械复算"层；污染注入改为领域化
  （篡改 cite_marker 为 [99]、数值漂移 999，而非仅清空字段）。
- 闸门从 3 个扩到 5 个（新增 citation_audit_output / numeric_audit_output）。
