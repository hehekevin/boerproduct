# worklog — read-note-harvest（challenge-c050aaed）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期同类包（challenge-2dd1f64c / lit-screen-rank）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：批注位置回证 / 四类型事前口径 / 卡片三要素 / 主题归纳依据 /
  待查证登记 / 确定性检索索引——全部对应题面机检五点（批注位置可回证、类型口径一致、
  卡片三要素完备、归纳有依据、待查证登记）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 148 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | ~230 | 落骨架 + 批注清单 + 材料 sha256 + 口径模板 |
| scripts/index_search.py | ~200 | 确定性检索索引 + 主题统计（键归属：retrieval/theme_stats） |
| scripts/verify_check.py | ~340 | 五组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | ~160 | 结构守卫 |
| scripts/gain_probe.py | ~430 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 3 份虚构材料 + 5 条批注 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- index_search.py：`result.retrieval`、`result.theme_stats`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-readnote-001）

**全链路自测（干净输入，全部 exit 0）**：build_skeleton（5 批注 / 3 材料 / 2 文件）✓ /
index_search（7 条索引：2 卡片 + 5 已判定批注；查询 "memory" 命中 1 条 card-C01）✓ /
verify_check PASS（28 检查项全 applied）/ schema_guard PASS / gain_probe 两跑均记录成功。
干净输入上 normal vs degraded 五类漏检均为 0（无违规可漏，符合预期），
steps_count normal=34 / degraded=7（delta=+27：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | FAIL（仅剩 coverage 常开检查 1 处） | — |
| problems | 14 | 1 | −13 |
| 位置回证漏检 | 0 | 6 | +6 |
| 类型漂移漏检 | 0 | 1 | +1 |
| 卡片漏检 | 0 | 2 | +2 |
| 归纳漏检 | 0 | 1 | +1 |
| 待查证漏登记 | 0 | 2 | +2 |

注入的 5 项污染：A01 清空 locator/quote 并注入越界类型 rumor-type（置 needs_verify）；
C01 清空 source 并把 evidence 指向不存在的批注 ghost-ann；T01 清空 member_anns 与
basis；清空 to_verify；清空 claims。
正常模式抓全（caught_by_normal_mode=true），退化模式把锚点错位（6 处 quote 无回证 +
locator 缺失）、类型漂移（rumor-type）、卡片无源/幽灵引用（2 处）、归纳无依据（1 处）、
待查证丢失（2 处）全部放行——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock≈0.007s，示例 result.json≈11KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上五类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 四类型口径与切词规则是本技能事前声明的设定，不是外部标准；扫描件坐标校正依赖
   平台 ocr-tool，本技能只登记（anchor_kind=ocr）不修正。
4. examples 全部为合成案例（材料/批注虚构，sha256 留空注明），非正式答案；正式结果
   只能来自平台 3 个固定案例的实际运行。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
6. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与 challenge-2dd1f64c（lit-screen-rank）的差异（防同质化说明）
- 领域 schema 全换：items/rubric/ranking/pending_review → annotations/annotation_vocab/
  cards/themes/to_verify/retrieval/theme_stats/source_materials。
- 删除排序引擎 score_rank.py，新增检索引擎 index_search.py（题面"后续检索"方向）：
  确定性切词（ASCII 词 + CJK 二元组，ord 显式码位判断，避开 isalpha 汉字陷阱）+
  召回不足处置。
- 校验点全换：纳排一致性+排序复算 → 位置回证 + 类型口径 + 三要素 + 归纳依据 +
  待查证登记五组。
- 污染注入改为领域化污染（锚点清空+越界类型+卡片幽灵引用+归纳清空+待查证清空）。
