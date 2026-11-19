# stat-analysis-audit — 统计分析与结果解读 Skill（v1）

针对 Bohrium 第 4 期 challenge-c0e1e220「统计分析与结果解读」的参赛 Skill。
锁定子场景：**六分面统计审计 + 描述统计复算回证 + 检验选择依据登记 + 解读强度
机械分级（过强结论降级）+ 因果表述约束（相关≠因果）+ 弃权登记**。

## 1. 用途与适用条件

给定科研数据集与其统计报告（case.json），完成六件事：

1. **数据质量口径审计**：缺失/重复/异常值的处理是否声明、删了多少、单位口径
   是否交代（DQ-01）。缺失绝不静默当 0，删行必须留痕。
2. **描述统计复算回证**：对每个 claimed 统计量（n/均值/方差/标准差/分位数），
   `stat_recompute.py` 从 case.json 原始数值用标准库 statistics/math 复算
   （样本方差 n-1、分位数线性插值），相对容差 1e-6 对照；claimed 数字还须在
   claims 证据链与来源文本中回证，拍脑袋数字进 unbacked_numbers 判 FAIL。
3. **检验选择依据登记**：test_registration 登记家族（parametric/nonparametric）、
   名称、组数、配对、正态性/方差齐性假设与理由；校验器按假设机械推期望检验
   （Welch t / Mann-Whitney / ANOVA / Kruskal-Wallis / 配对 t / Wilcoxon /
   Pearson/Spearman），失配即判——杜绝"三组数据塞进两样本 t 检验"。
4. **效应量与 CI 报告检查**：只有 p 值没有效应量/置信区间按 unreported 登记，
   不允许 p=0.04 写成"证明有效"。
5. **解读强度机械分级**：claim_strength 必须不超过
   `strength_map[design_type]`（experimental→causal、observational/correlational→
   associative、unknown→descriptive），过强结论由 `interpret_rollup.py` 机械
   降级并登记；grade/category/penalty/overall 全部由事前声明的 claim_rules
   机械导出，杜绝口径漂移。
6. **因果表述约束**：观察性/相关性设计 + 因果动词词表命中（导致/证明/因果/…）
   ⇒ FAIL（相关≠因果）；扫描用子串匹配，不依赖 isalpha（汉字串安全）。

**核心保证**：`verify_check.py` 七组机械校验（含统计复算现场比对）；
`gain_probe.py` 正常 vs 退化双跑实测机制增益并写入 result.gain_evidence。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers /
unbacked_evidence / validator_verdict` 五键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | 拿到带缺失/重复的测量记录和一串统计数字，要判断能不能写进报告 | 六分面审计表 + 复算对照 + 强度匹配的结论 |
| 统计复核者 | 核对报告里的均值/p 值/检验方法是否站得住 | stat_recompute 复算明细 + 检验期望对照 + 数字回证清单 |
| 期刊编辑/初筛 | 区分"方法用错了"和"只是没写" | method_error 与 reporting_gap 逐条分离的清单 |
| 教学/培训 | 演示 p=0.04≠证明有效、相关≠因果的审稿纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做实验方案设计、样本量估算与论文写作；不覆盖全部"科研数据分析"；
缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（json / os / re / sys / argparse / copy / time / math / **statistics**——不装 numpy/scipy） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 磁盘 | 整包 < 120 KB |
| 资源上限 | 平台契约：≤50 个 UTF-8 文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需安装步骤、无依赖解析、无需联网。脚本自带定位标志
校验（与 SKILL.md 同包才报 marker_hit=True）。

```bash
# Step 0：自动落骨架 + 数据集清单 + claim_rules 模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明 claim_rules，逐分面评价并登记统计量/检验/结论（见 SKILL.md）

# Step 3：统计量复算 + 检验选择期望（写 result.stat_recompute）
python3 /skills/weekly-skill/scripts/stat_recompute.py --result /app/output/result.json \
  --case /input/case.json

# Step 4：解读强度机械汇总（写 result.interpret_summary）
python3 /skills/weekly-skill/scripts/interpret_rollup.py --result /app/output/result.json

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（数据集/记录 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `unbacked_evidence` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`review_scope`、`checklist`（六分面）、
    `claim_rules`、`analyses[]`（data_quality/descriptive/test_registration/claim/appraisals）、
    `stat_recompute`、`interpret_summary`、`coverage`、`pending_review`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
  - 判定体系：`judgment`（六枚举）→ `grade` × `category`（method_error /
    reporting_gap / interpretation_risk / none）× `bias_direction`；
    `claim_strength`（causal/associative/descriptive/insufficient）受
    strength_map 机械约束。
