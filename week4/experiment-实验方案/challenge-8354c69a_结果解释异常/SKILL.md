---
name: exp-result-anomaly
description: Experimental-result anomaly localization skill. The ONLY focus is mechanically localizing anomalies (outliers / relative jumps / plateaus) from raw numeric readings with pre-declared thresholds (z>3 or relative jump>50%), binding each anomaly to a concrete dimension (sample/batch/channel/well/time point) with observed value, threshold used, baseline and deviation magnitude, then the model attaches at most ONE sentence of possible cause per hit. Trend fitting / cause ranking / recheck checklist / follow-up suggestion are out of scope and each gets only a one-line fallback. Detection is done 100% by script (anomaly_detect.py, stdlib only); the model never hand-judges points one by one. Use when the task asks to interpret experimental results into anomalies bound to objects with threshold and deviation.
---

## 强制执行协议（最高优先级）
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py` 写 /app/output/result.json 骨架；此后任何时刻 result.json 必须存在且 JSON 可解析。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（thresholds / anomalies / detection / run_status / verdict）；无法产出时保留键填 unknown 或空数组，原因写 uncertainties，不得删键、不得编造。
3. **异常检测由脚本机械完成**：只准调用 `anomaly_detect.py` 产出 anomalies；阈值必须事前声明（thresholds：outlier_z=3.0 / jump_rel=0.5 / plateau_min_points=3 / plateau_tol_rel=0.05）且声明后禁改。模型**只给命中的异常点配 possible_cause 一句话**，不逐点人工判读、不新增/删减异常点。
4. **自检只判 verdict**：所有脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems`。FAIL 就逐条修复后覆盖写再重跑。
5. **失败也要交付**：中断/失败仍写 result.json（status=partial，写明中断位置），绝不让 /app/output 缺 result.json。

## 定位与约定
只做**异常点定位**一个方向：脚本对读数做离群检测（z 分数 / 相对跳变 / 平台段），定位到 样本/批次/通道/孔位/时间点 维度，给出异常程度、判定阈值、与对照基线的偏离幅度。这是最机械、最可复算的方向。
趋势拟合、原因清单、复核步骤、后续建议 4 个方向砍掉（各只在输出里给一句话兜底，见 schema 的 fallbacks）。
- 输入：`/input/case.json`（数据集读数 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区 `/app/work`；产物 `/app/output/result.json`。预算 64 次模型请求 / 900 秒；只用标准库，不装 pip 依赖。
- 按 Step 0–4 线性推进，禁止分支回环。脚本定位以 `/app/work/skill_marker.json` 标志文件为准。

## 五步流程

### Step 0 — 落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动提取 output_contract 全字段与数据集序列清单 → 写骨架 + 落 skill_marker.json。失败则手工兜底抄字段名写骨架。

### Step 1 — 事前声明阈值（1 次响应，检测前完成）
填 `result.thresholds`（缺省内置：outlier_z=3.0 / jump_rel=0.5 / plateau_min_points=3 / plateau_tol_rel=0.05）。**声明后禁止调整**。不逐点人工判读——这是脚本的活。

### Step 2 — 脚本机械检测（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/anomaly_detect.py --result /app/output/result.json \
  --case /input/case.json --max-per-case 8
