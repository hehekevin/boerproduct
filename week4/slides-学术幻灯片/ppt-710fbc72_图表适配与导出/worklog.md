# worklog — template-fit-skill v3（ppt-710fbc72）

日期：2026-11-13 ｜ 执行者：pptfix-templatefit

## 一、差距分析：69 分版（重做版 73326）vs 75 分标杆

| 维度（分值） | 69 分版现状 | 75 分标杆（paper2deck） | v3 处置 |
|---|---|---|---|
| 实际效果 40（可核验 5） | 依赖**模型手抄**探查值进 rule_map，抄不全即掉可信度；本轮实测发现更致命问题：`pptx_build.py`/`pptx_verify.py` 均 `import layout_budget`，而该文件**未随包提交** → 构建/校验脚本一加载即崩溃，Agent 只能退到 stdlib 兜底，python-pptx 真实继承路径形同虚设 | layout_budget 在包内，构建稳定走 python-pptx | ①补齐 `layout_budget.py`（P0 修复）②新增 `fit_audit.py`，对账值由"探查报告 + 成品 pptx 实读"两端机器生成，彻底移除人工抄写环节 |
| 使用增益 25 | 只有 layout_log 与文字描述，无对照 | 有对照叙述，但无结构化 diff | 双份构建（模板版 vs 无模板基线），`diff` 输出逐页五维（title/body/font/color/layout）`changed`，`gain` 量化改动页数与待人工处理页数 |
| 创新增益 15 | 仅"映射决策内嵌"一条 | 版面预算阶梯 + contain-fit | 新增**继承链分层判定**（master_theme_inherited / layout_placeholder / +textbox_fallback / standalone），并让"真实继承"可被脚本验证：字体与颜色交给主题、强调色取 `theme_colors[0]` |
| 可靠体验 10 | 三级容错只写在文档里，未修复崩溃点 | — | 修复 P0 崩溃 + 降级链显式登记 `degrade_chain`（probe/build/render 三段） |
| 生态贡献 10 | README 有资源清单 | — | README 增「模板准备规范清单」7 条 + 导出/字体要求 + 复用方式；`fit_audit.py` 可独立复用于任意"模板 vs 成品"对账 |

## 二、v3 相对 69 分版的改动

1. **P0：补齐 `scripts/layout_budget.py`**（原包缺失，导致 build/verify 直接 ImportError）。实测修复后 `builder: python-pptx` 正常执行，`verify: fail 0 / warn 0`。
2. **P0：`pptx_build.py` 真实继承修复**
   - 有模板且 `deck_meta` 未指定字体时，run 上**不写 typeface**（此前恒写 Arial，覆盖主题字体，与"真实继承"主张自相矛盾）。
   - 新增 `--report`，强调色取模板 `theme_colors[0]`；占位符内标题色不显式设置，继承版式/母版。
   - 实测写入 `layout_log.font_mode=theme_inherit`、`accent_color`。
3. **新增 `scripts/fit_audit.py`**（替代 `consistency_check.py`，功能合并+扩展）：`checks`（整册一致性）+ `format_fit`（逐页四维 template_value→applied→match）+ `inheritance`（继承链与生效层级）+ `diff`（前/后五维）+ `summary`（fit_match_rate、diff_changed_pages、diff_dim_hits）。
4. **SKILL.md 重写**：对账字段（format_fit_table / inheritance_chain / slide_diff / gain）升为一等产物，明确"从 fit_audit.json 复制，禁止手写"；新增 `degrade_chain` 字段；`references/` 目录取消（schema 内联），资源维持 8 个脚本。
5. **README 重写**：补模板准备规范清单、导出与字体要求、已知限制、复用方式。
6. **P0：模板损坏时不再抛栈崩溃**（实测复现：`probe_template.py` 与 `pptx_build.py` 遇损坏 pptx 直接 `PackageNotFoundError` 中断，产物为零，与"三级容错"承诺不符）：
   - probe → 落 `{"ok": false, "error": ..., "fallback": "academic_default_layouts"}` 报告并正常退出，供降级链登记；
   - build → 捕获后转学术默认版式继续构建，`layout_log.warnings` 记 `template_unusable`，成品照常产出。
7. **补齐 verify 的两处断链**：
   - SKILL.md 第 5 步原先**漏传 `--evidence`**，证据覆盖闸门实际不生效（与 69 分包 SKILL 引用不存在的 `scripts/evidence_check.py` 同类病：文档承诺的能力没接上线）。已带 `--evidence` 并实测 `covers_all:false` 会触发 warn。
   - 移植 `pptfix-deckedit`（ppt-6ad93034 线）的数字对账逻辑进 `pptx_verify.py`（不新增文件）：`numeric_tokens` + `check_slide_coverage`，事实源为 evidence_map 逐页 quote，分母为页面文本（不含 notes），无证据行=fail、数字未回证=warn，输出 `slide_coverage` 与 `summary.numeric_unbacked`。

## 三、验证记录（本地实测，非正式案例结果）

构造 3 页示意 deck + 默认模板，跑通全链：

