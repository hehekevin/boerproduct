# sysrev-review-synthesis — 系统性文献综述全流程 Skill（v1）

针对 Bohrium 第 4 期「深度研究与文献综述」赛道「系统性文献综述」
(challenge-51977f9b) 的参赛 Skill。锁定子场景：**PRISMA 式六段流程——协议注册
→ 检索式声明 → 逐条筛选 → 质量评价 → 结构化提取 → 分级综合**。

## 1. 用途与适用条件

给定研究问题与题录快照（真实署名论文 + 可能混入的合成重复导出/夹具，夹具是
输入不是期望答案），完成八件事：

1. **协议事前注册**：综述协议（研究问题/PICO/检索式/纳排标准）在任何判定
   **之前**注册版本号与 registered_at，登记进 protocol_ledger 台账；筛选途中
   禁止口头修改，确需修改必须新增版本并回溯重判（防协议漂移）。
2. **检索式可执行声明**：把研究问题转成带布尔逻辑的检索式，写明数据库、字段、
   时间范围、语种与检索日期，并逐条说明与纳入标准的对应（criteria_mapping）；
   快照模式只对输入全集做全记录筛选，不宣称实时全域召回。
3. **确定性去重**：DOI/标题归一化精确一致 → 直接合并；标题相似 ≥0.90 → 升级
   人工；保留规则 published > 有 DOI > 标题长 > 序号小。
4. **逐条纳排判定**：每条题录 decision + 理由码（RC-EX-*/RC-PD-* 字典）+
   criteria_ref + 逐字证据 + rationale + confidence；全记录覆盖。
5. **质量评价**：每条纳入研究按 QAS-GEN-1 量表逐维度评价（yes/partly/no/
   unclear），overall_grade 必须等于量表机械推导（均分 ≥0.8→high、≥0.5→
   moderate、<0.5→low），杜绝一句"质量较高"。
6. **结构化数据提取**：每条纳入研究提取 study_design / sample（size+units）/
   effect（measure+value+ci+direction），每块证据逐字回证到来源文本；缺值必须
   在 extraction_notes 说明。
7. **分级综合**：每条结论 strength（strong/moderate/weak/insufficient）必须等
   于按规则推导的级别（支持数 × 支持质量 × 冲突数）；冲突证据矩阵、研究空白、
   偏倚登记齐备。
8. **漏斗计数闭合**：PRISMA 五级计数由 flow_audit.py 机械复算，closure=closed
   才算闭合；待复核条目逐条登记 reason+needed_action。

**核心保证**：`verify_check.py` 六组机械校验（protocol/screening/funnel/
extraction/quality/synthesis，可 --ablate 分组消融）+ `gain_probe.py` 正常 vs
退化双跑 + 14 项污染反例副本实测机制增益。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 系统综述作者 | 有了题录集，要完成可复核的筛选→评价→提取→综合全流程 | 逐条判定 + 质量等级 + 结构化证据表 + 分级结论 + 闭合漏斗 |
| 复核者 / 审稿人 | 质疑"这条结论凭什么 strong""这个效应量哪来的" | strength_basis + supporting_records + 提取块逐字回证逐条可查 |
| 研究助理 | 需要解释"为什么排除、等级怎么来的" | reason_code + criteria_ref + 量表推导过程全部落键 |
| 教学 / 培训 | 演示 PRISMA 纪律与协议漂移防范 | 可复算的消融对照实验（gain_evidence） |

**不适用**：不做数据库实时检索、不全文精读翻译、不做元分析统计合并、不论文
写作润色；缺什么登记什么，不脑补、不补造文献。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（json/os/re/sys/argparse/copy/time/math） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 磁盘 | 整包约 90 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（实测 16 个文件） |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需安装步骤、无依赖解析、无需联网。

```bash
# Step 0：骨架 + 题录清单 + 协议台账模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
# Step 1：Agent 注册协议 + 声明检索式与纳排标准（判定前）
# Step 2-8：去重/判定/质量评价/提取/综合/漏斗/增益与自检（见 SKILL.md 九步流程）
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究问题 + 题录快照 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id / status / result / claims / uncertainties / changelog`
    + `self_check / unbacked_numbers / gates / validator_verdict`
  - `result` 内：`review_registration / search_protocol / criteria / records[] /
    funnel / quality_appraisal / extraction / synthesis / conflicts /
    pending_review / coverage / steps / run_status / verdict / gain_evidence /
    efficiency` 等。
