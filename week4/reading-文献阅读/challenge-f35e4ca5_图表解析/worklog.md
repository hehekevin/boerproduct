# WORKLOG — challenge-f35e4ca5（科研图表解析）83 公式增强

日期：2026-11-16　执行：r83-01-chart　产出：`bohrium-week3-final/challenge-f35e4ca5/submission/`

## 1. 对照 83 公式的缺失要素清单（增强前 chart2data 包）

| 公式要素 | 增强前状态 |
|-|-|
| 要素1 强制执行协议置顶（7条） | ❌ SKILL.md 第0节只是输入输出约定，无协议 |
| 要素3 校验三元组 {item,template_value,applied,match} 嵌入 result.json | ❌ chart_check 只写独立报告文件，评分器需开附件 |
| 要素3 数值逐字回证（unbacked 逐条列出） | ❌ 无任何数值回证机制 |
| 要素3 问题计入 fail 并冒泡到退出码 | ⚠️ 部分（缺回证类检查） |
| 要素4 闸门状态显式枚举 enforced/skipped_not_provided/not_found/unreadable | ❌ 无闸门概念 |
| 要素5 claims 引文 ≤40 字 + 归一化子串逐字回证 | ❌ schema_guard 只做结构校验，不验引文真伪 |
| 团队加码：系列首/中/尾回证、图例-分类数、颜色映射、轴范围机械校验 | ❌ 全缺 |

保留未动（已有效）：五字段契约+骨架先落盘、工单驱动 build_workorder、photo/schematic 禁 readings、表格逐字转录、approximate+误差标注、status 四级诚实。

## 2. 补强点（增量，不推翻）

1. **SKILL.md（107 行 ≤150）**：第0节置顶 7 条强制协议（抄契约→立即落骨架→每步写盘→广度优先→48次/700秒熔断→写盘前 JSON 自检→失败也交付，预算按本题契约 64 请求/900 秒）；Stage 2a 增加轴 `end` 声明、`colors` 系列颜色映射、"每条系列至少首/中/尾 3 点"；schema 增加 `verification` 块。
2. **chart_check.py 重写**：新增 4 类机械校验并逐条产出三元组：
   - 数值回证：每条数据系列首/中/尾读数的 x/y 数字须在证据 blob（claims 逐字引文+表格转录+材料文件）中归一化子串命中；非 approx 无回证=FAIL，approx 无回证降级 warn 并逐条列入 `unbacked_readings` + 回填 `uncertainties.human_review`（gate_note：下游不得宣称已核对）。
   - 图例-分类数：`elements.series` 声明数与读数实际系列数一致。
   - 颜色映射：提供 colors 时每条系列必须有条目；未提供 → gate=skipped_not_provided。
   - 轴范围：axes 声明 `end` 时读数越界=FAIL；未声明 → skipped_not_provided。
   - 校验结果写回 `result.json.verification`（gates/checks/unbacked/all_pass），评分器免开附件即可核对；fail 冒泡退出码 1。
3. **schema_guard.py**：新增 `--input-root` 引文回证——claims 每条 evidence.quote ≤40 字（归一化后）且必须在材料/表格中逐字命中，找不到=FAIL（抓编造）。

## 3. 双测证据

**正例**（examples 合成 case 全链路）：
- `build_workorder` → images=1 tables=1，骨架落盘 ✅
- `chart_check` → PASS，gates 全部 enforced，10 条 checks 全 match=true，verification 已嵌入 example-result.json ✅（exit 0）
- `schema_guard` → PASS ✅（exit 0）

**反例**（注入 7 类脏数据到 dirty.json）——校验器抓到 9 处 FAIL（exit 1），逐条命中：
- 缺 changelog 契约字段 ✅；图例-分类数不符 ✅；颜色映射缺条目 ✅；轴范围越界（y=200）✅；非 approx 读数无回证（y=999）✅；缺 approx 标记 ✅；照片写 readings ✅；object_inventory 与实际不符 ✅
- schema_guard 抓到伪造引文：`quote 无法在材料/表格中逐字回证` ✅（exit 1）

## 4. 约束自查

- SKILL.md 107 行；submission 共 7 个文件（SKILL.md + 3 脚本 + 3 示例）≤8；脚本纯标准库；无外部 CDN；路径运行时传参/find 定位；示例全部标注"示意/非正式案例"。
- 未提交正式答案；未调用平台提交。
