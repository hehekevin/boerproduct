# worklog — exp-plan-design（challenge-cf1995b5）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制沿用第 4 期已交付同类包（challenge-2dd1f64c / lit-screen-rank）的成熟结构：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测；⑤ 事前声明 rubric + 确定性平局排序。
- 领域逻辑全新：变量表完备性（操作定义/测量/单位逐项机检）/ 对照排除混杂说明 /
  样本量功效依据登记 / 分析计划-假设对齐 / 参数数值 claims 回证——全部对应题面
  六类要素与本题机检四点（变量表完备、对照设置检查、样本量/功效依据登记、
  分析计划-假设对齐）。
- 新增：脚本定位走标志文件（`skill_marker.json`，Step 0 落盘脚本存在性校验，
  verify_check 据此设 `skill_scripts` 闸门），不依赖挂载路径假设。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 150 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | ~220 | 落骨架 + 要素清单 + rubric 模板 + 标志文件 |
| scripts/score_plan.py | ~160 | 四因子机械打分 + 确定性排序（键归属：plan_ranking/fused_score/rank） |
| scripts/verify_check.py | ~400 | 五组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | ~160 | 结构守卫 |
| scripts/gain_probe.py | ~430 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成拟南芥光强实验 | 标注"非正式答案"，材料批号数据全虚构 |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- score_plan.py：`result.plan_ranking`、`plan_versions[].fused_score`、`plan_versions[].rank`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-expplan-001）

**全链路自测（干净输入，退出码全部 0）**：build_skeleton ✓（标志文件 all_present=5/5）/
verify_check PASS（28 检查项全 applied）/ schema_guard PASS /
score_plan（V1 fused=0.8 rank1 > V2 0.78 > V3 0.72，ties 空）✓ / gain_probe 两跑均记录成功。
干净输入上 normal vs degraded 五组漏检均为 0（无违规可漏，符合预期），
steps_count normal=30 / degraded=2（delta=+28：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | FAIL | — |
| problems | 11 | 2 | −9 |
| 变量表违规漏检 | 0 | 1 | +1 |
| 对照设置违规漏检 | 0 | 1 | +1 |
| 功效依据漏登记 | 0 | 4 | +4 |
| 分析对齐漏检 | 0 | 1 | +1 |
| 证据回证漏检 | 0 | 1 | +1 |

注入的 5 项污染：清空 controls（无对照设计）、IV-01 清空 operational_definition、
清空 power_basis.n_registry、清空 analysis_plan、清空 claims。
正常模式抓全（caught_by_normal_mode=true，11 处问题），退化模式 8 处客观违规漏检、
problems 从 11 掉到 2——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**子集消融复测**：污染副本上 `--ablate variables,controls,power` 后剩 4 处问题
（对齐 1 + 回证 1 + 常开 completeness/verdict 各 1），说明五组可独立开关、
指标差可逐组归因。

**效率计数**：gain_probe 全链路 wall_clock≈0.005s，example-result.json≈12KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 开发中修过的 bug（诚实记录）
1. gain_probe.count_caught 用 `% _`（dict）做 `%d` 格式化 → TypeError；改为按索引枚举。
2. 污染注入"清空 claims"后回证检查被 `corpus and …` 短路跳过 → 证据漏检恒 0；
   改为 claims 空但有数值参数时计 1 条客观违规，verify_check 同步补
   `claims.backchain` 三元组。
3. count_caught 漏数 `hypotheses[*].analysis_aligned` 三元组 → 正常模式对齐漏检虚高；
   补齐后 normal=0/degraded=1 的对照才成立。
4. example-result.json 初版缺 plan_versions[].fused_score → verify_check 复算 FAIL；
   补齐 0.8/0.78/0.72 后 PASS。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上五组漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本
   （同一校验器双跑 11 vs 2 的 FAIL 差）。
3. 退化模式因常开检查（枚举/completeness 汇总/verdict 一致性）仍抓到 2 处，
   verdict 保持 FAIL——漏检数是下界而非最坏情形，照实呈现，不宣称"退化=全漏"。
4. examples 全部为合成 fixture：材料批号、功效参数、价格均为虚构示意，
   不预置正式案例答案。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
