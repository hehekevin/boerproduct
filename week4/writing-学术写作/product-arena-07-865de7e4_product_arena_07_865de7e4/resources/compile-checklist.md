# 编译自查清单

交付前逐项机械执行。前三节为工具可查项（不消耗模型请求），末节为判读项。任何一项不通过：回修复循环，或如实降级标注。

## A. 编译状态检查（读 log 与产物列表）

- [ ] 期望产物存在：main.pdf 已生成（无 pdf 时至少 log 中无 `!` 错误行）。
- [ ] log 中无以 `!` 开头的错误行。
- [ ] log 中无 `LaTeX Warning: Reference ... undefined`。
- [ ] log 中无 `LaTeX Warning: Citation ... undefined`。
- [ ] log 中无 `LaTeX Warning: Label(s) may have changed`（有则再编译一轮）。
- [ ] log 中无 `multiply defined` 警告。
- [ ] 编译命令与轮次已记录（编译器、latexmk 或手动轮次、TeX 发行版），写入 result.json 供复现。

## B. 源码结构检查（文本搜索，不编译即可查）

- [ ] \begin{xxx} 与 \end{xxx} 逐类计数相等。
- [ ] $ 定界符数量为偶数（排除 \$ 转义后的计数）。
- [ ] 花括号在去除转义与注释后配对。
- [ ] 正文裸露的 % & # _ 均已转义。
- [ ] \ref/\eqref 的每个 key 都有对应 \label。
- [ ] \cite 的每个 key 都有对应 \bibitem 或 bib 条目。
- [ ] \label 无重复定义。
- [ ] 无手写编号替代 \ref/\cite 的残留（如正文中出现 [1]、式(3) 字样）。

## C. 内容一致性检查（判读）

- [ ] 数字、术语、图表数据与原始材料逐条一致，无新增材料外事实。
- [ ] 公式符号在正文首次出现处有定义。
- [ ] 表格数值与材料来源列对应，无串行错位。
- [ ] caption 与图/表内容相符。
- [ ] 模板必填项（标题、作者、摘要、关键词等）已填齐，缺项已标注。

## D. 输出契约检查

- [ ] result.json 位于 /app/output/ 且为合法 JSON。
- [ ] result.json 含 case_id（值取自 case.json，非手造）。
- [ ] result.json 含 output_contract 要求的全部字段。
- [ ] status 取值诚实：compiled / partial / compile_failed / degraded_static_check 与实际相符。
- [ ] sources 字段包含事实与来源映射，可逐条回溯。
- [ ] changes 字段记录修改差异；uncertainties 记录缺口、冲突与需人工确认项。
- [ ] 交付物为可编辑源码，而非仅 PDF。
