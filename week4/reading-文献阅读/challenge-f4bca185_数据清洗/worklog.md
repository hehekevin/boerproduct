# worklog — clean2table-r3 重做记录（challenge-f4bca185）

## 背景

- 当前赛道聚合最高 69.00（71336: 69 / 72156: 67.67），达标线 70，只差 1 分。
- 采用**保底增强路线**：保留 69 分版 clean2table-r2 全部机制（尤其 units 单位处理、
  协议置顶、五步主流程、三级容错、规则库六类、去重条件指纹纪律），最小化改动补三件。

## 本版改动（相对 r2，全部最小化）

### 增强①：清洗台账逐条嵌入 result.json
- `apply_clean` 末尾新增行级台账索引：每行 `__changes__` = 该行全部 change_id；
- 每个被改格 `__raw__[field].ledger` 内嵌 `{change_id, kind, original, new, rule_id}`；
- `result.changelog` 全量台账照旧保留——单行自足 + 全量可查，双通道可核；
- check 新增校验：每行 `__changes__` 条数 == 该行 changelog 条数，ledger 变更号必须在 `__changes__` 内。

### 增强②：单位换算中间值留痕（可复算）
- `convert_scalar` 返回值扩为 4 元组，新增 `trace`：`factor_source`（si_prefix/rule/identity）、
  前后缀因子、基准/分母一致性留痕、`net_factor`、`offset`、`value_in`/`value_out`、
  `precision`/`value_final`、`recompute` 一行复算公式串；
- 区间值换算 trace 形如 `{"interval": true, "ends": [前端, 后端], "value_out": "…"}`，不取中点；
- trace 同时写入 changelog 条目与被改格 `__raw__[field].trace`（两处一致）；
- claims 换算结论附带 recompute 说明；
- check 新增校验：convert 变更必须带 trace（含 value_out 或 ends）；
- units-table.md 新增 trace 字段说明表与复核式：`value_final == round(value_in × net_factor + offset, precision)`。

### 增强③：无法清洗的脏值逐条登记 uncertainty，不静默丢弃
- 新增 `add_dirty()`：未知单位/不可解析格式/多列映射冲突/条件指纹不同去重未判定行，
  逐条进 `uncertainties.dirty_values`（row_id/field/value/reason/pending_id）；
- 原值保留在 cleaned_table 中，不删格不改写；pending 与 dirty_values 同号关联；
- summary 新增 `dirty_values` 计数；check 新增校验：
  `dirty_values == summary.unknown_units`、pending 中 unknown_unit* 必须逐条出现在 dirty_values；
- uncertainties.summary 与 claims 均显式报告脏值处置。

## 保持不变（r2 全部机制）

- 强制执行协议 6 条置顶；五步线性主流程；SKILL.md 行数受控（约 170 行）；
- 资源共 6 文件（≤8）；规则六类（FM/UC/SN/MM/AF/DD）+ 字段字典 + conflict_policy；
- units 单位处理全保留：SI 前缀表、复合单位归一（g-1 → /g、µ/μ 统一）、区间双端换算、
  仿射换算 factor+offset、规则显式 factor、基准/分母不同不猜、跨维度不猜、ppm 近似须声明；
- 去重判定键 =（归一物质, 归一指标, 条件指纹）；键全同且值相容才合并，指纹不同绝不合并；
- 三级容错：多编码读入、异常全捕获不裸崩、失败仍写 result.json（status 如实）；
- 不硬编码路径：引擎路径 /skills/weekly-skill/scripts/、工作区 /app/work、产物 /app/output 全按平台约定。

## 自测记录

- 本地双测（skeleton→profile→run→check）通过：换算/去重/脏值登记/校验全部 PASS。
- 合成用例覆盖：正常换算（ug/g→mg/g）、重复记录合并、未知单位脏值（"12 xyz"）逐条登记、
  check 对 trace/ledger/dirty 计数的失败检出。

## 待验证

- 平台 3 个固定案例实际运行（本次不提交，由团队统一提交）。
