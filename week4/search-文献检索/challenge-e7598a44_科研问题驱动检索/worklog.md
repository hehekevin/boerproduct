# worklog — quest-search v1（challenge-e7598a44 科研问题驱动检索）

## 一、定位与选题

题面聚焦五个突破方向：问题拆解 / 查询规划 / 术语扩展 / 多轮检索 / 停止条件。
本 Skill 全部纳入，落成「问题拆解 → 检索式规划 → 执行检索 → 相关性判定 → 缺口登记」
的结构化可复跑流程；无联网检索工具时，价值在于把流程做成**机械可校验**：
子问题覆盖、检索式合规（依赖引用/术语扩展）、相关性判定有据（逐字回证）、
缺口登记（枚举 + follow_up）都有校验器兜底，Agent 的自由发挥被压缩到
"读材料写依据"，而依据可以逐字回证。

机制骨架沿用第 3 周冠军包已验证的纪律（落骨架 / 事前声明 / 三元组自检 / 闸门四态 /
数字逐字回证 / 双模式消融 / 污染反例 / 失败路径 exit 0），**领域逻辑全新编写**：
- 事前声明对象从"数值容差"换成"停止条件"（stop_criteria，检索前写定禁止放宽）；
- 校验对象从"参数/指标对照"换成"子问题覆盖 / 相关性依据 / 缺口登记"；
- 数字回证从"论文值 vs 计算值"换成"relevance_score 须在 claim text 中回证 +
  relevance_basis 逐字摘自材料 quote"；
- 消融开关从"回证/容差"换成"子问题覆盖(coverage) / 相关性判定(relevance) / 缺口登记(gaps)"。

## 二、关键实现记录

- `build_skeleton.py`：Step 0 落骨架（16 个业务键一个不缺）+ 扫描 /input 与 case 内嵌
  记录集（records/papers/corpus 等键名兼容）+ 生成 `/app/work/stop_criteria.json`
  事前声明模板。三级容错，退出码恒 0。
- `verify_check.py`：63 项机械检查（示例输入实测），含 `--selftest` 包身份校验
  （读 `.package-marker.json` 防 find|head -1 式定位串包）。
  `--ablate none|coverage|relevance|gaps|all` 供增益对照。
  **防 isalpha 汉字陷阱**：数字判定只走 `float()` 可转换性（`num_variants`），
  全代码无 `str.isalpha()` 调用——汉字会通过 isalpha，用它判数字必错。
- `schema_guard.py`：output_contract 全字段 + 本题 16 个业务键结构守卫。
- `gain_probe.py`：同输入跑 normal/degraded 两遍，五项指标 + 机制→指标映射 +
  边界 + 失效条件 + 污染反例自测（副本注入，原文件不动）。
- result.json 写盘分工（多脚本禁写同一键）：verify_check → `self_check` /
  `unbacked_numbers` / `gates` / `validator_verdict`；gain_probe →
  `result.gain_evidence` / `result.efficiency`；build_skeleton 只做初始骨架。
- SKILL.md 143 行（≤150 硬约束），frontmatter name/description 单行合法英文。

## 三、自检清单实测（逐条 exit 0）

```
S1 python3 scripts/verify_check.py --selftest
   → selftest PASS  package=quest-search challenge=challenge-e7598a44  exit=0
S2 python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples \
     --out $T/skel.json --work-dir $T/wk
   → case_id=demo-quest-001 | contract 字段 6 个 | case 内嵌记录集 records(3 条) | exit=0
S3 python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json
   → PASS  counts={'subquestions':3,'query_plan':3,'search_rounds':2,'candidates':3,
     'gaps':1,'claims':4,'steps':5,'unbacked_numbers':0,'checks_executed':63}  exit=0
S4 python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
   → PASS: 结构完整（case_id=demo-quest-001）  exit=0
S5 cp examples/example-result.json $T/demo.json && python3 scripts/gain_probe.py \
     --result $T/demo.json --case examples/example-case.json --work-dir $T/wk --emit-into --inject-pollution
   → 双模式实跑 + 污染自测 caught_by_normal_mode=true  exit=0
S6 python3 scripts/verify_check.py --result "$T/不存在.json"
   → FAIL: result.json 不存在（不中断交付）  exit=0   ← 失败路径退出码 0
py_compile 4 脚本 → OK
```

## 四、同输入机制消融：真实对照数字

同一份示例输入（demo-quest-001，3 子问题 / 3 查询 / 3 候选 / 1 缺口），
同一套校验器 `verify_check.analyze()` 跑两遍：

