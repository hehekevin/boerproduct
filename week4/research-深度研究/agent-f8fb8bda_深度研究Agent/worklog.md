# worklog — deep-research-loop（agent-f8fb8bda）

## 2026-11-19 v1 开发记录

### 结构与机制来源
- 骨架与机制沿用团队已验证的第 4 期同类包骨架（challenge-2dd1f64c / lit-screen-rank，
  其源头为第 3 周冠军包 repro-verify）：
  ① 强制协议 8 条 + 线性 Step 流程；② 失败路径 exit 0、verdict 照实写 JSON；
  ③ 三元组自检 `{item, template_value, applied, match}` 回写 + 闸门四态；
  ④ 正常 vs 退化双跑增益探针 + 污染反例副本自测。
- 领域逻辑全新，对应题面四个突破方向与机检四点（计划事前声明、迭代轮次留痕可回放、
  结论-证据对齐、未决问题登记）：
  研究计划事前声明（依赖 DAG + sha256 指纹锁定）/ 逐轮检索-综合-缺口留痕 /
  kind×strength 双维结论标注 + 引文逐字回证 / 分歧观点并陈 / 未决问题登记。

### 文件清单
| 文件 | 行数/大小 | 说明 |
|------|----------|------|
| SKILL.md | 150 行（≤150 ✓） | frontmatter name/description 合法 |
| scripts/build_skeleton.py | 214 | 落骨架 + 子问题/来源提取 + 计划模板 |
| scripts/plan_audit.py | 158 | 计划事前声明审计 + sha256 指纹台账（键归属：result.plan_audit） |
| scripts/coverage_calc.py | 141 | 覆盖面/强度机械汇总（键归属：coverage/strength_summary） |
| scripts/verify_check.py | 421 | 四组消融校验（plan/trace/evidence/registry）+ 回写四顶层键 |
| scripts/schema_guard.py | 186 | 结构守卫 |
| scripts/gain_probe.py | 469 | 双跑增益对照 + 污染反例（键归属：gain_evidence/efficiency） |
| examples/* | 合成 3 子问题 + 6 条虚构来源 | 标注"非正式答案" |

### 键归属（多脚本禁写同一键）
- build_skeleton.py：骨架全部初始键
- plan_audit.py：`result.plan_audit` + /app/work/plan_ledger.json
- coverage_calc.py：`result.coverage`、`result.strength_summary` + /app/work/coverage_ledger.json
- verify_check.py：顶层 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`
- gain_probe.py：`result.gain_evidence` / `result.efficiency`

### 实测对照数字（2026-11-19，Python 3.13.14，Windows，合成案例 demo-deepresearch-001）

**全链路自测（干净输入，全部 exit 0）**：build_skeleton（3 子问题 + 6 来源提取）✓ /
plan_audit PASS（digest=3f0869ba8adb651d）✓ / coverage_calc（answered=2 partially=1，
strong=1 moderate=1 weak=2）✓ / verify_check PASS（36 检查项全 applied）✓ /
schema_guard PASS ✓ / gain_probe 两跑均记录成功 ✓。

干净输入上 normal vs degraded 四类漏检均为 0（无违规可漏，符合预期），
steps_count normal=44 / degraded=8（delta=+36：正常模式执行更多检查项）。

**同一校验器、同一污染输入（副本注入 5 项污染）双跑**：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| verdict | FAIL | PASS | — |
| problems | 10 | 0 | −10 |
| 计划违规漏检 | 0 | 1 | +1 |
| 迭代留痕漏检 | 0 | 1 | +1 |
| 证据对齐漏检 | 0 | 7 | +7 |
| 未决漏登记 | 0 | 2 | +2 |

注入的 5 项污染：F1 保持 strength=strong 但清空 sources；清空 claims；清空 open_questions；
清空 plan.declared_at；R1 清空 queries_run。
正常模式抓全（caught_by_normal_mode=true，10 处问题含"F1 strong 但带引文来源 0 个"
"F2/F3 引文无逐字回证""SQ-03 未登记 open_questions"等），退化模式 11 处客观违规全部
漏检且 verdict 翻成 PASS——这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

**效率计数**：gain_probe 全链路 wall_clock≈0.005s，result.json≈22.0KB；
`efficiency.model_requests` 保持 null（不可脚本采集，由 Agent 侧回填）。

### 硬约束逐条自检
1. SKILL.md 150 行 ≤150 ✓，YAML frontmatter name/description 合法 ✓
2. 脚本 6 个 ≤8 ✓；包文件 10 个 ≤50 ✓；总大小 ~92KB <2MB ✓；零外部依赖（stdlib only）✓；命令一律 python3 ✓
3. 挂载路径 /skills/weekly-skill；输入 /input/case.json + task.md；产出 /app/output/result.json（含 case_id 与 output_contract 全字段，build_skeleton 自动补齐 contract 字段）✓
4. 六个脚本全部 try/except 全捕获 + 恒 return 0 / sys.exit(0)，实测异常路径 exit 0 ✓（结论写 JSON verdict）
5. examples 标注"合成示意案例（非正式答案）"，来源内容虚构 ✓
6. 脚本定位：SKILL.md Step 0-6 全部以 `/skills/weekly-skill/scripts/...` 标志路径调用，挂载后逐字命中 ✓
7. 键归属表如上，六脚本互不写同一业务键 ✓；代码无 isalpha 汉字陷阱（中文判定全用非空串检查与 norm 正则）✓

### 诚实边界
1. 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台基础 Agent 对照；
   平台白板对照由平台生成。
2. 干净合成输入上四类漏检 delta 全为 0（无区分度）——增益证据主要来自污染反例副本，
   已在 gain_evidence.interpretation_rule 说明 delta=0 的含义。
3. strength 判级中"来源方向一致"由 Agent 判定，校验器只机械核对来源数量与引文回证，
   无法验证语义方向判断本身。
4. examples 全部为合成案例（研究问题与来源虚构），非正式答案；正式结果只能来自平台
   固定案例的实际运行。
5. 追问轮次按每轮 3 条折算的估计量，非实测交互次数。
6. 平台案例若提供 PDF 全文而非结构化 sources，需 Agent 在 Step 2 前自行解析并将解析产物
   记入 iterations 留痕（本包不含 PDF 解析脚本，属平台环境工具）。
7. 待办（主控统一处理）：GITHUB_URL.txt 需在公开仓库后生成。

### 与同类包（challenge-2dd1f64c / lit-screen-rank）的差异（防同质化说明）
- 领域 schema 全换：candidates/rubric/ranking/pending_review → plan/iterations/findings/
  divergent_views/open_questions/coverage/strength_summary/plan_audit。
- 新增 plan_audit.py（事前声明 + sha256 指纹锁定 + 依赖 DAG 无环检查）替代排序环节。
- 校验点全换：纳排一致性+排序复算 → 计划一致性 + 迭代留痕可回放 + 结论-证据对齐
  （引文逐字回证）+ 未决问题登记四组。
- 污染注入改为领域化污染（strong 清来源/清证据链/清未决登记/清计划声明/清检索式）。
- verdict 分级全换：synthesized / partially_synthesized / not_synthesized / cannot_verify。
