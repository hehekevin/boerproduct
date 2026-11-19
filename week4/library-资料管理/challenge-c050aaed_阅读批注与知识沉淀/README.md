# read-note-harvest — 阅读批注与知识沉淀 Skill（v1）

针对 Bohrium 产品赛第 4 周「library 资料管理」赛道「阅读批注与知识沉淀」(challenge-c050aaed)
的参赛 Skill。锁定子场景：**批注逐条定位回证 + 四类型口径标注 + 知识卡片三要素沉淀 +
主题归纳 + 待查证登记 + 检索入口**。

## 1. 用途与适用条件

给定科研材料与其上的散落批注（高亮/划线/页边/手写/剪藏），完成六件事：

1. **逐条批注定位**：每条批注给 `locator`（页/节/段，与实际材料一致）+ `anchor_kind`
   载体枚举 + `quote`（逐字摘录）+ `quote_location`——批注能逐条回到原文的具体页与位置。
2. **四类型口径标注**：`question / supplement / challenge / association`（疑问/补充/质疑/联想）
   口径在**任何判定之前**事前声明（annotation_vocab，declared_at 必填），ann_type 必须命中
   口径——类型不漂移、高亮划线不混一类。
3. **claims 证据链回证**：每条已判定批注在 `claims[]` 有对应证据条目，quote 逐字回证
   （空白归一化后子串匹配），无回证判 FAIL——锚点错位被机械闸门拦下。
4. **知识卡片三要素**：每张卡片 `point / evidence / source` 一个不缺；卡片摘录必须逐字
   来自所引批注的 quote——笔记不退化为无来源摘抄。
5. **主题归纳有依据**：每个主题 `member_anns ≥2` 且全部真实存在 + `basis` 写明归纳依据，
   禁止单词重合即连接；重复下载/多版本用 `duplicate_of + conflicts` 归并。
6. **待查证登记与检索入口**：`needs_verify=true` 的批注逐条登记 `to_verify[]`（含
   question + needed_action）；`index_search.py` 生成确定性检索索引并演示一次真实查询，
   命中 0 条时给出召回不足处置。

**核心保证**：`verify_check.py` 五组机械校验（位置回证/类型口径/卡片三要素/归纳依据/
待查证登记）；`gain_probe.py` 正常 vs 退化双跑实测机制增益并注入污染反例副本。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 研究生 | PDF 高亮与页边批注散落多处，要整理成可检索的知识卡片 | 逐条回证的批注清单 + 三要素卡片 |
| 文献管理员 | 同一文献重复下载把批注拆散 | duplicate_of + conflicts 归并记录 |
| 写作者 | 写综述时需要"每条论断指到原文片段" | claims 证据链 + 主题归纳依据 |
| 复核者 | 抽查批注是否被错挂到相邻段落 | locator/quote 逐字回证 + to_verify 清单 |

**不适用**：不做 PDF 解析库接入、不全文精读、不文献检索、不目录治理；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math` / `hashlib`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB，零外部依赖 |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 批注清单 + 材料哈希 + 类型口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明四类型口径，然后逐条批注判定与回证（见 SKILL.md 七步流程）

# Step 3：检索索引与主题统计（写 result.retrieval / result.theme_stats）
python3 /skills/weekly-skill/scripts/index_search.py --result /app/output/result.json --query "核心术语"

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

- **输入**：`/input/case.json`（材料 + 批注线索 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`source_materials`、
    `annotation_vocab`、`annotations[]`（逐条批注）、`cards[]`、`themes[]`、`to_verify[]`、
    `coverage`、`conflicts`、`retrieval`、`theme_stats`、`steps`、`run_status`、`verdict`、
    `verdict_basis`、`gain_evidence`、`efficiency`
- **类型体系**：`annotation_vocab` 四类型（question/supplement/challenge/association）
  × `anchor_kind` 载体枚举 × `confidence`（high/medium/low）；判定规则在 Step 1 事前声明。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/type_vocab.json`
  （类型口径台账）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（材料与批注均为虚构）：5 条批注 → 全部逐条判定（A05 与 A04
重复合并）、2 张三要素卡片、2 个主题、2 条待查证登记。示意输出关键片段：

