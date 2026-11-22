# doc-compare-r3 — 多文档比较与整合 Skill（r3 覆盖密度增强版）

面向"同一研究问题的多篇论文"，产出**可逐格回溯的两两比较矩阵 + 共同字段比较矩阵**。
相对 r2 的核心增强：新增 `result.pairwise` 结构化比较维度矩阵——每对文档 × 每个比较维度
一条记录，verdict 判定必须同时附**双方逐字引文**（每个比较单元格可回溯到两份原文）；
冲突登记带 `attribution_dimension` 归因标签；`coverage` 统计块让比较覆盖密度一眼可核。

## 文件清单

| 文件 | 作用 |
|------|------|
| `SKILL.md` | Skill 本体：强制执行协议 + 五步流程 + 输出 schema + 异常处置 |
| `scripts/check_result.py` | 唯一校验器（合并版，三级容错）：覆盖/引文/pairwise 双引文/冲突归因/混池检测 |
| `resources/field_dictionary.json` | 七组字段字典模板 + 枚举定义（可复用到任意论文集合） |
| `resources/example-workorder.json` | 合成比较工单示例（2 文档 × 5 字段 × 6 维度） |
| `resources/example-result.json` | 示意输出（**非正式答案**，仅说明接口） |
| `worklog.md` | 重设计动作记录 |

## 快速使用（他人复用）

1. 把 Skill 安装到 `/skills/weekly-skill`（或任意目录，脚本路径相应调整）。
2. Agent 按 SKILL.md 五步流程执行：抄契约落骨架 → 字段字典 → 逐格抽取 →
   两两比较矩阵+可比性+冲突登记 → 校验收尾。
3. 每步之后 `/app/output/result.json` 始终存在且 JSON 可解析（骨架先行）。

## 本地自测

```bash
python scripts/check_result.py \
  --result resources/example-result.json \
  --workorder resources/example-workorder.json \
  --out /tmp/check_report.json
# 预期输出：PASS（10 格 = 2 文档 × 5 字段；reported 10；pairwise 6 条（双引文 5）；冲突 1；claims 2）
```

## 最小调用示例（标注示意）

输入（合成工单，节选自 `resources/example-workorder.json`）：
- documents: `DOC-A`（MOF 吸附甲基蓝）、`DOC-B`（活性炭吸附甲基蓝）
- fields: research_object / material_system / max_adsorption_capacity / evaluation_metric / main_finding

调用方式：平台加载本 Skill 后按 SKILL.md 第 1-5 步执行，最终写 `/app/output/result.json`。

示意输出节选（完整见 `resources/example-result.json`，**非正式答案**）：

```json
// ① 逐格抽取：每格绑定单文档引文
{"field_id":"max_adsorption_capacity","source_document_id":"DOC-A","value":312.5,
 "units":"mg/g","cell_status":"reported",
 "evidence":{"source_document_id":"DOC-A","paragraph_id":"p07","quote":"Langmuir 模型拟合得最大吸附量为 312.5 mg/g"}}

// ② 两两比较矩阵：verdict 必须附双方引文（r3 核心新增）
{"pair":["DOC-A","DOC-B"],"dimension":"material","verdict":"different",
 "note":"MOF vs 颗粒活性炭，材料体系不同",
 "evidence":[{"source_document_id":"DOC-A","paragraph_id":"p03","quote":"采用自合成 Fe3O4@MIL-100(Fe) 作为吸附剂"},
             {"source_document_id":"DOC-B","paragraph_id":"p02","quote":"吸附剂为市售颗粒活性炭 GAC-40"}]}

// ③ 冲突登记：双方原文并列 + 归因维度标签
{"what":"吸附量绝对值差异大（312.5 vs 86.4 mg/g）","attribution_dimension":"object",
 "quotes":[{"source_document_id":"DOC-A","paragraph_id":"p07","quote":"…312.5 mg/g"},
           {"source_document_id":"DOC-B","paragraph_id":"p06","quote":"qmax 计算值为 86.4 mg/g"}]}
```

## 适用范围与限制

- 5-10 篇论文规模稳定运行；pairwise 记录数 = 文档对数 × 比较维度数（10 篇 × 6 维 = 270 条）。
- 依赖语料段落编号；无编号文档按章节标题定位，粒度下降（如实记录）。
- 仅 1 篇文档时不构成比较，pairwise 置空、status=partial 并说明原因。
- 环境依赖：Python 3 标准库，无第三方包。

## 维护

- 版本：r3（2026-11）。变更记录见 `worklog.md`。
- 校验器异常一律降级不崩溃；校验 FAIL 时按打印清单逐条回填后重跑。
