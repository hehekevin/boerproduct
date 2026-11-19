# worklog — exp-param-optimize（challenge-ec02b694）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制沿用第 4 期已交付同类包（challenge-cf1995b5 / exp-plan-design）的成熟结构：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测；⑤ 事前声明 rubric + 确定性平局排序；
  ⑥ 脚本定位走标志文件（`skill_marker.json`）。
- 领域逻辑全新，逐条对应本题机检点：
  - **当前值依据登记** → parameters[].basis（manual/pilot/literature/vendor）+ source_ref
    + 有限域 domain{min,max,step}，逐参数机检。
  - **建议有据可回证** → 每条建议 basis/rationale 非空 + claims 数字回证（当前值/
    建议值/projected 空白归一化后子串匹配）。
  - **预期收益量化** → expected_gain 四件套（metric_ref/baseline/projected/delta），
    delta=projected−baseline 机械核对，虚标（只有形容词没有数字）判 FAIL。
  - **耦合约束完备** → constraints 非空（确无耦合须显式 none_declared+source）、
    params 引用有效、expression/source 齐备。
- **本题新增工具**：`param_check.py` —— 受限 AST 求值器（白名单四则/比较/and-or，
  函数调用与属性拒绝）对耦合约束做真实算术求值，在「当前值」与「建议执行值」
  两套映射下分别校验；建议执行值 = set_to→suggested_value、up/down→current±magnitude；
  建议值域越界记硬违规、步进不对齐记警告。对应题面 "finite parameter domains,
  real arithmetic and required validation"。
- 键归属（多脚本禁写同一键）：build_skeleton=骨架；score_strategy=strategy_ranking/
  fused_score/rank；param_check=feasibility_check；verify_check=顶层 self_check/gates/
  unbacked_numbers/validator_verdict；gain_probe=gain_evidence/efficiency。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 150 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 247 | 落骨架 + 要素清单 + rubric 模板 + 标志文件 |
| scripts/verify_check.py | 492 | 五组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 168 | 结构守卫 |
| scripts/score_strategy.py | 164 | 四因子机械打分 + 确定性排序（键归属：strategy_ranking/fused_score/rank） |
| scripts/param_check.py | 314 | 受限 AST 约束求值 + 域校验（键归属：feasibility_check） |
| scripts/gain_probe.py | 511 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成催化微反应器参数优化场景 | 标注"非正式答案"，文献/批号/价格/数据全虚构 |

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-paramopt-001）

**全链路自测（干净输入，退出码全部 0）**：build_skeleton ✓（标志文件 all_present=6/6）/
verify_check PASS（30 检查项全 applied）/ schema_guard PASS / param_check PASS
（域越界 0/0，违规 0，警告 0）/ score_strategy（V1 fused=0.825 rank1 > V3 0.68 > V2 0.64，
ties 空）✓ / gain_probe 两跑均记录成功。
干净输入上五组漏检均为 0（无违规可漏，符合预期）；steps_count normal=39 / degraded=9
（delta=+30：正常模式执行更多检查项，checks_executed 30 vs 0）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | FAIL | — |
| problems | 15 | 1 | −14 |
| 审计违规漏检 | 0 | 4 | +4 |
| 建议违规漏检 | 0 | 4 | +4 |
| 耦合约束漏检 | 0 | 1 | +1 |
| 寻优方法漏检 | 0 | 0 | 0 |
| 回证漏检 | 0 | 1 | +1 |

注入的 5 项污染：清空 parameters[].basis（当前值无依据）、清空
optimization_suggestions[].basis（建议无据）、把 expected_gain 改为无数字虚标声明
（收益不量化）、清空 coupling_constraints、清空 claims。
正常模式抓全（caught_by_normal_mode=true，15 处问题，五组漏检全 0），退化模式
10 处客观违规漏掉 9 处、problems 从 15 掉到 1（只剩常开的 completeness 汇总检查）
——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**子集消融复测**：污染副本上 `--ablate audit,suggestions,coupling` 后剩 2 处问题
（claims 回证缺失 1 + 常开 completeness 汇总 1），说明五组可独立开关、指标差可逐组归因。

**效率计数**：gain_probe 全链路 wall_clock≈0.012s，example-result.json≈13.9KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 开发中修过的 bug（诚实记录）
1. verify_check B 组 `need_val` 把「suggested_value 键存在但为 null 且 direction=up/down」
   误判为 set_to 缺数值 → 合法建议被判 FAIL；改为仅 direction=set_to 时要求数值。
2. param_check 求值 `P-01 * P-02` 时连字符被 ast.parse 当减法、`01` 触发
   "leading zeros" 语法错误 → 6 条约束全部不可求值；新增 `rewrite_expr()`：
   求值前把参数 id 按长度降序整串替换为安全占位符 v0/v1/…，参数 id 支持连字符
   与中文，全程不用 `isalpha()` 类启发式（汉字 isalpha=True、连字符被拆词都是已知陷阱）。
3. gain_probe.count_caught 初版只数组级三元组（audit.complete 1 条），污染副本上
   normal 漏检虚高为 3；改为逐条三元组计数（parameters[i].audited 等）后
   normal 漏检归 0，对照关系才成立。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 寻优方法组（search）在本污染集上无区分度（污染未触及 search_strategy，漏检 0/0），
   照实呈现不做修饰。
3. 干净合成输入上五组漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本
   （同一校验器双跑 15 vs 1 的 FAIL 差）。
4. 退化模式因常开检查（completeness 汇总/verdict 一致性）仍抓到 1 处，verdict 保持
   FAIL——漏检数是下界而非最坏情形，照实呈现，不宣称"退化=全漏"。
5. examples 全部为合成 fixture：文献引文、pilot 数据、价格均为虚构示意，
   不预置正式案例答案。
6. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
7. param_check 的算术校验基于登记的声明域/当前值/建议值（前瞻性规划口径），
   不代表实测实验室数据或供应商确认。
