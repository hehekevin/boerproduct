---
name: methods-experiments-writer
description: >
  Writes, rewrites, and fact-checks the Methods and Experiments sections of
  academic papers from raw research materials such as experiment logs, config
  files, dataset notes, code snippets, and result tables. Use when the user
  asks to draft or complete a methods/experiments section, reorganize
  scattered experiment notes into ordered reproducible procedures, align
  numbers in the text with configs and tables, add reproducibility details
  such as dataset versions, splits, hyperparameters, hardware, seeds and
  statistical tests, or audit an existing draft for fabricated or missing
  values. Trigger phrases include: write methods section, experimental
  setup, methods and experiments, 整理实验记录, 写方法章节, 补全实验细节,
  实验设置, 可复现性, methods section, reproduce experiment.
---

# 方法与实验章节写作 Skill

## 一、用途与目标

将零散的科研材料（实验记录、配置文件、日志、数据说明、结果表、代码片段）整理成符合学术惯例、事实可回溯、细节可复现的 Methods 与 Experiments 章节成稿。

本 Skill 的四个核心目标，与题目四问一一对应：

1. 写得全：覆盖步骤、实验设置、参数、数据集与划分、对照与重复次数六类要素。
2. 写得准：所有数值、单位、版本、条件均来自材料，不为行文顺畅补造数值。
3. 做得着：读者能按成稿复做实验，版本、环境、种子、命令给全。
4. 说得住：缺口与冲突显式标注交作者确认，限制条件指向具体失效场景。

## 二、核心机制（区别于基础 Agent 的三点）

1. 事实底稿先行：先建参数表、数据集表、环境表、对照表四张事实底稿（每条带来源编号），后写正文。正文数值只能从底稿取，禁止凭记忆写数。
2. 数字-来源映射：成稿中每个数值对应映射表中的一条记录（数值、单位、位置、来源文件与定位、状态）。任何数值可逐条回溯，无来源的数值一律转为 TODO 标注，不进入正文。
3. 缺口显式化：材料不足处用 `[TODO: 具体缺什么]` 与 `[待确认: 建议向谁确认]` 标注，绝不编造。冲突处（如结果表与正文不一致）按 配置文件与日志优先于文字记录 的规则取值，并同时在映射表中标记冲突待确认。

## 三、适用条件

- 已提供至少一份科研材料（记录、配置、日志、说明、表格、代码任意形态）。
- 任务目标是撰写、补全、改写或核查 Methods/Experiments 章节，或其中的实验设置、参数、数据集、复现性等局部。
- 材料完全为空且无任何实验事实时，本 Skill 不适用，应告知用户需先提供材料。

## 四、调用方式与输入输出约定

输入：

- `/input/case.json`：含任务说明、材料清单与 `output_contract` 字段约定。
- `task.md`：题目与要求。
- 材料文件：位于案例指定目录，格式为文本类文件（md、txt、json、yaml、csv、代码）。

输出（写入 `/app/output/`）：

1. 章节成稿：`methods_and_experiments.md`（如 output_contract 指定了其他文件名或格式，以契约为准）。
2. `fact_source_map.md`：事实与来源映射表（含来源登记表、参数表、符号表、缺口与冲突清单）。
3. `result.json`：包含 `case_id` 及 output_contract 要求的全部字段，结构见 `resources/result-json-template.md`。

预算约束：64 次模型请求、900 秒、单响应 16384 tokens。因此流程固定为 少量读取、少量生成、一次自检，禁止逐段反复调用。

## 五、工作流程

### Phase 0：解析任务（1 次操作）

1. 读 `/input/case.json` 与 `task.md`，确认：任务类型（撰写/改写/核查）、章节范围、语言、格式、受众、output_contract 的全部字段名。
2. 列出材料文件清单。若 case.json 中未给出，用一次目录列举获取。
3. 建立输出目录 `/app/output/`，先把 result.json 写一个含 `case_id` 和 `status: in_progress` 的骨架，保证中途失败也有诚实交付。

### Phase 1：材料通读与要素抽取（1 到 2 次读取）

1. 一次性读取全部材料文件（小文件全读，大文件按需分段）。
2. 边读边抽，填四张事实底稿（模板见 `resources/`）：
   - 参数表：名称、取值、单位、作用对象、来源编号。
   - 数据集表：名称、版本、规模、预处理、划分比例与随机方式、各子集用途。
   - 环境表：硬件、软件与框架版本、运行环境、随机种子、重复次数。
   - 对照表：基线及其版本、对照条件是否同预算、指标与统计方式。
3. 为每份材料建立来源登记表：S1、S2 编号，含文件名与定位（行号、表名、配置键）。
4. 识别到的符号（变量、指标、模型记号）记入符号表，记录首次出现位置。

### Phase 2：缺口与冲突分析（无需额外调用，与 Phase 1 同步完成）

1. 对照 `resources/experiment-setup-checklist.md` 与 `resources/reproducibility-checklist.md` 逐项核对，缺项记入缺口清单，格式：`[TODO: 缺少 X 的 Y]`。
2. 同一事实在多份材料中不一致时，按优先级取值：配置文件与日志 > 结果表 > 实验记录文字 > 论文旧稿，冲突双方均记入冲突清单标记 `[待确认]`。
3. 数值无法确定时宁缺毋滥：正文用定性描述加 TODO，或直接留 TODO 占位，不编造。

