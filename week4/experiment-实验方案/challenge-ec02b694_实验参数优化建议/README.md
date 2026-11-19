# exp-param-optimize — 实验参数优化建议 Skill（v1）

针对 Bohrium 产品赛第 4 期「实验方案设计」赛道 (challenge-ec02b694) 的
**实验参数优化建议**子题的参赛 Skill。锁定子场景：**响应指标 → 参数-响应
关系图 → 当前值依据审计 → 优化建议（方向/幅度/预期收益）→ 耦合约束登记 →
寻优方法与停止判据 → 候选策略机械比较**。

## 1. 用途与适用条件

给定研究目标、约束与科研材料（含组织方前瞻性资源/价格/预约合同、有限参数域），
完成八件事：

1. **响应指标定义**：每个指标给口径、单位、测量方法与可接受波动——没有测量
   口径的指标不能进建议链。
2. **参数-响应关系图**：每条关系（递增/递减/单峰/耦合）都必须挂 evidence
   （文献图表/预实验编号），引用的参数与指标必须存在。
3. **当前值依据审计**：每个参数声明 name/unit/有限域 domain{min,max,step}/
   当前值/**basis（manual/pilot/literature/vendor）+ source_ref**——无依据的
   取值进不了优化，被校验器判 FAIL。
4. **优化建议**：每条给 direction（up/down/hold/set_to）+ 幅度或建议值 +
   **量化预期收益 expected_gain（baseline/projected/delta，delta=projected−baseline
   机械核对）** + basis + rationale + risk_note；形容词收益（"显著提升"）不算量化。
5. **耦合约束登记**：每条约束 params 引用有效 + 算术表达式 + 可查来源 +
   severity；确无耦合也须显式登记 none_declared——约束缺失被机检判 FAIL。
6. **数值可行性校验（param_check.py）**：受限 AST 求值器（白名单四则/比较/
   and-or，函数调用与属性访问拒绝）在**当前值与建议执行值两套映射**下逐条求值
   约束、核对建议值是否越声明域——建议越界却不提示正是本题抓的失败模式。
7. **寻优方法建议**：method（OFAT/网格/RSM/贝叶斯/序贯/分阶段）+ 初始点 +
   **停止判据** + 预算口径；grid 必须给分辨率，"怎么停"说不清判 FAIL。
8. **候选策略机械比较 + 证据链**：≥2 个策略版本在事前声明的四因子 rubric 下
   由 score_strategy 复算 fused_score 并按确定性平局规则排序；当前值/建议值/
   收益数字逐字回证 claims；verify_check 五组机检 + schema_guard 结构守卫 +
   gain_probe 消融对照全部退出码恒 0，判据只看报告 verdict。

**核心保证**：`verify_check.py` 独立机械复核审计/建议/耦合/寻优/回证五组检查；
`param_check.py` 做真实算术校验（finite domains + real arithmetic）；
`gain_probe.py` 用正常 vs 退化双跑实测机制增益并写入 result.gain_evidence。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers /
validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 实验设计者 | 要在机时预算内调参拿更高转化率 | 带依据的参数建议表 + 可执行寻优策略 + 成本口径 |
| 研究助理 / 研究生 | 要向导师解释"为什么建议 165 ℃、依据是什么" | 逐条建议的 basis/source_ref + claims 回证链 |
| 复核者 / 评审 | 检查建议是否在可行域内、收益有没有虚标 | 机械校验报告（self_check 三元组 + unbacked_numbers + feasibility_check）|
| 教学 / 培训 | 演示"事前声明口径 + 真实算术校验 + 消融对照"的设计纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做文献综述、不执行实验、不替代安全与伦理审批；缺什么登记什么，
不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math` / `ast`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需任何安装步骤、无依赖解析、无需联网。脚本定位走
标志文件：Step 0 会在 `/app/work/skill_marker.json` 落盘脚本存在性校验结果，
后续校验器据此命中。

```bash
# Step 0：自动落骨架 + 要素清单 + rubric 模板 + 脚本标志文件（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-4：Agent 填响应指标/参数响应图/当前值审计/建议/约束/寻优方法/claims（见 SKILL.md 八步流程）

# Step 5a：数值可行性校验（写 result.feasibility_check）
python3 /skills/weekly-skill/scripts/param_check.py --result /app/output/result.json --emit-into

# Step 5b：候选策略机械比较（写 result.strategy_ranking / fused_score / rank）
python3 /skills/weekly-skill/scripts/score_strategy.py --result /app/output/result.json --k 1

# Step 6：增益对照 + 效率计数 + 污染反例（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 7：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究目标 + 约束 + 材料 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`rubric`、
    `response_metrics`、`parameter_response_map`、`parameters`、
    `optimization_suggestions`、`coupling_constraints`、`search_strategy`、
    `strategy_versions`、`strategy_ranking`、`feasibility_check`、`risks`、
    `confirmations`、`completeness`、`steps`、`run_status`、`verdict`、
    `verdict_basis`、`gain_evidence`、`efficiency`
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/rubric.json`（口径台账）、
  `/app/work/skill_marker.json`（脚本标志）、`/app/work/gain_probe_polluted.json`
  （污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（材料批号、文献出处与数据均为虚构）：4 参数
（温度/浓度/采样间隔/搅拌速率，全部带 basis 登记）→ 2 响应指标 → 4 条
参数-响应关系 → 4 条建议（含 set_to/up/down/hold 全方向，收益全部量化）→
3 条耦合约束（耐温裕度/机时口径/放热阈值，param_check 全部算术求值通过）→
分阶段筛选策略（V1 fused=0.825 排第 1、V3 0.68、V2 0.64）。示意输出关键片段：

```json
{
  "case_id": "demo-paramopt-001", "status": "answered",
  "result": {
    "parameters": [{"param_id": "P-01", "unit": "℃", "domain": {"min": 120, "max": 180, "step": 5}, "current_value": 150, "basis": "literature"}],
    "optimization_suggestions": [{"sugg_id": "S-01", "direction": "set_to", "suggested_value": 165, "expected_gain": {"baseline": 78.5, "projected": 84.2, "delta": 5.7}}],
    "coupling_constraints": [{"cid": "C-03", "params": ["P-01", "P-02"], "expression": "P-01 * P-02 <= 2500", "severity": "hard"}],
    "strategy_ranking": {"ordered_ids": ["V1", "V3", "V2"], "k_value": 1},
    "feasibility_check": {"all_within_domain": true, "all_constraints_satisfied": true},
    "verdict": "optimized"
  }
}
```

### 最小自检清单（本包全部实测通过，退出码均为 0）

| # | 自检项 | 实测结果 |
|---|--------|---------|
| 1 | build_skeleton 落骨架 + 标志文件 | exit 0，all_present=6/6 |
| 2 | verify_check 干净输入 | exit 0，verdict=PASS（30 检查项全 applied）|
| 3 | schema_guard 结构守卫 | exit 0，verdict=PASS |
| 4 | param_check 数值校验 | exit 0，PASS（域越界 0，违规 0，警告 0）|
| 5 | score_strategy 排序 | exit 0，V1 0.825 > V3 0.68 > V2 0.64，ties 空 |
| 6 | gain_probe 消融双跑 | exit 0，steps_count 39 vs 9（delta +30）|
| 7 | 污染反例副本 | exit 0，caught_by_normal_mode=true |
| 8 | SKILL.md 行数 | 150 行（≤150）|

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 五态枚举（含 param_feasibility_check）；非 enforced 必有 note |
| A5 | 五要素齐 | response_metrics/parameter_response_map/parameters/optimization_suggestions/coupling_constraints/search_strategy 全落键且 completeness 汇总与实际一致 |
| A6 | 当前值有据 | 每个 parameters[] 项 basis ∈ 四枚举 + source_ref 非空 + domain 有限 |
| A7 | 建议有据且收益量化 | 每条建议 basis/rationale 非空，expected_gain 四件套齐且 delta 机械核对一致 |
| A8 | 耦合约束可求值 | 每条约束 expression 被 param_check 在两套映射下算术求值；引用参数存在 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（审计 + 建议 + 耦合 + 寻优 + 回证） | — |
| `degraded` | 枚举/结构/completeness 汇总/verdict 一致性 | **audit / suggestions / coupling / search / evidence 五组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 污染副本 problems | 15 | 1 | −14 |
| 审计违规漏检（当前值无依据） | 0 | 4 | +4 |
| 建议违规漏检（建议无据/收益虚标） | 0 | 4 | +4 |
| 耦合约束漏检 | 0 | 1 | +1 |
| 寻优方法漏检 | 0 | 0 | 0 |
| 回证漏检 | 0 | 1 | +1 |
| steps_count（干净输入） | 39 | 9 | +30 |

注入的 5 项污染：清空 parameters[].basis（当前值无依据）、清空
optimization_suggestions[].basis（建议无据）、把 expected_gain 改成无数字的
虚标声明（收益不量化）、清空 coupling_constraints、清空 claims。
**同一校验器、同一污染输入**：正常模式抓全（漏检 0，verdict=FAIL 15 处问题），
退化模式 10 处客观违规漏掉 9 处、problems 从 15 掉到 1（只剩常开的
completeness 汇总检查）——这是机制增益最直接的证据。数字由探针独立复算违规
真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。
> 寻优方法组在本污染集上无区分度（污染未触及 search_strategy，漏检 0/0），
> 照实呈现不做修饰；退化模式漏检数是下界而非最坏情形。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 材料/设备/预算缺失 | material_gaps 登记 + confirmations pending，参数域留待定，不脑补 |
| 约束冲突（目标值 vs 耐温/机时） | param_check violations 如实登记；放宽 soft 须在 uncertainties.conflicts 登记双方与代价，hard 不静默放宽 |
| 无可行解 | verdict=partially_optimized/not_optimized + reason + 转人工 fallback |
| 指标互相矛盾 | 关系分列两条 + 建议风险注记联动监控 + trade-off 写入 rationale |
| 大量同分 | 并列组记入 ties，按 tie_break 规则破平，不静默改分 |
| 算力/时间不足 | 保留已完成要素，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身
故障打断。

**Q：约束表达式能写多复杂？支持中文参数名吗？**
支持 `+ − × ÷`、比较（<= >= < > == !=）、and/or 与括号；函数调用与属性访问
一律拒绝（白名单 AST）。参数 id 允许连字符（`P-01`）与中文（`反应温度`）：
求值前整串替换为安全占位符再进 ast.parse，不用 `isalpha()` 类启发式判断
（汉字会让 isalpha 返回 True、连字符会被误当减法，都是已知陷阱）。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：预期收益是拍脑袋的数字吗？**
不是可拍脑袋的：expected_gain 必须给 metric_ref/baseline/projected/delta 四件套，
delta=projected−baseline 被机械核对，全部数字必须出现在 claims 证据链里；
收益口径（如"按置信区间收窄折算"）写在 rationale 与 evidence，属前瞻性折算
而非实测承诺，不确定度进 uncertainties.unverifiable。

**Q：为什么"确无耦合"也要登记一条约束？**
题面机检点要求"耦合约束完备"。空列表分不清"没发现耦合"和"忘了查"，
kind=none_declared 条目强制 Agent 显式声明"我查过、没有"，把判断变成可复核
的登记。

**Q：confirmations 里 pending 是不是没做完？**
不是——它是题面要求的"标注需要专家确认的内容"。未确认的建议（如放热阈值
须 EHS 确认）必须标 pending，把人工注意力集中到真正需要确认的事项上，不把
未经确认的建议写成可执行事实。

## 11. 适用范围与限制

- 仅处理输入范围内的参数优化建议：不做文献综述、不执行实验、不替代安全与
  伦理审查；不冒充设备量程认定或安全认证。
- 预期收益为前瞻性折算口径并写明来源，不是实测承诺。
- 参数域/约束取自输入登记与声明出处；输入未给时不臆造，登记 material_gaps。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，
  缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/param_check.py` 的受限 AST 求值器 | 白名单算术 + 占位符重写，任何"约束表达式安全求值"需求可直接照抄（含连字符/中文 id 处理） |
| `expected_gain` 四件套 + delta 机械核对 | 任何"建议必须量化"的场景：baseline/projected/delta 三数互锁，虚标即 FAIL |
| `coupling_constraints` + none_declared 机制 | 任何"完备性检查"场景：空列表分不清没发现和忘了查，强制显式声明 |
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/score_strategy.py` 的确定性排序 | 权重事前声明 + 固定平局规则 + ties 登记，任何"稳定可解释排序"需求可直接照抄 |
| basis 四枚举 + source_ref 台账 | `{param_id, domain, current_value, basis, source_ref}` 是通用的"取值依据登记"格式 |
| 闸门五态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `skill_marker.json` 标志文件 | 脚本定位走标志文件校验，挂载路径变化时无需改代码 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份删字段即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 八步流程 + schema + 校验说明，150 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/要素清单/rubric 模板/标志文件（退出码恒 0） | 是 |
| scripts/param_check.py | 受限 AST 约束求值 + 域校验 + 建议执行值映射（键归属：feasibility_check） | 是（核心工具） |
| scripts/score_strategy.py | 四因子机械打分 + 确定性排序 + 平局登记 | 是 |
| scripts/verify_check.py | 业务校验器（审计/建议/耦合/寻优/回证五组，--ablate 可关） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构催化微反应器参数优化） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节八条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/PARAM_REQUIRED/
  SUGG_REQUIRED` 与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
