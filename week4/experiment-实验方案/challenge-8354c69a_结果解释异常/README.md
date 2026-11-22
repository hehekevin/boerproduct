# exp-result-anomaly — 实验结果异常点定位 Skill

只做**异常点定位**一个方向：脚本对读数机械做离群检测（z 分数 / 相对跳变），定位到 样本/批次/通道/孔位/时间点 维度，给出异常程度、判定阈值、与对照基线的偏离幅度。趋势拟合、原因清单、复核步骤、后续建议 4 个方向各只给一句话兜底。

## 0. 最小自检清单（本仓库实测）

```bash
# ① 落骨架（退出码 0）
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
# ② 离群机械检测（退出码 0）
python3 scripts/anomaly_detect.py --result examples/example-result.json --case examples/example-case.json --max-per-case 8
# ③ 主校验器（退出码恒 0，判据看 verdict=PASS）
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json --emit-into
# ④ 契约守卫（退出码恒 0，verdict=PASS）
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

2026-11-22 实测：四条命令退出码全部 0；verify_check verdict=PASS（0 问题）；schema_guard PASS；anomaly_detect 检出 3 个异常（1 outlier + 2 jump），全部定位到索引并给阈值与偏离幅度。

## 1. 输入格式

平台挂载后自动读取 `/input/case.json`（`case_id` + `output_contract.fields` + 数据集读数：`datasets`/`series`/`traces`/`records`/`data`/`tables`/`results`/`readings`/`curves` 键，元素含 `dataset_id`、`title`、`unit`、`dimension`、`values` 数值序列或含 `value` 字段的字典）与 `/input/task.md`。**以实际文件为准，不依据标签假设内容。**

## 2. 输出格式（/app/output/result.json）

- 顶层：`case_id` / `status`（answered·partial·insufficient_evidence·input_error）/ `result`（业务主体）/ `uncertainties` / `changelog` / `self_check` / `validator_verdict` / `gates`
- `result.thresholds`：**事前声明**的检测阈值（outlier_z=3.0 / jump_rel=0.5 / plateau_min_points=3 / plateau_tol_rel=0.05），声明后禁改
- `result.anomalies[]`：每条含 anomaly_id / dataset_id / dimension / object_ref / anomaly_type(outlier|jump) / observed_value / unit / threshold_used / severity / baseline / baseline_ref / deviation / evidence_location / possible_cause（模型一句话）
- `result.detection`：脚本回写的检测统计（thresholds_used / 检出总数 / 上报数 / per_dataset 统计，per_dataset 含 plateaus 背景统计）
- `result.fallbacks`：趋势/原因清单/复核/后续 4 方向各一句话兜底
- `result.gain_evidence`：`available:false`（增益层降级，预算过 50% 跳过）

## 3. 核心设计（异常检测怎么做）

1. **阈值事前声明**：`thresholds` 在检测前写定（z>3.0、相对跳变>50%），声明后禁止调整，脚本只按声明阈值机械执行。
2. **脚本机械检测**：`anomaly_detect.py` 对每组数值序列计算样本均值/sd，检出 |z|>3 的离群点（对照基线用**中位数**避免离群点污染）与相邻相对变化 >50% 的跳变点；平台段（plateau）只进背景统计，**不作为异常**（避免把正常平台期当异常）。
3. **维度定位**：值点若带 sample/batch/channel/well/time 等维度键，用该键值定位；否则退回 dataset 的 dimension + 数组索引。
4. **模型只配一句话**：仅给命中的异常填 `possible_cause`（一句话可能原因），不排序、不断因果。
5. **封顶**：每案例至多上报 8 个异常（--max-per-case）。

## 4. 判定阈值（默认口径）

| 阈值 | 默认 | 含义 |
|------|------|------|
| outlier_z | 3.0 | \|z\|>3.0 判离群（z 用样本 sd，对照基线用中位数） |
| jump_rel | 0.5 | 相邻读数相对变化 >50% 判跳变 |
| plateau_min_points | 3 | 连续 ≥3 点记平台段（仅背景统计，不报异常） |
| plateau_tol_rel | 0.05 | 段内相邻相对变化 ≤5% |

## 5. 调用方式（Agent 执行流）

Step 0 落骨架 → Step 1 声明阈值 → Step 2 脚本机械检测 → Step 3 模型配一句话原因 → Step 4 自检（看 verdict 不看退出码）。全部命令见 SKILL.md「五步流程」。

## 6. 依赖与限制

- 零外部依赖：仅 Python 标准库，命令一律 `python3`，不装 pip 包。
- 资源：4 脚本 + 2 示例 + README + worklog + SKILL.md，共 9 个 UTF-8 文本文件（限额 50 个/2MB 内），总体积约 84KB。
- 阈值是事前声明的保守默认，不冒充 Grubbs/ISO 等外部标准；z 分数小样本偏保守，可能漏报边缘离群。
- 只做异常定位，不做趋势拟合检验、原因排序、可执行复核清单与后续实验设计；这些方向仅给一句话兜底。
- 数值用正则/\d提取，不使用 .isalpha() 判汉字。

## 7. 边界（诚实声明）

- 异常检测 100% 由脚本机械完成，模型不逐点人工判读；possible_cause 仅一句话，未定因果。
- 平台段不作为异常上报，只有 outlier 与 jump 进 anomalies。
- 增益层降级（available:false），不声称有正常 vs 退化对照数字。