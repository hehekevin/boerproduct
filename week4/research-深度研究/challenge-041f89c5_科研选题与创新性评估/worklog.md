# worklog — topic-novelty-audit（challenge-041f89c5）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制沿用本周已交付的 lit-screen-rank（challenge-2dd1f64c）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新，逐条对应题面五个突破方向与机检四点：
  - **新颖性对照有据**：novelty_claims 逐条 closest_work_id + overlap 四值 + 逐字引文
    回证；covered ⇒ not_novel + duplicate_of + conflicts 登记；对照不到标 uncertain，
    绝不写"尚无人研究"。
  - **口径事前声明**：rubric 含五级 grade_rules + 三因子权重（合计=1.0）+ declared_at，
    任何分级/排序之前写定；verify_check 机械核对分级一致性。
  - **要素覆盖**：四要素（problem/hypothesis/method/expected_contribution）非空或登记
    missing_elements；feasibility 四要素（data/method/resource/time）各给 status+basis。
  - **评估回证**：novelty_claims 引文与 fused_score 数字在 claims 证据链中空白归一化
    后逐字子串回证，未回证进 unbacked_numbers 判 FAIL。
  - **风险与替代路线登记**：risks[] / alternatives[] 逐条登记；uncertain、缺要素、
    可行性缺口、冲突升级逐条进 human_review。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 150 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 241 | 落骨架 + 选题/已知工作清单 + rubric 模板 + known_works 台账 |
| scripts/novelty_rank.py | 181 | 三因子机械打分 + 确定性排序（键归属：ranking/fused_score/rank） |
| scripts/verify_check.py | ~465 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 171 | 结构守卫 |
| scripts/gain_probe.py | ~524 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 4 选题 + 5 已知工作（全虚构） | 标注"非正式答案" |
| 整包 | 10 文件 ≈ 128 KB | ≤50 文件 / <2MB ✓，零第三方依赖，命令一律 python3 |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- novelty_rank.py：`result.ranking`、`proposals[].fused_score`、`proposals[].rank`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-topicaudit-001）

**全链路自测（干净输入）**：build_skeleton ✓（提取 4 选题 5 已知工作）/
novelty_rank（T01 0.865 > T04 0.56 > T02 0.51 > T03 0.48，无平局）✓ /
verify_check PASS（51 检查项全 applied）/ schema_guard PASS /
gain_probe 两跑均成功（wall_clock 0.0054s，result 18313 bytes）。
干净输入上 normal vs degraded 四类漏检 delta 全为 0（无违规可漏，符合预期）；
steps_count normal=58 / degraded=7（delta=+51：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | FAIL（仅剩 1 处常开 coverage 检查） | — |
| problems | 13 | 1 | −12 |
| 要素漏检 | 0 | 1 | +1 |
| 口径/分级漏检 | 0 | 1 | +1 |
| 回证漏检 | 0 | 4 | +4 |
| 登记漏项 | 0 | 3 | +3 |

注入的 5 项污染：清空 T01 structure.method 且不登记；T01 首条 novelty_claim 改
covered、清空引文并标 breakthrough；清空 rubric.declared_at；清空 human_review；
清空 claims。正常模式抓全（caught_by_normal_mode=true，四类漏检 0/0/0/0），
退化模式 9 处客观违规漏掉 8 处——"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**失败路径实测**：result.json 不存在 / 坏 JSON / case.json 缺失五种情形，5 个脚本
退出码全部为 0，报告照实写 FAIL + problems。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 新颖性结论仅相对输入 known_works 清单成立；"新颖"不作外部断言，这是设计决定
   （防止把"检索不到"说成"尚无人研究"），不是能力缺陷掩饰。
4. 三因子与五级分级口径是本技能在 rubric 事前声明的设定，不是外部标准。
5. examples 全部为合成案例（选题/文献/引文均虚构），非正式答案；正式结果只能来自
   平台 3 个固定案例的实际运行。
6. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
7. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与 lit-screen-rank（challenge-2dd1f64c）的差异（防同质化说明）
- 领域 schema 全换：papers/label/ranking → proposals/structure/novelty_claims/
  feasibility/risks/alternatives/human_review。
- 校验四组全换：纳排一致性/排序复算/证据回证/待复核 → 要素覆盖/口径与分级一致性/
  评估回证（逐条对照引文）/登记完备（缺口+风险+替代路线）。
- 新增分级一致性机械检查（covered⇒not_novel、breakthrough/strong⇒有 none 陈述、
  not_novel⇒duplicate_of）与可行性四要素检查——对应本题独有"可行性判断/创新点识别"。
- 污染注入改为领域化污染（要素缺失未登记/covered 却标 breakthrough/口径声明清空/
  登记丢失/证据链清空）。
- 已知限制更严：明确"新颖仅相对清单范围成立"，把题面"检索不到≠尚无人研究"写成
  机械闸门（uncertain 强制转 human_review）。
