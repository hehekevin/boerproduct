---
name: paper2deck-edit-skill
description: 学术PPT生成与编辑技能：读 /input/case.json 契约+slide-workorder工单（mode/页数/受众/保真/模板继承），材料提取（PyMuPDF→pdftotext→material.json→起始稿四级降级），排页与证据映射（每条事实挂逐字quote回证材料原文），构建前闸门（内容对齐+结构校验双闸）→构建（generate模板克隆继承/edit工单原位编辑保真其余页+change_log）→fit_audit模板对账→PDF/PNG/SVG三级渲染→--ablate双臂消融+污染反例真跑增益。产出原生可编辑presentation.pptx与result.json（case_id/status/editable_source/export_artifact/content_map/compliance_checks/exceptions全字段不删键）。Use when the task asks to generate or edit an academic slide deck (学术汇报/答辩/组会/演示稿迭代) with evidence tracing, template compliance and honest degradation.
---

# paper2deck-edit — 学术PPT生成与编辑（工单驱动 · 证据回证 · 保真编辑）

产出主产物是 **result.json 全量内嵌的 content_map（逐页主张/要点/图表/备注/证据定位）**，配套实物是原生可编辑 presentation.pptx + 导出件 + fit_audit 对账 + change_log 修改记录。硬规则：**任何数字、单位、方法名、结论上页前必须挂一条逐字 quote 回证材料原文；引不对就改页，不改 quote 迁就页**。编辑模式下工单之外的内容零改动（source preservation）。

## 0. 执行协议（最高优先级，先于一切工作）

1. **第1步（首个响应内）**：读 `/input/case.json`，把 `output_contract` **全部字段名原样抄下** + `case_id`。本题契约字段：case_id / status / editable_source / export_artifact / content_map / compliance_checks / exceptions。
2. **第2步（同响应内）**：立即写 `/app/output/result.json` **骨架**（case_id + 全字段，值 null，`status:"in_progress"`）。此后每完成一步回填；即使熔断/崩溃，result.json 必须存在、字段完整、JSON 合法（失败也交付）。
3. **每步一次写盘**：脚本输出或 result.json 回填，不许只打印不落盘。
4. **广度优先**：先跑通全链拿到可评产物，再逐页精修；禁止单页打磨到完美才继续。
5. **预算熔断**：56 次模型请求 / 800 秒即停止新工作，保存已有产物，status 如实降级 partial。
6. **写盘前 JSON 自检**：`python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"`；字段只增不减。
7. **不许编造**：数字/quote/模板值/渲染状态只来自机器输出；材料缺失、无法判断、运行失败三者**分开**写进 exceptions。
8. **退出码纪律**：所有脚本所有失败路径 exit 0（校验失败/argparse错误/内部异常一律 0），verdict 照实写 JSON，语义值返回不是退出码。

## 1. 主流程（线性 6 步）

### 第 1 步 — 契约、骨架、探查（1 次响应内完成）
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/probe_input.py --input-dir /input --out /app/work/probe_report.json
python3 scripts/extract_source.py <材料.pdf或material.json> --outdir /app/work/extracted \
    --starting-deck <起始稿.pptx>   # 无材料时以起始稿文本为弱基线并登记 exceptions
```
- 按 protocol 1、2 抄契约、写骨架。probe_report.workorder 给出 mode(generate/edit)/受众/页数约束/保真/模板继承——**只抄真实存在的键，缺键记 unknown 不臆测**；把页数上限等写进 `/app/work/constraints.json`。
- 模板探查产出版式清单与主题 majorFont/minorFont/accent1-6；后续模板映射必须引用这里的原始值，不许手抄转述。scanned 材料走页码定位；图少于正文提及走整页渲染 `figure_mode:"page_render"`，**禁止占位图**。

### 第 2 步 — 页计划与证据映射（1-2 次响应）
产出 `/app/work/deck.json` 与 `/app/work/evidence_map.jsonl`（schema 示意，非答案）：
```json
{"meta": {"title": "...", "mode": "generate|edit", "template": "<模板路径或null>"},
 "slides": [{"no": 3, "role": "problem|method|result|limitation|conclusion|title",
             "layout": "title|bullets|bullets+figure|table|closing", "title": "≤25字主张",
             "bullets": ["≤40字，≤5条"], "figure": {"path": "...", "caption": "图注原文",
             "source_locator": "Fig.2 p.5"}, "notes": "过渡+强调+预判问题(40-800字，不复述页面)"}]}
