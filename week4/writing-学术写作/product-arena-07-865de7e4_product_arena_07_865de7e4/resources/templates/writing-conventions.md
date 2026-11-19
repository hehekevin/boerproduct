# 学术写作规范速查（公式、图表、引用、转义）

本文件是 SKILL.md 第 3 步与第 6 步预检的依据，写法不规范项在预检中被视为不通过。

## 1. 特殊字符转义清单

| 字符 | 正确写法 | 说明 |
|-|-|-|
| % | \% | 注释符，正文百分比必须转义 |
| & | \& | 表格列分隔符，正文中必须转义 |
| # | \# | 参数符 |
| _ | \_ | 下标符，正文/文件名中必须转义 |
| $ | \$ | 数学定界符 |
| ^ | \textasciicircum{} | 上标符 |
| ~ | \textasciitilde{} | 不换行空格符 |
| \ | \textbackslash{} | 反斜杠 |
| { } | \{ \} | 分组符 |
| 中文引号 | xelatex/ctex 下可直接用 | pdflatex 下改用 `` `` '' |
| 连字符 | - en-dash 为 -- em-dash 为 --- | 按原文意图选择 |

## 2. 数学公式规范

- 行内公式 $...$ 或 \(...\)；独立公式 \[...\] 或 equation 环境，禁止 $$...$$ 与其混用。
- 多行对齐推导用 align，每行 \ 结尾，需引用的行加 \label。
- 引用公式统一用 \eqref{eq:xxx}（amsmath 自动加括号）。
- 变量斜体是默认；函数名用命令（\sin \cos \exp \log）；单位、文字下标用正体 \mathrm{}。
- 向量/矩阵用 \mathbf{v} 或 \boldsymbol{\theta}；集合用 \mathbb{R}。
- 分式用 \frac{a}{b}，行内复杂分式可改 \frac 的 a/b 或 slased 形式以免行高溢出。
- 定理环境先 \newtheorem 再使用；证明用 proof 环境。
- 公式与正文叙述必须一致：符号首次出现时在正文中定义。

## 3. 表格规范

- 学术表用 booktabs 三线表：\toprule \midrule \bottomrule，禁止竖线。
- 宽表防溢出：用 tabularx 的 X 列自适应，或 p{宽度} 固定列宽；禁止靠 \scalebox 缩放掩盖溢出。
- 合并单元格：横向 \multicolumn{n}{列格式}{内容}，纵向 \multirow{n}{*}{内容}。
- 跨页长表用 longtable。
- 每个表必须有 \caption 与 \label{tab:xxx}，caption 在表体之前（学术惯例）。
- 浮动体位置参数用 [htbp]，不用 [H] 强钉（除非必要）。

## 4. 图规范

- \includegraphics[width=0.8\linewidth]{path}，宽度用比例不用固定 cm（模板适配性更好）。
- 每图必须有 \caption 与 \label{fig:xxx}，caption 在图体之后。
- 图片文件缺失时用 \fbox{占位文字} 保留位置并在 result.json 标注，不要删除 figure 环境。

## 5. 引用与参考文献规范

- 正文引用一律 \cite{key}，禁止手写 [1]。
- 交叉引用一律 \ref/\eqref，禁止手写编号。
- \label 紧跟被引用对象：\section{...}\label{sec:xxx}，\caption{...}\label{fig:xxx}。
- bib 方式：\bibliographystyle{...} + \bibliography{refs}，key 与 bib 条目一一对应。
- 无 bib 文件时用 thebibliography 环境与 \bibitem{key}。
- 交付前用文本搜索核对：\ref/\cite 的 key 集合 与 \label/\bibitem/bib key 集合相等，无多余、无缺失。

## 6. 结构规范（可维护性要求）

- 导言区宏包按"编码、字体、数学、图表、工具、hyperref 最后"的顺序排列，并加注释。
- 章节层级不超过 \subsubsection；再深用段落标题。
- 自定义命令集中在导言区 \newcommand 定义，不在正文中散落。
- 主文件与子文件用 \input/\include 划分时，编译入口始终是主文件。
