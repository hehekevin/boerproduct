---
name: latex-write-compile
description: "Write or fix LaTeX academic documents with a guaranteed compile-verify loop. Use when the task asks to convert scientific content (paper text, structured notes, Markdown or Word drafts) into a compilable LaTeX document, adapt a manuscript to a journal or thesis template, or diagnose and repair LaTeX compilation errors. Trigger keywords: LaTeX, .tex, compile, 编译, pdflatex, xelatex, bibtex, documentclass, 交叉引用, 参考文献, 编译错误. The skill drives a bounded write-compile-diagnose-repair cycle, validates cross references and citations before delivery, and always emits a structured result.json with honest compile status."
---


## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty/说明字段，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。



# LaTeX 写作与编译 Skill

## 一、用途

本 Skill 用于两类任务：

1. 写作生成：把给定内容（论文文本、结构化材料、Markdown 或 Word 底稿）写成一份结构规范、可编译的 LaTeX 文档。
2. 修复编译：诊断并修复无法编译的 LaTeX 源码，使编译通过且改动最小。

核心价值主张：交付前必须经过真实编译验证。先编译后交付的硬校验循环是本 Skill 与基础 Agent 的根本区别。所有交付物为可继续编辑的 .tex 源码，绝不以 PDF 截图或无法编译的片段充当结果。

## 二、适用条件与触发

- 输入包含需要写成 LaTeX 的科研内容，或包含待修复的 .tex 源码。
- 运行环境提供 latex-compiler 工具（或本地 TeX 发行版）。
- 不适用：需要图像设计排版、PDF 美化等与编译无关的任务。

## 三、调用方式与运行约定

运行时固定约定（Harbor 契约）：

- 输入：`/input/case.json` 与 `task.md`。case.json 含案例材料与 output_contract 字段约定。
- 工作目录：`/app/work`（中间产物）。
- 输出目录：`/app/output/`（最终产物），必须含 `result.json`，其中必须包含 case_id 和 output_contract 要求的全部字段。
- 执行预算：64 次模型请求、900 秒、单响应 16384 tokens。因此本流程被刻意设计为低请求量：正常路径不超过 8 次模型请求。

## 四、完整工作流程

严格按以下 7 步执行，每步标注预计模型请求次数。

### 第 1 步：读取输入（0 次额外请求，与第 2 步合并）

读取 `/input/case.json` 与 `task.md`。提取四类信息：

- 任务要求：是生成还是修复；指定模板或 documentclass；编译器要求（pdflatex/xelatex/lualatex）；输出格式要求。
- 材料内容：论文文本、数据、图表、参考文献来源。
- output_contract：result.json 必须包含的字段清单。
- 材料格式：LaTeX / Markdown / Word / 纯文本，决定第 3 步是否需要转换路径。

注意：以实际文件内容为准，不要依据文件名或标签假设内容。

### 第 2 步：材料规范化（按需 1 次请求）

- LaTeX 材料：直接进入第 4 步。
- Markdown / 纯文本 / Word 提取文本：转换为 LaTeX。转换规则：
  - Markdown 标题映射：# 对应 \section{...}，## 对应 \subsection{...}，以此类推。
  - 粗体 *text* 映射 \textbf{text}，斜体映射 \textit{text}。
  - 数学内容如为 $...$ 或 $$...$$ 直接保留。
  - 列表映射 itemize/enumerate 环境。
  - 特殊字符按 resources/escape-cheatsheet.md 中的清单转义（% & _ # $ ^ ~ \ { } 等）。
- 若材料含 .bib 文件或引用列表，原样复制到工作目录并在正文中用 \cite{key} 对应。
- 事实与来源映射：为数字、术语、引用建立"来源位置"记录，写入 result.json 的 sources 字段。不新增材料外事实。

### 第 3 步：骨架与模板适配（1 次请求）

- 若任务指定模板：以模板为准，把内容迁入模板，保持版式必填项完整（标题、作者、摘要、关键词等）。
- 若未指定模板：使用 resources/templates/academic-article.tex 骨架（标准 article 类，常用宏包已在导言区按安全顺序排列）。
- 数学公式用规范写法：多行公式用 align 环境；变量斜体、单位正体（用 \mathrm）；定理用 theorem/proof 环境。
- 表格用 booktabs 三线表；宽表用 tabularx 或调整列宽，禁止靠缩放掩盖溢出。
- 每个浮动体（figure/table）配 \caption 和 \label；正文引用一律用 \ref/\cite，禁止手写编号。

### 第 4 步：首次编译（0 次请求，工具调用）

编译轮次协议：

- 有参考文献（.bib）：latexmk -pdf（或 -xelatex），latexmk 自动处理 bibtex/biber 与多遍收敛。无 latexmk 时手动执行：编译 1 次 → bibtex/biber 1 次 → 编译 2 次。
- 无参考文献：编译 2 次（第二遍解析交叉引用）。
- 单次编译超时（约 120 秒）：中断，记录超时，按第 7 步异常分支处理。

读取编译 log，提取所有错误（error）与警告（warning），重点是：

- `!` 开头的错误行及其后附带的行号与上下文。
- `LaTeX Warning: Reference ... undefined`、`Citation ... undefined`、`Label(s) may have changed`（表示还需再编译一轮）。
- `Overfull \hbox`（溢出，记录但非致命）。

