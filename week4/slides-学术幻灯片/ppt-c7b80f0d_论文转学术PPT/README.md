# paper2deck-skill — 论文转学术 PPT（v2，83 公式增强版）

把一篇论文变成能上台讲的学术 PPT：主线成立、每页可回溯到论文原文、模板真实继承、导出不塌版。

## 资源清单

```
SKILL.md            执行协议 + 线性 5 步主流程 + 闸门四态 + 降级链 + 自查清单（131 行）
README.md           本文件：安装、调用、依赖、复用、限制
worklog.md          差距分析 + 增强点 + 双测证据
scripts/            8 个，纯 Python（优先标准库）
  probe_template.py   模板探查：版式/占位符/主题字体配色/页型推荐
  extract_pdf.py      论文提取：文本锚点 + 图表导出 + manifest
  pptx_verify.py      双模式闸门：PLAN 构建前闸门 / pptx 构建后校验
                      （quote 逐字回证 + 数字回证 + 证据覆盖 + 备注检查 + slides_embed 生成）
  layout_budget.py    版面预算：字号阶梯 18→10、备注规范检查
  pptx_build.py       构建：有模板克隆填充（主题继承，不写死字体），无模板学术版式
  pptx_minimal.py     stdlib 兜底构建（python-pptx 缺失时可编辑性保持）
  fit_audit.py        模板对账：逐页 template_value→applied→match + 继承链 + 前/后 diff
  render_preview.py   渲染：deck.pdf + previews/*.png，无渲染器如实记 no_renderer
```

## 依赖与安装

- Python 3.8+；预装 python-pptx / PyMuPDF / Pillow 时走完整路径；**全部缺失时脚本自动降级到 stdlib 兜底**（pptx_minimal 构建、raw-xml 校验、no_renderer 如实登记），产物仍可交付。
- 无外部 CDN / 网络依赖；所有路径运行时定位（/input、/app/work、/app/output 为平台契约）。

## 调用方式（一段话版）

Agent 读 `/input/case.json` 抄 `output_contract` → 写 result.json 骨架 → `probe_template.py` 探查模板 → `extract_pdf.py` 提取论文 → 模型生成 `deck.json` + `evidence_map.jsonl`（每条事实带逐字 quote）→ `pptx_verify.py PLAN` 构建前闸门（quote 回证 + 数字回证，fail 必须修）→ `pptx_build.py` 双份构建（模板版 + 基线）→ `pptx_verify.py` + `fit_audit.py` 构建后校验对账 → `render_preview.py` 渲染 → slides 全量内嵌 result.json。

详细步骤、字段 schema、异常处置见 SKILL.md；最小调用示例见 SKILL.md 第 4 节（标注示意，非正式案例结果）。

## 模板准备规范（可选输入）

1. 真实 .pptx 母版文件（不要导出的 PDF/图片）；2. 版式含 title/body 占位符；3. 主题字体含 CJK ea 字体；4. accent1 用于强调色；5. 页脚/页码在母版层（Skill 不覆盖）；6. 16:9 或 4:3 均可（探查报告自动识别）；7. 损坏/非 pptx 文件会触发降级链并如实登记。

## 适用范围与限制

- 适用：论文 PDF / markdown / txt → 学术汇报 PPT（组会/答辩/评审），证据可回溯，模板可套用。
- 不适用：论文精读结论生成、科研绘图美化、学术写作润色（相邻课题）。
- 已知限制：fit_audit 字体判定是"是否残留显式字体"，非字形度量；PDF 渲染依赖 soffice，缺失时记 no_renderer；纯中文自造版式名可能落到 title-only 推荐（对账表会暴露该偏差）。

## 复用

- `pptx_verify.py PLAN` 可独立用于任何"计划→闸门"场景；`fit_audit.py` 可独立复用于任意"模板 vs 成品"对账；`evidence_map.jsonl` 格式可直接接其他证据回证流程。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12，仅标准库）；无 python-pptx / soffice / 浏览器时走 `pptx_minimal` 兜底与如实降级，**不做 pip/apt 安装**。 |
| 安装与运行 | 提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json` + 论文；产物写 `/app/output/result.json`（slides 全量内嵌、gates、gain_evidence、efficiency）。 |
| 输入 / 输出解释 | 输入=论文与转换要求；输出=逐页计划与要点、每页证据（locator+quote）、模板继承记录、闸门状态、增益对照指标。 |
| 目标用户与场景 | 需要把论文快速转成可讲、可核验、可编辑的学术幻灯片的作者与导师；用于组会、开题与投稿前自查。 |
| 验收方式 | ①契约键齐全且 JSON 可解析；②每页有角色/标题/要点，证据可逐字回论文；③gates 四态显式；④gain_evidence 含基线与当前两套指标及削减量。 |
| 常见问题 | quote 回证失败→换原文短引文而非改写；模板继承探测失败→用 standalone_minimal_fallback 并登记；页数超限→按页计划裁剪并记 exceptions。 |
| 已知限制 | 无渲染环境只交付可编辑 pptx 与结构化页面内容，像素级导出需在有渲染器的环境复跑。 |
| 失败处理 | 闸门未过即修一轮；仍不过则如实写 gates 与 uncertainty 并继续交付，机检结论照实记录且退出码恒 0。 |
| 复用建议 | 直接复用 scripts/ 下各脚本；slides 内嵌结构与 gates/gain_evidence 字段可套用到其它"文档转演示"任务。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"                     # 1) 解释器可用
ls scripts/                                                   # 2) 脚本在位
python3 scripts/pptx_minimal.py                                 # 3) 兜底构建器可执行
python3 scripts/gain_evidence.py --help                         # 4) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 5) 产物可解析
```
