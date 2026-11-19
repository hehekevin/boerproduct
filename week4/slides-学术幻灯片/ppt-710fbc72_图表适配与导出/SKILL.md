---
name: paper2template-skill
description: 学术 PPT 模板与格式适配技能：模板真实套用（先 stdlib 探查母版/版式/主题字体配色，再克隆填充，run 上不写死字体）、版式约束（字号阶梯 18→10 机器预算，10pt 仍溢出删内容不压字号）、图表适配（等比缩放+拉伸变形抓捕+图号/正文引用错位抓捕）、批量一致性（页码/标题位置/字号阶梯逐页机器审计）、导出渲染横切（pdf 页数对账+逐页 PNG+无渲染器如实登记）。证据回证贯穿：quote 逐字回证论文原文+数字回证。构建前 PLAN 闸门必须 pass 才准构建。增益层 --ablate 消融双臂真跑（污染反例注入副本，同一校验器各跑一遍，FAIL 数差机器判定）。Use when the task asks to adapt a research paper/材料 into a template-compliant academic deck (学术汇报/模板套用/格式适配), with 模板继承可查、页页证据可溯、导出不塌版.
---

# paper2template — 学术 PPT 模板与格式适配（模板真实继承 · 六要素机器审计 · 消融增益）

产出的可评主体是 result.json 里**全量内嵌的 slides**（页号/角色/标题/要点/图表引用/演讲备注/论文原文定位），评审不开附件即可逐页核对；pptx + 导出件 + 对账表/审计表是配套实物。硬规则：**任何数字、单位、结论上页前必须先挂一条逐字 quote；引不对就改页，不改 quote 迁就页。**

六要素映射（题面）：论文主线=deck.json 排页；页结构=版式映射；图表引用=figure+Fig.N 配对审计；讲解逻辑=notes 过渡+预判问题；模板约束=probe→build→fit_audit 对账；导出渲染=render_export 横切闸门。

## 0. 执行协议（最高优先级，先于一切工作）

1. **第1步（首个响应内）**：读 `/input/case.json`，把 `output_contract` **全部字段名原样抄下** + `case_id`。
2. **第2步（同响应内）**：立即写 `/app/output/result.json` **骨架**（case_id + 全字段，值 null，`status:"in_progress"`）。此后每完成一步回填；即使熔断/崩溃，result.json 必须存在、字段完整、JSON 合法（失败也交付）。
3. **每步一次写盘动作**：脚本输出或 result.json 回填，不许只打印不落盘。
4. **广度优先**：先跑通全链拿到可评产物，再回头逐页精修。
5. **预算熔断**：48 次模型请求 / 700 秒即停止新工作，status 如实降级 partial。
6. **写盘前 JSON 自检**：`python3 -c "import json;print(len(json.load(open('/app/output/result.json'))))"`；字段只增不减。
7. **不许编造**：数字/quote/模板值/渲染状态只来自机器输出；材料缺失、无法判断、运行失败分开写进 uncertainty。
8. **文件定位**：输入一律用显式路径 + 存在性校验（`ls /input/`、`os.path.exists`），禁用 `find | head -1` 式命中。

## 1. 主流程（线性 6 步）

### 第 1 步 — 契约、骨架、模板与材料探查
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/probe_template.py <模板.pptx> --out /app/work/template_report.json   # 无模板则跳过
python3 scripts/extract_pdf.py <论文或材料> --outdir /app/work/extracted
```
- probe 是**纯标准库**（zipfile+ElementTree），评测沙箱无 python-pptx 也可探查版式/占位符/主题字体配色/页型推荐。`ok:false` → 走降级链，不中断。
- 页数上限/时长/受众记入 `/app/work/constraints.json`。后续每条模板映射必须引用 template_report 原始值，不许模型手抄转述。
- 扫描件/非 PDF：locator 用页码或章节标题；图少于正文提及 → 整页渲染 `page_p{n}.png`，禁止占位图。

### 第 2 步 — 主线页计划与证据映射（1-2 次响应）
产出 `/app/work/deck.json` 与 `/app/work/evidence_map.jsonl`（示意 schema，非答案）：
```json
{"meta": {"title": "...", "template": "<模板路径或null>"},
 "slides": [{"no": 3, "role": "problem|method|result|limitation|conclusion|title",
             "layout": "title|bullets|bullets+figure|table|closing", "title": "≤25字主张",
             "bullets": ["≤40字，≤5条；图号引用写 Fig.N"], "figure": {"path": "...", "caption": "Fig.1 论文图注原文",
             "source_locator": "Fig.2 p.5"}, "notes": "过渡+强调点+预判问题(40-800字，不复述页面)"}]}
