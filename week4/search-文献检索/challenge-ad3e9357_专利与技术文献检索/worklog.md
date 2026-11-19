# worklog — patent-search-verify（challenge-ad3e9357）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 周同类包（challenge-2dd1f64c / lit-screen-rank，其源头为第 3 周冠军包
  repro-verify）：① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：号码规范化与 norm/raw 一致性 / 优先权-申请号族键归并与口径声明 /
  法律状态登记（来源+查询日期+滞后）/ 论文-专利交叉引用逐字回证 /
  绿黄红授权分级——全部对应题面五个突破方向与机检四点（分类号/号码使用有据、
  专利族归并正确、来源与状态登记完备、交叉引用可回证）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 150 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 217 | 落骨架 + 候选清单 + ledger 口径台账模板 |
| scripts/norm_family.py | 176 | 号码规范化引擎 + 族归并 + 确定性筛选排序 |
| scripts/verify_check.py | ~470 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 166 | 结构守卫 |
| scripts/gain_probe.py | ~480 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 6 条虚构专利/论文 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- norm_family.py：`items[].norm_number`、`items[].family_id`、`result.family_groups`、`result.screening`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13，Windows，合成案例 demo-patent-001）

**全链路自测（干净输入）**：build_skeleton（6 条候选，P01–P06）✓ /
norm_family（4 条号码归一 US20200123456A1 / EP3987654A1 / US20200123456A1 /
WO2021098765A1，1 个族 F-US16123456={P01,P02}，并列组 tier0conf0={P01,P02,P03}）✓ /
verify_check PASS（24 检查项全 applied）/ schema_guard PASS /
gain_probe 两跑均记录成功。
干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=31 / degraded=8（delta=+23：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 6 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 15 | 0 | −15 |
| 号码违规漏检 | 0 | 1 | +1 |
| 族归并漏检 | 0 | 1 | +1 |
| 证据回证漏检 | 0 | 4 | +4 |
| 登记缺失漏检 | 0 | 1 | +1 |

注入的 6 项污染：P01 改 keep 但清空 criteria_hit/evidence_quote；P01 norm_number
篡改为 XX-INVALID；family_groups 注入幽灵族 F-FAKE（成员 P-UNKNOWN-MEMBER 不存在）；
P04 清空 pending_reason；清空 pending_review；清空 claims。
正常模式抓全（caught_by_normal_mode=true），退化模式 7 处客观违规全部漏检且 verdict
翻成 PASS——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock≈0.01s，result.json≈35KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 族归并按 ledger 声明的族键机械归并，简单族/扩展族的语义差异以声明为准，
   不是官方 INPADOC 口径。
4. 法律状态是登记快照转述，不是官方实时核验结论；示例中的 status/gaps 均为合成数据。
5. examples 全部为合成案例（号码/著录项/摘录虚构），非正式答案；正式结果只能来自平台
   3 个固定案例的实际运行。
6. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
7. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 4 周同类包（lit-screen-rank）的差异（防同质化说明）
- 领域 schema 全换：items 的 factors/fused_score/rank → norm_number/family_id/
  legal_status/cross_refs/tech_points；rubric 权重 → ledger 口径台账 + sources 授权分级。
- 机械引擎换型：score_rank 三因子加权排序 → norm_family 号码归一 + 族键归并 +
  relevance/confidence 层级排序（专利域排序依据是族与相关性，不是打分权重）。
- 校验点全换：纳排一致性/排序复算/证据回证/待复核 → 号码与标签一致性（含 norm=normalize(raw)）/
  族归并独立复算（幽灵族、同键拆组）/ 证据与号码逐字回证 / 登记完备性（法律状态来源、
  授权分级、交叉引用目标）。
- 污染注入改为领域化污染（篡改 norm_number / 幽灵族 / 清空法律状态链）。