| 指标 | normal（全开） | degraded（ablate=all） | delta（正常−退化） | 方向 |
|------|--------------|----------------------|-------------------|------|
| coverage_ratio 子问题覆盖机器判定占比 | 100% | 0% | +1.0 | 越高越好 |
| relevance_missed 相关性依据缺失漏检 | 0 | 0 | 0 | 越低越好 |
| candidates_adjudicated 候选判定覆盖 | 3 | 0 | +3 | 越高越好 |
| manual_review_items 需人工核对条目 | 0 | 6 | −6 | 越低越好 |
| steps_count 步骤数 | 68 | 54 | +14 | 参考（higher_is_better=null） |
| clarification_rounds 追问轮次 | 0 | 2 | −2 | 越低越好 |

干净输入上 relevance_missed 两臂均为 0（无违规可漏）——区分度由污染反例给出。

**污染反例自测**（副本注入 5 类污染：清空 relevance_basis、清空排除原因、
清空子问题 query_ids、清空 gaps、清空 claims）：

| 臂 | verdict | problems | unbacked_numbers | relevance_missed | manual_review_items |
|----|---------|----------|------------------|------------------|---------------------|
| polluted_normal | FAIL | 8 | 3 | 0 | 0 |
| polluted_degraded | FAIL | 1 | 0 | 2 | 8 |

`missed_detection_delta`：relevance_missed +2、unbacked_numbers +3、problems +7
（退化臂比正常臂漏掉 12 项中的 7 项判罚与 3 个未回证数字）；
`caught_by_normal_mode=true`。**同一套校验器对两臂各跑一遍，FAIL 数差是机器判定。**

## 五、诚实声明

- 本消融是**机制消融**（本校验层正常 vs 退化两模式、同一输入同一套校验器），
  **不是平台"基础 Agent vs 参赛 Skill"白板对照**；白板对照由平台生成，不冒充。
- `examples/` 为合成案例并标注「示意，非正式案例答案」；正式答案不预置，
  三个固定案例在平台侧运行。
- `efficiency.model_requests` 保持 null（脚本不可采集，由 Agent 按实际回填）。
- 追问轮次为折算估计量（ceil(manual/3)），原始计数 manual_review_items 落盘可复算。
- relevance_score 是基于材料原文的判定分数，非人工金标准；冲突登记 human_review。

## 六、迭代与修复记录

1. 首版 gain_probe 漏检统计 bug：校验项"未应用"时违规未计入 missed，导致退化臂
   relevance_missed 恒 0——重构为"applied 且 match=False 才算捕获，否则计入漏检"。
2. exclusion_reason 校验原不在消融范围内，污染反例的退化臂仍能抓到该违规，
   稀释 delta——归入 relevance 消融开关。修复后对照数字见第四节。
3. 第 3 周包的 example-result 未内嵌 gain_evidence/efficiency 占位，实跑校验会误报
   FAIL（本次实测复现：gain_evidence.present / efficiency.present 两条 FAIL）。
   本包示例内嵌 `{available:false, reason:…}` 诚实占位，S3 实测 PASS。
4. gain_probe `--emit-into` 会回写目标文件：自测一律在副本上跑，示例文件保持静态占位。

## 七、约束自查

- SKILL.md 143 行 ≤150 ✓；frontmatter 单行合法 ✓
- 脚本 4 个 ≤8 ✓；文件 10 个 ≤50 ✓；包 ~131KB <2MB ✓；零外部依赖、全 python3 ✓
- 所有失败路径 exit 0（S6 实测；argparse/校验/缺失全捕获降级）✓
- 标志文件校验式定位（--selftest），无 find|head -1 ✓
- examples 标注「示意，非正式案例答案」，不预置正式答案，无伪造执行记录 ✓
- 多脚本 result.json 写键零重叠 ✓；数字判定无 isalpha ✓

## 八、剩余风险

1. 正式案例的 output_contract 字段名未知——build_skeleton/schema_guard 均按多排布
   兼容提取，缺失字段自动补 "unknown"，但极端嵌套排布可能需 Agent 手工兜底（SKILL.md 已写）。
2. 正式案例若为 9 篇真实论文的全记录筛查，候选数可能远大于示例（3 条）——
   校验器逐候选检查是 O(N) 纯内存计算，无性能风险；预算风险在相关性摘录写作量，
   协议第 3/6 条已给广度优先与预算保护。
3. 合成重复/冲突记录（题面 search09 fixture）——校验器按输入事实处理，冲突登记
   gaps kind=conflict；若平台期望口径不同，relevance 判定边界已声明（非人工金标准）。
4. `__pycache__`：gain_probe 导入 verify_check 会在运行时生成字节码缓存（平台允许
   runtime artifacts 二进制）；提交包内已清理。