### Phase 3：成稿写作（1 次生成）

按 `resources/methods-structure-template.md` 的结构一次成稿：

1. 结构顺序：数据与数据集，模型与方法，实验流程（训练、验证、测试分开），实验设置（硬件、软件、种子、重复次数），评估指标与统计方式，对照实验，复现信息，限制条件。
2. 方法与实验流程用一般过去时加被动语态为主；普遍事实与结论可用现在时。
3. 每个符号在首次出现处定义，全篇与符号表一致。
4. 每个数值只从事实底稿取，写作时同步记录进映射表的 位置 列。
5. 缺口处写入 TODO 标注原文，不润色掩盖。
6. 限制条件写到具体失效场景（如 当输入长度超过 X 时显存溢出），不写泛泛套话。
7. 若 output_contract 要求了特定小节名、字数或语言，按契约执行。

### Phase 4：一致性自检（1 次生成或本地检查）

逐项检查并修正：

1. 数值核对：正文每个数值都能在映射表找到同名同值条目，单位一致。
2. 符号核对：无未定义符号，无一符多义。
3. 时态语态：方法与流程过去时加被动为主。
4. 要素覆盖：六类要素（步骤、设置、参数、数据集、对照、复现与限制）逐项确认在稿中出现或已标 TODO。
5. TODO 与待确认：全部保留在稿中或汇总在映射表，未被误删。
6. 契约核对：result.json 字段与 output_contract 一一对应，`case_id` 正确。

### Phase 5：交付（写入文件）

1. 写 `methods_and_experiments.md`（或契约指定文件）。
2. 写 `fact_source_map.md`。
3. 写最终 `result.json`：status 取 `complete`（六类要素齐且无未决冲突）、`partial`（有缺口或冲突，已在 gaps 与 conflicts 中列明）、`failed`（无法运行，说明原因）三者之一，如实标注。

### 步骤经济性说明

正常路径共约：1 次目录列举 + 1 到 2 次批量读取 + 2 到 3 次文件写入，模型请求集中在成稿与自检两次，远低于 64 次预算。禁止为润色单独小段而反复调用。

## 六、异常处理分支

| 情形 | 识别信号 | 处置 |
|---|---|---|
| 材料缺失某要素 | 清单核对缺项 | 正文留 `[TODO]`，gaps 列明，status 取 partial |
| 表与文数值不一致 | 同一参数两处取值不同 | 按 配置日志优先 规则取值，冲突清单记双方，标 `[待确认]` |
| 数据集版本不明 | 材料只写名称无版本号 | 写名称加 `[TODO: 版本号待确认]`，不猜版本 |
| 单位缺失 | 数值后无单位且材料无据 | 写数值加 `[待确认: 单位]`，不臆测单位 |
| 材料为图片或无法解析 | 读取失败 | 在 result.json 标明该文件无法解析，status 取 partial，不凭文件名猜测内容 |
| 任务超出章节写作范围 | 如要求补实验结论但材料无结果 | 只写材料可支撑的部分，越界部分列人工确认项 |
| 材料之间互相矛盾且无优先级依据 | 无配置或日志可裁决 | 取最详细来源，冲突记入 conflicts，标 `[待确认]` |
| output_contract 字段无法满足 | 契约要求但材料不支持 | 该字段如实填 unknown 并在 notes 说明，不编造 |
| 完全无法运行 | 材料为空或读取全部失败 | result.json status 取 failed，写明原因，不输出虚构成稿 |

详细处置见 `resources/gap-and-conflict-playbook.md`。

## 七、自检清单（交付前逐项打勾）

- [ ] result.json 含 case_id 且字段覆盖 output_contract 全部要求。
- [ ] status 如实：complete 或 partial 或 failed，缺口未清不标 complete。
- [ ] 正文每个数值在 fact_source_map 中有对应条目，且来源指向具体文件与定位。
- [ ] 映射表中无 状态为已证实但来源为空 的条目。
- [ ] 所有 TODO 与待确认 标注保留在成稿或映射表中。
- [ ] 符号表齐全，正文与公式符号一致。
- [ ] 六类要素（步骤、设置、参数、数据集、对照、复现与限制）逐项覆盖或显式标缺。
- [ ] 方法与流程段落为过去时加被动语态为主。
- [ ] 限制条件至少一条落到具体失效场景。
- [ ] 未在材料之外新增任何事实、数值或引用。

## 八、资源文件索引

- `resources/methods-structure-template.md`：Methods 与 Experiments 章节结构模板（数据、模型、流程、评估）。
- `resources/experiment-setup-checklist.md`：实验设置要素清单。
- `resources/reproducibility-checklist.md`：可复现性核查清单。
- `resources/fact-source-map-template.md`：事实与来源映射表模板。
- `resources/symbol-table-template.md`：符号表模板。
- `resources/result-json-template.md`：result.json 输出模板。
- `resources/gap-and-conflict-playbook.md`：缺口与冲突处置手册。
