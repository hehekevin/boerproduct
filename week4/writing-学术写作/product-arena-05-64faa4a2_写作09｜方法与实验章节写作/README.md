# methods-experiments-writer 使用说明

一个用于撰写、改写与核查学术论文 Methods 与 Experiments 章节的 Skill。它把零散的实验记录、配置文件、日志、数据说明与结果表，整理成事实可回溯、细节可复现的章节成稿，并同步产出事实与来源映射表。

## 一、文件清单

| 文件 | 作用 |
|---|---|
| SKILL.md | Skill 本体：触发条件、核心机制、六阶段工作流程、异常分支、自检清单 |
| resources/methods-structure-template.md | 章节结构模板：数据、模型、流程、设置、指标、对照、复现、限制八个区块的写法与惯例句式 |
| resources/experiment-setup-checklist.md | 实验设置要素清单：数据集、训练、软硬件、评测、对照五类共 28 项要素 |
| resources/reproducibility-checklist.md | 可复现性核查清单：代码、环境、依赖、数据、划分、种子、命令、硬件、预期结果十项 |
| resources/fact-source-map-template.md | 事实与来源映射表模板：来源登记、事实映射、参数表、缺口与冲突清单四部分 |
| resources/symbol-table-template.md | 符号表模板：一符一义、首次定义、公式与正文一致性管理 |
| resources/result-json-template.md | result.json 输出模板与字段说明 |
| resources/gap-and-conflict-playbook.md | 缺口与冲突处置手册：十类异常情形的识别与处置 |
| README.md | 本说明 |

全部为 UTF-8 文本文件，共 10 个，无脚本依赖，无需安装任何额外组件。

## 二、安装与触发

1. 将整个目录放入平台的 Skill 加载位置（评测环境为 `/skills/weekly-skill`）。
2. Agent 读取 SKILL.md 的 frontmatter 后即可触发。触发场景：撰写或补全方法与实验章节、整理实验记录为可执行步骤、把正文数值与配置表对齐、补齐复现细节、核查稿件中的编造或缺失数值。
3. 典型触发语：写方法章节、整理实验记录、补全实验细节、写实验设置、可复现性检查、write the methods section、experimental setup、make it reproducible。

## 三、调用方式

### 运行时输入

- `/input/case.json`：任务说明、材料清单、`output_contract` 字段约定。
- `task.md`：题目与要求。
- 材料文件：文本类文件（md、txt、json、yaml、csv、代码等）。

### 运行时输出（`/app/output/`）

1. `methods_and_experiments.md`：章节成稿（契约指定其他文件名时从契约）。
2. `fact_source_map.md`：事实与来源映射表。
3. `result.json`：含 `case_id` 与 output_contract 全部字段的结构化结果。

### 工作流程概要

Phase 0 解析任务与契约，先写 result.json 骨架；Phase 1 一次通读材料并抽取参数表、数据集表、环境表、对照表四张事实底稿；Phase 2 对照两份清单找缺口与冲突，全部标注；Phase 3 按结构模板一次成稿（过去时加被动为主，数值只取自底稿）；Phase 4 数值、符号、时态、要素覆盖、契约五项自检；Phase 5 写入三个输出文件并如实标注 status。

正常路径约消耗：1 次目录列举、1 到 2 次批量读取、2 到 3 次写入，远低于 64 次请求与 900 秒预算。

## 四、最小调用示例

以下为示意输出，非正式案例结果。

示例输入（case.json 摘要）：

```json
{
  "case_id": "demo-001",
  "task": "根据 materials/ 下的配置文件与实验记录，撰写论文的 Methods 与 Experiments 章节",
  "output_contract": {
    "fields": ["case_id", "status", "main_result", "fact_source_map", "gaps"]
  }
}
```

材料摘要（示意）：config.yaml 给出 learning_rate 3e-4、batch_size 256、epochs 40；dataset_notes.md 给出 SST-2 训练集 54,000 条、验证 872 条；测试集规模在数据说明与结果表中分别为 872 与 826，两处不一致；种子列表未提及。

示意成稿片段（methods_and_experiments.md）：

```
Experiments were conducted on the SST-2 dataset, whose training and
validation sets contain 54,000 and 872 samples, respectively [S3].
The model was trained for 40 epochs with a batch size of 256, using
the AdamW optimizer with an initial learning rate of 3e-4 [S1].
Each configuration was repeated with random seeds [TODO: 种子列表].
The test set contained 826 samples [待确认: 数据说明记为 872，与
results.csv 的 826 不一致，需核对最终划分文件].
```

示意 result.json（摘要）：

```json
{
  "case_id": "demo-001",
  "status": "partial",
  "status_reason": "存在一处数值冲突与一处缺口，其余要素齐备",
  "gaps": [{"id": "G1", "description": "缺少随机种子列表", "marked_in_draft": true}],
  "conflicts": [{"id": "G2", "description": "测试集规模 872 与 826 不一致", "resolution": "取结果表值并标注待确认", "marked_in_draft": true}]
}
```

## 五、适用边界与限制

1. 需要至少一份含实验事实的材料；材料完全为空时不适用。
2. 图片型材料（扫描件、图表截图）无法解析，相关要素标 TODO，不据文件名猜测。
3. 本 Skill 只产出基于材料的内容，不推断实验结论、不补造数值、不生成材料之外的引用。
4. 中英文成稿均可，句式模板以英文论文惯例为准，中文稿按对应惯例调整时态语态。

## 六、失败处理与自查

1. 运行失败时 result.json 仍会写出，status 为 failed 并写明原因。
2. 用户自查方法：打开 fact_source_map.md，抽查任意一条正文数值是否能回溯到来源定位；统计 TODO 数量确认缺口均已登记。
3. 常见问题：材料路径与 case.json 不符时，先用目录列举确认实际路径再读取；output_contract 字段缺失时按模板补 unknown 并在 notes 说明。

## 七、维护信息

- 版本：1.0
- 依赖：无外部依赖，纯文本流程，任何能读写文件与执行目录列举的 Agent 均可运行。
- 定制方法：新增领域时只需在 experiment-setup-checklist.md 增补要素行，在 methods-structure-template.md 增补句式，无需改动流程。
