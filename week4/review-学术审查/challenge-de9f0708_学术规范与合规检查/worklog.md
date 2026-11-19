# worklog — paper-compliance-audit（challenge-de9f0708）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期已交付同类包（challenge-0999879e / paper-review-audit）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：学术规范与合规检查——八分面审查（数据可用性/伦理知情同意/
  利益冲突/作者贡献/基金资助/版权许可/参考文献格式/重复发表与一稿多投）、
  三类区分（norm_missing 规范缺失 / norm_violation 规范不合规 / substantive_issue
  实质性学术问题）、必备声明存在性关键词机检（中英双语）、格式规则（FR-01~08）
  事前声明与 rule_id 依据绑定、三类×严重度机械映射、误报抑制规则表、
  待复核登记——全部对应题面检查项与机检点（必备声明存在性机检、格式规则
  事前声明、三类区分口径一致、位置回证）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 149 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 262 | 落骨架 + 稿件结构 + compliance_rubric 模板 + FR-01~08 预填 + 挂载标志校验 |
| scripts/decl_audit.py | 251 | 六项声明存在性机检（中英关键词）+ 八分面×章节覆盖审计（键归属：declaration_audit/coverage/unchecked） |
| scripts/verify_check.py | 419 | 五组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 166 | 结构守卫（三类 categories + 三级 severity_levels 键校验） |
| scripts/gain_probe.py | 500 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 6 章节虚构稿件 | 标注"非正式答案" |
| README.md | 生态十项说明 | 用途/依赖/安装/输入输出/示例/验收/异常/FAQ/限制/复用 |
| worklog.md | 本文件 | 真实对照数字 + 诚实边界 |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- decl_audit.py：`result.declaration_audit`、`result.coverage`、`result.unchecked`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-compliance-001）

**全链路自测（干净输入）**：build_skeleton ✓（章节 S1–S6 全部提取、标志文件命中）/
decl_audit（声明机检 2/6 项检出：ethics、funding；未检出 4 项均被 norm_missing
发现对账覆盖；9 findings：confirmed=7 pending=1 suppressed=1，章节 5/6 有发现，
unchecked=0——facet:ethics 与 section:S2 有显式 clearances）✓ /
gain_probe 两跑均记录成功 / verify_check PASS（36 检查项全 applied）/
schema_guard PASS（含 output_contract 全字段）。
干净输入上 normal vs degraded 五类漏检均为 0（无违规可漏，符合预期），
steps_count normal=43 / degraded=7（delta=+36：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 6 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 12 | 0 | −12 |
| 定位失据漏检 | 0 | 1 | +1 |
| 三类口径漏检 | 0 | 1 | +1 |
| 依据绑定漏检 | 0 | 1 | +1 |
| 证据缺失漏检 | 0 | 7 | +7 |
| 待复核漏登记 | 0 | 1 | +1 |

注入的 6 项污染：F01 清空 quote/location（定位失据）；F01（norm_missing）severity
抬升为 critical（三类口径违规）；F01 清空 rule_id（依据绑定丢失）；F08 标 pending
但清空 pending_reason；清空 pending_review；清空 claims。
正常模式抓全（caught_by_normal_mode=true，12 处问题含逐条列出），退化模式 11 处
客观违规全部漏检且 verdict 翻成 PASS——"同一校验器双跑 FAIL 差"最直接的机制
增益证据。证据缺失漏检 delta=7 是因为清空 claims 使全部 7 条 confirmed 同时
失去证据链回证，属一次注入的级联效应，非 7 处独立污染。

**失败路径实测**：verify_check / gain_probe / decl_audit / schema_guard 对缺失
result.json / 缺失 case.json 全部打印 FAIL 并 **exit 0**；5 个脚本对非法 CLI 参数
（argparse SystemExit 2）也统一降级为 **exit 0**（比参考包更严的一处加固）。

