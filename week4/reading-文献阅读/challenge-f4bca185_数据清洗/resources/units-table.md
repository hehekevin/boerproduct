# 单位换算表（clean2table-r3）

原则：换算只做字面等价变换；保留原值；换算记录必须写公式与精度，并附 trace
中间值留痕（可逐步复算）；基准/分母不同不猜；区间值双端换算不取中点；
无法识别的单位进 pending_review 并逐条登记 uncertainties.dirty_values，不猜、
不编造、不静默丢弃。

## SI 数量级前缀（乘到基准单位）

| 前缀 | T | G | M | k | （无） | m | µ / μ / u | n | p | f |
|------|------|------|------|------|------|------|------|------|------|------|
| 因子 | 1e12 | 1e9 | 1e6 | 1e3 | 1 | 1e-3 | 1e-6 | 1e-9 | 1e-12 | 1e-15 |

## 常见线性换算（同基准）

| 原单位 | 目标单位 | 公式 | 因子 |
|--------|----------|------|------|
| ug/g | mg/g | 新值 = 原值 × 0.001 | 1e-3 |
| mg/g | g/g | 新值 = 原值 × 0.001 | 1e-3 |
| ug/L | mg/L | 新值 = 原值 × 0.001 | 1e-3 |
| mg/L | g/L | 新值 = 原值 × 0.001 | 1e-3 |
| ng/mL | ug/L | 新值 = 原值 × 1 | 1（1 ng/mL = 1 ug/L） |
| kPa | Pa | 新值 = 原值 × 1000 | 1e3 |
| mol/L | mmol/L | 新值 = 原值 × 1000 | 1e3 |
| mmol/L | umol/L | 新值 = 原值 × 1000 | 1e3 |

## 复合单位与文献写法

- 形如 `mg/L`、`ug/g`：分子分母各自带前缀；分子分母基准须一致才换算。
- 文献等价写法（引擎已归一）：`ug g-1`、`µg·g-1`、`ug/g` 均按 `ug/g` 处理；`mg kg-1` = `mg/kg`。
- 分母不同（mg/L vs mg/kg）或基准不同（g vs mol）：不猜，进 pending_review + dirty_values。
- 跨维度换算（质量 vs 摩尔需分子量）：不猜，进 pending_review/dirty_values 或由规则显式给 `factor`。

## 区间、精度与仿射换算

- 区间 `3.1–4.4 mg/L`：双端分别换算，保留区间形式，不取中点、不拆成两行；
  trace 形如 `{"interval": true, "ends": [前端 trace, 后端 trace], "value_out": "…–…"}`。
- 精度：按规则 `action.precision` 四舍五入；换算记录必须同时含 `formula`、`precision` 与 `trace`。
- 仿射换算（温标）：`新值 = 原值 × factor + offset`（规则给 factor+offset）。
  例：°C→K 用 factor=1, offset=273.15；未给 offset 的规则只做线性换算。

## trace 中间值留痕（r3 核心，换算可复算）

每条 convert 变更的 `trace` 字段逐项记录换算全过程：

| 字段 | 含义 | 示例（250 ug/g → mg/g） |
|------|------|------|
| factor_source | 因子来源：si_prefix（前缀表）/ rule（规则给定）/ identity（同单位） | `si_prefix` |
| src_prefix / src_prefix_factor | 源前缀及其因子 | `u` / `1e-06` |
| dst_prefix / dst_prefix_factor | 目标前缀及其因子 | `m` / `0.001` |
| src_base / dst_base / src_denom / dst_denom | 两侧基准与分母（一致性检查留痕） | `g` / `g` / `g` / `g` |
| net_factor | 净因子 = src_factor / dst_factor | `0.001` |
| offset | 仿射偏移（默认 0） | `0` |
| value_in / value_out | 换算前数值 / 换算后（四舍五入前）数值 | `250` / `0.25` |
| precision / value_final | 精度位 / 精度化后最终值 | `4` / `0.25` |
| recompute | 一行复算公式串 | `250 x (1e-06/0.001) +0 = 0.25` |

复核方法：`value_final == round(value_in × net_factor + offset, precision)`；
`net_factor == src_prefix_factor / dst_prefix_factor`（si_prefix 来源时）。
trace 同时内嵌在被改格 `__raw__[field].trace` 与 changelog 条目中，两处一致。

## 显式系数换算（规则驱动）

- `action.factor` 存在时按规则系数换算，trace 的 factor_source=`rule` 并记录 rule_factor。
- 典型用途：ppm ≈ mg/kg（水相稀溶液近似，1:1 按质量），须在 rationale 标注"近似"并进 claims 说明。
- 禁止把近似换算当精确换算写进结果而不留说明。

## 不猜边界（一律进 pending_review + uncertainties.dirty_values / human_review）

1. 未知单位串（如 `xyz`、`a.u.`、`FU`）；
2. 同名异义单位（如裸 `m`：米/毫）；
3. ppm 与 mg/L 的密度依赖换算（除非规则显式给 factor 并声明近似）；
4. 跨维度换算（质量↔摩尔、浓度↔吸附量）；
5. 字面换算后仍不相等的同指标异值——这是科学冲突，登记 conflicts，不裁决。

以上命中的脏值逐条登记 `uncertainties.dirty_values`
（row_id / field / value / reason / pending_id），原值保留在表中不静默丢弃。

## 用法（示意，非正式答案）

```bash
python scripts/clean_run.py run --case /input/case.json --rules /app/work/rules.json --outdir /app/output
```

换算细节以 `scripts/clean_run.py` 的 `convert_scalar()` 实现为准；本表与之保持一致。
