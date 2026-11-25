# lit-kg-builder：文献知识图谱构建 Skill

从科研论文中构建带证据的知识图谱：抽取类型化实体与有向关系三元组，每条三元组绑定段落定位与原文短引；规范化别名并从严处理跨篇消歧；执行至少 3 个真实查询；输出结构化图谱文件与 result.json。

## 目录结构

```
submission/
  SKILL.md                    Skill 本体（加载入口）
  resources/
    types.md                  实体与关系类型体系（可配置扩展）
    triple-spec.md            三元组 schema、证据定位与置信度规范
    normalization.md          实体规范化与消歧规则
    result-template.json      result.json 输出模板
    checklist.md              交付前自检清单
  README.md                   本文件
  worklog.md                  开发过程记录
```

## 使用方法

### 环境要求

无需安装任何依赖，全部为文本规则文件。适用于任何具备文件读写能力的 Agent（Harbor 平台 DeepSeek Harness 或通用 Agent 框架）。Skill 资源共 7 个 UTF-8 文本文件，总量远小于 2MB 限制。

### 调用步骤

1. 平台将 Skill 安装到 /skills/weekly-skill（或用户手动将 submission 目录放入 Skill 加载路径）。
2. Agent 运行时读取 /input/case.json 与 task.md；当任务要求构建知识图谱、抽取实体关系或输入含 corpus-manifest.json、primary-material.json、secondary-material.json 时，按 SKILL.md 第 3 节流程执行。
3. 流程概要：S1 输入盘点（读 case.json、corpus-manifest.json、material.json，登记 source_id）到 S2 建实体登记表到 S3 逐篇实体抽取到 S4 逐篇关系抽取到 S5 规范化与跨篇消歧到 S6 执行查询（至少 3 个）到 S7 输出落盘到 S8 自检。
4. 最终产物全部写入 /app/output/。

### 输入约定

| 文件 | 必需 | 说明 |
| - | - | - |
| /input/case.json | 是 | case_id、任务说明、output_contract 字段 |
| /input/task.md | 是 | 题目与约束 |
| /input/corpus-manifest.json | 推荐 | 论文清单：DOI、作者、哈希、许可证 |
| /input/material.json | 推荐 | 段落索引，用于定位与篇幅估计 |
| /input/primary-material.json | 至少其一 | 第一篇论文原文 |
| /input/secondary-material.json | 至少其一 | 第二篇论文原文 |

其他形式的论文文本（Markdown、XML、纯文本、PDF）同样支持；PDF 经平台解析工具转文本后按同一流程处理。

### 输出约定

写入 /app/output/：nodes.csv（节点表）、edges.csv（边表）、triples.json（三元组列表）、merges.json（合并与冲突记录）、result.json（含 case_id 与 output_contract 全部字段、status、证据、不确定性、查询结果、变更记录）。

## 最小调用示例

以下为示意输出，非正式案例结果，仅说明接口与数据形态。

输入（示意）：

```
/input/case.json    {"case_id": "demo-001", "output_contract": ["case_id", "entities", "triples", "queries", "status"]}
/input/primary-material.json   第一篇论文段落文本
/input/secondary-material.json 第二篇论文段落文本
```

调用：加载 SKILL.md 后执行第 3 节流程 S1 到 S8。

输出（示意，非正式案例结果）：

```json
{
  "case_id": "demo-001",
  "status": "success",
  "papers": [
    {"source_id": "P1", "doi": "10.0000/demo.1", "title": "示意论文一", "license": "CC-BY"},
    {"source_id": "P2", "doi": "10.0000/demo.2", "title": "示意论文二", "license": "CC-BY"}
  ],
  "entities": [
    {"entity_id": "P1-E01", "mention": "GraphNet", "normalized_name": "GraphNet", "type": "method",
     "aliases": ["GN"], "attribution": "self_reported",
     "evidence": [{"paragraph_id": "p3", "quote": "we propose GraphNet (GN), a ..."}]}
  ],
  "triples": [
    {"triple_id": "P1-T001",
     "subject": {"entity_id": "P1-E01", "name": "GraphNet", "type": "method"},
     "predicate": "uses",
     "object": {"entity_id": "P1-E02", "name": "DemoBench", "type": "dataset"},
     "direction": "subject_to_object",
     "condition": "在 DemoBench 测试划分上",
     "stance": "affirmed", "confidence": "high",
     "evidence": {"source_id": "P1", "paragraph_id": "p12", "quote": "GraphNet is evaluated on DemoBench"},
     "attribution": "self_reported", "note": ""}
  ],
  "merges": [
    {"canonical_id": "M01", "members": ["P1-E01", "P2-E04"], "normalized_name": "GraphNet",
     "basis": "P2 p4: 'the GraphNet method of [1]'", "decision_time": "S5"}
  ],
  "conflicts": [
    {"entities": ["P1-E02", "P2-E07"], "kind": "cross_paper_same_name",
     "reason": "两篇各自的数据集同名 DemoBench，版本与划分不同，依据不足不合并",
     "resolution": "保留为独立节点"}
  ],
  "queries": [
    {"query_id": "Q1", "question": "GraphNet 的一跳邻域", "executed": true,
     "result": [{"triple_id": "P1-T001", "summary": "GraphNet uses DemoBench"}],
     "evidence": [{"source_id": "P1", "paragraph_id": "p12", "quote": "GraphNet is evaluated on DemoBench"}],
     "undetermined": ""}
  ],
  "unreported": ["材料不含 PDF 页码，仅提供 paragraph_id 定位"],
  "limitations": []
}
```

edges.csv 对应示意行（示意输出，非正式案例结果）：

```
triple_id,subject_id,subject_name,predicate,object_id,object_name,direction,condition,stance,confidence,source_id,paragraph_id,quote,attribution,note
P1-T001,P1-E01,GraphNet,uses,P1-E02,DemoBench,subject_to_object,在 DemoBench 测试划分上,affirmed,high,P1,p12,GraphNet is evaluated on DemoBench,self_reported,
```

## 关键设计

1. 证据定位强制回填：没有 paragraph_id 与原文短引的三元组不允许存在，保证每条边可回查。
2. 置信度与立场双标注：confidence（high/medium/low）与 stance（affirmed/negated/conditional/speculative）独立，否定句、比较句、转述句各有固定处置规则，防止方向颠倒与把推测当事实。
3. 从严跨篇消歧：跨篇同名默认不合并，只有显式同指依据才合并；冲突登记而不删除，禁止跨篇融合结论。
4. 固定类型体系：实体与谓词均有方向化定义与反例，防止实体类型漂移与关系方向错误。
5. 预算友好：两遍抽取加一次消歧一次查询，中间产物落盘，支持超时前保存诚实部分结果。

## 限制与失败处理

- 材料缺失或解析失败：status=partial 或 failed，原因写入 limitations，不编造内容。
- 材料不含 PDF 页码：只提供段落 ID 定位，不生成页码。
- 扫描件图像：本 Skill 不做 OCR 推断，无 OCR 工具时 status=failed。
- 超长论文：分段抽取；预算不足时优先保证实体登记表与核心关系，status=partial。
- 完整异常分支见 SKILL.md 第 5 节（E1 到 E10）。

## 复用与扩展

替换 resources/types.md 中的类型表即可适配其他学科（医学、化学、材料等），流程与 schema 不变；新增谓词须提供语义、方向规则、正反例。
