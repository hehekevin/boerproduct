# LaTeX 编译错误诊断速查表

用法：编译 log 中以 `!` 开头的行是错误行。将错误行内容与下表第一列匹配，按"定位方法"找到根因，按"修法"做最小修改。级联报错时只修第一条根因，立即重编译。

## 1. 命令与宏包类

| 错误信息 | 根因 | 定位方法 | 修法 |
|-|-|-|-|
| `Undefined control sequence` | 命令拼错，或宏包未加载，或命令用在导言区 | log 给出的行号是 TeX 已读位置，通常偏后。回溯 5 到 15 行找实际出错命令。l. 行后显示断点，断点前是完整命令，断点后是残缺部分 | 拼写改对；缺宏包则在导言区按规范顺序 `\usepackage`；确认该命令属于正文还是导言 |
| `File 'xxx.sty' not found` / `File 'xxx.cls' not found` | 宏包或文档类缺失 | log 中 `! LaTeX Error:` 后的 File 行 | 换等效已装宏包；.cls 缺失时若平台提供则复制入工作目录，否则降级 article 并标注差异 |
| `Environment xxx undefined` | 环境名拼错或对应宏包未加载 | 同上回溯法 | 改名或加载对应宏包（如 algorithm 需要 algorithm/algpseudocode） |
| `Command \xxx already defined` | 宏包冲突，重复定义 | 看最近加载的宏包 | 移除冲突宏包或用 `\renewcommand`；典型冲突：amsmath 与其他公式包重复加载 |

## 2. 数学模式类

| 错误信息 | 根因 | 定位方法 | 修法 |
|-|-|-|-|
| `Missing $ inserted` | 数学符号（_ ^ \alpha 等）出现在文本模式 | 同上回溯法，注意上一行结尾 | 补 $...$ 包裹，或改用 \(...\)；若想显示下划线应转义 `\_` |
| `Missing } inserted` / `\end{xxx} ended by \end{yyy}` | 数学或花括号定界符不配对 | 从报错行向前找未闭合的 `{` 或 `$` | 补全配对；用编辑器配对高亮核对 |
| `Display math should end with $$` | $ 与 $$ 混用 | 报错行 | 统一用 `\[...\]` 或 equation 环境，禁止混用 |
| `Bad math environment delimiter` | equation/align 内再嵌套 $$ 或环境嵌套错 | 报错行 | align 内每行用 `\\` 分隔，不要嵌套数学环境 |
| `\begin{align}` 报 `Missing \begin{document}` | 公式出现在导言区 | 确认 `\begin{document}` 位置 | 把公式移入正文 |

## 3. 环境与配对类

| 错误信息 | 根因 | 定位方法 | 修法 |
|-|-|-|-|
| `\begin{document} ended by \end{...}` 或 `ended by \end{xxx}` | 环境嵌套顺序错或漏写 \end | log 会同时显示两个环境名 | 补齐 \end 或调整嵌套顺序；检查 begin/end 数量是否相等 |
| `No counter 'xxx' defined` | 引用了不存在的计数器环境 | 报错行 | 改用正确环境名 |
| `\includegraphics` 报 `File not found` | 图片路径或文件名错 | log 的 File 行 | 核对路径与扩展名；缺图时用 `\fbox` 占位并标注 |

## 4. 交叉引用与文献类

| 错误信息（含 Warning） | 根因 | 修法 |
|-|-|-|-|
| `LaTeX Warning: Reference 'x' undefined` | \ref 的 key 无对应 \label，或还需再编译一轮 | 先重编译一遍；仍报错则核对 key 拼写与 \label 存在性 |
| `LaTeX Warning: Citation 'x' undefined` | \cite 的 key 不在 .bib/.bibitem 中，或未跑 bibtex | 核对 key；有 bib 则补跑 latexmk 或手动 bibtex + 编译 2 次 |
| `LaTeX Warning: There were undefined references` | 汇总提示 | 同上，逐个解决 |
| `multiply defined` | 同一 \label 定义了两次 | 文本搜索 `\label{key}`，删除或重命名重复者 |
| `Label(s) may have changed. Rerun` | 正常现象，引用编号待收敛 | 再编译 1 至 2 次直到该警告消失 |
| `No file xxx.bbl` | 未运行 bibtex/biber | 用 latexmk，或手动编译后跑 bibtex 再编译 2 次 |

## 5. 版面与字符类

| 错误信息 | 根因 | 修法 |
|-|-|-|-|
| `Overfull \hbox (badness ...)` | 内容溢出版心，常见于长 URL、宽表 | 表格用 tabularx 调列宽；URL 用 \url{}；轻微溢出可接受但须在结果中记录 |
| `Underfull \hbox` | 排版过松，多为警告 | 通常可忽略 |
| `Not in outer par mode` | 在浮动体内再嵌浮动体 | 把内层 figure/table 移出 |
| `Float too large` / 图表消失 | 浮动体超过版心 | 用 [p] 或改小图、缩列宽；禁止 hide 缩放掩盖 |
| `Unicode character ... not set up` | pdflatex 收到非 ASCII 字符（中文、全角符号） | 改用 xelatex/lualatex + ctex 或 fontspec；或删除全角字符 |
| `! LaTeX Error: Missing \begin{document}` 且行号在导言区 | 正文出现在导言区，或导言区有文本输出命令 | 检查 \documentclass 与 \begin{document} 之间是否有正文 |

## 6. 修后验证规则

1. 每修一处立即重编译，一次只改一个根因。
2. 重编译后 log 中错误必须减少或消失；若错误增多，说明改错了地方，回退该次修改。
3. 终态判定：无 `!` 错误行，无 undefined reference/citation 警告，无 multiply defined labels。
4. 达到 3 轮修复上限仍未通过时停止，按 SKILL.md 第 5 步诚实记录。
