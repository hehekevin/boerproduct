# cite-trace — 引文追踪与关联文献发现 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「引文追踪与关联文献发现」(challenge-60a8202d)
的参赛 Skill。锁定子场景：**种子出发的双向引文追踪 + 有据关联 + 身份合并**。

## 1. 用途与适用条件

给定种子文献与引文材料（引用记录、参考文献表、被引列表），完成六件事：

1. **种子定位与节点登记**：种子逐字来自 case.json；每个文献登记进 `nodes[]`
   （node_id 全局唯一，roles 标注 seed/backward/forward/related/orphan）。
2. **双向追踪**：`traces.backward`（种子引用了谁——方法/数据出处）、
   `traces.forward`（谁引用了种子——改进/批评/应用），逐条 edge 带
   `source_ref`（输入文件具体位置，可回指）、`relation` 语境、`layer` 层数；
   多层扩展按事前声明的剪枝规则截断。
3. **关联发现**：`related[]` 平行工作，signals ∈ co_citation/bib_coupling/
   author/dataset/task/topic，每条给 reason + confidence + confidence_basis；
   **high 置信必须有可回指证据**（高被引≠高相关）。
4. **引用网络与路径**：foundational/bridge/recent_hot 角色节点、引用环、
   孤立节点显式登记；`paths[]` 逐跳引用已登记的 edge_id，区分直接/间接可达。
5. **去重与身份合并**：`merges[]` 合并预印本/会议版/期刊版/增补版，
   keys 声明判定键、evidence 保留合并证据；键冲突不合并只登记 pending。
6. **显式登记**：待复核条目进 `pending_review[]`（item_id/kind/reason/
   what_to_check）；空方向、缺元数据、撤稿类缺口进 material_gaps，不补造。

**核心保证**：每条引用边可回指 source_ref；节点标题/年份在 claims quote 中
逐字回证（norm_title 口径，CJK 原样保留，不踩 isalpha 汉字陷阱）；覆盖计数
与列表长度一致（机器复算）；verify_check 把每条检查的三元组
`{item, template_value, applied, match}`、闸门状态与 unbacked 清单回写进
result.json（键 `self_check` / `gates` / `unbacked_numbers` /
`validator_verdict`），评分器不开附件即可核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 综述作者 | 从种子论文顺藤摸瓜：方法出处（后向）+ 后续改进与批评（前向）+ 平行工作 | 双向边表（逐条可回指）、关联清单（带理由与置信度）、去重后的干净清单 |
| 系统复现者 | 找某方法的真正来源与数据集出处 | backward 边按 relation 标注 method_origin/dataset_origin |
| 引文数据清洗 | 预印本/会议版/期刊版散落多库 | merges 合并表（keys + evidence）+ 同名不同文冲突登记 |
| 教学 / 培训 | 演示"事前声明规则 + 机械复核"的追踪纪律 | declared_rules 台账 + 可复算的对照实验（gain_evidence） |

**不适用**：不调外部引文接口、不抓未经授权数据、不装 pip 依赖；材料没给的
引用边登记缺口而非联网补；不能替代全文阅读与引文内容理解。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 与 3.12 上实测通过），只用标准库 |
| 第三方依赖 | **零**（json / os / re / sys / argparse / copy / time / math） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 材料清单 + 规则声明模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```

## 5. 输入与输出

- **输入**：`/input/case.json`（种子 + 引文材料 + output_contract）+ `task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`seed`、`nodes`、`traces`
    （backward/forward 边表）、`related`、`clusters`、`network`、`paths`、
    `merges`、`declared_rules`、`tracking_coverage`、`pending_review`、
    `steps`、`run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **边表字段**：edge_id / direction / from_id / to_id / layer / relation /
  context_clue / source_ref / pending / pending_reason（他人可直接复用该结构）。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/declared_rules.json`（规则声明台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例：种子 S0 + 12 节点 + 8 条边（后向 3 / 前向 5）+ 2 组
合并（预印本、扩展版）+ 1 个引用环 + 1 个孤立节点 + 1 条缺 DOI 待复核边。
示意输出关键片段：

