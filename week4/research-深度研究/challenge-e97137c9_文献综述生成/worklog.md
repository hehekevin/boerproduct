# worklog — lit-review-bind（challenge-e97137c9）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制沿用第 4 期已交付同类包（challenge-2dd1f64c / lit-screen-rank）验证过的框架：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测；⑤ 键归属分离防多脚本写同一键。
- 领域逻辑全新（对应题面机检四点与突破方向 2/3/4/5）：
  - 主题归纳（themes[].basis 必须写明主题从文献哪里长出来，outline 台账事前声明）；
  - 段落-来源绑定（非空段落 ⇒ source_ids 非空且来自输入文献集）；
  - 引用逐字回证（claims[].evidence.quote 在 case.json 实际正文/摘要中空白归一化后
    子串命中 → unbacked_quotes 拦截编造引用）；
  - 分歧对照登记（disputes[] 双方并列、立场文献不重叠）+ 强度三级
    （established ≥2 来源 / suggestive / disputed ⇒ dispute_id）；
  - 覆盖与遗漏登记（coverage 机械重算 + omissions[] 入册）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 141 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | ~210 | 落骨架 + 文献清单 + outline 台账模板 |
| scripts/theme_group.py | ~200 | 主题归属核对 + coverage 机械重算（键归属 coverage） |
| scripts/draft_bind.py | ~230 | 段落绑定 + 逐字回证（键归属 quote_audit） |
| scripts/dispute_table.py | ~190 | 分歧对照 + 强度不越界（键归属 dispute_audit） |
| scripts/verify_check.py | ~250 | 总校验器（汇聚四组，键归属 self_check/gates/unbacked_quotes/validator_verdict） |
| scripts/schema_guard.py | ~180 | 结构守卫（含 claims/paragraphs 子字段校验） |
| scripts/gain_probe.py | ~430 | 双跑增益对照 + 污染反例（键归属 gain_evidence/efficiency） |
| examples/* | 合成 6 条虚构文献 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- theme_group.py：`result.coverage`（机械重算覆盖）
- draft_bind.py：顶层 `quote_audit`
- dispute_table.py：顶层 `dispute_audit`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_quotes` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`
- Agent：其余（items/themes/outline/evidence_table/disputes/omissions/claims 等）

### 实测对照数字（2026-11-19，Python 3.13，Windows，合成案例 demo-litreview-001）

**全链路自测（干净输入，全部退出码 0）**：build_skeleton ✓（6 条文献全识别）/ draft_bind
PASS（7 检查项，unbacked_quotes=0）/ dispute_table PASS（6 检查项）/ theme_group PASS
（4 检查项，coverage={total:6, included:4, cited:4, uncited:0, ratio:1.0}）/ verify_check
PASS（17 检查项全 applied）/ schema_guard PASS / gain_probe 两跑均记录成功。

**消融双跑（同一干净输入）**：四类漏检 normal=degraded=0（干净输入无违规可漏，符合预期）；
steps_count normal=25 / degraded=7（delta=+18：正常模式执行更多检查项）；
manual_review_items 与 clarification_rounds 均 0。

**同一校验器、同一污染输入（副本注入 3 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 8 | 0 | −8 |
| 无来源论断漏检 | 0 | 1 | +1 |
| 编造引用漏检 | 0 | 1 | +1 |
| 分歧漏检 | 0 | 1 | +1 |
| 覆盖遗漏漏检 | 0 | 3 | +3 |

注入的 3 项污染：P-01 清空 source_ids（无来源论断）；c-01 的 quote 换成虚构英文句
（编造引用）；D-01 拆散分歧对照（立场砍到 1 方）。第 4 项污染（清空 omissions）因示例
omissions 为空未触发注入（探针如实跳过）。正常模式抓全（caught_by_normal_mode=true，
8 处问题全部报出），退化模式 6 处客观违规全部漏检且 verdict 翻成 PASS——这是"同一校验器
双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock ≈0.01s 量级；`efficiency.model_requests`
保持 null（不可脚本采集，由 Agent 侧回填）。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. established 的「≥2 来源」阈值是本技能保守设定（题面未给定），不是外部标准。
4. case.json 未提供文献正文时，逐字回证退化为 evidence_table 摘录底本并登记
   unverifiable_text，quote 组判据强度受限（boundaries 已写明）。
5. examples 全部为合成案例（标题摘要虚构），非正式答案；正式结果只能来自平台 3 个
   固定案例的实际运行。
6. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
7. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 4 期同类包（challenge-2dd1f64c）的差异（防同质化说明）
- 领域 schema 全换：items/relevance/fused_score/ranking/rubric → themes/outline/
  evidence_table/disputes/omissions/coverage（综述域）。
- 校验点全换：纳排一致性/排序复算/分数回证 → 段落-来源绑定/引用逐字回证/分歧对照/
  覆盖遗漏登记四组（与本题机检点一一对应）。
- 新增领域校验器三件套：draft_bind.py（逐字回证）、dispute_table.py（强度分级）、
  theme_group.py（覆盖机械重算），verify_check 改为汇聚式总校验器。
- 污染注入改为领域化污染（无来源论断/编造引用/拆散分歧/清空 omissions）。
- 结构差异：评分排序域无 fused_score/ranking；新增 claims 强度分级与大纲台账闸门
  （outline_ledger / outline_written）。