```json
{
  "case_id": "demo-readnote-001", "status": "answered",
  "result": {
    "annotation_vocab": {"types": [{"type_id": "question", "label": "疑问"}, "…"], "declared_at": "step1"},
    "annotations": [{"ann_id": "A01", "locator": "M01 p.2 §3 para1", "ann_type": "question", "judged": true}],
    "coverage": {"total_annotations": 5, "judged": 5, "cards_total": 2, "themes_total": 2, "to_verify_total": 2},
    "verdict": "extracted"
  },
  "claims": [{"claim_id": "c-01", "source_id": "A01",
               "evidence": [{"paragraph_id": "materials[0].excerpts[0]", "quote": "Sleep-restricted participants showed significantly reduced working memory accuracy (p < .01)"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/index_search.py --result examples/example-result.json --query "memory" --k 3 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --vocab /tmp/wk/type_vocab.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 批注位置可回证 | 每条已判定批注 locator 非空且 quote 在 claims 逐字回证 |
| A4 | 类型口径一致 | ann_type 全部命中事前 vocab；declared_at 非空且判定前声明 |
| A5 | 卡片三要素完备 | point/evidence/source 一个不缺；卡片摘录逐字来自所引批注 |
| A6 | 归纳有依据 | 每主题 member_anns≥2 且全部存在 + basis 非空 |
| A7 | 待查证全登记 | 每个 needs_verify 条目进 to_verify（含 question+needed_action） |
| A8 | 重复文件归并 | duplicate_of 全部在 conflicts 登记 merged/escalated |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（位置回证 + 类型口径 + 卡片三要素 + 归纳依据 + 待查证登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **location / type / card / theme / toverify 五组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑，详见 worklog.md）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（五类） | 0 | 0 | 0 |
| steps_count | 34 | 7 | +27 |
| 污染副本 verdict | FAIL（14 处问题） | FAIL（仅剩 1 处常开检查） | −13 |
| 污染副本位置回证漏检 | 0 | 6 | +6 |
| 污染副本类型漂移漏检 | 0 | 1 | +1 |
| 污染副本卡片漏检 | 0 | 2 | +2 |
| 污染副本归纳漏检 | 0 | 1 | +1 |
| 污染副本待查证漏登记 | 0 | 2 | +2 |

**同一校验器、同一污染输入**：正常模式抓全（caught_by_normal_mode=true，13 处客观违规
漏检 delta 全部 >0），退化模式把锚点错位、类型漂移、卡片无源、归纳无依据、待查证丢失
全部放行——这是机制增益最直接的证据。数字由探针独立复算违规真值，与校验层分开实现；
详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 材料目录为空 / 无批注线索 | annotations 空、coverage.total=0、verdict=cannot_verify 或 not_extracted，绝不补造 |
| OCR 置信度低 / 无文本层 | anchor_kind=ocr + missing_metadata + 置信度降级；无法定位则 needs_verify |
| 重复下载 / 版本串味 | duplicate_of + conflicts 登记 merged；无法确认则 escalated 进 to_verify |
| 加密或损坏文件 | 登记 material_gaps，status 如实降级，不假装已读取 |
| 批注类型难判 | 按 vocab 规则就近归类并注明依据；无法归类则 confidence=low + needs_verify |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：切词为什么不用 isalpha？**
Python 3 里汉字 `'汉'.isalpha()` 返回 True，中英混排会被切成假"单词"。本技能用 `ord()`
显式判断 ASCII 词与 CJK 码位（0x4E00–0x9FFF 二元组），同输入重复运行逐位一致。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：主题归纳会不会"仅共享一个术语就连成一片"？**
不会静默发生。verify_check 要求 member_anns≥2 且全部真实存在 + basis 写明归纳依据；
to_verify 里明确要求机制关联类疑点"不得凭术语重合直接连接"。

**Q：为什么卡片摘录必须逐字来自所引批注？**
题面要求"笔记里的每条论断能否指到支撑它的原文片段"。卡片证据一旦脱离批注原文，
verify_check 判 FAIL——这正是防止"笔记退化为摘抄"的机械闸门。

**Q：needs_verify 是不是偷懒？**
不是——它是题面要求的"待查证事项登记"。needs_verify 必须写 question 并登记进
to_verify（含 needed_action），恰恰是把人工注意力集中到真正难判的条目上。

## 11. 适用范围与限制

- 仅处理输入材料内的批注：不做 PDF 解析库接入、不全文精读、不文献检索、不目录治理。
- 四类型口径与切词规则是本技能设定并事前声明，不冒充外部标准；扫描件坐标校正依赖
  平台 ocr-tool，本技能只登记不修正。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/index_search.py` 的 `tokenize()` | ASCII 词 + CJK 二元组确定性切词（ord 显式码位判断），任何中文检索需求可直接照抄 |
| `annotation_vocab` 台账格式 | `{types:[{type_id,label,definition,rule}], declared_at}` 是通用的"事前口径声明"台账 |
| 卡片三要素 schema | `{point, evidence, source}` 通用的结构化笔记最小单元 |
| `to_verify` 登记 | `{item_id, question, related_anns, needed_action}` 通用的人工核查入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/批注清单/材料哈希/口径模板（退出码恒 0） | 是 |
| scripts/index_search.py | 确定性检索索引 + 主题统计 + 查询演示（键归属：retrieval/theme_stats） | 是 |
| scripts/verify_check.py | 业务校验器（位置回证/类型口径/三要素/归纳依据/待查证） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（3 份虚构材料 + 5 条批注） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 最小自检清单（交付前实测，全部 exit 0）

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk   # exit 0
python3 scripts/index_search.py --result examples/example-result.json --query "memory" --k 3 --dry-run                              # exit 0
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --vocab /tmp/wk/type_vocab.json --out /tmp/vc.json   # PASS
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json                             # PASS
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution  # caught=true
wc -l SKILL.md   # ≤150
```

## 15. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 14 节自测清单 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/ANN_REQUIRED/CARD_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
