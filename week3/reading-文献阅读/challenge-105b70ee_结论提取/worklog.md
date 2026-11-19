# worklog — field2table-r4 final 交付（challenge-105b70ee）

## 任务

按 FORMULA-83 六要素清单，把本目录半成品（scripts/examples 为 r3 空壳、无 SKILL.md）
补全为完整交付。当前赛道最高 64.33（field2table 系列），83 为 rubric 饱和点。

## 对照 FORMULA-83 的缺失要素清单（开工时盘点）

| # | 要素 | 开工状态 | 处置 |
|---|---|---|---|
| 1 | 强制执行协议 7 条置顶 | SKILL.md 缺失（无文件） | 新写 SKILL.md 第 0 节，7 条全量置顶 |
| 2 | 主产物全量内嵌 result.json | scripts/examples 已具备 r3 基线 | 保留，SKILL.md schema 节写明"完整内嵌 result.fields 不外挂" |
| 3 | 机械校验器+逐条三元组嵌入 | check.py 已具备（r3） | 保留原样，本地双测复验 |
| 4 | 闸门状态显式枚举 | search_log 五源机制在 r3 脚本内 | SKILL.md 补写 search_log 协议与"材料未提供"登记规则 |
| 5 | 证据逐字摘录+定位 | check.py verbatim_number∈quote 机检 | 保留；SKILL.md 写明 quote 逐字+locator 粒度 |
| 6 | status 诚实四级 | schema 已有 | 保留（answered/partial/insufficient_evidence/input_error） |
| 硬约束 | SKILL.md ≤150 行 | — | 压缩至 135 行（frontmatter 合法、7 条协议全保留） |

## 交付物（8 文件，均 UTF-8 文本）

```
submission/
├── SKILL.md                 # r4：协议置顶 + 五步流程 + schema + 判定表（135 行）
├── README.md                # 使用与方法说明 + 最小示例（标注示意）
├── worklog.md               # 本文件
├── scripts/
│   ├── skeleton.py          # 骨架生成 + 段落收割（与 r3 一致，三级容错，退出码恒 0）
│   └── check.py             # 覆盖门禁 + 逐字校验（与 r3 一致，异常降级为报告项）
└── examples/
    ├── example-fields.json  # 5 字段合成工单
    ├── example-input.json   # 3 段合成材料 + output_contract
    └── example-result.json  # 示意输出（5 字段/5 claims，标注为示意）
```

相对 redo 包 r3 SKILL.md（213 行）的改动：压缩至 135 行以满足 ≤150 行硬约束，内容
要素无损（7 条协议、每行一条 claim、五源 search_log、verbatim_number∈quote、四状态
判定表、异常处置、最小示例全部保留），schema 版本号升为 r4。

## 本地双测记录

正测：
- skeleton.py：5 行字段骨架 + 3 段段落库收割成功，JSON 可解析。
- check.py 对 example-result.json：PASS（5 字段/5 claims，reported×5），退出码 0。

反测（注入脏数据，校验器必须抓到，退出码须为 1）——6/6 全部抓到：
1. 删一行字段+对应 claim → FAIL（缺字段行 + coverage 不符）✓
2. 只删一条 claim → FAIL（claims 4<5 + 缺对应 claim）✓
3. 改数字 scalar=91.2（与 verbatim/quote 不一致）→ FAIL ✓
4. quote 改写（非逐字）→ FAIL ✓
5. not_reported 却补值 → FAIL（缺项≠0 门禁）✓
6. 删 uncertainties 契约键 → FAIL ✓

## 遗留与建议

- 未提交（按指示）。
- 评测材料为 PDF 时段落收割可能拿不到文本：check 降级为警告跳过逐字校验，逐字责任
  落回模型自查；coverage/uncertainties 如实体现。
- search_log 五源以实际材料为准，材料没有的源登记"材料未提供"而不是跳过。
