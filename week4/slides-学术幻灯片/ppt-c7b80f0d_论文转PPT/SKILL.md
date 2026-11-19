---
name: paper2deck-skill
description: 论文转学术PPT全流程技能：从论文PDF提取主线（问题-方法-结果-限制），产出可编辑pptx + 页级证据映射（每条quote逐字回证论文原文）+ 演讲备注 + 模板真实继承（先探查母版/版式/主题字体配色再填槽，不写死字体）+ PDF/PNG渲染。构建前后双闸门（quote逐字回证+数字回证）显式四态，主产物 slides 全量结构化内嵌 result.json。Use when the task asks to convert a research paper / 科研材料 into an academic slide deck (学术汇报/答辩/组会PPT), with evidence tracing back to the paper (证据可溯、模板合规、导出不塌版).
---

# paper2deck — 论文转学术PPT（主线优先 · 证据回证 · 模板真实继承）

产出的可评主体是 result.json 里**全量内嵌的 slides**（页号/角色/标题/要点/图表引用/演讲备注/论文原文定位），评审不开附件即可逐页核对；pptx + PDF/PNG 渲染件 + 对账表是配套实物。硬规则：**任何数字、单位、方法名、结论上页前，必须先挂一条逐字 quote**；引不对就改页，不改 quote 迁就页。

## 0. 执行协议（最高优先级，先于一切工作）

1. **第1步（首个响应内）**：读 `/input/case.json`，把 `output_contract` **全部字段名原样抄下** + `case_id`。
2. **第2步（同响应内）**：立即写 `/app/output/result.json` **骨架**（case_id + 全字段，值 null，`status:"in_progress"`）。此后每完成一步回填；即使熔断/崩溃，result.json 必须存在、字段完整、JSON 合法（失败也交付）。
3. **每步一次写盘动作**：脚本输出或 result.json 回填，不许只打印不落盘。
4. **广度优先**：先跑通全链拿到可评产物，再回头逐页精修；禁止单页打磨到完美才继续。
5. **预算熔断**：48 次模型请求 / 700 秒即停止新工作，保存已有产物，status 如实降级 partial。
6. **写盘前 JSON 自检**：`python3 -c "import json;print(len(json.load(open('/app/output/result.json'))))"`；字段只增不减。
7. **不许编造**：数字/quote/模板值/渲染状态只来自机器输出；材料缺失、无法判断、运行失败三者分开写进 uncertainty。

## 1. 主流程（线性 5 步）

### 第 1 步 — 契约、骨架、模板与材料探查
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/probe_template.py <模板.pptx> --out /app/work/template_report.json   # 无模板则跳过
python3 scripts/extract_pdf.py <论文.pdf> --outdir /app/work/extracted
```
- 按协议 1、2 抄契约、写骨架；页数上限/时长/受众记入 `/app/work/constraints.json`。
- 探查产出版式清单（占位符 idx/type/几何）、主题 `majorFont/minorFont`、accent1-6、页型推荐映射。**后续每条模板映射都必须引用这里的原始值，不许模型手抄转述**。
- `scanned:true` → OCR 或整页渲染，locator 用页码；材料非 PDF 直读，locator 用章节标题；图少于正文提及 → 整页渲染 `page_p{n}.png`（`figure_mode:"page_render"`），禁止占位图。

### 第 2 步 — 主线页计划与证据映射（1-2 次响应）
产出 `/app/work/deck.json` 与 `/app/work/evidence_map.jsonl`（deck schema 示意，非答案）：
```json
{"meta": {"title": "...", "template": "<模板路径或null>"},
 "slides": [{"no": 3, "role": "problem|method|result|limitation|conclusion|title",
             "layout": "title|bullets|bullets+figure|table|closing", "title": "≤25字主张",
             "bullets": ["≤40字，≤5条"], "figure": {"path": "...", "caption": "论文图注原文",
             "source_locator": "Fig.2 p.5"}, "notes": "过渡+强调点+预判问题(40-800字，不复述页面)"}]}