```
probe_template.py    → 11 layouts, majorFont=Calibri, accent1=4F81BD
pptx_build.py (模板) → builder: python-pptx, font_mode: theme_inherit, warnings: 0
pptx_build.py (基线) → baseline.pptx（Blank 版式）
pptx_verify.py       → {'fail': 0, 'warn': 0, 'verdict': 'pass'}
fit_audit.py         → {"slides":3,"fit_match_pages":3,"fit_match_rate":1.0,
                        "diff_changed_pages":3,"diff_dim_hits":{"body":3,"font":3,"color":3,"layout":3},"fail":0}
```

继承链抽样：`[layout_placeholder, layout_placeholder_plus_textbox_fallback, layout_placeholder]`——
第 2 页图文页因右侧图用独立文本框而如实标注 fallback，未伪造为纯继承。

降级链实测（坏模板写入 `echo "not a zip" > bad.pptx`）：

```
probe_template.py → {"ok": false, "error": "PackageNotFoundError...", "fallback": "academic_default_layouts"}（退出码 0，不中断）
pptx_build.py     → builder: python-pptx | warnings: 1 (template_unusable) → 仍产出可用 pptx
fit_audit.py      → effective_level 全部 standalone_textbox_no_inheritance（诚实降级，未伪造继承）
```

数字对账闸门实测（同一份 3 页 deck）：

```
正例（quote 含 "activity 92%"） → slide2 numeric_unbacked=[100%,61%]（该页另两个数未回证）→ warn
负例（quote 改成 "activity improved"） → numeric_unbacked=[92%,100%,61%] → warn，92% 立刻被抓出
负例（第 3 页无证据行）→ coverage_fail_slides=[3] → fail
表格/双栏页取样实测（deck 用 table.rows + columns 嵌套）：
  表格页 92%/61% 只回证 92% → numeric_unbacked=["61%"]，92% 无误报
  双栏页 "1.8 ms" 与数字型单元格 0.92 → numeric_unbacked=["1.8","0.92"]
```

**回归基线（改 `numeric_tokens` / `_slide_flat` / 匹配方式前先跑这四条，期望值不得变，任一不符即视为回归）**：
① 表格页 → `["61%"]`；② 双栏页 → `["1.8","0.92"]`（数字型单元格不换算百分比，判独立 token）；③ `92%` 在 quote 中 → 无误报，仅 warn 级；④ 无证据行页 → `coverage_fail_slides=[n]` → **summary.verdict=fail 且退出码 1**（页级 fail 必须冒泡到顶层，否则闸门形同虚设）；⑤ 不给 `--evidence` → `coverage_gate.status="skipped_no_evidence"` + warn 1 + rc=0（旧调用向后兼容，且明确"闸门未跑"而非"已通过"）；⑥ `fit_audit` 输入缺失 → `inputs.<name>.status` ∈ {loaded, skipped_not_provided, not_found, unreadable}，`audit_gate.format_fit/diff` 记 `not_run` + 原因 + `gate_notes`，warn 递增（缺 `--report` 时不得出现"看起来正常"的报告）；⑦ 检查项必须计入总账：`notes` 缺失/过短/与正文雷同 → `fail`+1 且 `verdict:"fail"`、rc=1；空页（无任何文本）与缺标题页同样计 fail（figure/blank 版式除外）。
该组期望值与 pptfix-deckedit（ppt-6ad93034 线）包内基线一致，两包对账口径相同。

> **⑤/⑥/⑦ 是一组真实回归修复**，共同病根是"闸门自身的状态没有被显式表达"，四种失效形态分别是：跑了但页级 fail 没冒泡到顶层（对方包）、空 evidence 导致每页假 fail（本包）、没跑却看起来像通过（本包 verify 缺 `--evidence` / fit_audit 缺 `--report`）、检查发现了问题但不计入总分（本包 notes/title 只打印 `ok:false`）。四种现在都有锚点。

## 四、产出文件（8 资源 + 3 文档）

```
submission/
├── SKILL.md            # ≤140 行：执行协议 6 条 + 线性 5 步 + 降级链 + 自查清单
├── README.md           # 调用流程 + 模板规范清单 + 字体导出要求 + 复用说明 + 示意示例
├── worklog.md          # 本文件
└── scripts/            # 8 个
    ├── probe_template.py   模板探查
    ├── extract_pdf.py      材料提取
    ├── layout_budget.py    版面预算（本轮补齐，修复崩溃）
    ├── pptx_build.py       真实继承构建（本轮改：主题字体/色继承、--report）
    ├── pptx_minimal.py     stdlib 兜底
    ├── fit_audit.py        对账表+继承链+diff（本轮新增，替代 consistency_check）
    ├── pptx_verify.py      结构/证据校验
    └── render_preview.py   PDF/PNG 渲染
```

## 五、遗留风险

- `fit_audit` 的字体判定是"是否残留显式字体"，非字形度量比对；跨机渲染仍可能有字形差异，已在 README「已知限制」声明。
- PDF 渲染依赖 `soffice`，环境缺失会记 `no_renderer`（诚实降级，不伪造）。
- 若案例模板版式名高度非标（纯中文自造名），推荐映射可能落到 title-only；`fit_audit` 的 layout `match` 会暴露该偏差，需在 uncertainty 说明。
- 主控若仍卡分，下一步优先做"pptx 内嵌图片比例机器判定"（当前图片框比例只记录，未判 fail）。