```
脚本回写 `result.anomalies[]`（每条：anomaly_id + dataset_id + dimension + object_ref + anomaly_type + observed_value + unit + threshold_used + severity + baseline + baseline_ref + deviation + evidence_location + possible_cause=null）与 `result.detection`（thresholds_used + 检出总数 + 上报数 + per_dataset 统计）。anomalies 每案例 3–8 个封顶。读数不可得 ⇒ detection 记 unavailable + material_gaps 登记。

### Step 3 — 模型配一句话原因（1 次响应）
仅对每个命中的 anomaly 填 `possible_cause`（一句话可能原因，如"同一读数 90.1 偏高，疑与该读数对应设备的装夹变更同期相关"），**不排序、不算证据强度、不断因果**。趋势/原因清单/复核/后续各填一句兜底到 `result.fallbacks`，不展开。

### Step 4 — 自检与交付（2 次脚本调用，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
FAIL 则按 problems 逐条修复 → 覆盖写 → 重跑直到 PASS（或如实登记）。填 `run_status.state`（success/partial/unable_to_determine/refused）与 `verdict`（audited 全部检出并回证；partially_audited 部分；cannot_verify 材料缺口且 material_gaps 非空）。**增益层降级：预算 50% 已过即跳过，gain_evidence={available:false}。**

## 输出 schema（result.json）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "contract_fields": [], "dataset_ids": [], "input_files": [],
    "thresholds": {"outlier_z": 3.0, "jump_rel": 0.5, "plateau_min_points": 3, "plateau_tol_rel": 0.05},
    "anomalies": [{"anomaly_id": "AN-01", "dataset_id": "ds-01", "dimension": "时间点|样本|批次|通道|孔位",
      "object_ref": "index=5 或 batch=B2 channel=3 ...", "anomaly_type": "outlier|jump|plateau",
      "observed_value": 90.1, "unit": "MPa", "threshold_used": "outlier_z=3.0",
      "severity": "z=3.16", "baseline": {"value": 50.8, "reference": "全序列均值"},
      "baseline_ref": "全序列均值", "deviation": "+77.4%", "evidence_location": "datasets[ds-01][5]",
      "possible_cause": "一句话可能原因（Step 3 模型配）"}],
    "detection": {"computed_by": "scripts/anomaly_detect.py", "thresholds_used": {},
      "datasets_scanned": 0, "anomalies_detected_total": 0, "anomalies_reported": 0, "per_dataset": []},
    "fallbacks": {"trend": "一句话", "cause_list": "一句话", "recheck": "一句话", "followup": "一句话"},
    "gain_evidence": {"available": false, "reason": "预算过50%降级"},
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | cannot_verify", "verdict_basis": "一句话"
  },
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [], "validator_verdict": "PASS|FAIL", "gates": []
}
```

## 校验器会抓的错（verify_check.py）
1. [enum] anomaly_type / run_status.state 枚举非法。
2. [anomaly] 任一 anomaly 缺 dimension / object_ref / threshold_used / deviation / observed_value（未定位到对象或未给阈值与偏离幅度）。
3. [detection] detection.anomalies_reported 与 anomalies 实际长度不符。
4. [contract] 缺 case_id / 顶层字段 / 业务字段 / output_contract 字段。
5. [structure] run_status 非 success 缺 reason；verdict=audited 但 anomalies 为空；verdict=cannot_verify 但 material_gaps 为空。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，数据虚构）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/anomaly_detect.py --result examples/example-result.json --case examples/example-case.json --max-per-case 8
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 异常处置
| 场景 | 处置 |
|------|------|
| 原始读数不可得 / 字段非数值 | anomaly_detect 记 unavailable + material_gaps 登记，绝不臆造复算值 |
| 单位不一致 / 读数饱和 | material_gaps + uncertainties 登记，不编偏离幅度 |
| 对照缺失 | deviation 写"无对照可比"，登记 uncertainties |
| 预算过半 | 跳过增益层，gain_evidence.available=false，status 如实填 partial |
| 校验报 FAIL | 按 problems 逐条修复；修不了如实登记，绝不中断交付 |
| 运行中断 | 按协议第 5 条写 result.json，status=partial |

## 已知限制
- 阈值（outlier_z=3.0 / jump_rel=0.5 / plateau_tol_rel=0.05）是事前声明并机械执行的保守默认，不冒充 Grubbs/ISO 等外部标准；z 分数对小样本偏保守，可能漏报边缘离群。
- z 分数要求 n≥2 且 sd>0；小样本或常量序列自动跳过离群检测，如实登记。
- 只做异常定位，不做趋势拟合检验、原因排序、可执行复核清单与后续实验设计；这些方向仅给一句话兜底。
- 数值用正则/\d提取，不使用 .isalpha() 判汉字。