```
evidence 每行 `{"slide_no","claim","type":"figure|table|section|quote","locator":"Fig.1 p.3 / §3.2","quote":"逐字原文","figure_mode":null}`。
- 排页：标题→问题→方法→结果（每关键结果一页）→限制→结论。**按论文贡献排页序，不是按章节顺序搬运**；超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- 主结论与支撑细节分开：支撑细节不上正片主张，只进 notes 或备用页。
- **示意图不是实验数据**：`type:figure` 的页不得从图里读数，数值必须另有 `quote` 行。

### 第 3 步 — 构建前闸门（fail 必须修完才准构建）
```bash
python3 scripts/pptx_verify.py PLAN /app/work/deck.json --paper /app/work/extracted/paper_text.txt \
    --evidence /app/work/evidence_map.jsonl --out /app/work/gate_report.json
```
- **quote 闸门**：每条 quote 空白归一化后必须逐字出现在论文原文（改写/取整/换算一律 fail）。
- **数字闸门**：页面每个百分数/小数/带单位数必须在同页 quote 里逐字出现（`numeric_unbacked`）。
- 验证器 verdict=fail → 改页面或补 quote，**不许改 quote 迁就页面**；确属模板占位/页码等新数字登 uncertainty。（验证器退出码恒 0，失败只经由 verdict/报告传递，禁止中断交付）
- 闸门四态显式输出（见下）；未运行的闸门在 uncertainty 登记「不得宣称已核对」。

### 第 4 步 — 双份构建 + 对账 + 校验 + 渲染
```bash
python3 scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx <模板.pptx> \
    --report /app/work/template_report.json --log /app/output/layout_log.json
python3 scripts/pptx_build.py /app/work/deck.json /app/work/baseline.pptx --log /app/work/baseline_log.json
python3 scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json \
    --evidence /app/work/evidence_map.jsonl --paper /app/work/extracted/paper_text.txt --out /app/output/verify_report.json
python3 scripts/fit_audit.py /app/output/deck.pptx --deck /app/work/deck.json \
    --report /app/work/template_report.json --baseline /app/work/baseline.pptx --out /app/output/fit_audit.json
python3 scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
```
- 有模板 → **克隆模板文件构建**；deck_meta 未显式指定字体/颜色时 run 上**不写 typeface 与颜色**，交给母版主题（真实继承：改主题即整册换字变色）。强调色取模板 accent1。
- 字号阶梯 18→16→14→12→11→10，10pt 仍溢出**删内容不许再缩**；verify/fit_audit 的 fail 必须修复后重跑。
- 渲染后抽查 PNG：乱码/溢出/图片变形 → 修复重跑 Stage 4；无渲染器如实记 `render.status="no_renderer"`，不伪造。
- `cp /app/work/deck.json /app/output/deck.v1.json` 存档交付版快照。

### 第 5 步 — result.json 定稿（主产物全量内嵌，禁止手写对账值）
```json
{"case_id": "...",
 "...(output_contract 原字段逐个填，一个不缺)...": {},
 "deliverable": {"slides": ["verify_report.json 的 slides_embed 全量内嵌：每页 no/role/title/bullets/figure/notes/evidence(type+locator+quote)"],
                 "slides_count": N, "page_plan_summary": "问题x页-方法x页-结果x页-限制x页"},
 "template": {"file": "<模板路径或null>", "report": "template_report.json",
              "inheritance": "real|real_plus_textbox_fallback|standalone_minimal_fallback"},
 "format_fit_table": "fit_audit.json 的 format_fit 全量内嵌（有模板时）",
 "inheritance_chain": "fit_audit.json 的 inheritance 全量内嵌",
 "gain": {"fit_match_rate": "来自 fit_audit summary", "diff_changed_pages": "适配前/后改动页数", "manual_fix_pages": "match:false 页数"},
 "evidence_map": ["evidence_map.jsonl 逐行内嵌"],
 "gates": {"quote_gate": "闸门状态+fail数", "coverage_gate": "闸门状态", "numeric_unbacked": {}},
 "render": {"pdf": "deck.pdf", "previews": "previews/", "status": "ok|pdf_only_no_png|no_renderer"},
 "verification": {"layout_log": "layout_log.json", "verify_report": "verify_report.json", "fit_audit": "fit_audit.json"},
 "degrade_chain": [{"stage": "probe|build|verify|render", "fallback": "...", "reason": "..."}],
 "status": "complete|partial|failed|blocked", "uncertainty": ["..."], "changelog": ["每条取舍与修复记录"]}