```
evidence 每行 `{"slide_no","claim","type":"figure|table|section|quote","locator":"Fig.1 p.3 / §3.2","quote":"逐字原文","figure_mode":null}`。
- 排页：标题→问题→方法→结果（每关键结果一页）→限制→结论；按贡献排页序，超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- **示意图不是实验数据**：`type:figure` 的页不得从图里读数，数值必须另有 `quote` 行。

### 第 3 步 — 构建前闸门（fail 必须修完才准构建）
```bash
python3 scripts/pptx_verify.py PLAN /app/work/deck.json --paper /app/work/extracted/paper_text.txt \
    --evidence /app/work/evidence_map.jsonl --out /app/work/gate_report.json
```
- **quote 闸门**：空白归一化后逐字出现在论文原文（改写/取整/换算一律 fail）。
- **数字闸门**：页面百分数/小数/带单位数必须在同页 quote 里逐字出现（`numeric_unbacked`）。
- **覆盖闸门 + 页面卫生**：每页 ≥1 条证据行；notes 40-800 字非复述；要点 ≤5；单页 ≤700 字符。
- verdict=fail → 改页面或补 quote，**不许改 quote 迁就页面**；退出码恒 0，失败只经由 verdict 传递。

### 第 4 步 — 双份构建 + 对账 + 一致性审计 + 渲染
```bash
python3 scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx <模板.pptx> \
    --report /app/work/template_report.json --log /app/output/layout_log.json
python3 scripts/pptx_build.py /app/work/deck.json /app/work/baseline.pptx --log /app/work/baseline_log.json
python3 scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json \
    --evidence /app/work/evidence_map.jsonl --paper /app/work/extracted/paper_text.txt --out /app/output/verify_report.json
python3 scripts/fit_audit.py /app/output/deck.pptx --deck /app/work/deck.json \
    --report /app/work/template_report.json --baseline /app/work/baseline.pptx --out /app/output/fit_audit.json
python3 scripts/render_export.py /app/output/deck.pptx --outdir /app/output/previews --out /app/output/export_audit.json
```
- 有模板 → 克隆填充占位符；deck_meta 未显式指定字体时 run 上**不写 typeface**，交给母版主题（真实继承）。字号阶梯 18→10pt 机器预算，10pt 仍溢出**删内容不许再缩**。
- render_export 四类机器审计：页码逐页/标题字号阶梯/标题位置跨页一致；图片拉伸变形（框比 vs 源图比 >5% 即 fail）；图号引用错位（Fig.N 配对）；导出 pdf 页数对账+逐页 PNG。无渲染器如实记 `pptx_only_no_renderer`，不伪造。
- `cp /app/work/deck.json /app/output/deck.v1.json` 存档交付版快照。

### 第 5 步 — result.json 定稿（主产物全量内嵌，禁止手写对账值）
```json
{"case_id": "...",
 "...(output_contract 原字段逐个填，一个不缺)...": {},
 "deliverable": {"slides": ["verify_report.json 的 slides_embed 全量内嵌"], "slides_count": N,
                 "page_plan_summary": "问题x页-方法x页-结果x页-限制x页"},
 "template": {"file": "<模板路径或null>", "report": "template_report.json",
              "inheritance": "real|real_plus_textbox_fallback|standalone_minimal_fallback"},
 "format_fit_table": "fit_audit.json 的 format_fit 全量内嵌（有模板时）",
 "consistency_audit": "export_audit.json 的 consistency 全量内嵌（六要素机器审计）",
 "gain": {"fit_match_rate": "来自 fit_audit summary", "diff_changed_pages": "适配前/后改动页数",
          "ablation_gate_fail_diff": "gain_evidence.ablation 两臂 FAIL 差"},
 "evidence_map": ["evidence_map.jsonl 逐行内嵌"],
 "gates": {"quote_gate": "状态+fail数", "coverage_gate": "状态", "numeric_unbacked": {}},
 "render": {"pdf": "deck.pdf", "previews": "previews/", "export_audit": "export_audit.json",
            "status": "ok|pdf_only_no_png|pptx_only_no_renderer"},
 "degrade_chain": [{"stage": "probe|build|verify|render", "fallback": "...", "reason": "..."}],
 "status": "complete|partial|failed|blocked", "uncertainty": ["..."], "changelog": ["每条取舍与修复记录"]}