- **键归属（多脚本禁写同一键）**：stat_recompute ← stat_recompute.py；
  interpret_summary ← interpret_rollup.py；self_check/gates/unbacked_*/validator_verdict
  ← verify_check.py；gain_evidence/efficiency ← gain_probe.py；其余 ← build_skeleton.py + Agent。
- **工作区产物**：/app/work/{verify_check.json, schema_guard.json, claim_rules.json,
  gain_evidence.json, gain_probe_polluted.json}。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（数据与引文均为虚构）：2 组分析 × 6 分面 = 12 条评价。
示意结论：A01（实验组产量，experimental）penalty=2 → overall=medium（效应量/CI
未报告 + "证明有效"强度过高）；A02（观察性队列）penalty=1 但 1 条弃权 →
overall=uncertain。关键片段：

```json
{
  "case_id": "demo-stat-audit-001", "status": "answered",
  "result": {
    "analyses": [{"analysis_id": "A01", "design_type": "experimental",
      "descriptive": {"n_claimed": 12, "mean_claimed": 53.65833333333333, "sd_claimed": 4.740053381619881},
      "test_registration": {"test_family": "parametric", "test_name": "welch t-test"},
      "claim": {"claim_strength": "causal"},
      "appraisals": [{"checklist_id": "EC-01", "judgment": "unreported", "category": "reporting_gap"}]}],
    "stat_recompute": {"all_match": true},
    "interpret_summary": {"per_analysis": [{"analysis_id": "A01", "penalty_total": 2, "overall": "medium", "overclaim": false}]},
    "verdict": "audited"
  }
}
```

本地自测整条链路（合成案例，非正式答案）见 SKILL.md「最小调用示例」六条命令。

## 7. 最小自检清单（2026-11-19 实测，全部退出码 0）

| 编号 | 自检项 | 实测结果 |
|------|--------|---------|
| C1 | build_skeleton 落骨架（2 组数据集提取、claim_rules 模板落台账） | exit 0，case_id=demo-stat-audit-001 |
| C2 | stat_recompute 复算（A01/A02 match=true，test_mismatch=false，all_match=true） | exit 0 |
| C3 | interpret_rollup 机械汇总（A01 penalty=2→medium / A02 penalty=1+弃权→uncertain） | exit 0 |
| C4 | gain_probe 双模式对照（干净输入正常=退化=0 漏检，steps_count 68 vs 19，delta=49） | exit 0 |
| C5 | gain_probe 污染反例（注入 9 项：正常模式 25 处全抓、七组漏检全 0；退化模式漏检 16） | exit 0，caught_by_normal_mode=True |
| C6 | verify_check 业务校验（61 条检查项） | exit 0，verdict=PASS |
| C7 | schema_guard 结构守卫（output_contract + 业务 schema 全字段） | exit 0，verdict=PASS |
| C8 | 六脚本失败路径（result/case 缺失） | 全部 exit 0 |
| C9 | examples 标注为示意（数据与引文虚构，非正式答案） | 已标注 |
| C10 | SKILL.md ≤150 行 / 脚本 6 个 / 全包 11 文件 / 零第三方依赖 | 148 行 / 6 / 11 / stdlib-only |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍（违规真值由探针独立复算，
统计复算真值含"claimed vs 落盘复算值现场比对"，与 verify_check 分开实现）：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（覆盖 + 分级 + 证据 + 缺陷 + 复算 + 因果 + 弃权） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **七组机械检查** |

实测对照（合成案例 + 注入 9 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（七组） | 0 | 0 | 0 |
| steps_count（已执行检查项+流程步） | 68 | 19 | +49 |
| 污染副本 verdict | FAIL（25 处） | FAIL（仅剩 1 处通用结构问题） | −24 |
| 污染副本清单覆盖漏检 | 0 | 1 | +1 |
| 污染副本解读分级漏检 | 0 | 3 | +3 |
| 污染副本证据回证漏检 | 0 | 8 | +8 |
| 污染副本缺陷分类漏检 | 0 | 1 | +1 |
| 污染副本统计复算漏检 | 0 | 1 | +1 |
| 污染副本因果约束漏检 | 0 | 1 | +1 |
| 污染副本弃权登记漏检 | 0 | 1 | +1 |