**消融单组实测**：污染副本 `--ablate rules` → FAIL（11 处，比全开少 1 处，
仅关闭规则绑定组）；`--ablate none` → FAIL（12 处）——组级开关粒度生效。

**效率计数**：gain_probe 全链路 wall_clock≈0.0097s；example-result.json 回写增益
证据后 ≈40.9KB（40,886 字节，回写前约 25KB）；整包 10 个文件、180,975 字节
（<2MB、<50 文件）✓；`efficiency.model_requests` 保持 null（不可脚本采集，
由 Agent 侧回填）。

### 防陷阱落实
- **isalpha 汉字陷阱**：decl_audit 统计英文词数用正则 `[A-Za-z]+`（`en_words()`），
  并在 manuscript_stats.note 中写明原因——汉字 `"字".isalpha()==True` 会把中文
  全部误计。
- **引文回证**：空白归一化子串匹配（`re.sub(r"\s+","",s)`），不做大小写折叠，
  保持中文逐字语义。
- **挂载标志**：build_skeleton 校验技能根 SKILL.md 存在（校验式命中），
  未命中时 WARN 进 problems，不中断。
- **关键词机检的英文匹配**：全文小写化后子串匹配（`kw.lower() in low`），
  中文关键词不受影响。
- **零发现豁免口径**：verify_check 的零分面检查把 clearances/unchecked 一并
  视为豁免来源（开发中发现原写法误报 ethics 分面，已修复并记入本 worklog）。

### 开发中修复的 bug（诚实记录）
1. decl_audit.py 首版 `clearances`/`cleared` 变量名不一致导致 NameError
   （被全捕获容错降级为 WARN，未崩溃）——已修复并全链路重跑。
2. verify_check.py 首版零发现分面检查只看 unchecked，漏掉 clearances 豁免，
   导致 ethics 分面（有显式豁免）被误报——已修复：豁免来源 = clearances ∪ unchecked。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上五类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例
   副本，已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 声明存在性机检基于关键词表：只能证明"稿件文本中未出现相关表述"，不能证明
   声明不在投稿系统或单独文件；机检判缺失须有发现或豁免对账（单向），
   机检命中不强制有发现（关键词可能误命中）。关键词表是通用约定，不针对
   任何具体期刊。
4. 重复发表判定只能基于稿件内部线索（会议版提及/未引用/未声明），无外部
   查重库与检索能力；需外部比对的需求标 pending + needed_action。
5. format_rules（FR-01~08）与 compliance_rubric 口径是本技能事前声明的设定，
   不是外部标准；题面或目标期刊给出实际要求时应改写并冻结。
6. examples 全部为合成案例（论文/数据/基金/文献虚构），非正式答案；正式结果
   只能来自平台 3 个固定案例的实际运行。
7. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
8. 污染注入未覆盖 pending 漏登记之外的全部维度组合（如 suppressed 绕过规则表
   未单独注入），该维度由 verify_check E 组在干净输入上由检查项覆盖支撑，
   未单独实测出非零 delta。
9. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 4 期同类包（challenge-0999879e）的差异（防同质化说明）
- 领域 schema 全换：六分面论文质量审查 → 八分面合规审查；severity_rubric →
  compliance_rubric（三类 categories + 三级 severity_levels + mapping）；新增
  format_rules（FR-01~08 依据绑定）与 declaration_checklist/declaration_audit。
- 校验点全换：引文回证保留为公共底座（位置回证是本题机检点），新增三类×严重度
  机械映射、规则绑定检查、声明机检一致性单向对账。
- 新增领域引擎 decl_audit.py（声明存在性关键词机检 + 覆盖审计二合一），
  替换原 coverage_audit.py（单覆盖审计）；gain_probe 五组消融（原四组），
  污染注入改为领域化（清空引文定位/severity 抬升违规/清空 rule_id/清空待复核/
  清空证据链）。
- 消融组名与指标全换：location/rubric/rules/evidence/pending（原 location/
  severity/evidence/pending），新增 rules_missed（依据绑定+声明机检漏检）。
