# cite-support-check — 引用支持判定 Skill（极简单点 v2）

针对 Bohrium 产品赛第 4 期「学术审查」赛道「引用与事实核验」(challenge-cbe96f01)
的参赛 Skill。锁定**单一方向**：**引用支持判定**——把正文中带引用标号的结论句拆
成可判定单元，逐条判定「完整支持 / 部分支持 / 不支持 / 无法判定」四档，识别
「结论超出引文范围」的过度推断。

## 1. 用途与适用条件

给定一篇固定稿件与审查要求，只做一件事：

- **引用支持判定**：只处理正文中**带引用标号的结论句**（每案例 8-12 条），逐条
  给出四档判定 + 定位到引文编号。
  - `fully_supported`（完整支持）：被引主张与本句结论一致。
  - `partially_supported`（部分支持）：只支持部分，结论有超出。
  - `unsupported`（不支持）：被引主张不支持该结论。
  - `cannot_determine`（无法判定）：读不到被引原文，无法判断——**不脑补、不冒充已核对**。
- **识别过度推断**：结论超出引文范围（over_inference=true），是"引用存在 ≠ 引用支持"的核心。

**明确不做**：事实来源可靠性分级、数值统计一致性、论证链完整性、学术规范核查、
外部文献检索、查重、润色改写。这些方向一律不展开。

## 2. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | 3.8+，只用标准库 |
| 第三方依赖 | 零（json / os / re / sys / argparse） |
| 资源上限 | 4 个脚本 + 2 个 examples，远低于 ≤50 文件 / 2MB 上限 |

## 3. 安装与运行

把 `submission/` 目录挂到 `/skills/weekly-skill`，无需安装。

```bash
# Step 0：落骨架（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1：提取带引用结论句候选（回写 result.citation_scan）
python3 /skills/weekly-skill/scripts/citation_scan.py --result /app/output/result.json \
  --case /input/case.json --emit-into
# 然后 Agent 按候选逐条判定，写入 result.citation_checks

# Step 2：双自检（退出码恒 0，判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 4. 输入与输出

- **输入**：`/input/case.json`（稿件 + 要求 + output_contract）、`task.md`。以实际文件为准。
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `validator_verdict` / `gates`
  - `result` 内：`material_gaps`、`environment`、`manuscript_overview`、`citation_scan`、
    `citation_checks[]`（逐条：quote / claim / cite_markers / support_state /
    over_inference / source_accessible / reason / revision_suggestion）、`coverage`、
    `unchecked`、`steps`、`run_status`、`verdict`、`verdict_basis`、`gain_evidence`、
    `efficiency`

## 5. 最小调用示例（示意，非正式答案）

`examples/` 提供合成案例（虚构论文）：5 章节 → 4 条判定（1 完整支持 / 2 部分支持
含过度推断 / 1 无法判定因 [4] 全文未获取）。本地自测：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/citation_scan.py --result examples/example-result.json --case examples/example-case.json --emit-into
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 6. 四条保命铁纪律

1. 第 0 步落骨架（result.json 任何时刻存在且可解析）。
2. 失败也交付（status=partial，写明中断位置）。
3. 退出码恒 0 看 verdict（自检只判报告 verdict + problems）。
4. 预算过半即定稿（模型请求 >32 或运行 >450 秒就收尾）。

## 7. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps + verdict=cannot_verify，不编造结论 |
| 被引文献全文读不到 | support_state=cannot_determine + source_accessible=false + uncertainties 登记 |
| 正文无带引用结论句 | citation_checks 空 + verdict=not_audited + reason 写明 |
| 引用标记样式异常 | citation_scan 闸门记 not_found，退化为人工分句并在 steps 注明 |
| 预算不足 | 保留已审部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 修复后重跑；修不了如实登记 uncertainties |

## 8. 已知限制

- 仅做引用支持判定单一方向，不做其他五个方向。
- 判定依据是被引文献在材料内可读的摘要/主张文本；原文不可读一律 cannot_determine。
- quote 逐字回证是"逐字命中原文"的机械下界，不替代被引主张语义核对。