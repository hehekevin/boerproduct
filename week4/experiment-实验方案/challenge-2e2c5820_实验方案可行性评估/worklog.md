# worklog — feas-review（challenge-2e2c5820）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期已交付同类包（challenge-2dd1f64c / lit-screen-rank）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：七类约束维度覆盖 / 四级分级口径事前声明 / 「没写 ≠ 满足」证据闸门 /
  时间三分量机械累加 / 风险-缓解配对与转人工节点——全部对应题面五个突破方向
  （检查项体系、资源与条件核验、时间与样本估算、风险与异常处置、伦理与安全合规路径）
  与机检四点（维度覆盖、分级口径一致、判断依据回证、风险-缓解配对完备）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 145 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | ~220 | 落骨架 + 方案清单 + 7 维度槽位 + 口径模板 |
| scripts/estimate_time.py | ~130 | 时间三分量机械累加（键归属：result.time_estimate） |
| scripts/verify_check.py | ~430 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | ~170 | 结构守卫 |
| scripts/gain_probe.py | ~430 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 2 方案 × 7 维度 | 标注"非正式答案"，方案/设备/审批状态均为虚构 |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- estimate_time.py：`result.time_estimate`（rows[].total_h / totals / computed_by）
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-feasreview-001）

**全链路自测（干净输入）**：build_skeleton（2 方案、14 槽位）✓ /
estimate_time（5 行，PL-A 6.0h、PL-B 4.0h）✓ / verify_check PASS（49 检查项全 applied）/
schema_guard PASS / gain_probe 两跑均记录成功。
干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=55 / degraded=6（delta=+49：正常模式执行 49 项校验检查，
退化模式全部关闭）。

**同一校验器、同一污染输入（副本注入 6 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 21 | 0 | −21 |
| 维度覆盖漏检 | 0 | 5 | +5 |
| 口径失据漏检 | 0 | 0 | 0（污染未篡改时间合计） |
| 依据回证漏检 | 0 | 11 | +11 |
| 风险漏配对 | 0 | 2 | +2 |

注入的 6 项污染：PL-A-D1 判 feasible 但清空 evidence_quote/rationale（判断无据）；
PL-A-D3 判 conditional 但清空 conditions；R1 清空 mitigation（有风险无缓解）；
PL-A-D7 判 unverifiable 但清空 pending_reason；清空 pending_review；清空 claims。
正常模式抓全 21 处客观违规（caught_by_normal_mode=true），退化模式 18 处漏检且 verdict
翻成 PASS——「同一校验器双跑 FAIL 差」最直接的机制增益证据。

**grading 组单点补证**：副本篡改 time_estimate.totals（PL-A 6.0→99.0），
正常模式 FAIL 并精确命中「totals[PL-A] 与 rows 复算不符（期望 6.0，实际 99.0）」；
同输入退化模式 PASS 漏检 1 处。

**失败路径实测**：5 个脚本对不存在的 result.json / case.json 全部返回退出码 0
（verify_check / schema_guard / gain_probe / estimate_time / build_skeleton 各自打印
FAIL 报告并正常退出，不中断交付）。

**效率计数**：gain_probe 全链路 wall_clock≈0.008s，result.json≈45.0KB（含回写键）；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 开发中修复的问题
1. estimate_time.py 首版漏写 `args = ap.parse_args()`（未预期异常被兜底捕获、exit 0），
   自测发现后修复。
2. verify_check.py 风险组自检三元组 `applied` 误硬编码为 True，导致退化模式下风险漏检
   被误记为已捕获（污染副本 risks_missed 显示 0 而非 2）——与参考包「applied=not off(g)」
   口径对齐后修复并复测。
3. verify_check.py main 中 estimate_output 闸门重复登记，去重。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无违规可漏，无区分度）——增益证据主要来自
   污染反例副本；grading 组在本次污染方案中 delta=0（污染未含时间篡改），
   以单点篡改测试补证。已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 时间估算口径（设备占用+人工+等待三分量机械累加）是本技能在 grading_rubric/脚本
   note 事前声明并落盘的设定，不是外部标准；数值依赖 Agent 对方案步骤的拆解质量。
4. examples 全部为合成案例（方案/设备/审批状态虚构），非正式答案；正式结果只能来自
   平台 3 个固定案例的实际运行。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
6. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 4 期同类包（challenge-2dd1f64c / lit-screen-rank）的差异（防同质化说明）
- 领域 schema 全换：papers/rubric权重/ranking → plans/check_items/grading_rubric/
  time_estimate/risks/confirmations。
- 机械引擎换位：多因子排序 score_rank.py → 时间三分量累加 estimate_time.py
  （排序场景换成了「时间与样本估算」突破方向）。
- 校验点全换：纳排一致性+排序复算 → 维度覆盖+口径一致+依据回证+风险-缓解配对四组；
  新增「feasible 必附逐字证据」的『没写 ≠ 满足』闸门与 conditional 必列条件清单。
- 污染注入改为领域化污染（判断无据/有条件无清单/有风险无缓解/待复核清空/证据链清空）。
- 检查项由"每条文献一槽位"变为"每方案 × 七维度固定槽位"（build_skeleton 预填 14 槽）。
