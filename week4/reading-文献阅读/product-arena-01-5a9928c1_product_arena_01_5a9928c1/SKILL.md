---
name: academic-paper-translate
description: Bilingual academic paper translation skill with glossary-enforced terminology consistency, paragraph-level source-target alignment, and verifiable output. Use when the task requires translating a scientific paper or a specified section range into Chinese, producing a bilingual paragraph-by-paragraph document, a locked terminology table, and evidence-traceable result.json. Trigger on tasks mentioning 文献翻译, bilingual translation, 术语表, 双语对照, or when /input/case.json contains translation output_contract fields.
---


## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty/说明字段，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。



# 学术文献翻译 Skill

## 1. 用途

将一篇真实科研论文（PDF 或纯文本）翻译为中文，输出段落级双语对照文档、术语表和可核验的结果文件。核心保障四个质量维度：

1. 术语稳：术语表强制约束全篇译名，标题、摘要、正文、图注、结论使用同一译名。
2. 段落全：段号与原文一一对应，跨页跨栏不漏段、不重复、不错位。
3. 关系准：指代、否定、限定、因果、数字单位、公式与文献编号与原文一致。
4. 可核验：每段译文指回原文位置并说明译法依据，译不准处明确标注而非含混处理。

## 2. 适用条件

- 输入为 PDF 论文或 UTF-8 文本，语言以英文为主，兼容中英混杂。
- 运行环境有 Python 3（纯标准库脚本，无第三方依赖）。
- 执行预算：64 次模型请求、900 秒、单响应 16384 tokens。本流程按不超过 20 次模型请求设计，其余核验由脚本完成。

## 3. 调用方式

运行时读取 `/input/case.json` 与 `task.md`，在 `/app/work` 下工作，产物写入 `/app/output`。Agent 按第 4 节流程执行；核验脚本命令行见第 8 节。

## 4. 工作流程

### 阶段 0：输入识别（1 次模型请求可省略，优先直接读文件）

1. 读取 `/input/case.json`，记录 `case_id`、材料路径、任务说明、`output_contract` 字段清单。
2. 读取 `task.md`，确认翻译范围（全文或指定段落区间）。若范围未指明，默认翻译全文，并在结果中注明该假设。
3. 判断任务边界：仅翻译，不臆造数据；材料缺失、无法判断必须如实记录。

### 阶段 1：文本获取与质量判断

1. 用平台的 pdf-text-tool 提取 PDF 文字层，逐页保存到 `/app/work/src/page_NN.txt`。
2. 质量判断分支：
   - 文字层正常：继续。
   - 文字层缺失或明显乱码（单页可读字符少于 100 或乱码比例高）：改用 ocr-tool，并在结果中标记 `text_source: ocr`，OCR 置信度低的行记入不确定性清单。
   - 扫描件模糊、公式或表格为图片：公式保留原样的占位符（见阶段 4），在 `uncertainty` 中登记图片位置，不猜测公式内容。
3. 若为纯文本输入，直接按行读入。
4. 语言混杂段（如中文文献中的英文摘要）：原文照抄，仅翻译目标语言部分，段落备注中说明。

### 阶段 2：结构解析与分段编号（脚本辅助，不占模型请求）

1. 将文本切分为翻译单元（unit）：标题、摘要、各级章节标题、正文段落、图注、表头、公式行、参考文献条目。
2. 段号规则：正文段落用 `P001`、`P002` 连续编号；图注用 `F01`、表格用 `T01`、公式用 `E01`、参考文献用 `R001`。每个单元记录定位 `页码p-栏c-段序n`，如 `p2c1p4`。
3. 跨页跨栏合并规则：若上一页末段句子未以终止标点结束且下一单元以小写字母或连字符开头，合并为同一段，段号沿用前段，定位写为区间（如 `p2c2p6-p3c1p1`）。
4. 输出 `/app/work/segment_map.csv`，列：`unit_id,kind,location,src_text`。切分结果用 `scripts/verify_alignment.py --mode segment` 自查段数与空段。
5. 漏段自查：核对每个章节标题之间的段落数，参考文献区从 `[1]` 连续编号到最后一条；发现缺号立即回查原文。

### 阶段 3：术语表构建与锁定（1 到 2 次模型请求）

1. 扫描全文，抽取候选术语：高频名词短语、缩写（首次出现处的全称与缩写对）、方法名、数据集名、模型名。目标 15 到 40 条，优先任务说明或 case.json 中点名的术语。
2. 为每个术语确定唯一中文译名，写入 `/app/work/glossary.csv`（模板见 `resources/terminology-template.csv`）。列：`term_en,term_zh,variant,category,first_location,status,note`。
3. 状态规则：已确定的术语 `status=locked`；无把握的 `status=pending`，译文首次出现时在括号内保留英文原文，并记入不确定性清单。
4. 缩写处理：首次出现译为"中文全称（英文全称, ABBR）"，此后全文只译中文全称或保留 ABBR，术语表记录该决定。
5. 锁定后术语表即约束，后续所有翻译请求只注入该表，不再现场改译。

### 阶段 4：分段翻译（批量，约 8 到 12 次模型请求）

1. 将单元按 3 到 6 段一批组装翻译请求，每批包含：
   - 本批术语表子集（locked 项全部注入，一行一条：`term_en => term_zh`）。
   - 上下文携带：上一段末尾约 80 字符原文，仅用于理解指代，不得翻译输出。
   - 保护标记规则：翻译前把公式、文献引用标记、图表编号、数字加单位替换为占位符（如 `⟪E01⟫`、`⟪R12⟫`、`⟪N17:5.3 mm⟫`），译文输出后原样回填，禁止改写数字与单位。
