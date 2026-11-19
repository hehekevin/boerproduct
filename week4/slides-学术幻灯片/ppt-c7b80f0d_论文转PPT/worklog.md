# worklog — paper2deck-skill v2（83 公式增强版，ppt-c7b80f0d）

日期：2026-11-16 ｜ 执行者：p83-25-p2deck ｜ 底座：75 分 paper2deck-skill + 83 分 ppt-710fbc72 脚本线

## 一、差距分析：75 分版（paper2deck）对照 83 公式逐要素检查

| # | 83 公式要素 | 75 分版现状 | v2 处置 |
|---|---|---|---|
| 1 | 强制执行协议置顶（7条：抄契约→骨架→每步写盘→广度优先→48请求/700秒熔断→JSON自检→失败也交付） | Stage 0 有骨架步骤，但无置顶协议、无熔断阈值、无写盘自检 | SKILL.md 第 0 节新增 7 条执行协议，置顶于一切工作之前 |
| 2 | 主产物结构化全量嵌入 result.json | 只内嵌 evidence_map，slides 数组未内嵌（评审须开附件才能核对页面） | `pptx_verify.py` 新增 `build_slides_embed`：逐页合并 plan+evidence（no/role/title/bullets/figure/notes/evidence 四元组）机器生成 `slides_embed`，result.json 原样内嵌、禁止手写 |
| 3 | 数字回证闸门（页面百分数/带单位数必须在 quote） | evidence_check 只查 quote 是否在论文里，**页面数字无回证** | 移植 ppt-710fbc72 的 `numeric_tokens + check_slide_coverage` 进 pptx_verify；fail 冒泡到 verdict 与退出码 |
| 4 | quote 逐字回证论文原文 | evidence_check.py 独立脚本（第 9 个资源，超 8 文件约束） | 合并进 `pptx_verify.py`（`--paper` 参数 + `PLAN` 构建前模式），删除独立脚本，保持 8 资源 |
| 5 | 闸门四态显式（enforced/skipped_not_provided/not_found/unreadable） | 无四态；缺 `--evidence` 时闸门静默等于没跑 | quote_gate 与 coverage_gate 均输出四态 + gate note「下游不得宣称已核对」；fit_audit inputs 四态沿用 710fbc72（已验证） |
| 6 | 模板真实继承 | SKILL 提到模板克隆，但 build 恒写 Arial 覆盖主题字体，无探查/对账 | 整体移植 710fbc72 的 `probe_template.py + fit_audit.py + build 主题继承`（不写 typeface、accent 取主题色、逐页 template_value→applied→match） |
| 7 | python-pptx 缺失降级链 | 有 pptx_minimal 兜底但无显式登记 | `degrade_chain` 字段（probe/build/verify/render 四段逐级登记） |
| 8 | status 诚实四级 | 只有 complete/partial/failed | 补 `blocked`（材料缺失无法开始） |

保留 75 分版全部有效机制：extract_pdf 页锚点提取、layout_budget 字号阶梯、pptx_minimal 兜底、render_preview no_renderer 诚实登记、异常处置表、示例标注「示意」。不推翻、不重构。

## 二、v2 关键改动

1. **scripts/pptx_verify.py 重写为双模式闸门中枢**：
   - `PLAN` 构建前模式：quote 逐字回证（空白归一化子串匹配）+ 数字回证 + 证据覆盖 + 页面卫生（notes 40-800 字非复述/要点≤5/单页≤700 字符）——fail 不修完不准构建；
   - pptx 构建后模式：沿用 710fbc72 全部检查（页数/标题/密度/notes/图/几何）+ 新增 quote_gate；
   - 两个模式都输出 `slides_embed` 与四态闸门状态；`summary.quote_gate_status/quote_gate_fails/numeric_unbacked/coverage_fail_slides` 全部机器生成。
2. **SKILL.md 重写（131 行 ≤150）**：执行协议 7 条置顶 → 线性 5 步（探查→页计划→前闸门→构建对账渲染→定稿内嵌）→ 闸门四态节 → 降级链表 → 示意示例 → 自查清单。result.json 终稿 schema 中 deliverable.slides / format_fit_table / inheritance_chain / gates 全部标注「机器生成禁止手写」+ 16384 token 分批写规则。
3. **资源 8 个脚本**（probe/extract/verify/budget/build/minimal/fit_audit/render），README + worklog 三文档；总计 ~85KB，远低于 2MB 限制。

## 三、双测证据（本地 Python 3.13 纯 stdlib 环境，恰好实测降级链；非正式案例结果）

合成 case：3 页 deck（title/result/limitation）+ 论文原文 paper_text.txt + 5 行 evidence_map。

### 正例（全链路）
```
pptx_verify.py PLAN        → {'fail':0,'warn':0,'verdict':'pass', quote_gate:enforced, numeric_unbacked:{}} rc=0
pptx_build.py (无python-pptx) → builder: pptx_minimal(fallback, stdlib-only) | warnings: 0   ← 降级链实测
pptx_verify.py (构建后, raw-xml) → {'fail':0,'warn':0,'verdict':'pass'} rc=0
slides_embed 抽查          → 3 页，每页 no/role/title/bullets/notes/evidence(type+locator+quote) 齐全
probe_template.py          → {"ok":false,"error":"python-pptx unavailable"} 正常退出，供 degrade_chain 登记
render_preview.py          → {"status":"no_renderer",...} 如实登记，不伪造
fit_audit.py               → 优雅退出（python-pptx 缺失），不抛栈
```

### 反例（闸门抓捕）
```
a. quote 改写（"cut...with the same accuracy"）→ quote_not_found_in_paper, fail=1, rc=1（hint: asapcuttrain）
b. 删 61% 的 quote 行 → numeric_unbacked={2:['61%']} → warn；92% 已回证无误报（闸门只抓未回证数）
c. 第 3 页无证据行 → coverage_fail_slides=[3] → fail=1, rc=1（页级 fail 冒泡到退出码）
d. 缺 --paper → quote_gate=skipped_not_provided + warn=1（未跑≠通过）
e. 缺 --evidence → coverage_gate=skipped_not_provided + quote_gate=skipped_no_evidence
f. evidence 行 JSON 损坏 → evidence_json_parse_error, fail=1
```

期望值与 ppt-710fbc72（83 分）包内回归基线同口径：b/d/e 对齐其 ③⑤⑥ 条（数字回证 warn 级、缺参显式 skipped、四态登记），c 对齐其 ④ 条（fail 必须冒泡）。

## 四、遗留风险

- 本地无 python-pptx/soffice，模板真实继承路径（probe→build theme_inherit→fit_audit 对账）未在本机端到端实跑；该路径为 710fbc72 原样代码（其 worklog 有完整实测记录：probe 11 layouts / font_mode=theme_inherit / fit_match_rate=1.0），本包未改动其逻辑。
- 环境预装 python-pptx 时全链路走完整路径，stdlib 兜底仅作降级保险。
