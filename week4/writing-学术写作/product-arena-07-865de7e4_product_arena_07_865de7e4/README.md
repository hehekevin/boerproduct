# LaTeX 写作与编译 Skill 使用说明

本 Skill 面向"LaTeX 写作与编译"任务：把科研内容写成可编译的 LaTeX 文档，或诊断修复无法编译的 LaTeX 源码。核心机制是先编译后交付的硬校验闭环，交付物始终为可继续编辑的源码加诚实的结构化状态报告。

## 一、文件清单与作用

| 文件 | 作用 |
|-|-|
| SKILL.md | Skill 本体。Agent 加载入口，含工作流程、修复协议、异常分支、自检清单 |
| resources/latex-error-cheatsheet.md | LaTeX 错误诊断速查表。6 大类常见编译错误的根因、定位方法与最小修法，驱动修复循环中的错误分类 |
| resources/templates/academic-article.tex | 学术文档骨架模板。未指定模板时的默认骨架，宏包按安全顺序排列，含公式、图、表、引用的规范写法示例 |
| resources/templates/writing-conventions.md | 学术写作规范速查。特殊字符转义清单、数学公式、表格、图、引用与结构规范，是交付前预检的判定依据 |
| resources/compile-checklist.md | 编译自查清单。交付前逐项机械核对的检查表，分编译状态、源码结构、内容一致性、输出契约四节 |
| resources/result-template.json | result.json 输出模板。含全部契约字段、status 取值语义与示例条目 |

## 二、环境依赖

- 运行环境：平台提供 latex-compiler 工具的 Harbor 运行时，或本地 TeX 发行版（TeX Live / MiKTeX 2021 及以上，含 latexmk、amsmath、graphicx、booktabs、hyperref 等常用宏包）。
- 无二进制依赖，所有资源为 UTF-8 文本文件。
- 编译器不可用时会自动降级为静态语法检查并明确标注"未经真实编译验证"，不会伪造编译状态。

## 三、调用方式

Skill 按 Harbor 契约自动触发，无需人工参数：

1. 平台将 Skill 安装到 Agent 环境后，Agent 收到 `/input/case.json` 与 `task.md`。
2. Agent 在 `/app/work` 下工作，按 SKILL.md 的 7 步流程执行。
3. 最终产物（.tex、.bib、编译产物、log）与 result.json 写入 `/app/output/`。

预算约束下的设计：正常路径不超过 8 次模型请求（读输入合并 1 次、材料转换 1 次、骨架生成 1 次、修复循环每轮 1 次上限 3 次、最终输出 1 次），编译与预检为工具调用不消耗模型请求。

## 四、最小调用示例

以下为示意输出，非正式案例结果。

输入（case.json 摘要示意）：

```json
{
  "case_id": "demo-001",
  "task": "将给定的方法描述文本写成 LaTeX 文档，要求公式编号可引用",
  "material": "我们提出了一种加权方法 f(x) = sum w_i phi(x_i)，实验表明指标A提升到0.91 ..."
}
```

Agent 执行过程（示意）：

1. 读取 case.json，识别任务为生成型，无指定模板，材料为纯文本。
2. 用骨架模板生成 main.tex，公式放入 equation 环境并加 \label{eq:model}，数字 0.91 登记来源。
3. 调用 latex-compiler 编译。log 无错误、无 undefined reference。
4. 预检通过，写入 /app/output/main.tex、main.pdf、result.json。

示意输出（result.json，节选，非正式案例结果）：

```json
{
  "case_id": "demo-001",
  "status": "compiled",
  "outputs": { "main_tex": "/app/output/main.tex", "build_artifacts": ["/app/output/main.pdf"] },
  "sources": [
    { "claim": "指标A为0.91", "source": "材料实验段", "action": "原样保留" }
  ],
  "uncertainties": []
}
```

修复型任务示意：输入一份报错的 .tex，log 报 `! Undefined control sequence` 于 \eqref 处。速查表命中"命令与宏包类"：根因是未加载 amsmath。最小修改为导言区补 \usepackage{amsmath}，重编译通过，1 轮修复完成，diagnostics 字段记录该错误链。

## 五、适用范围与限制

适用：

- 内容转 LaTeX 生成任务（纯文本、Markdown、Word 提取文本）。
- LaTeX 编译错误诊断与修复。
- 通用 article 或标准模板下的稿件迁移。

限制：

- 复杂期刊模板（含严格版式校验脚本）需以模板为准，Skill 保证可编译与结构规范，不保证逐像素版式一致。
- 编译器缺失时降级为静态检查，此时无法保证编译通过，会在 status 中如实标注。
- 修复循环上限 3 轮，防死循环；超限输出部分成果与根因分析，而非无限重试。

## 六、复用指南

他人可将本 Skill 用于自己的 LaTeX 工程场景：

- 速查表与规范文件可直接作为团队编码规范与 code review 清单。
- 编译-修复循环协议（分类、定位、最小修改、重编译、轮次上限）可移植到其他编译型语言的构建修复场景。
- result-template.json 的字段设计（status 诚实取值、sources 溯源、diagnostics 错误链）可复用于任何需要可核验交付的 Agent 任务。

## 七、维护信息

- 版本：1.0。
- 资源限制内：共 8 个 UTF-8 文本文件，单文件远小于 500KB，总量远小于 2MB，无 symlink。
- 已知边界与改进方向：中文文档在 pdflatex 下的兼容提示已写入速查表；后续可增加 xelatex 中文字体自动探测逻辑。
