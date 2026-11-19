# multi-step-analysis-chain — 多步骤数据分析 Agent Skill（analysis 赛道）

把一句分析需求编排成**可复核的多步骤执行链**：先声明依赖无环的步骤图，再逐步执行留痕、中间产物双闸校验（schema + 数值复算）、失败步骤降级登记，最终结论的每个数字与引文都能回到步骤产物或原始数据。

> **示例声明**：`examples/` 内的数据、数字与结论均为合成示意，用于演示接口与自测链路，**非正式案例、非正式答案**。

## 1. 用途
科研数据分析场景（UCI Concrete / Iris / Wine 类固定快照与 SQLite）：清洗、分组统计、图表选型、报告生成的多步编排，输出可复核、可回放、可重跑的结构化结果。

## 2. 适用条件 / 不适用情况
- 适用：输入为 `/input/case.json`（数据表 + 数据字典 + output_contract）+ `task.md`；需求可拆成「导入→清洗→统计→可视化→报告」链路。
- 不适用：数据库检索、联网取数、需要 pip 第三方库的建模；图形渲染受环境限制时降级为 figure_spec 数据规格并登记，不冒充已出图。

## 3. 调用方式
Agent 挂载后按 SKILL.md 七步流程线性推进（Step 0 骨架 → Step 1 步骤图声明 → Step 2 逐步执行留痕 → Step 3 留痕审计 → Step 4 降级登记 → Step 5 增益对照 → Step 6 自检交付）。所有脚本 `python3` 运行、零外部依赖。

## 4. 输入 / 输出
- 输入：`/input/case.json`、`/input/task.md`（以实际文件为准，不依据标签假设内容）。
- 输出：`/app/output/result.json`（含 `case_id` 与 output_contract 全字段）；中间台账在 `/app/work`。
- 失败路径：所有脚本退出码恒为 0，结论照实写进 JSON 的 `verdict` / `validator_verdict` / `status`（语义值返回，不用退出码）。

## 5. 方法说明（关键机制）
| 机制 | 实现 | 机检对应 |
|------|------|----------|
| 步骤图完备 | plan 事前声明 + Kahn 拓扑环检测（探针侧另有一套 DFS 第二实现互核） | 依赖无环 |
| 逐步留痕 | 每步 status/command/inputs/outputs/artifacts/checks，留痕顺序须合拓扑序 | 逐步留痕可回放 |
| 中间校验 | 每步至少 1 条 schema + 1 条 recompute；通过率由 verify_check 独立复算 | 中间校验通过率 |
| 失败降级 | failed/degraded→fallbacks，skipped→pending_review，不静默 | 异常处置 |
| 结论-证据对齐 | claims 引文逐字回证 + 正文数字回证到步骤产物/原始数据 | 结论-证据对齐 |
| 增益对照 | --ablate 双跑 + 污染反例注入副本，真实数字写入 gain_evidence | 增益可验证性 |

## 6. 字段字典（result.json 核心）
- `result.plan`：步骤图（step_id/name/depends_on/inputs/outputs/checkpoint + declared_at，声明后禁改）
- `result.steps[]`：逐步留痕（status ∈ done|failed|degraded|skipped）
- `result.fallbacks[]` / `result.pending_review[]`：失败降级 / 跳过登记
- `result.middle_checks`：中间校验通过率（verify_check.py 复算回填）
- `result.dag` / `result.trace_audit`：无环结论与留痕审计（pipeline_run.py 专属）
- `result.gain_evidence` / `result.efficiency`：增益证据与效率计数（gain_probe.py 专属）
- `claims[]`：结论证据链（kind=grounded|inferred，quote 逐字回证）
- 完整 schema 见 SKILL.md「输出 schema」节。

## 7. 环境依赖
Python 3.8+，仅标准库（json/os/re/argparse/copy/time/math/sys）。无 pip 安装、无网络、无 symlinks。包体 ≤50 个 UTF-8 文本文件。

## 8. 文件清单
```
SKILL.md                     # 技能主文档（≤150 行）
README.md                    # 本文件
worklog.md                   # 开发对照记录（真实数字）
scripts/build_skeleton.py    # Step 0 骨架与步骤图模板
scripts/pipeline_run.py      # Step 3 留痕审计与无环复核
scripts/verify_check.py      # Step 6 中间校验复算 + 结论-证据对齐
scripts/schema_guard.py      # Step 6 结构守卫与键归属纪律
scripts/gain_probe.py        # Step 5 消融双跑 + 污染反例
examples/example-case.json   # 合成示例输入（示意）
examples/example-result.json # 合成示例示意输出（示意）
```

## 9. 最小调用示例（本地自测，全部实测退出码 0）
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/out/result.json --work-dir /tmp/wk
python3 scripts/pipeline_run.py --result examples/example-result.json --plan /tmp/wk/analysis_plan.json --out /tmp/wk/pipeline_run.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --plan /tmp/wk/analysis_plan.json --out /tmp/wk/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/wk/sg.json
```

## 10. 异常处理与自查方法
- 空表/列缺失/编码错误 → material_gaps 登记 + 步骤 skipped/pending_review，verdict 如实降级。
- 校验 FAIL → 按 `problems` 组标签逐条修复后重跑；「没跑 ≠ 通过」，闸门非 enforced 会 warn。
- 自查三问：每步有可回放留痕吗？通过率是复算的吗？每个数字有回证吗？
- 逐条硬约束自检清单（2026-11-19 实测，见 worklog.md）：

| # | 自检项 | 命令 | 实测结果 |
|---|--------|------|----------|
| 1 | SKILL.md ≤150 行 | `wc -l SKILL.md` | 140 行 ✓ |
| 2 | 脚本数 ≤8 | `ls scripts/*.py \| wc -l` | 5 ✓ |
| 3 | 文件数 ≤50 | `find . -type f \| wc -l` | 10 ✓ |
| 4 | 包体积 <2MB | `du -sh .` | 约 0.12MB ✓ |
| 5 | 零外部依赖 | 头部 import 仅标准库 | ✓ |
| 6 | 五脚本全链路 exit 0 | 第 9 节五条命令 | 全部 0 ✓ |
| 7 | 全链路 verdict 全 PASS | 第 9 节输出 | pipeline/verify/guard=PASS ✓ |
| 8 | 污染双跑 FAIL 差 | gain_probe --inject-pollution | normal FAIL(14)/degraded PASS(0) ✓ |
| 9 | 消融双跑真实差 | gain_probe --emit-into | steps_count delta=5 ✓ |
| 10 | 不预置正式答案 | examples 标注示意 | ✓ |

## 11. 维护与边界
- 退化模式（--ablate）结果仅用于增益对照，不得当交付自检结论；平台白板对照由平台生成。
- 键归属矩阵（dag/trace_audit→pipeline_run，middle_checks/self_check/…→verify_check，gain_evidence/efficiency→gain_probe）由 schema_guard 机械检查，多脚本禁写同一键。
- step_id 校验用显式 ASCII 白名单而非 str.isalpha（该函数对汉字返回 True，会把「步骤一」误判为合法标识符）。
- 版本：analysis-plan-v1 / probe 1.0（2026-11-19）。