```
- 内嵌超 16384 token 时分批写：先骨架与 slides 前半，回填后半，每段 ≤1500 字。
- status 四级：complete=全链通过；partial=某阶段失败但有可评产物；failed=无可用产物（仍写全字段）；blocked=材料缺失（附原因）。

### 第 6 步 — 增益证据与消融（回填 result.json）
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --paper <论文文本> --write
python3 scripts/gain_evidence.py --result /app/output/result.json --paper <论文文本> \
    --deck /app/work/deck.json --evidence /app/work/evidence_map.jsonl --work /app/work --ablate --write
```
- 第一条：skill 模式实测（quote 可回证率/数值有据率/需人工核对条目）+ 基线对照削减量。
- 第二条：**消融双臂真跑**——臂A=原始 deck+evidence；臂B=注入污染反例的副本（quote 改写/证据行删除/悬空图号，写入 `/app/work/ablate/`）；同一校验器 run_gates 各跑一遍，逐闸门 FAIL 数差 + 机制→指标映射 + 边界 + 失效条件写入 `result.json.gain_evidence.ablation` 与 `result.json.efficiency`（本包仅此脚本写这两个键）。
- 闸门/校验失败**一律 verdict 记录、退出码 0**；未过就修一轮，仍不过如实写 gates 与 uncertainty 并继续交付。

## 2. 闸门四态（未跑 ≠ 通过）
`enforced` / `skipped_not_provided`（参数未给，warn+登记） / `not_found`（路径不存在） / `unreadable`（解析失败）。闸门 note 写明「下游不得宣称已核对」。

## 3. 异常处置与降级链（每级登记 degrade_chain）
| 情形 | 处置 |
|---|---|
| 模板缺失/损坏/非pptx | probe 落 ok:false 报告正常退出 → 学术默认版式构建 → uncertainty 登记 |
| python-pptx 缺失 | pptx_minimal stdlib 兜底（inheritance=standalone_minimal_fallback）；**禁止 pip 安装** |
| 版式缺失/占位符不够 | 最近版式+独立文本框，`template_slot_insufficient`，不改母版 |
| 字体缺失/乱码 | 有模板→继承主题字体；无模板→换实存 CJK 字体 |
| 图表提不出来 | 整页渲染 `page_p{n}.png`，`figure_mode=page_render`，禁止占位图 |
| 页数超限 | 先砍方法细节页；限制页/结果页不砍；changelog 记取舍 |
| 渲染失败/无渲染器 | render.status 如实登记，交 pptx+已完成部分，status=partial |

## 4. 最小调用示例（示意，非正式案例结果）
```bash
python3 scripts/probe_template.py /input/template.pptx --out /app/work/template_report.json   # → ok:true, layouts:N, majorFont=...
python3 scripts/extract_pdf.py /input/paper.pdf --outdir /app/work/extracted                  # → pages:N, figures:N
python3 scripts/pptx_verify.py PLAN /app/work/deck.json --paper /app/work/extracted/paper_text.txt \
    --evidence /app/work/evidence_map.jsonl --out /app/work/gate_report.json                  # → verdict:pass, quote_gate:enforced
python3 scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx /input/template.pptx \
    --report /app/work/template_report.json --log /app/output/layout_log.json                 # → builder: python-pptx/pptx_minimal
python3 scripts/render_export.py /app/output/deck.pptx --outdir /app/output/previews          # → consistency verdict + render.status
python3 scripts/gain_evidence.py --result /app/output/result.json --paper /app/work/extracted/paper_text.txt \
    --deck /app/work/deck.json --evidence /app/work/evidence_map.jsonl --ablate --write       # → ablation 两臂 FAIL 差
```

## 最小可运行自检清单（复制即跑）
```bash
python3 -c "import sys;print(sys.version)"                    # 1) 解释器可用
ls scripts/                                                   # 2) 脚本在位
python3 scripts/pptx_minimal.py                               # 3) 兜底构建器可执行（缺参 exit 0）
python3 scripts/gain_evidence.py --help                       # 4) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 5) 产物可解析
```