### 第 5 步：编译-修复循环（每轮 1 次请求，最多 3 轮）

这是本 Skill 的核心创新机制，协议如下，严禁盲目重试或大段重写：

1. 分类：在 resources/latex-error-cheatsheet.md 中匹配错误模式，确定错误类别（未定义命令、数学模式错误、环境未闭合、宏包缺失、标签冲突等）。
2. 定位：从 log 提取报错的具体文件与行号。log 中的行号是 TeX 已读入位置，通常偏后，需向前回溯约 5 到 15 行找到根因。
3. 最小修改：只改动导致错误的最小范围。禁止顺带重构、重排或美化。
4. 重编译：重复第 4 步的编译轮次。
5. 终止条件：编译无 error 且无 undefined reference/citation 警告，或已满 3 轮。

满 3 轮仍失败的处置：停止修复，在 result.json 中如实记录 status、已尝试的修复、剩余错误的 log 摘要与根因分析，交付当前最优部分成果。诚实报告失败原因优于掩盖失败。

### 第 6 步：交付前预检（0 次请求，工具调用）

逐项机械检查，任何一项不通过则回第 5 步或如实标注：

- 编译产物存在（.pdf 或至少 .log 无 error）。
- log 中无 `??` 相关的 undefined reference/citation 警告。
- 源码中每个 \ref/\cite/\eqref 都有对应的 \label/\bibitem/bib key（用文本搜索核对集合相等）。
- 无 multiply defined labels。
- 数学定界符配对：$ 数量为偶数（跳过 \$），\begin/\end 数量配对。
- 特殊字符转义：正文裸露的 % & # _ 已处理。
- result.json 包含 case_id 与 output_contract 全部字段。

### 第 7 步：写输出（1 次请求）

把最终 .tex、.bib 及编译产物写入 `/app/output/`，并写 result.json，格式见 resources/result-template.json。必含字段：

- case_id：来自 case.json。
- status：compiled / partial / compile_failed / degraded_static_check。
- 主产物路径与文件清单。
- sources：事实与来源映射（数字、术语、引用的来源位置或修改记录）。
- changes：修改差异记录。
- uncertainties / limits：材料缺口、需人工确认项、异常。

status 取值语义：

- compiled：编译通过、预检全绿。
- partial：编译通过但存在已标注的未决项（如个别 warning、缺图占位）。
- compile_failed：满 3 轮仍报错，附 log 摘要与根因。
- degraded_static_check：编译器不可用，降级为静态检查，明确标注"未经真实编译验证"。

## 五、输入输出约定

输入：

| 输入 | 处理方式 |
|-|-|
| case.json + task.md | 任务要求与 output_contract 的唯一权威来源 |
| 材料（.tex/.md/.docx/文本） | 按第 2 步转换；docx 文本先经平台 pdf/ocr 工具或纯文本提取 |
| 模板（.cls/.sty） | 原样复制到工作目录，不修改模板本身 |
| .bib | 原样使用；正文 \cite 的 key 必须能在 bib 中找到 |

输出（写入 /app/output/）：

- 主 .tex 文件（结构规范、可继续编辑）。
- 配套 .bib（若有引用）。
- 编译产物与 log（供独立复核）。
- result.json（含全部契约字段与诚实 status）。

## 六、异常处理分支

| 异常 | 处置 |
|-|-|
| latex-compiler 工具不可用 | 降级策略：执行静态语法检查（定界符配对、环境配对、命令拼写核对速查表、引用集合核对），result.json 标注 status=degraded_static_check 并写明"未经真实编译验证"。禁止伪造编译成功。 |
| 编译超时 | 中断该轮，检查是否死循环宏或超大文件；拆分最小可编译片段定位问题；记录超时与已等待时长。 |
| 缺宏包 / 缺字体 | log 中 `File ... not found`、`Font ... not found`：优先改用等效已装宏包（如 subcaption 替代缺失项）；必要时在 result.json 记录依赖缺口，不臆造安装。 |
| 模板类文件（.cls）缺失 | 若平台提供该文件则使用；否则降级为通用 article 并在 uncertainties 中明确标注版式与目标模板的差异。 |
| 报错级联 | 只修 log 中第一条根因错误后立即重编译，级联错误常随根因消失，避免连锁误改。 |
| 材料为 Word/PDF | 用平台文本提取工具取纯文本后按第 2 步转换；转换中丢失的格式在 changes 中记录。 |
| 材料不足或互相冲突 | 不编造。在 result.json 的 uncertainties 逐条列出缺口与冲突点。 |

## 七、自检清单（交付前逐项确认）

- [ ] result.json 存在且含 case_id 与 output_contract 全部字段。
- [ ] status 与实际编译结果一致，无虚报。
- [ ] 主 .tex 可独立编译（或失败原因已被完整记录）。
- [ ] 交叉引用与引用编号完整，无 ??。
- [ ] 公式、表格、图环境完整，caption 与 label 齐备。
- [ ] 特殊字符已转义。
- [ ] 事实与来源映射可逐条回溯，无材料外新增事实。
- [ ] 未确认项、材料缺口在 uncertainties 中明确标注。
- [ ] 交付物为可编辑源码，而非仅 PDF 或片段。
