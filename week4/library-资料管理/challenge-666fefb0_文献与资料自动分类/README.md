# lit-classify — 文献与资料自动分类 Skill（v1）

针对 Bohrium 产品赛第 4 期「文献与资料自动分类：科研资料管理」(challenge-666fefb0)
的参赛 Skill。锁定子场景：**多级分类体系事前声明 + 逐条归类判定（含置信度与原文引用）+
多标签 + 边界情形登记 + 同键同类一致性校验**。

## 1. 用途与适用条件

给定混杂的科研资料集合（期刊论文、预印本、数据集说明、扫描件等），完成六件事：

1. **多级体系事前声明**：学科主题/文献类型/年份段等维度建目录层级（node_id/path/keywords），
   在任何分类判定之前写定 `taxonomy`（declared_at），之后禁止调整——体系外类目会被
   校验器判 FAIL。
2. **逐条归类判定**：每条文件归入唯一主类目（primary_path ∈ 体系 node_id），
   `confidence ∈ high/medium/low`（机械分差 ≥2 → high，=1 → medium，同分/无命中 → low），
   置信度升降须在 rationale 说明。
3. **依据引用原文**：evidence_quote 逐字摘自该条目在 case.json 的原文（标题/摘要/关键词），
   claims 证据链逐条对应；quote 不在原文中会被列入 `unbacked_numbers` 判 FAIL。
4. **多标签**：类型/年份段等维度按元数据打标签（tags 均须命中体系 node_id），
   跨主题命中多节点且分差小时判 `multi_domain` 边界。
5. **重复与边界登记**：同键（DOI > 归一化标题+年份 > source_ref）条目不同判必须在
   `conflicts[]` 登记 merged（保留正式版）或 escalated；multi_domain/missing_fields/
   duplicate/unreadable 边界与全部未判定条目逐条登记 `pending_review`（含
   reason+needed_action）。绝不静默覆盖或删除。
6. **同键同类一致性**：`classify_engine.py` 产出 key_signature 分组建议，
   `verify_check.py` 独立重算分组——同键同类是机械复算结论，不是自述。

**核心保证**：`verify_check.py` 机械核对体系命中、逐字回证、同键同类、待复核登记；
`gain_probe.py` 用正常 vs 退化双跑实测机制增益并写入 `result.gain_evidence`。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers / validator_verdict`
四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 资料库管理员 | 几百个混杂文件要按学科/类型/年份归目录，并识别重复下载与版本差异 | 全记录分类清单 + 多标签 + 逐条原文依据 |
| 研究助理 | 需要向导师/团队解释"为什么这篇归这个类目、那份扫描件为什么挂起" | evidence_quote + rationale + 置信度逐条可回溯 |
| 复核者 | 抽查分类一致性与边界处理 | pending_review 清单 + coverage 汇总 + 同键复算结果 |
| 教学 / 培训 | 演示"体系事前声明 + 机械复算 + 边界登记"的整理纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做文献检索发现、不全文精读、不翻译润色；缺什么登记什么，不脑补元数据。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 资料清单 + 分类体系模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1：Agent 声明多级体系（result.taxonomy + /app/work/taxonomy.json，declared_at）

# Step 2：机械归类与同键分组（写 result.consistency / items[].mechanical）
python3 /skills/weekly-skill/scripts/classify_engine.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work

# Step 3-4：Agent 逐条判定 + 待复核登记（见 SKILL.md 七步流程）

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

- **输入**：`/input/case.json`（分类目标 + 资料清单 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`classification_goal`、`taxonomy`、
    `items[]`（逐条判定）、`consistency`（同键分组）、`coverage`、`conflicts`、
    `pending_review`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **判定体系**：`primary_path`（体系 node_id，主类目唯一）× `tags[]`（多标签）×
  `confidence`（high/medium/low）× `boundary`（multi_domain/ambiguous/missing_fields/
  duplicate/unreadable）；约定见 SKILL.md「Step 1/3」。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/taxonomy.json`
  （体系台账）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题摘要 DOI 均为虚构）：8 条资料 → 7 条归类（F01 深度学习
T-01 high、F02 同 DOI 预印本合并、F03/F08 同题重复下载同键同类、F06 数据集 T-04、
F07 强化学习 T-02）、F04 跨主题（机器学习×气候）multi_domain 待复核、F05 扫描件无文本层
missing_fields 待复核。示意输出关键片段：