```json
{
  "case_id": "demo-cite-001", "status": "answered",
  "result": {
    "traces": {"backward": [{"edge_id": "be1", "from_id": "S0", "to_id": "B1",
               "relation": "method_origin", "source_ref": "records.references[0]"}],
               "forward": [{"edge_id": "fe1", "from_id": "F1", "to_id": "S0",
               "relation": "improvement", "source_ref": "records.citing[0]"}]},
    "related": [{"node_id": "P1", "signals": ["bib_coupling"], "confidence": "high",
                  "reason": "P1 与种子共享参考文献 B1（文献耦合）"}],
    "merges": [{"kept_id": "S0", "merged_ids": ["S0x"], "evidence": ["预印本标题主体+作者一致"]}],
    "tracking_coverage": {"backward_edges": 3, "forward_edges": 5},
    "verdict": "complete"
  },
  "claims": [{"claim_id": "k03", "kind": "reported", "evidence":
               [{"quote": "Memory-Augmented Key-Value Networks. 2019."}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题 19 个业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字与标题全回证 | `unbacked_numbers` 与 unbacked_titles 均为空 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 双向覆盖 | 两方向边数 >0 或空方向已登记原因；coverage 计数与列表长度一致 |
| A6 | 规则事前 | `declared_rules` ≥4 条且每条有 threshold/basis/declared_at |
| A7 | 边边可回指 | 每条边 source_ref 非空；端点全部登记在 nodes |
| A8 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 + 失效条件 |
| A9 | 效率可复算 | `efficiency` 含自动采集计数与 `reproduce` 命令；`model_requests` 缺失时为 null |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查（--ablate） |
|------|-----------|-----------|
| `normal` | 全部（方向覆盖 + 理由回证 + 去重 + 待复核） | — |
| `degraded` | 枚举/结构/规则声明/运行状态等基础检查 | `reasons`（关联理由+逐字回证）/ `dedup`（合并证据+键冲突）/ `direction`（方向覆盖+悬空端点/跳）/ `all` |

逐项对照五项指标（全部实测，不臆造）：
`backed_edge_ratio`（来源可回指边占比）、`violations_missed`（客观违规漏检数，
真值由探针独立复算）、`manual_review_items`（需人工复核条目数）、
`steps_count`（步骤数）、`clarification_rounds`（追问轮次，公式
`ceil(manual_review_items/3)` 随记录落盘）。

每项指标都写明**机制 → 指标映射**（`mechanism_to_metric_map`）、**边界**
（`boundaries`）与**失效条件**（`failure_conditions`）。污染反例自测在副本上
注入 5 类污染（清空 source_ref / 虚增覆盖计数 / 清空合并证据 / 清空关联理由 /
清空 claims），正常模式必须全部抓到。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 数据源无前向引用记录 | forward 留空 + seed_forward_available=false + material_gaps 登记，verdict=partial_coverage |
| 种子未在材料中明示 | 按题面定位并登记依据，不猜；定位失败 status=insufficient_evidence |
| 同名不同文 / 同文不同名 | 去重键冲突不合并：登记 conflicts 或走 merges 留证据 |
| 缺 DOI / 元数据冲突 | 边 pending=true + pending_reason，进 pending_review 给 what_to_check |
| 算力/时间不足 | 按 pruning_stop 收尾，verdict=partial_coverage，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| 运行中断 | 仍写 result.json（status=partial），注明中断点与已完成部分 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器
自身故障打断。SKILL.md 协议第 7 条明确"自检只判 verdict"。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"，
作为增益证据。SKILL.md 明确：退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：`gain_evidence` 里的数字是真实的吗？**
是。两遍都由 `verify_check.analyze()` 在同一份输入上实跑产出；
`violations_missed` 的真值由探针独立复算（与校验层分开实现）。污染反例只在
副本上注入，原 result.json 不被改动。

**Q：为什么标题回证不用 isalpha 判断语言？**
汉字对 `str.isalpha()` 返回 True，任何"字母词过滤"式启发式都会把中文标题
剥空。本包统一用 `norm_title`：显式字符替换 + 去空白标点 + 小写，CJK 原样保留，
并有单测断言中文标题归一化后无损。

**Q：高置信关联为什么必须带证据边？**
题面要求"每条关联给出理由与置信度"，且"高被引不等于高相关"。机器可复核的
做法是：high 置信必须指到具体 edge_ids 或 source_ref，否则降级或登记待复核。

**Q：没有前向引用记录的种子怎么办？**
新预印本常见此情况。forward 留空 + `seed_forward_available=false` +
material_gaps 登记，校验器要求空方向必须登记原因——不冒充覆盖，也不补造。

**Q：同一篇论文的多个版本怎么算"合并成功"？**
`merges[].keys` 声明判定键（doi 优先），`evidence` 至少一条可回指证据
（标题主体一致 + 作者一致 / DOI 版本对 / 发布形态递进）。键冲突时不合并、
只登记 pending——宁可少合并，不可错合并。

## 11. 适用范围与限制

- 仅追踪输入材料内的引用关系：不调外部引文接口、不抓未经授权数据（stdlib-only）。
- 关联发现受材料覆盖度限制：共被引/耦合信号只能在已有引用图上计算。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次是按约定批量（每轮 3 条）折算的估计量；原始计数 manual_review_items 一并落盘，可换批量重算。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null，不得臆造。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘、不读环境），可直接 `import`；`ablate` 参数可复用为别处的"机制开关"对照实验 |
| `scripts/gain_probe.py` 的双模式对照 | 换掉 `analyze` 即可测任何校验器的机制增益；指标公式全部写在 `mechanism_to_metric_map` 里 |
| `traces` 边表结构 | `{edge_id, direction, from_id, to_id, layer, relation, source_ref, pending}` 适合任何"逐条可回指"型边表交付 |
| `merges` 合并台账格式 | `{kept_id, merged_ids, keys, evidence, conflict}` 是通用的身份合并台账 |
| `declared_rules` 台账格式 | `{rule, threshold, basis, declared_at}` 是通用的"事前声明"台账 |
| `norm_title()` 归一化 | 自带 CJK 保护的标题归一化，任何中英混排场景可直接抄 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改字段即得新的负例 |

**建议的复用顺序**：先抄 `verify_check.py` 的 `analyze()` 骨架（拿到三元组 +
闸门 + 回证），再抄 `gain_probe.py` 的双模式对照（拿到可验证的增益证据），
最后按自己的业务 schema 改 `RESULT_REQUIRED` 列表。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明 + 异常表） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 自动落骨架/材料清单/规则声明模板（三级容错，退出码恒 0） | 是 |
| scripts/verify_check.py | 业务逻辑校验器（四组机检/回证/闸门/三元组，含 `analyze()` API） | 是 |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例自测 | 是（含指标公式） |
| examples/example-case.json | 合成输入示例（种子 + 引文材料） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明（用途/依赖/安装/输入输出/验收/FAQ/限制/异常/复用/维护） | — |
| worklog.md | 开发记录、真实对照数字与负例证据 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第四节四条自测命令 + 污染反例 + 十类负例，确认 verdict=PASS、负例全被抓。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED` 与 SKILL.md 的 schema 段。
- 键所有权：`self_check`/`unbacked_numbers`/`gates`/`validator_verdict` 归 verify_check 独写；`gain_evidence`/`efficiency` 归 gain_probe 独写；其余键只在 Agent 主流程更新——多脚本禁写同一键。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。

## 15. 最小自检清单（发布前逐条实测，全部 exit 0）

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk   # exit 0，骨架落盘
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json          # exit 0，verdict=PASS
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json                             # exit 0，verdict=PASS
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution   # exit 0，caught_by_normal_mode=true
python3 -c "import ast;[ast.parse(open(f'scripts/{s}',encoding='utf-8').read()) for s in ('build_skeleton.py','verify_check.py','schema_guard.py','gain_probe.py')];print('syntax OK')"   # exit 0
```

实测记录（2026-11-19，真实数字见 worklog.md）：
`verify_check PASS（135 项检查，unbacked=0）`；
`schema_guard PASS`；
`gain_probe 正常/退化双跑 + 污染 caught_by_normal_mode=True（normal 抓 7 problems/13 unbacked，退化漏检 3）`；
十类负例全部 FAIL 被抓；所有命令 exit 0。