```
evidence 每行 `{"slide_no","claim","type":"figure|table|section|quote","locator":"Fig.1 p.3 / §3.2","quote":"逐字原文"}`。
- generate：标题→问题→方法→结果（每关键结果一页）→限制→结论；**按贡献排页序不是按章节搬运**；超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- edit：先从 probe_report.starting_deck 逐页文本起草受影响页清单，再逐条写编辑操作（第 4 步的 edits.json），**工单未涉及的页不动**。示意图不是实验数据：`type:figure` 的页不得从图读数，数值必须另有 quote 行。

### 第 3 步 — 构建前闸门（fail 必须修完才准构建）
```bash
python3 scripts/gate_verify.py PLAN /app/work/deck.json --source /app/work/extracted/source_text.txt \
    --evidence /app/work/evidence_map.jsonl --constraints /app/work/constraints.json \
    --out /app/work/gate_report.json
```
- **内容对齐闸门**：每条 quote 空白归一化后逐字出现在材料原文（改写/取整/换算一律 fail）；页面每个百分数/小数/带单位数必须在该页 quote 里逐字出现。
- **结构校验闸门**：页数上限、备注 40-800 字非复述、要点≤5、单页密度、布局预算（字号阶梯 18→16→14→12→11→10，10pt 仍溢出删内容不许再缩）。
- verdict=fail → 改页面或补 quote，**不许改 quote 迁就页面**；确属模板占位/页码等新数字登 exceptions。四态显式（enforced/skipped_not_provided/not_found/unreadable），未跑的闸门在 exceptions 登记「不得宣称已核对」。校验器恒 exit 0，禁止以非零退出码结束。

### 第 4 步 — 构建 + 校验 + 对账 + 渲染
```bash
# generate 模式
python3 scripts/deck_build.py /app/work/deck.json /app/output/presentation.pptx --mode generate \
    --template <模板.pptx> --report /app/work/probe_report.json --log /app/output/layout_log.json
# edit 模式（先写 /app/work/edits.json：{"ops":[{"op":"set_title","slide":2,"text":"..."},...]}）
python3 scripts/deck_build.py /app/work/edits.json /app/output/presentation.pptx --mode edit \
    --starting-deck <起始稿.pptx> --log /app/output/change_log.json
python3 scripts/gate_verify.py /app/output/presentation.pptx /app/work/deck.json \
    --source /app/work/extracted/source_text.txt --evidence /app/work/evidence_map.jsonl \
    --out /app/output/verify_report.json
python3 scripts/fit_audit.py /app/output/presentation.pptx --deck /app/work/deck.json \
    --report /app/work/probe_report.json --log /app/output/layout_log.json --out /app/output/fit_audit.json
python3 scripts/render_preview.py /app/output/presentation.pptx --outdir /app/output/previews --log /app/output/render_log.json
```
- generate：有模板 → 克隆模板填充（deck 未显式指定字体/颜色时 run 不写 typeface 与颜色，交给母版主题，改主题即整册换字变色）；python-pptx 缺失 → pptx_minimal stdlib 兜底（评测沙箱无 pip，**禁止安装依赖**），inheritance 如实登记 standalone_minimal_fallback。
- edit：先整份复制起始稿再原位改，每条操作 applied/fallback/skipped 记入 change_log；stdlib 兜底不支持删页/重排时如实登记，不许谎报已改。
- 渲染三级：soffice PDF+PNG → COM → stdlib 逐页 SVG 兜底；无渲染器如实记 no_renderer 不伪造。渲染后抽查：乱码/溢出/图片变形 → 修复重跑本步。
- `cp /app/work/deck.json /app/output/deck.v1.json` 存交付版快照；多轮迭代每轮存 `deck.vN.json`，result.json.changelog 写明每轮改了什么、为什么。

### 第 5 步 — 增益证据（真跑，禁止文字声明）
```bash
python3 scripts/ablate_gain.py --deck /app/work/deck.json --evidence /app/work/evidence_map.jsonl \
    --source /app/work/extracted/source_text.txt --result /app/output/result.json \
    --workdir /app/work/ablation --write
```
- 双臂消融：full（全闸门）vs ablated（`--skip-content-gate --skip-structure-gate`），**同一校验器 gate_verify 两臂各跑一遍**，FAIL 数差是机器判定。
- 污染反例：错数字取整+编造 quote 注入**副本**，full 臂复核，检出 fail 数>0 才证明校验器敏感；=0 必须如实上报。
- 结果写入 result.json 的 `gain_evidence` 与 `efficiency`（本包唯一写这两个键的脚本）。

### 第 6 步 — result.json 定稿（主产物全量内嵌，禁止手写对账值）
```json
{"case_id": "...", "status": "complete|partial|failed|blocked",
 "editable_source": {"file": "presentation.pptx", "pages": N, "mode": "generate|edit",
                     "builder": "deck_build.build_info", "inheritance": "real|standalone_minimal_fallback",
                     "source_preserved_pages": "edit 模式未改动页数", "version_snapshots": ["deck.v1.json"]},
 "export_artifact": {"pdf": "previews/deck.pdf", "previews": "previews/", "status": "ok|pdf_only_no_png|svg_only_no_pdf|no_renderer",
                     "render_log": "render_log.json"},
 "content_map": ["verify_report.json 的 slides_embed 全量内嵌：每页 no/role/title/bullets/figure/notes/evidence(type+locator+quote)"],
 "compliance_checks": {"fit_audit": "fit_audit.summary 全量内嵌", "gates": {"content_gate": "四态+fail数", "structure_gate": "四态+fail数"},
                       "change_log": "edit 模式逐条 applied/fallback"},
 "exceptions": {"missing_material": ["材料缺失项"], "unverifiable": ["无法判断项"], "run_failures": ["运行失败项"], "degrade_chain": ["每级降级记录"]},
 "gain_evidence": {}, "efficiency": {}, "uncertainty": ["..."], "changelog": ["每条取舍与修复"]}
