# worklog — cov-gap-audit（challenge-0467f5db）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期同批交付包（challenge-2dd1f64c / lit-screen-rank）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测；⑤ 多脚本键归属分离。
- 领域逻辑全新：参考集冻结分母 / 标识符+标题机械匹配 / 漏检六类归因（落到
  query_id/field/source_db）/ 补检边际收益复算（防空转）/ 残余遗漏解释——
  全部对应题面五个突破方向与机检三点（分母可核对、漏检归因具体、补检真实降遗漏）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 148 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | ~270 | 落骨架 + 参考集/查询/记录提取 + 分母冻结台账 |
| scripts/coverage_calc.py | ~240 | 机械匹配（identifier→title）+ coverage 回填（键：coverage/hit_*） |
| scripts/miss_audit.py | ~190 | 遗漏登记完备 + 归因可回溯审计（键：miss_registry） |
| scripts/supp_check.py | ~230 | 补检边际收益复算 + 空转检测（键：supplementary） |
| scripts/verify_check.py | ~430 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | ~170 | 结构守卫 |
| scripts/gain_probe.py | ~470 | 双跑增益对照 + 污染反例（键：gain_evidence/efficiency） |
| examples/* | 合成 6 条虚构文献 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- coverage_calc.py：`result.coverage`、`items[].hit_status / matched_by / matched_query_id / matched_record_ref`
- miss_audit.py：`result.miss_registry`
- supp_check.py：`result.supplementary`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-covgap-001）

**全链路自测（干净输入）**：build_skeleton ✓（6 参考条目/2 查询/4 记录）/
coverage_calc ✓（K01-K03 命中 by identifier；K04/K06 漏检；K05 撤稿不入分母；
coverage_rate=0.6 / miss_rate=0.4）→ miss_audit PASS（2 条遗漏归因全可回溯）→
supp_check PASS（Q3 新增 K04，post_coverage_rate=0.8 / post_miss_rate=0.2）→
verify_check PASS（15 检查项全 applied）/ schema_guard PASS /
gain_probe 两跑均记录成功。干净输入上 normal vs degraded 四类漏检均为 0
（无违规可漏，符合预期），steps_count normal=22 / degraded=7（delta=+15：
正常模式执行更多检查项），wall_clock normal=0.0022s / degraded=0.0003s。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | FAIL* | — |
| problems | 10 | 1 | −9 |
| 分母违规漏检 | 0 | 2 | +2 |
| 遗漏登记漏检 | 0 | 1 | +1 |
| 补检违规漏检 | 0 | 3 | +3 |
| 证据漏检 | 0 | 3 | +3 |

注入的 5 项污染：coverage_rate 篡改为 1.0（"以结果定义分母"）/ 清空 K04 遗漏登记 /
K04 命中证据与匹配方式清空 / 补检 new_hits 清空且 effective=true（补检空转）/ 清空 claims。
正常模式抓全（caught_by_normal_mode=true）。*退化模式仍 FAIL 是因为"verdict=covered_audited
但存在未登记遗漏"始终开启——退化侧 9 处客观违规不可见、仅剩 1 处基础检查兜底，
这正说明退化侧漏检数是下界（与 gain_evidence.boundaries 第 2 条一致）。

**效率计数**：gain_probe 全链路 wall_clock≈0.0088s，result.json≈16031B（回写增益证据后）；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 中文数值回证陷阱的处理（硬约束第 7 条）
- 不用 `\b` / isalpha 做数字定界：汉字的 `str.isalpha()` 为 True，`"0.6学生"` 用 `\w`
  词边界会判定失败。改用显式字符类 `(?<![0-9.])…(?![0-9])`（verify_check.num_in_text）。
- 标识符内嵌数字排除：回证匹配前先剥离 DOI 形态 `10\.\d{4,9}/\S+`，避免把
  "10.1000/mind-001" 里的数字当回证或误命中；年份区间端点（2018-2025）不在剥离范围，保留。
- 标题归一化同样用显式字符类 `[^0-9a-z\u4e00-\u9fff]`，不用 isalpha 过滤。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 机械匹配只覆盖标识符精确与标题归一化精确两种规则；近似匹配需人工裁决
  （matched_by=manual + 证据），这是口径声明（coverage.match_rule）的一部分。
4. examples 全部为合成案例（标题/DOI 虚构），非正式答案；正式结果只能来自平台 3 个
   固定案例的实际运行。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
6. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与同批包（challenge-2dd1f64c）的差异（防同质化说明）
- 领域 schema 全换：rubric/fused_score/ranking/pending_review → reference_set（冻结分母）/
  coverage/miss_registry/supplementary/review。
- 排序引擎换成分母审计引擎：三因子加权排序 → 分母冻结 + 机械命中匹配 + 覆盖率复算；
  本题不看排序，看口径与遗漏。
- 校验点全换：纳排一致性+排序复算 → 分母口径 + 遗漏登记归因 + 补检真实收益 + 证据回证四组
  （对应题面四种失效方式逐条设防）。
- 污染注入改为领域化污染（篡改覆盖率=1.0 / 清空遗漏登记 / 归因清空 / 补检空转 / 清空证据链）。
- 新增中文数值回证显式字符类处理与 DOI 内嵌数字剥离（硬约束第 7 条专项）。