**同一校验器、同一污染输入**：正常模式漏检 0（含统计量篡改与因果越界两类领域
污染），退化模式漏掉 16 处客观违规且只剩一条通用结构问题可看——机制增益最直接
的证据。数字全部来自实跑，详见 `gain_evidence.mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 原始数据不可得 / 字段非数值 | stat_recompute 记 unavailable + material_gaps 登记，绝不臆造 |
| 缺失值被当 0 / 静默删行 | 数据质量分面按 inadequate 处理；复算侧缺失跳过并计数（missing_skipped） |
| 单位口径不明 | review_scope.unit_policy 写明不换算，unreported 登记并提示追问 |
| 正态性/方差齐性未检验 | test_choice 按 unreported 处理，期望检验按保守假设推导 |
| 观察性设计写因果 | causal 判 FAIL，强度降级到 associative 并登记 |
| 样本量不足 / 方差为零 / 缺失比例过高 | unassessable 弃权 + pending_review 登记，弃权不罚分 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 verdict 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict` 与 `problems`，Agent
读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断（六脚本失败路径
实测全部 exit 0）。

**Q：统计复算为什么不用 numpy？**
平台契约零外部依赖。标准库 statistics/math 足够覆盖 n/均值/样本方差/标准差/分位
数；口径在 stat_recompute 里固定声明（n-1 方差、线性插值分位数），复算透明可核。

**Q：p=0.04 能写"证明有效"吗？**
不能。无效应量与置信区间时结论强度必须降级——统计显著≠证明有效。claim_strength
受 strength_map 机械约束，overclaim 由 interpret_rollup 降级并由 verify_check 判
FAIL；"证明/导致/因果"等动词在观察性设计下直接触发 causal 违规。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它量化"关闭这些机制会漏掉多少"。SKILL.md
明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：检验选择是脚本定的还是 Agent 定的？**
Agent 依据假设登记（test_registration），脚本只按同一假设机械推"期望检验"并对照
失配——选择依据（理由字段）必填，登记与期望不一致会被抓出来要求解释或修正。

**Q：因果动词扫描会不会误伤否定句（如"未导致"）？**
可能。子串匹配是保守设计，宁误报不漏报；命中后由 Agent 人工复核，复核结果如实
登记（这一点写进 SKILL.md 已知限制）。

## 11. 生态贡献十项（可复用资源）

1. **六分面审计清单**：data_quality/descriptive/test_choice/effect_ci/interpretation/causal_claim
   的 checklist 定义，JSON 直接复用或按数据类型裁剪。
2. **claim_rules 口径台账**：grade_map/category_map/penalty_map/strength_map/
   causal_verbs/thresholds 的声明格式，通用于任何"口径先行"的结果解读场景。
3. **统计复算引擎 `stat_recompute.py`**：纯标准库描述统计复算 + 缺失跳过计数 +
   检验期望推导，可独立用于任何"claimed 数字 vs 原始数据"对照场景。
4. **解读强度机械导出 `interpret_rollup()`**：设计类型→允许强度→过强降级→因果
   动词约束→罚分分档的确定性管线，任何结论分级需求可照抄。
5. **数字回证双闸格式**：claimed 统计量回证 claims 证据链 + 来源文本（unbacked_numbers），
   引文逐字回证（unbacked_evidence），三元组 `{item, value, reason}`。
6. **校验器 `analyze()` API**：verify_check.py 纯函数式（不写盘），ablate 参数可直接
   用作别处的机制开关对照；含 stat_live_diff 现场比对（防复算后被篡改）。
7. **增益对照探针**：正常 vs 退化双跑 + 9 类领域污染注入（统计量篡改/因果越界/
   强度夸大/…），可移植到任何校验型 Skill。
8. **合成示例 fixture**：examples/ 全部标注示意，复制改标签即得新的负例。
9. **失败经验沉淀**：worklog.md 记录真实对照数字与诚实边界（含 claimed 键名
   映射 bug、外层变量泄漏 bug 的定位与修复）。
10. **键归属纪律**：多脚本分键写入、互不覆盖的约定，可直接套用到多脚本 Skill 包。

## 12. 已知限制与诚实边界

- strength_map 与因果动词词表是本技能事前声明的保守设定，不冒充 APA/CONSORT 等
  外部标准；子串匹配可能误报否定句式，命中后须人工复核。
- 复算口径固定为样本方差（n-1）与线性插值分位数；claimed 为总体方差口径时会在
  diffs 中显示，需按口径人工核对。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照；追问轮次按每轮 3 条
  折算是估计量。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/数据集清单/口径模板（退出码恒 0） | 是 |
| scripts/stat_recompute.py | 描述统计复算 + 检验期望 + stat_recompute 回写（仅写此键） | 是（核心引擎） |
| scripts/interpret_rollup.py | 解读强度机械汇总 + interpret_summary 回写（仅写此键） | 是（含 rollup()） |
| scripts/verify_check.py | 业务校验器（覆盖/分级/证据/缺陷/复算/因果/弃权七组） | 是（含 analyze() API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（2 组虚构数据集） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节六条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 REQUIRED 常量与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
