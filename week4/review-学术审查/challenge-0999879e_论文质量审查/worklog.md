# worklog — paper-review-audit（challenge-0999879e）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期已交付同类包（challenge-2dd1f64c / lit-screen-rank）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：六分面审查（事实核验/引用支持/方法设计/统计报告/论证链/学术规范）、
  引文逐字回证于稿件原文、严重度三级口径事前声明、四类区分
  （事实错误/证据不足/规范问题/建议）、误报抑制规则表、待复核登记——
  全部对应题面六类检查项与机检点（六项覆盖、定位可回证、严重度分级口径、
  误报抑制规则、待复核登记）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 144 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 250 | 落骨架 + 稿件结构 + severity_rubric 模板 + 挂载标志校验 |
| scripts/coverage_audit.py | 195 | 六分面×章节覆盖机械审计（键归属：coverage/unchecked） |
| scripts/verify_check.py | 385 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 156 | 结构守卫 |
| scripts/gain_probe.py | 462 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 5 章节虚构稿件 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- coverage_audit.py：`result.coverage`、`result.unchecked`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.x，Windows，合成案例 demo-paperaudit-001）

**全链路自测（干净输入）**：build_skeleton ✓（章节 S1–S5 全部提取）/
coverage_audit（9 findings：confirmed=7 pending=1 suppressed=1，章节 5/5 有发现，
facet_counts 六项 1/2/2/2/1/1，unchecked=0）✓ /
gain_probe 两跑均记录成功 / verify_check PASS（26 检查项全 applied）/
schema_guard PASS（含 output_contract 全字段）。
干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=33 / degraded=7（delta=+26：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 11 | 0 | −11 |
| 定位失据漏检 | 0 | 1 | +1 |
| 分级口径漏检 | 0 | 0 | 0 |
| 证据缺失漏检 | 0 | 7 | +7 |
| 待复核漏登记 | 0 | 1 | +1 |

注入的 5 项污染：F01 清空 quote/location（定位失据）；F08 清空 pending_reason；
F01（fact_error）清空对照依据 evidence；清空 pending_review；清空 claims。
正常模式抓全（caught_by_normal_mode=true，11 处问题含逐条列出），
退化模式 9 处客观违规全部漏检且 verdict 翻成 PASS——"同一校验器双跑 FAIL 差"
最直接的机制增益证据。分级口径漏检 delta=0 是因为本次未注入 severity 违规
（F01 本身就是 critical，抬升无违规可判），属注入覆盖面边界，非校验缺口——
severity 组在干净输入上由 verify_check --ablate 单独验证过映射规则生效。

**失败路径实测**：verify_check / gain_probe / coverage_audit / schema_guard 对
缺失 result.json 全部打印 FAIL 并 **exit 0**，不中断交付。

**效率计数**：gain_probe 全链路 wall_clock≈0.0105s；example-result.json 回写增益证据后
≈31.3KB（回写前 17.1KB）；`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 防陷阱落实
- **isalpha 汉字陷阱**：coverage_audit 统计英文词数用正则 `[A-Za-z]+`
  （`en_words()`），并在 manuscript_stats.note 中写明原因——汉字
  `"字".isalpha()==True` 会把中文全部误计。
- **引文回证**：空白归一化子串匹配（`re.sub(r"\s+","",s)`），不做大小写折叠，
  保持中文逐字语义。
- **挂载标志**：build_skeleton 校验技能根 SKILL.md 存在（校验式命中），
  未命中时 WARN 进 problems，不中断。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 污染注入未覆盖 severity 违规维度（见上），severity 组增益由口径映射规则与
   verify_check --ablate 间接支撑，未单独实测出非零 delta。
4. 引文回证是"逐字出现于稿件原文"的机械下界，不能替代被引文献主张的语义核对；
   读不到文献时标 pending，不冒充已核对。
5. severity_rubric 与 suppression_rules 口径是本技能事前声明的设定，不是外部标准。
6. examples 全部为合成案例（论文/数据/文献虚构），非正式答案；正式结果只能来自
   平台 3 个固定案例的实际运行。
7. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
8. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 4 期同类包（challenge-2dd1f64c）的差异（防同质化说明）
- 领域 schema 全换：papers/rubric/ ranking/keep → findings/suppressed/clearances/
  severity_rubric/suppression_rules/unchecked。
- 校验点全换：纳排一致性+排序复算 → 引文逐字回证于稿件原文 + 严重度口径映射 +
  误报抑制登记 + 覆盖矩阵。
- 新增覆盖审计引擎 coverage_audit.py（六分面×章节双覆盖 + unchecked 机械缺口），
  替换原排序引擎 score_rank.py（审查场景无排序环节）。
- 污染注入改为领域化污染（清空引文定位/清空对照依据/清空待复核/清空证据链）。