- **status**：`answered | partial | insufficient_evidence | input_error`。
- **工作区产物**：`/app/work/` 下 protocol_ledger.json、dedupe_report.json、
  quality_audit.json、extraction_audit.json、synthesis_check.json、
  funnel_audit.json、gain_evidence.json、gain_probe_polluted.json（污染副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题/作者/摘要/DOI 均为虚构）：9 条题录 → 5 纳入
（R01-R05）、2 排除（R06 叙述性综述、R07 人群不符）、1 重复合并（R08 预印本 ←
R01 doi_exact）、1 待复核（R09 缺摘要）；质量等级 high×2 / moderate×2 / low×1；
提取 5 项逐字回证；结论 S-01 strong（3 支持 0 冲突）/ S-02 weak（1 支持 1 冲突）/
S-03 insufficient（0 支持）；漏斗 9→1→8→5/2/1 闭合。自测整条链路：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/dedupe.py --result examples/example-result.json --apply --report /tmp/dedupe.json
python3 scripts/quality_audit.py --result examples/example-result.json --out /tmp/quality.json
python3 scripts/extraction_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/extraction.json
python3 scripts/synthesis_check.py --result examples/example-result.json --out /tmp/synthesis.json
python3 scripts/flow_audit.py --result examples/example-result.json --report /tmp/funnel.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | verify_check PASS（含 output_contract 全字段 + 业务字段） |
| A2 | 协议事前注册 | review_registration 齐备；判定引用版本 == 台账最终版本 |
| A3 | 全记录覆盖 | coverage 与实际条目一致；每条 judged=true 或有 pending_reason |
| A4 | 判定可回溯 | included/excluded 引用存在的标准 id；证据在 claims 逐字回证 |
| A5 | 漏斗闭合 | closure==closed；五级计数 + excluded_by_reason 与复算一致 |
| A6 | 质量一致 | 每条纳入有评价；overall_grade == 量表机械推导（quality_audit PASS） |
| A7 | 提取回证 | 每条纳入有结构化提取；每块 quote 在来源语料/claims 逐字命中 |
| A8 | 强度一致 | 每条结论 strength == 规则推导；gaps/偏倚登记齐备 |
| A9 | 增益有据 | gain_evidence.runs 含 normal/degraded 两遍实跑 + delta + 机制映射 |
| A10 | 污染被抓 | pollution_selftest.caught_by_normal_mode == true（14 项注入全抓） |

## 8. 增益对照机制（真实实测数字，2026-11-19，Python 3.13.14）

`gain_probe.py` 对**同一份** result.json 跱两遍（normal 全开 / degraded 全关），
另在**副本**注入 14 项污染（漏斗 included 篡改 +1、R01 提取块清空 evidence、
R03 overall_grade 篡改、S-01 strength 篡改、清空 gaps/gaps_note、清空
registered_at/criteria.version、清空 pending_review、清空 claims 等）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入七类漏检 | 全 0 | 全 0 | 0（无违规可漏） |
| 干净输入 verdict | PASS | PASS | — |
| steps_count | 87 | 9 | +81 |
| 污染副本 verdict | **FAIL（20 处）** | **PASS（0 处）** | −20 |
| 污染副本漏检 criteria/funnel/evidence/pending | 0/0/0/0 | 3/2/7/1 | +3/+2/+7/+1 |
| 污染副本漏检 extraction/quality/synthesis | 0/0/0 | 3/1/1 | +3/+1/+1 |

正常模式把 14 项污染全部抓住（七类漏检全 0），退化模式 18 处客观违规全部漏掉
且 verdict 从 FAIL 翻成 PASS——协议注册/提取回证/强度分级/漏斗闭合四类机检点
的机制增益最直接证据。违规真值由探针独立复算，与校验层分开实现。

> **边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台"基础 Agent
> vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 最小自检清单（实测 exit 0）

```bash
python3 scripts/quality_audit.py    --result examples/example-result.json   # exit 0, PASS
python3 scripts/extraction_guard.py --result examples/example-result.json --case examples/example-case.json  # exit 0, PASS
python3 scripts/synthesis_check.py  --result examples/example-result.json   # exit 0, PASS
python3 scripts/flow_audit.py       --result examples/example-result.json   # exit 0, closure=closed
python3 scripts/verify_check.py     --result examples/example-result.json --case examples/example-case.json  # exit 0, PASS(81 检查项)
python3 scripts/gain_probe.py       --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution  # exit 0, caught=True
```

