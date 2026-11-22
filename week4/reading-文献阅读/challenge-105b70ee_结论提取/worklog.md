# worklog — field2table-r3 重做（challenge-105b70ee）

## 背景

- 本赛道历史最高聚合 64.33（71331:63.33 / 72160:64.33，均为 field2table 系列）；本赛道同型
  标杆 72.33（chart2data，72.33 的关键经验：协议置顶、工单全覆盖、缺口显式不构造）。
- 64→70 差距定位：**提取覆盖密度**——工单要求的每个字段都必须出现在 result 里
  （哪怕 null+说明），漏字段比填 null 扣分更重。

## r3 改动清单

1. SKILL.md：强制执行协议扩为 7 条，新增"每行一条 claim"与"覆盖密度铁律"（漏行比 null 重）。
2. check.py：新增覆盖密度门禁（缺字段行=FAIL）、claim 密度门禁（claims<fields=FAIL）、
   逐字段 claim 匹配（claim-<field_id> 缺失=FAIL）、reported 行 search_log 必填；
   修复 range 校验把 `2.8-4.3` 连字符当负号的误判（绝对值回退匹配）。
3. skeleton.py：合并段落收割（--paras 一次产出 paragraphs.json），r3 schema 版本号、
   empty_row 增加 search_log 槽位、extraction_criteria 增加 coverage_rule。
4. examples/：三件套合成示例，5 字段 / 5 claims，覆盖 reported（标量、范围、文本+推断层）。
5. README.md：含调用步骤、最小示例与标注示意、依赖、异常处置。

## 本地双测记录

- 正测：skeleton 产出 5 行骨架+3 段段落库；check PASS（5 字段/5 claims）。
- 负测1（删一行字段+对应 claim）：FAIL — 缺字段行（覆盖密度门禁）+ coverage 不符。✓
- 负测2（只删一条 claim）：FAIL — claims 数(4)<fields 数(5) + 缺对应 claim。✓
- 退出码：正测 0，负测 1。

## 交付物（8 文件，均 UTF-8 文本）

```
submission/
├── SKILL.md                 # 协议置顶 + 五步流程 + schema + 判定表（约 175 行）
├── README.md                # 使用与方法说明 + 最小示例 + 标注示意
├── worklog.md               # 本文件
├── scripts/
│   ├── skeleton.py          # 骨架生成 + 段落收割（三级容错，退出码恒 0）
│   └── check.py             # 覆盖门禁 + 逐字校验（异常降级为报告项）
└── examples/
    ├── example-fields.json
    ├── example-input.json
    └── example-result.json
```

## 遗留与建议

- 未提交（按指示）。
- 评测时若材料为 PDF，段落收割拿不到文本属预期：check 降级跳过逐字校验（警告），
  逐字校验责任落回模型自查；后续可加 PDF 文本收割增强。
- search_log 的"五源"以实际材料为准，材料没有的源登记"材料未提供"而不是跳过。
