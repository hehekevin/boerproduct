# cite-trace — 引文前向/后向追踪 Skill（v2）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「引文追踪与关联文献发现」
(challenge-60a8202d) 的参赛 Skill。锁定子场景：**只做种子论文的前向/后向追踪**——
沿参考文献找方法与数据出处（后向），沿施引文献找改进与批评（前向），处理层级
扩展与停止判断。砍掉关联文献发现、引用网络、路径解释、去重合并四个方向。

## 1. 用途与适用条件

给定种子论文与引文材料，完成：

1. **种子定位**：seed 逐字来自 case.json，source_ref 写定位来源。
2. **前后向追踪**：`trace_results[]` 每条含方向（backward/forward）、层级（layer）、
   关系（relation：method_origin/dataset_origin/prior_work/improvement/critique/
   application/other）、关联依据一句话（related_basis）、来源定位（source_ref）。
3. **停止判断**：只做 1–2 层，每层按相关性选最重要的 3–5 篇（≤5），到第 2 层或
   每层满 5 篇即停止（per_layer_cap=5）。
4. **显式登记**：无前向记录、缺 DOI、元数据缺失进 material_gaps / pending_reason，
   不补造文献。

**不适用**：不调外部引文接口、不抓数据（stdlib-only）；不做关联发现/引用网络/
路径解释/去重合并。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 综述作者 | 从种子顺藤摸瓜：方法/数据出处（后向）+ 改进与批评（前向） | 双向边表，每条可回指 source_ref |
| 系统复现者 | 找某方法真正来源 | backward 边按 relation 标 method_origin/dataset_origin |
| 评审/复核者 | 确认扩展文献来路 | 每条边的方向+层级+关联依据一句话 |

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | 3.8+（只用标准库） |
| 第三方依赖 | 零（json/os/sys/argparse） |
| 操作系统 | Linux / macOS / Windows 均可（路径全 argparse 参数化） |
| 资源上限 | ≤50 文本文件、单文件 ≤500KB、总计 ≤2MB |

## 4. 安装与运行

把 `submission/` 挂到 `/skills/weekly-skill`，无需安装。

```bash
# Step 0：自动落骨架（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 4：自检（退出码恒 0；判据是报告 verdict PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（种子 + 引文材料 + output_contract）+ `task.md`。
- **输出**：`/app/output/result.json`，顶层 case_id/status/result/claims/
  uncertainties/changelog + 自检四键（self_check/validator_verdict 等）。
- **result 内**：material_gaps、environment、seed、trace_results、trace_summary、
  run_status、verdict、verdict_basis、gain_evidence、efficiency。
- **status**：answered | partial | insufficient_evidence | input_error。
- **verdict**：traced | partial_trace | insufficient_records | unverifiable。

## 6. 最小调用示例（示意，非正式答案）

```json
{
  "case_id": "demo-cite-002",
  "result": {
    "trace_results": [
      {"trace_id": "t1", "direction": "backward", "layer": 1, "relation": "method_origin",
       "related_basis": "种子 S0 以此为方法出处（后向第1层）", "source_ref": "records.references[0]"},
      {"trace_id": "t4", "direction": "forward", "layer": 1, "relation": "improvement",
       "related_basis": "F1 改进种子（前向第1层）", "source_ref": "records.citing[0]"}
    ],
    "trace_summary": {"backward_count": 1, "forward_count": 1, "per_layer_cap": 5},
    "verdict": "traced"
  }
}
```

本地自测：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 7. 验收标准

| 编号 | 验收项 | 判定 |
|------|--------|------|
| A1 | 契约字段齐 | schema_guard verdict=PASS |
| A2 | 业务逻辑齐 | verify_check verdict=PASS 且 problems 空 |
| A3 | 计数一致 | trace_summary count/layers 与 trace_results 实况一致 |
| A4 | 闸门诚实 | gates state ∈ 四态枚举 |
| A5 | 边边可回指 | 每条 source_ref 非空 |

## 8. 异常处理

| 异常 | 处置 |
|------|------|
| 无前向引用记录 | forward 留空 + seed_forward_available=false + material_gaps 登记，verdict=partial_trace |
| 种子未明示 | 按题面定位并登记依据，不猜；失败 status=insufficient_evidence |
| 缺 DOI / 元数据冲突 | pending=true + pending_reason，不补造 |
| 算力/时间不足 | 按 stop_rule 收尾，verdict=partial_trace |
| 校验 FAIL | 按 problems 修复后覆盖写再重跑；修不了登记 uncertainties |
| 运行中断 | 仍写 result.json（status=partial） |
| 校验脚本失败 | 退出码恒 0，结论记在报告 verdict |

## 9. 已知限制

- 仅追踪输入材料内引用关系；材料没给的边登记缺口，不联网补。
- 只做前后向追踪，不输出关联发现/网络/路径/去重。
- 增益对照仅在预算 <50% 时以 verify_check 正常/退化双跑量化；≥50% 时 available=false。

## 10. 资源清单

| 文件 | 作用 |
|------|------|
| SKILL.md | 技能本体（4 条铁纪律 + 五步流程 + schema + 异常表） |
| scripts/build_skeleton.py | Step 0 自动落骨架 + 标志文件（三级容错） |
| scripts/verify_check.py | 业务校验器（方向/层级/依据/回指/计数/枚举） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 |
| examples/example-case.json | 合成输入示例 |
| examples/example-result.json | 示意输出（非正式答案） |
| README.md | 本说明 |
| worklog.md | 开发记录与对照数字 |

## 11. 版本与维护

版本 v2（2026-11-22）。依赖 Python 3.8+ 标准库，零第三方依赖。

- 改动 scripts/*.py 后重跑第 6 节自测命令，确认 verdict=PASS 且 exit 0。
- 改动 SKILL.md 后检查 `wc -l SKILL.md` ≤ 150。
- 键所有权：self_check/unbacked_numbers/gates/validator_verdict 归 verify_check 独写；
  gain_evidence/efficiency 由 Agent 主流程写；其余键只在 Agent 主流程更新。
- 不预置正式案例答案：examples 全合成并标注"示意"。