## 10. 异常处理

| 异常 | 处置 |
|------|------|
| 题录清单为空 | records 空、funnel.identified=0、verdict=cannot_verify，绝不补造 |
| 无摘要/缺 DOI | missing_metadata 登记 + pending（RC-PD-NO-ABSTRACT/METADATA） |
| 标准冲突 | uncertainties.conflicts 登记 + 声明优先序；改协议新增版本回溯重判 |
| 纳入证据矛盾 | conflict_matrix 登记 + 按强度规则降级，不静默取舍 |
| 提取缺值 | extraction_notes 说明 + material_gaps 登记 |
| 校验报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何脚本失败** | **退出码恒 0**；结论记在报告 verdict 字段，不中断交付 |

## 11. FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告 verdict 与 problems，退出码恒 0
保证流程不被校验器自身故障打断。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式只会让漏检变多，作用是量化"关闭这些机制会漏掉多少"。退化结果
仅用于增益对照，不得当作交付自检结论。

**Q：强度是拍脑袋定的吗？**
不是。strong/moderate/weak/insufficient 由 supporting_records 数量、其质量等级、
conflicting_records 数量按 strength_rules.json 机械推导；声明与推导不一致会被
synthesis_check/verify_check 判 FAIL。

**Q：示例里的结论是答案吗？**
不是。examples/ 全部是合成数据并标注"示意"；正式结论只能来自实际运行。

## 12. 适用范围与限制

- 仅处理输入题录快照；不实时全域召回、不全文精读、不做元分析统计合并。
- 量表与强度规则是方法学约定，可替换并声明新版本。
- 增益对照是本校验层两模式对照，不等于平台白板对照。
- 追问轮次按每轮 3 条折算的估计量；模型请求数由 Agent 侧回填，缺失保持 null。

## 13. 复用建议

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/quality_audit.py` + `resources/quality_scales.json` | "维度判定 → 机械推导等级"范式，任何量表需求可换维度即用 |
| `scripts/extraction_guard.py` | 结构化提取 + 逐字回证（语料归一化子串命中），适用于任何"字段必须有出处"场景 |
| `scripts/synthesis_check.py` + `resources/strength_rules.json` | "规则推导级别 vs 声明一致性"范式，任何分级场景可复用 |
| `scripts/flow_audit.py` / `dedupe.py` | 五级漏斗闭合 / 三级确定性去重，与第 4 期检索筛选包同源 |
| `scripts/gain_probe.py` | 消融双跑 + 污染注入 + 效率计数的完整对照实验骨架 |

## 14. 资源清单与维护

| 文件 | 作用 |
|------|------|
| SKILL.md | 技能本体（8 条强制协议 + 九步流程 + schema + 校验说明，恰 150 行） |
| scripts/build_skeleton.py | Step 0 骨架/题录清单/协议台账模板 |
| scripts/dedupe.py | 确定性去重 + 合并依据登记 |
| scripts/quality_audit.py | 质量评价一致性审计（量表推导） |
| scripts/extraction_guard.py | 结构化提取 + 逐字回证守卫 |
| scripts/synthesis_check.py | 强度分级一致性审计 |
| scripts/flow_audit.py | PRISMA 漏斗机械复算 + 闭合审计 |
| scripts/verify_check.py | 六组业务校验器（含 --ablate，self_check/gates 回写） |
| scripts/gain_probe.py | 消融双跑 + 污染反例 + 效率计数 |
| resources/reason_codes.json | 理由码字典（EX 9 码 + PD 5 码） |
| resources/quality_scales.json | QAS-GEN-1 量表（Q1-Q6 + 推导规则） |
| resources/strength_rules.json | STRENGTH-GEN-1 强度规则 |
| examples/example-case.json | 合成输入示例（9 条虚构题录） |
| examples/example-result.json | 示意输出（非正式答案，含实测 gain_evidence） |
| README.md / worklog.md | 本说明 / 开发记录与实测数字 |

版本 v1（2026-11-19）。维护约定：改 scripts 后重跑第 6/9 节全部命令确认
PASS；改 SKILL.md 后 `wc -l` ≤150；新增文件前核对 ≤50 文件 / ≤2MB 契约。