```
- 内嵌超 16384 token 时分批写：先写骨架与 slides 前半，回填后再写后半，每段 ≤1500 字。
- status 四级：complete=全链路通过；partial=某阶段失败但有可评产物（写明哪步）；failed=无可用产物（仍写全字段）；blocked=材料缺失无法开始（附原因）。

### 第 6 步 — 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --paper <论文文本或目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --paper <论文文本或目录> --write
```
- 第一条：基础模式对照——模拟「不做证据映射、不做引用逐字回证」的基础路径，统计每页标题/要点/引用需人工回论文核对的规模。
- 第二条：当前模式实测——页数、含证据页数、quote 逐字可回证率、数值有据率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 闸门/校验失败**一律 verdict 记录、退出码 0**：闸门未过就修一轮，仍不过则如实写 gates 与 uncertainty 并继续交付，禁止以非零退出码结束会话。

## 2. 闸门四态（每个闸门显式枚举，未跑 ≠ 通过）

`enforced`（已执行并计入总账） / `skipped_not_provided`（参数未给，warn+登记） / `not_found`（路径不存在，warn+登记） / `unreadable`（存在但解析失败，warn+登记）。闸门 note 一律写明「下游不得宣称已核对」。

## 3. 异常处置与降级链（每级登记 degrade_chain）

| 情形 | 处置 |
|---|---|
| 模板缺失/损坏/非pptx | probe 落探查失败报告正常退出 → 学术默认版式构建 → uncertainty 登记 |
| python-pptx 缺失 | 直接用 `pptx_minimal` stdlib 兜底（评测沙箱本就无 python-pptx），inheritance=`standalone_minimal_fallback`；**不要 （评测沙箱无 pip，禁止安装：改用标准库实现）** |
| 版式缺失/占位符不够 | 最近版式+独立文本框，`template_slot_insufficient`，不改母版 |
| 字体缺失/乱码 | 有模板→继承主题字体；无模板→换 fc-list 实存 CJK 字体 |
| 图表提不出来 | 整页渲染 `page_p{n}.png`，`figure_mode=page_render`，禁止占位图 |
| 扫描件/加密PDF | OCR 或页级渲染，locator 用页码，uncertainty 注明来源 |
| 页数超限 | 先砍方法细节页；限制页/结果页不砍；changelog 记取舍 |
| 渲染失败 | render_log 记原因，交 pptx+已完成部分，status=partial |

## 4. 最小调用示例（示意，非正式案例结果）
```bash
python3 scripts/probe_template.py /input/template.pptx --out /app/work/template_report.json  # → 11 layouts, majorFont=Calibri
python3 scripts/extract_pdf.py /input/paper.pdf --outdir /app/work/extracted                 # → pages 12, figures 6
# （模型响应）deck.json + evidence_map.jsonl
python3 scripts/pptx_verify.py PLAN /app/work/deck.json --paper /app/work/extracted/paper_text.txt \
    --evidence /app/work/evidence_map.jsonl --out /app/work/gate_report.json                # → verdict:pass, quote_gate:enforced
python3 scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx /input/template.pptx \
    --report /app/work/template_report.json --log /app/output/layout_log.json               # → builder: python-pptx, font_mode: theme_inherit
python3 scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json \
    --evidence /app/work/evidence_map.jsonl --paper /app/work/extracted/paper_text.txt      # → fail:0, numeric_unbacked:{}
python3 scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews        # → {"status":"ok","pngs":12}
```

## 5. 交付自查清单
- [ ] result.json 含 case_id 与 output_contract 全部字段，无未解释 null；`deliverable.slides` 全量内嵌且每页带 evidence 定位
- [ ] 构建前闸门 verdict=pass（quote_gate+coverage_gate 均 enforced 且 fail=0）
- [ ] 页面数字全部回证（numeric_unbacked 为空或已登 uncertainty）；quote 逐字、未改写
- [ ] 每页一主张、要点 ≤5 条、notes 40-800 字非复述、含过渡+强调+预判问题
- [ ] 模板真实继承：layout_log.font_mode=theme_inherit（有模板时）；fit_audit 无未处理 match:false
- [ ] deck.pdf/PNG 存在且与 pptx 一致；渲染状态如实；degrade_chain 完整
- [ ] status/uncertainty/changelog 诚实；每条闸门状态可解释

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"                     # 1) 解释器可用
ls scripts/                                                   # 2) 脚本在位
python3 scripts/pptx_minimal.py                                 # 3) 兜底构建器可执行
python3 scripts/gain_evidence.py --help                         # 4) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 5) 产物可解析
```
