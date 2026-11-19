# worklog — lit-screen-rank（challenge-2dd1f64c）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 3 周冠军包（challenge-da62e8d4 / repro-verify）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：纳排一致性 / 三因子事前权重 / 确定性平局排序 / 预印本重复合并 /
  待复核登记——全部对应题面五个突破方向与机检四点（纳入排除一致性、排序依据可追溯、
  理由完备性、待复核登记）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 146 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 173 | 落骨架 + 候选清单 + rubric 模板 |
| scripts/score_rank.py | 152 | 机械打分 + 确定性排序（键归属：ranking/fused_score/rank） |
| scripts/verify_check.py | ~430 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 176 | 结构守卫 |
| scripts/gain_probe.py | ~430 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 6 条虚构文献 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- score_rank.py：`result.ranking`、`items[].fused_score`、`items[].rank`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-litscreen-001）

**全链路自测（干净输入）**：build_skeleton ✓ / score_rank（P01 0.91 > P02 0.82 > P04 0.58）✓ /
verify_check PASS（13 检查项全 applied）/ schema_guard PASS / gain_probe 两跑均记录成功。
干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=19 / degraded=7（delta=+12：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 4 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 9 | 0 | −9 |
| 纳排违规漏检 | 0 | 2 | +2 |
| 排序失据漏检 | 0 | 1 | +1 |
| 证据缺失漏检 | 0 | 3 | +3 |
| 待复核漏登记 | 0 | 1 | +1 |

注入的 4 项污染：P01 改 keep 但清空 criteria_hit/evidence_quote 并把 fused_score 篡改为
9.9999；P04 清空 pending_reason；清空 pending_review；清空 claims。
正常模式抓全（caught_by_normal_mode=true），退化模式 7 处客观违规全部漏检且 verdict
翻成 PASS——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock≈0.01s，result.json≈25.6KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. quality/recency 归一化口径是本技能在 rubric 事前声明的设定，不是外部标准。
4. examples 全部为合成案例（标题摘要虚构），非正式答案；正式结果只能来自平台 3 个
   固定案例的实际运行。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
6. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 3 周冠军包的差异（防同质化说明）
- 领域 schema 全换：parameters/metric_checks/tolerances → items/rubric/ranking/pending_review。
- 新增确定性排序引擎 score_rank.py（第 3 周无排序环节）：事前权重 + 平局规则 + ties 登记。
- 校验点全换：容差复算 → 纳排一致性 + 排序复算 + 证据回证 + 待复核登记四组。
- 污染注入改为领域化污染（keep 无依据/篡改分数/清空待复核/清空证据链）。