2. 翻译要求（随批注入的固定规则）：
   - 逐段直译优先，保持句子边界，不合并、不拆分段落。
   - 保留否定词、限定条件（only, at least, up to, approximately）与因果让步连接词。
   - 指代不明确时（it, they, this），译文补出所指对象并加方括号标注 `[指代: xxx]`。
   - 译不准的句子：输出最佳译文并追加标记 `[!UNCLEAR: 原因]`，禁止静默省略。
3. 每批返回后立即回填占位符，写入 `/app/work/bilingual_draft.md`。格式：

```
### P001 | p1c1p1 | title
SRC: 原文...
TGT: 译文...
NOTE: 译法依据（术语依据、语序调整、占位符回填说明）
```

4. 断点保护：每批完成即写盘。若请求失败，重试 1 次；仍失败则保存已完成部分，`status` 记 `partial`，并在 `change_log` 记录失败批次与原因。

### 阶段 5：回填检查与对照装配（脚本，不占模型请求）

1. 用 `scripts/verify_alignment.py --mode placeholders` 检查 `⟪⟫` 残留，发现残留先回填，回填失败的占位符原文照抄并标记 `[!UNCLEAR: 占位符回填失败]`。
2. 组装最终双语文件 `/app/output/bilingual.md`：文首为元信息头（材料名、翻译范围、术语表版本、生成时间），正文按段号顺序，文末附未译与存疑段清单。

### 阶段 6：脚本核验（不占模型请求）

运行完整核验：

```bash
python scripts/verify_alignment.py \
  --bilingual /app/output/bilingual.md \
  --glossary /app/work/glossary.csv \
  --result /app/output/result.json
```

核验项与处置：

1. 段落对齐：SRC 与 TGT 单元数量一致、段号一一对应。不一致则回查原文补译，禁止跳过。
2. 术语一致性：对每个 locked 术语，凡 SRC 含 `term_en` 的段落，检查 TGT 含 `term_zh`；同时检查 TGT 是否出现 `variant` 列登记的禁用变体。命中问题则修正译文后再查。
3. 数字单位保留：抽取每段 SRC 中的数字（含小数与百分数），逐一确认在对应 TGT 中出现。缺失即修正。
4. 占位符残留与未译标记：统计 `[!UNCLEAR]` 数量，写入核验报告。
5. 输出核验报告 `/app/output/verification.md`，未通过的项必须修复后重跑，无法修复的如实登记。

### 阶段 7：结果输出

1. 写 `/app/output/result.json`，字段以 case.json 的 `output_contract` 为准，至少包含模板 `resources/result-template.json` 中的全部字段与 `case_id`。
2. 诚实状态：`success`（全部完成）、`partial`（部分段落未译或核验未全过，需列出未完成单元号）、`failed`（材料不可读等原因）、`blocked`（缺少必需输入）。禁止把 partial 写成 success。
3. `uncertainty` 数组登记：OCR 低置信行、图片公式位置、pending 术语、`[!UNCLEAR]` 句、指代补注。
4. `change_log` 按时间记录关键动作（分段数、术语锁定数、每批翻译、核验轮次与修复）。

## 5. 输入输出约定

输入：`/input/case.json`（含 `case_id`、材料、`output_contract`）、`task.md`、PDF 或文本材料。

输出（`/app/output/`）：

| 文件 | 内容 |
|---|---|
| `result.json` | 结构化结果，含 output_contract 全部字段与 case_id、status、uncertainty、change_log |
| `bilingual.md` | 段落级双语对照，段号与定位一一对应 |
| `glossary.csv` | 锁定术语表，可复用于同学科其他文献 |
| `verification.md` | 脚本核验报告与人工确认清单 |

## 6. 异常处理分支

| 情形 | 处置 | 状态 |
|---|---|---|
| 文字层缺失 | 用 ocr-tool，标记 `text_source: ocr`，低置信行入 uncertainty | 可 success |
| 扫描件模糊不可读 | 可读页照常，不可读页段号保留、TGT 写 `[!UNTRANSLATED: 原文不可读]` | partial |
| 公式或表格为图片 | 保留位置占位与图号，不猜测内容，入 uncertainty | 可 success |
| 参考文献无法解析 | 保留原文不译，标记说明 | 可 success |
| 原文残缺（句子截断） | 照抄残缺部分，标记 `[!UNCLEAR: 原文残缺]` | 可 success |
| 中英混杂 | 英文译中文，中文保留，备注说明 | 可 success |
| 翻译请求失败 | 重试 1 次，仍失败保存已完成部分 | partial |
| 预算将尽（剩余请求少于 3） | 立即走收尾：装配、核验、写 result.json，未译段如实列出 | partial |

## 7. 预算分配建议

| 阶段 | 模型请求 |
|---|---|
| 输入识别 | 0 到 1 |
| 分段与术语表 | 1 到 2 |
| 分批翻译 | 8 到 12 |
| 问题段修复 | 最多 3 |
| 核验、装配、result.json | 0（脚本完成） |

合计不超过 20 次，为异常重试留出余量。

## 8. 自检清单

提交前逐项确认：

1. result.json 含 output_contract 全部字段与 case_id，JSON 可解析。
2. status 与实际完成度一致，partial 时列出未完成单元号。
3. 段号连续无缺号，SRC 与 TGT 数量相等，跨页合并段有区间定位。
4. 全部 locked 术语在全文译名唯一，术语一致性扫描零问题或已登记。
5. 每段 TGT 中的数字、单位、公式占位符、文献编号与 SRC 一致。
6. 无 `⟪⟫` 占位符残留。
7. 每个 `[!UNCLEAR]`、pending 术语、图片公式均已登记到 uncertainty。
8. 每段 NOTE 说明译法依据，可指回原文定位。
9. 核验报告 verification.md 存在且与最终译文一致。
10. change_log 完整，可复现运行轨迹。
