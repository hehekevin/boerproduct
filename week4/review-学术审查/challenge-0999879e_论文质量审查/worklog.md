# worklog — paper-fact-citation-audit（challenge-0999879e）

## 2026-11-22 v1 开发记录（重构：极简单点）

### 重构动机（对应 0 分诊断）
原 v0（paper-review-audit）六分面全覆盖 + 5 脚本 + 增益强制双跑 + 全篇通读，
产物规模过大，无法在 harbor 64 请求/900 秒预算内跑完，实际效果 0 分。
本次按「极简单点」策略收敛：只做事实一致性 + 引用支持两分面，砍掉四类结构/
方法/统计/规范审查，令其在预算内查全查准目标两类缺陷。

### 砍掉了什么
1. **分面**：方法设计(stat_reporting/method_design/argument_chain/integrity_norms)
   四分面全部移除，只保留 fact_check + citation_support。
2. **脚本**：5→3。coverage_audit.py（六分面覆盖审计）并入 verify_check.py 的
   两分面覆盖检查；schema_guard.py（结构守卫）并入 verify_check.py 组 E。
3. **审查范围**：全篇逐句通读 → 只精读摘要+结果+参考文献列表扫编号。
4. **增益层**：强制双跑 + 污染注入 → 可选；累计请求 ≥32（预算 50%）即跳过，
   写 gain_evidence.available=false（reason=budget_over_half）。

### 文件清单
| 文件 | 说明 |
|------|------|
| SKILL.md | 114 行（≤150 ✓），frontmatter name/description 合法，置顶 4 条保命铁纪律 |
| scripts/build_skeleton.py | 落骨架 + 稿件结构 + 契约字段 + severity_rubric 模板 + 标志校验 |
| scripts/verify_check.py | 业务校验 + 结构守卫（合并 schema_guard），退出码恒 0 |
| scripts/gain_probe.py | 可选增益双跑 + 污染反例 + 预算过半跳过 |
| examples/* | 合成 5 章节虚构稿件 + 6 条示意 findings（非正式答案） |
| README.md | 生态十项 + 最小自检清单（7 条） |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键（含 gain_evidence/efficiency 占位）
- verify_check.py：顶层 self_check / gates / unbacked_numbers / validator_verdict
- gain_probe.py：result.gain_evidence / result.efficiency

### findings 规模与口径
- 目标 6-15 条/案例；超过 15 条即停，只保留证据最强的高置信项。
- finding 字段：finding_id/source_ref/section_id/location/facet/category/severity/
  quote/evidence/revision_suggestion/status/pending_reason/judged。
- category 枚举：fact_error / citation_mismatch / insufficient_evidence / suggestion。
- verdict 枚举：audited / partially_audited / not_audited / cannot_verify。

### 实测对照数字（2026-11-22，Python 3.x，Windows，合成案例 demo-paperaudit-001）

**全链路自测（干净输入）**：
- 三脚本 `py_compile` 通过（语法 0 错误）。
- build_skeleton：章节 S1–S5 全提取，参考文献 4，输出可解析骨架。
- verify_check（对 example-result.json，6 findings：fact_check=3，
  citation_support=3，5 confirmed + 1 pending）：PASS，检查项逐条 applied。
- 污染反例污染注入项全部被 normal 模式抓到（caught_by_normal_mode=true），
  degraded 模式漏检形成非零 delta。
- 缺 result.json 时 verify_check 打印 FAIL 且 exit 0（失败也交付）。

**真实 delta（污染副本，--inject-pollution）**（示意，正式数字以平台 3 案例实跑为准）：
- 注入：清空 quote/location、fact_error 降级 minor、清空 evidence。
- normal verdict=FAIL，degraded verdict=PASS（或 problems 显著减少），
  location/severity/evidence 三类漏检 delta > 0。

**预算保护实测**：`--used-requests 40`（≥32 阈值）时 gain_probe 直接跳过，
stdout 显示 `gain_evidence.available=false`，不对 result 做改动。

**效率计数**：gain_probe 双跑 wall_clock < 0.1s（纯标准库，无网络/无重 IO）。

### 防陷阱落实
- **isalpha 汉字陷阱**：脚本未用 str.isalpha() 做词数统计；引文回证用正则
  `re.sub(r"\s+","",s)` 空白归一化子串匹配，不折叠大小写，保持中文逐字语义。
- **挂载标志**：build_skeleton 校验技能根 SKILL.md 存在（校验式命中），未命中
  WARN 不中断。
- **禁预置答案**：examples 全部为合成虚构（_note 标注"非正式答案"），不含正式
  案例答案/白板。

### 3-4 个脚本职责
1. build_skeleton.py：第 0 步落骨架（契约字段 + 业务键一个不缺）+ 稿件结构 +
   严重度口径模板 + 挂载标志校验。
2. verify_check.py：四组业务校验（定位回证/严重度口径/证据链/两分面覆盖）+
   结构守卫（组 E）+ 回写 self_check/gates/validator_verdict。
3. gain_probe.py：可选增益对照（normal vs degraded 双跑 + 污染反例 + 预算过半跳过）。

### 诚实边界
1. 只审两分面，四类结构/方法/统计/规范问题有意不查——查全率只保证这两类。
2. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
3. 引文回证是"逐字出现于稿件原文"的机械下界，不能替代被引文献实际主张的语义核对；
   读不到文献主张标 pending。
4. severity_rubric 口径是本技能事前声明的设定，不是外部标准。
5. examples 全部为合成案例（论文/数据/文献虚构），非正式答案；正式结果只能来自
   平台 3 个固定案例的实际运行。
6. 待办（主控统一处理）：GITHUB_URL.txt 在公开仓库后由主控生成，本仓库不写。
7. 效率数字（wall_clock）为本地合成输入上的实测值，正式环境按时钟如实回填。