# worklog — sysrev-search-screen（challenge-5b90f5e9）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制照第 4 期同批已交付包（challenge-2dd1f64c / lit-screen-rank）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新，全部对应题面六个突破方向与四条机检点：
  标准事前声明（版本化 + 台账防漂移）→ 检索协议（PICO + 检索式 + criteria_mapping）→
  去重（DOI/标题归一化 + 三级合并依据 + 疑似升级）→ 逐条纳排（理由码字典 +
  criteria_ref + 逐字证据）→ 分歧仲裁（不掩盖、可升级）→ 漏斗计数闭合
  （PRISMA 五级机械复算）→ 待复核登记。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 149 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | ~230 | 落骨架 + 题录清单 + criteria_ledger 台账模板 |
| scripts/dedupe.py | ~200 | 确定性去重（doi_exact/title_exact/title_similar）+ 合并依据 |
| scripts/flow_audit.py | ~180 | PRISMA 漏斗机械复算 + 闭合判据 + 存值差异对照 |
| scripts/verify_check.py | ~430 | 四组业务校验（criteria/reasons/funnel/pending）+ 回写四键 |
| scripts/schema_guard.py | ~180 | 结构守卫（criteria/funnel/records 子 schema） |
| scripts/gain_probe.py | ~450 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| resources/reason_codes.json | 理由码字典 | 排除 9 码 + 待复核 5 码，可扩展并声明版本 |
| examples/* | 合成 7 条虚构题录 | 含 1 组重复对（R03←R04）与 1 组分歧夹具（R05） |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- dedupe.py：`records[].duplicate_of`、`records[].merge_basis`、`result.conflicts`（仅 kind=duplicate_versions 条目）
- flow_audit.py：`result.funnel`
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13，Windows，合成案例 demo-searchscreen-001）

**全链路自测（干净输入）**：build_skeleton（7 条题录）✓ /
dedupe 在未标注骨架上发现 R03←R04（doi_exact, sim=1.0，保留规则选 published 的 R04）✓ /
flow_audit 复算 identified=7 → 去重 1 → 筛选 6 → included 3 / excluded 1 / pending 2，
excluded_by_reason={RC-EX-DESIGN:1}，closure=closed ✓ /
verify_check PASS（34 检查项全部 applied）/ schema_guard PASS /
gain_probe 两跑均记录成功，全程退出码 0。
干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=42 / degraded=8（delta=+34：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 6 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 14 | 0 | −14 |
| 纳排违规漏检 | 0 | 3 | +3 |
| 计数失据漏检 | 0 | 2 | +2 |
| 证据缺失漏检 | 0 | 5 | +5 |
| 待复核漏登记 | 0 | 3 | +3 |

注入的 6 项污染：R01 判 included 但清空 criteria_ref/evidence_quote；R07 判 excluded
但清空 reason_code/criteria_ref；funnel.included 篡改 +1；R05 清空 pending_reason；
清空 pending_review；清空 claims。
正常模式抓全（四类漏检全 0，caught_by_normal_mode=true），退化模式 13 处客观违规
全部漏检且 verdict 翻成 PASS——"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock≈0.0098s，result.json≈26.2KB（26165 字节），
checker_runs=2，records_total=7；`efficiency.model_requests` 保持 null
（不可脚本采集，由 Agent 侧回填）。

### 开发中修复的问题（真实记录）
1. dedupe `rank_canonical` 两次解包错误（返回元组结构与调用方不匹配）→ 改为返回索引对。
2. verify_check 在 `--ablate all` 时 `judged` 变量未定义（定义在 funnel 组内）→ 提到组外。
3. 排除原因分布检查原来是"存值 vs 存值"（污染只篡改存值时抓不到）→ 改为
   "存值 vs 从 records 机械复算"，与 gain_probe 真值口径对齐。
4. pending 无摘要（evidence_quote 为空）时 verify_check 与 gain_probe 对
   claims 回证的要求不一致 → 统一为"quote 为空不算证据违规"（缺 quote 本身
   由 evidence_present 检查对 included/excluded 拦截）。
5. escalated 冲突漏登记只进 problems 不进 self_check 三元组 → 补聚合检查项
   `conflicts.escalated_registered`，gain_probe 捕获计数同步。
6. 示例夹具初版 R01/R04 意外同 DOI 同题 → 重写 R01 为独立研究（也借此验证了
   dedupe 对真重复对的检出）。

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. 理由码字典（RC-EX-*/RC-PD-*）是本技能参考 PRISMA 常规排除原因设定的方法学
   约定，不是外部权威标准；可按综述扩展并声明版本。
4. examples 全部为合成案例（标题/摘要/DOI 虚构），非正式答案；正式结果只能来自
   平台 3 个固定案例的实际运行；search09 式重复导出/分歧夹具是输入 fixture，
   本包的 examples 夹具同样是演示用输入，不是期望答案。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
6. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与同批 challenge-2dd1f64c 包的差异（防同质化说明）
- 领域 schema 全换：items/rubric/ranking/fused_score → records/criteria(版本化)/
  search_protocol/funnel/excluded_by_reason；本题主打"筛选流程可复跑"，不做排序。
- 新增确定性去重引擎 dedupe.py（三级合并依据 + 疑似升级人工，防误并/漏并）。
- 新增漏斗审计引擎 flow_audit.py（PRISMA 五级 + closure 判据 + 存值差异对照）。
- 校验点全换：排序复算 → 标准事前声明（版本/台账/漂移）+ 理由码字典 + 漏斗闭合。
- 污染注入改为领域化污染（纳入无依据/排除原因缺失/计数篡改/清空待复核/清空证据链）。
