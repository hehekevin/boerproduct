# worklog — sci-file-retrieval（challenge-139745c7）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期同类包（challenge-2dd1f64c / lit-screen-rank，其上游为第 3 周冠军包
  repro-verify）：① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新：检索式事前声明（词表/过滤/requirement_mapping）+ 逐 (query,file) 全覆盖
  判定 + 证据逐字对照 case.json 原文 + 按查询确定性排序 + 空结果/受限/版本登记——
  全部对应题面五个突破方向与机检四点（检索式与需求映射有据、命中依据可回证引用
  文件内原文、相关性排序可复算、空结果登记）。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 149 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 305 | 落骨架 + 资料库/需求清单 + 检索式台账模板 |
| scripts/score_rank.py | 212 | 三因子打分 + 按查询确定性排序（键归属：ranking/fused_score/rank） |
| scripts/verify_check.py | 583 | 四组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict |
| scripts/schema_guard.py | 158 | 结构守卫 |
| scripts/gain_probe.py | 534 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 8 份虚构文件 + 3 个查询 | 标注"非正式答案" |
| README.md | 生态十项 | 用途/依赖/安装/输入输出/示例/验收/异常/FAQ/限制/复用/维护 |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- score_rank.py：`result.ranking`、`hits[].fused_score`、`hits[].rank`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-scifileretrieve-001）

**全链路自测（干净输入）**：build_skeleton ✓（8 文件 + 3 查询 → 预填 24 判定对）/ 
score_rank ✓（Q01：H004 1.0 > H003 0.92 > H001 0.9 > H008 0.78；Q02：H012 1.0 >
H015 0.96 > H011 0.92 > H010 0.76）/ verify_check **PASS（81 检查项全部 applied）** /
schema_guard **PASS** / gain_probe 两跑均成功。

干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=88 / degraded=9（delta=+79：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 21 | 0 | −21 |
| 检索式漏检（grounding） | 2 | 3 | +1 |
| 排序漏检（ranking） | 0 | 1 | +1 |
| 证据漏检（evidence） | 0 | 14 | +14 |
| 登记漏报（registry） | 1 | 7 | +6 |

注入的 5 项污染：H001 改 hit 但清空 matched_terms/evidence_quote 并篡改 fused_score=9.9999；
H005 清空 pending_reason；清空 pending_review；清空 no_result_queries；清空 claims。
正常模式抓全（caught_by_normal_mode=true，verdict=FAIL），退化模式 7 处客观违规全部
漏检且 verdict 翻成 PASS——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock≈0.013s，example-result.json≈51.4KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

**开发中发现并修复的缺陷**：verify_check 的 `fused_recompute` 自检键最初使用查询内
局部索引 j，跨查询同名键相互覆盖（Q01 与 Q02 的第 0 个 hit 都写 hits[0].fused_recompute），
导致污染漏检统计把"已捕获"误计为"漏检"（修复前排序漏检 delta=0）。已改为全局索引
gi 并重跑确认：修复后污染副本排序漏检 normal=0 / degraded=1，delta=+1，与注入的
fused_score 篡改一一对应。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. missed 计数仅统计三元组键的捕获口径，低于实际捕获面：正常模式的违规同样进入
   problems 列表并判 FAIL（污染副本 normal 侧 grounding_missed=2、registry_missed=1
   属键覆盖口径下的保守计数，verdict 已为 FAIL）。该说明已写入
   gain_evidence.boundaries。
4. 证据逐字对照依赖 case.json 提供文件内容字段；内容不可得时退化为 claims 链回证
   （gate 记 not_found 并如实标注，不冒充已对照原文）。
5. 三因子归一化口径是本技能在 query_plan 事前声明的设定，不是外部标准。
6. examples 全部为合成案例（文件内容虚构），非正式答案；正式结果只能来自平台 3 个
   固定案例的实际运行。
7. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
8. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与第 4 期同类包（challenge-2dd1f64c）的差异（防同质化说明）
- 领域 schema 全换：papers/criteria/rubric/items → library/queries/query_plan/hits/
  no_result_queries/restricted_files。
- 新增"证据逐字对照原文"机械校验（verify_check C1）：hit 的 evidence_quote 必须
  子串命中 case.json 中该文件的内容字段——第 4 期同类包只做 claims 链回证，
  不做原文逐字对照；这是本题"命中依据可回证（引用文件内原文）"机检点的直接落地。
- 新增空结果登记（no_result_queries）与受限文件登记（restricted_files）两组校验，
  对应题面"无结果/权限受限登记"。
- 排序引擎改为按查询分组（per_query ordered_hits/查询内名次），平局破平键改为
  content_match。
- 污染注入改为领域化污染（hit 无词表依据/篡改分数/清空空结果登记/清空待复核/清空证据链）。
- 词表匹配全部用集合/子串运算，代码中无 str.isalpha 分词（防汉字陷阱，SKILL.md 协议 5 有明文）。