```json
{
  "case_id": "demo-litclassify-001", "status": "answered",
  "result": {
    "taxonomy": {"declared_at": "step1", "dimensions": ["D1 学科主题 4 节点", "D2 文献类型 3 节点", "D3 年份段 2 节点"]},
    "items": [{"item_id": "F01", "primary_path": "T-01", "tags": ["T-01", "T-10", "T-20"],
                "confidence": "high",
                "evidence_quote": "The deep learning model improves TM-score by 0.08 over prior baselines."}],
    "consistency": {"key_groups": [{"key": "doi:10.1000/demo-001", "item_ids": ["F01", "F02"], "same": true}]},
    "coverage": {"total_items": 8, "judged_items": 7, "classified": 7, "pending": 1, "boundary_flagged": 2},
    "verdict": "partially_classified"
  },
  "claims": [{"claim_id": "c-01", "source_id": "F01",
               "evidence": [{"paragraph_id": "files[0].abstract", "quote": "The deep learning model improves TM-score by 0.08 over prior baselines."}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/classify_engine.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --taxonomy /tmp/wk/taxonomy.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 依据全回证 | `unbacked_numbers` 为空数组（evidence_quote 逐字出现在 case 原文） |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage.total_items == items 条数，每条 judged=true 或有 pending_reason |
| A6 | 体系可回溯 | primary_path/tags 全部命中事前声明体系的 node_id，无体系外类目 |
| A7 | 同键同类 | key_signature 分组独立复算；同键不同判必须有 conflicts 处置记录 |
| A8 | 边界登记 | 每个未判定条目与边界条目都进 pending_review（含 reason+needed_action） |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（体系命中 + 引用回证 + 同键同类 + 边界登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **taxonomy / evidence / consistency / pending 四组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| 干净输入 steps_count | 37 | 6 | +31 |
| 干净输入已执行检查项 | 31 | 0 | +31 |
| 污染副本 verdict | FAIL（13 处问题） | PASS（0 处） | −13 |
| 污染副本体系外路径漏检 | 0 | 2 | +2 |
| 污染副本引用回证漏检 | 0 | 7 | +7 |
| 污染副本同键同类漏检 | 0 | 1 | +1 |
| 污染副本待复核漏检 | 0 | 2 | +2 |

**同一校验器、同一污染输入**：正常模式抓全（漏检 0，13 处问题全报），退化模式 12 处
客观违规全部漏掉且 verdict 从 FAIL 翻成 PASS——这是机制增益最直接的证据。污染注入五项：
体系外路径（T-FAKE-99）、依据缺失（清空 evidence_quote + claims）、同键不同判（F01/F02
改判不同路径 + 清空 conflicts）、待复核登记丢失（清空 pending_review）。数字由探针独立
复算违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 资料清单为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_classified，绝不补造文件 |
| 扫描件无文本层 / 加密 PDF / 乱码 | boundary=unreadable 或 missing_fields + pending_review 登记 needed_action，不脑补元数据 |
| 跨主题/多标签模糊 | 主类目暂取分差较大者并降置信度，boundary=multi_domain + 待复核登记 |
| 同名不同版本/重复下载 | key_signature 同键 + conflicts 登记 merged 或 escalated，绝不静默覆盖或删除 |
| 分类标准冲突 | uncertainties.conflicts 登记双方 + 声明采用的优先序，体系不得事后增删节点凑结果 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：同键同类是怎么算的？会不会误伤正常的多标签？**
key_signature 生成规则固定（DOI → 归一化标题+年份 → source_ref），只约束**主类目**
primary_path 一致，不约束 tags；同键不同判若确有正当理由（如预印本与正式版分目录），
在 conflicts 登记即可通过校验。

**Q：中文文件名/标题会出问题吗？**
关键词与原文都在去空白后做子串匹配（中文原样匹配），不用 isalpha 判字——规避了
"汉字 isalpha 返回 True 导致误判英文"的陷阱；实测 F03/F08 中文关键词节点命中正常。

**Q：mechanical 建议和 Agent 判定不一致算错吗？**
不算。mechanical 是关键词命中建议，Agent 采纳、上调或改判都允许，但改判必须给出
rationale 与原文证据；低分差（margin=0）建议默认不采纳而是登记边界。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：为什么归类条目必须有 evidence_quote？**
题面要求"每份文件的归属和标签能否用原文与元数据核对"。没有原文引用的归类会被
verify_check 列入 unbacked_numbers 判 FAIL，这正是防止"关键词猜类"退化的机械闸门。

## 11. 适用范围与限制

- 仅处理输入清单内资料：不做数据库实时检索、不全文精读、不做单篇深度解读。
- 机械归类是建议值，最终判定须由 Agent 引用原文证据复核；建议与最终不一致以 rationale 为准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/classify_engine.py` 的 key_signature | DOI → 归一化标题+年份 → source_ref 的同键判定规则，任何"重复识别/版本区分"需求可直接照抄 |
| `taxonomy` 台账格式 | `{declared_at, dimensions[nodes], multi_label_policy, boundary_policy}` 是通用的"事前体系声明"台账 |
| `pending_review` 登记 | `{item_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/资料清单/体系模板（退出码恒 0） | 是 |
| scripts/classify_engine.py | 关键词机械归类建议 + key_signature 同键分组 | 是 |
| scripts/verify_check.py | 业务校验器（体系命中/引用回证/同键同类/边界登记） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（8 条虚构资料） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/ITEM_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