```
- 内嵌超 16384 token 分批写：先骨架与 content_map 前半，回填后半，每段 ≤1500 字。status：complete=全链通过；partial=某阶段失败但有可评产物（写明哪步）；failed=无可用产物（仍写全字段）；blocked=材料缺失无法开始。

## 2. 异常处置与降级链（每级登记 exceptions.degrade_chain）

| 情形 | 处置 |
|---|---|
| 模板缺失/损坏/非pptx | probe 落探查失败报告正常退出 → 学术默认版式构建 → 登记 |
| python-pptx 缺失 | stdlib 兜底（pptx_minimal 构建 / raw-xml 编辑），禁装依赖 |
| 工单缺键/无工单 | mode 按有无起始稿推断，页数按 task.md；缺键记 unknown 不臆测 |
| 材料缺失/扫描件 | 起始稿文本弱基线（登记不可宣称回证）或 OCR/页级渲染，locator 用页码 |
| 图提不出来 | 整页渲染 page_render，禁止占位图；位图无法取数→引用原图并登记 |
| 编辑操作无目标占位符 | change_log 记 fallback，不静默跳过，不谎报已改 |
| 页数超限 | 先砍方法细节页，结果页/限制页不砍，changelog 记取舍 |
| 渲染失败 | render_log 记原因，交 pptx+已完成部分，status=partial |

## 3. 最小调用示例（示意，非正式案例结果）
```bash
python3 scripts/probe_input.py --input-dir examples/fake_input --out /tmp/probe.json        # → contract 字段7个, mode:generate
python3 scripts/extract_source.py examples/fake_input/material.json --outdir /tmp/extracted # → tool:material_json
python3 scripts/gate_verify.py PLAN examples/deck.json --source /tmp/extracted/source_text.txt \
    --evidence examples/evidence.jsonl --out /tmp/gate.json                                  # → verdict:pass
python3 scripts/deck_build.py examples/deck.json /tmp/presentation.pptx --mode generate --log /tmp/log.json  # → builder:pptx_minimal(stdlib)
python3 scripts/fit_audit.py /tmp/presentation.pptx --log /tmp/log.json --out /tmp/fit.json  # → verdict:pass
python3 scripts/render_preview.py /tmp/presentation.pptx --outdir /tmp/previews              # → status:svg_only_no_pdf(无Office时)
python3 scripts/ablate_gain.py --deck examples/deck.json --evidence examples/evidence.jsonl \
    --source /tmp/extracted/source_text.txt --result /tmp/result.json --workdir /tmp/abl     # → detected_fails>0
```

## 4. 交付自查清单
- [ ] result.json 含 case_id 与契约全部字段，无未解释 null；content_map 全量内嵌且每页带 evidence
- [ ] 构建前闸门 verdict=pass（content_gate+structure_gate 均 enforced 且 fail=0）
- [ ] 页面数字全部回证；quote 逐字未改写；edit 模式工单外页面零改动
- [ ] 每页一主张、要点≤5、notes 40-800 字非复述；fit_audit 无未处理 fail
- [ ] presentation.pptx 可打开可编辑；导出件状态如实；degrade_chain 完整
- [ ] gain_evidence/efficiency 来自 --ablate 真跑；status/uncertainty/changelog 诚实

## 最小可运行自检清单（复制即跑，逐条 exit 0）
```bash
python3 -c "import sys;print(sys.version)"                    # 1) 解释器可用
test -f scripts/gate_verify.py && echo scripts_ok             # 2) 脚本在位（校验式命中）
python3 scripts/pptx_minimal.py examples/deck.json /tmp/_self.pptx  # 3) 兜底构建器可执行
python3 scripts/gate_verify.py PLAN examples/deck.json --out /tmp/_self_gate.json  # 4) 校验器可执行
python3 scripts/ablate_gain.py --help >/dev/null              # 5) 增益脚本可执行
python3 -c "import json;print(json.load(open('/tmp/_self_gate.json'))['summary']['verdict'])"  # 6) 报告可解析
```
