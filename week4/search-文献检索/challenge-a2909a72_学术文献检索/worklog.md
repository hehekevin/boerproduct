# worklog — lit-search-pro（challenge-a2909a72）

## 时间线

### v1（2026-11-19）
目标：当天交付可运行的保底版 + 增益层（60 分钟窗口），主控统一提交。

1. **读题面与第 3 周冠军包骨架**：机制照搬 week3（Step0 落骨架 / 三元组自检 /
   闸门四态 / 数字逐字回证 / 5 步线性协议 / 退出码恒 0），领域逻辑全新写为
   「检索规划 → 执行登记 → 去重 → 来源追溯 → 遗漏分析」。
2. **SKILL.md**：149 行（≤150 达标）。frontmatter name=lit-search-pro，
   description 单行英文；8 条强制协议 + 六步流程 + 输出 schema + 校验器抓错
   清单 + 最小示例 + 异常处置 + 已知限制。
3. **6 个脚本**（≤8 达标），键分工约定防多脚本写同一键冲突：
   - `build_skeleton.py`：骨架 + 材料清单（检索响应文件识别），三级容错。
   - `plan_queries.py`：问题拆解 → 4 轮查询计划 + 机械关键词扩展
     （复数 y→ies / 形容词后缀不加复数 / 连字符变体 / 14 词缩写表 / 材料缩写发现）。
   - `dedup_records.py`：归一化标题 + DOI 聚类，正本选元数据最全行；
     写 dedup + coverage 两键；同名不同 DOI 不合并（conflict 登记）。
   - `verify_check.py`：查询计划/扩展/执行/追溯/去重/覆盖/回证/遗漏/结论分级
     全量校验；`--ablate none|backing|dedup|trace|all` 四档退化模式；
     纯函数 `analyze()` 供探针复用。
   - `schema_guard.py`：output_contract + 18 业务键结构守卫。
   - `gain_probe.py`：**5 臂机制消融**（normal + 退化 backing/dedup/trace/all）
     + 污染反例自测 + efficiency 计数。

## 修复记录（真实踩坑）

1. **标题回证检查写成列表成员判断**（`norm(title) not in quotes` 检查的是
   列表成员而非子串）→ 改为 `any(t_norm in q for q in quotes)`。
2. **argparse 错误退出码 2**：`except Exception` 抓不住 `SystemExit` →
   全部 6 个脚本补 `except SystemExit: return 0`（题面硬约束"argparse error
   一律退出码 0"）。week3 包此处也有同样隐患，本包修复。
3. **垃圾扩展词**：plural_add 对形容词失效（moleculars/neurals）+ does→doe +
   property→propertys → 引入形容词后缀表（al/ar/ic/ive/ous/ing/ed 不加复数）、
   y→ies 规则、停用词过滤（property→properties）。
4. **gain_probe 索引 bug**：`runs[label]` 用字符串索引列表 → 改为
   `by_mode = {m["mode"]: m for m in runs}`。
5. **数值回证结构**：papers 的 year/score 逐行判定（papers[i].numbers_backed）；
   dedup/coverage 计数由 counts.numbers_backed 单独判定——避免把 never-applied
   的检查名混入机器判定覆盖统计造成固定偏置。
6. **数字回证防误报（题面硬约束）**：DOI/URL/paper_id/query_id 等标识符内嵌
   数字排除在回证之外（IDENTIFIER_KEYS 过滤）；区间年份（2019-2024）逐端保留
   （子串匹配天然支持端点）；全部归一化用正则，**不用 isalpha**（汉字令
   isalpha 返回 True，中英混排必误判）。

## 真实对照数字（合成案例 demo-lit-001，2026-11-19 实测）

5 臂机制消融（同一份输入、同一校验层开关对照）：

| 指标 | normal | 退化backing | 退化dedup | 退化trace | 退化all |
|------|--------|------------|-----------|-----------|---------|
| 追溯机器判定 | 5/5 | 5/5 | 5/5 | **0/5** | **0/5** |
| 数字回证判定 | 11/11 | **0/11** | 11/11 | 11/11 | **0/11** |
| 去重判定覆盖 | 3 | 3 | **1** | 3 | **1** |
| 需人工核对条目 | **0** | 11 | 0 | 5 | **16** |
| 校验检查项 | 79 | 72 | 76 | 70 | 61 |

delta（normal − 退化）：backing 人工核对 Δ=−11 / 数字判定 Δ=−11；
trace 追溯判定 Δ=−5 / 人工核对 Δ=−5；dedup 判定覆盖 Δ=−2；all 人工核对 Δ=−16。
追问轮次折算（ceil(manual/3)）：normal 0 → all 6（Δ=−6）。

**污染反例自测**（副本注入 4 类污染：未标记重复文献、清空 matched_queries、
年份 2019→2819、removed_duplicates 置 0）：正常模式抓到 **9** 处 problems，
退化臂仅 **2** 处，missed_detection_delta.problems=**−7**（退化臂漏检 7 处），
`caught_by_normal_mode=true`。unbacked_numbers 差 −1（退化臂不再查回证）。

**诚实声明**：以上是**同一校验层的机制消融**（开关对照），不是平台
"基础 Agent vs 参赛 Skill"的白板对照；平台对照由平台生成。干净数据上
dup_missed=0（数据本身无未标记重复），去重机制的漏检证据来自污染反例自测。

## 自检记录（逐条实测 exit 0）

```
build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/wk4/skel.json --work-dir /tmp/wk4   exit 0
plan_queries.py    --case examples/example-case.json --result /tmp/wk4/skel.json --work-dir /tmp/wk4                    exit 0（4 轮计划 + 4 条扩展词）
dedup_records.py   --result /tmp/wk4/skel.json --work-dir /tmp/wk4                                                       exit 0（空表安全）
verify_check.py    --result examples/example-result.json --case examples/example-case.json                                    exit 0，verdict=PASS（86 项检查全过）
schema_guard.py    --result examples/example-result.json --case examples/example-case.json                                    exit 0，PASS
gain_probe.py      --result examples/example-result.json --case examples/example-case.json --emit-into --inject-pollution     exit 0，5 臂 + 污染被抓
失败路径：--badflag / 缺 --result / result 文件不存在 / 非 JSON → 全部 exit 0
```

注：examples/example-result.json 是**不含** gain_evidence 的纯净示意（对它直跑
verify_check 会报 gain_evidence 缺失 FAIL——这是设计行为，增益证据由
gain_probe --emit-into 运行时写入）；上面的 PASS 是对 emit-into 后副本测的。

## 剩余风险

1. SKILL.md 149 行逼近 150 上限，后续改动需先压缩。
2. 缩写表仅 14 条常见词，领域私有缩写依赖 Agent 结合材料人工补充。
3. 机制消融在干净小数据上 dedup 臂 delta 仅 −2（判定覆盖差），说服力主要来自
   污染反例（−7 漏检）；平台案例数据更大时该指标区分度会更好。
4. 沙箱仅 python3.12 + shell：本包零依赖、纯 stdlib，已在本机 3.12 实测；
   未在真实沙箱预演（无平台环境）。
5. 无 GitHub 链接文件（GITHUB_URL.txt 由主控提交时决定）。
