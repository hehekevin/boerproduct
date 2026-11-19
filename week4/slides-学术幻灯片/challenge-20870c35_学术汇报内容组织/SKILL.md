---
name: talk-organizer
description: 学术汇报内容组织技能：把已完成的论文/研究材料组织成可上台的学术汇报。围绕五个机制——报告目标→页数时长结论强度、听众画像→铺垫比例与术语深度、叙事取舍（不按论文章节搬运）、页级唯一主张+逐字证据回证、问答预演（每页 Q: 预判追问）。产出一键可编辑 pptx（纯标准库构建）+ 手写 SVG 逐页预览 + 页级证据映射，全部闸门机器可判。Use when the task asks to organize a research paper/material into an academic talk (学术汇报/组会/答辩/评审PPT) with traceable evidence, audience-fit narrative and Q&A preparation.
---

# talk-organizer — 学术汇报内容组织（主张唯一 · 证据逐字回证 · 问答预演）

产出的可评主体是 result.json 内嵌的 **slides 全量结构**（页号/角色/主张/要点/证据定位/讲稿备注/预判问题）。硬规则：**每页恰一个主张；主张与数字上页前必须有逐字 quote 回证源材料；每页备注必含 `Q:` 预判追问**。叙事服务于听众与时长，不按论文章节搬运。

## 0. 执行协议（最高优先级）

1. **第1步（首个响应内）**：读 `/input/case.json`，把 `output_contract` 全部字段名原样抄下 + `case_id`。
2. **第2步（同响应内）**：写 `/app/output/result.json` 骨架（case_id + 全字段=null + `status:"in_progress"`），之后逐步回填；即使熔断，result.json 必须存在、字段完整、JSON 合法。
3. **每步一次写盘**：脚本输出或 result.json 回填，不许只打印不落盘。
4. **广度优先**：先全链路拿可评产物，再逐页精修。
5. **预算熔断**：52 次模型请求 / 750 秒即停新工作，status 如实降级 partial。
6. **写盘前 JSON 自检**：`python3 -c "import json;json.load(open('/app/output/result.json'))"`。
7. **不许编造**：quote/数字/渲染状态只来自机器输出；材料缺失、无法判断、运行失败分开写进 uncertainty。
8. **所有失败路径退出码 0**：闸门 fail、材料缺失、argparse error 一律 exit 0，结论写 JSON，不以退出码表达成败。

## 1. 主流程（线性 6 步）

### 第 1 步 — 契约、骨架、材料与约束
```bash
python3 scripts/probe_contract.py --case /input/case.json --input-dir /input \
    --task /input/task.md --out /app/output/result.json --work /app/work
```
- 脚本抄契约、写骨架、扫 `/input` 材料（校验式命中：可读+可解码+非空）、产出 `/app/work/source_text.txt` 与 `/app/work/constraints.json`（听众/时长/页数关键词提取，best-effort）。
- PDF 原件登记 `needs_platform_pdf_tool`：用平台 pdf-text-tool 提取文本、pdf-render-tool 渲染图页，结果**追加**写入 source_text.txt（locator 记页码）。不伪造 PDF 文本。
- constraints 提取不到听众/时长时，在 uncertainty 登记「约束自拟，未获题面确认」。

### 第 2 步 — 组织决策（模型核心工作，1-2 次响应）
产出 `/app/work/deck.json`（deck schema 示意，非正式答案）：
```json
{"meta": {"title": "...", "audience": "组会|答辩|评审", "duration_min": 12,
          "narrative_rationale": "为何此顺序（一句话/页取舍记录）"},
 "slides": [{"no": 3, "role": "problem|method|result|limitation|conclusion|title|section|backup",
             "layout": "title|section|bullets|table|closing", "title": "≤25字",
             "claim": "本页唯一主张≤40字", "bullets": ["≤40字，≤5条"],
             "evidence": [{"type": "figure|table|section|quote", "locator": "Fig.2 p.5 / §3.2",
                           "quote": "逐字原文，空白归一化后须在源文本中出现"}],
             "notes": "过渡+强调点+Q: 预判追问及口径（40-800字，不复述页面）"}]}
```
- **报告目标**：先写一句「本次汇报要达成什么」，据此定页数（受 constraints.slide_limit）与结论强度；目标记入 meta.narrative_rationale。
- **听众画像**：constraints.audience 决定铺垫比例与术语深度——组会=方法细节多、答辩=创新点前置、评审=证据强度前置；画像记入 meta。
- **叙事顺序**：title→problem→method→result(每关键结果一页)→limitation→conclusion；按贡献排页，**不按论文目录搬运**；超限先砍方法细节页，不砍结果页与限制页，取舍写进 narrative_rationale。
- **重点信息**：每页唯一 claim；支撑细节不上主张，只进 notes 或 backup 页；数字必须在该页 quote 中逐字出现。
- **问答预演**：每个内容页 notes 必含至少一条 `Q:` 预判追问+口径一致的回答；高风险页（结果/限制）各配一条追问。

### 第 3 步 — 构建前闸门（fail 必须修完才准构建）
```bash
python3 scripts/verify_gate.py --plan /app/work/deck.json \
    --source /app/work/source_text.txt --constraints /app/work/constraints.json \
    --out /app/work/gate_report.json
```
- 6 项机械检查：quote 逐字回证 / 数字回证 / 页级唯一主张 / 备注含问答 / 叙事骨架 / 证据覆盖；另有时长软检查（讲稿字数/240≈分钟数）。
- verdict=fail → 改页面或补 quote，**不许改 quote 迁就页面**；闸门退出码恒 0，失败只经 verdict/报告传递。
- 未运行或缺源文本的闸门为 skipped_not_provided：在 uncertainty 登记「不得宣称已核对」。

### 第 4 步 — 构建 + 渲染 + 抽查
```bash
python3 scripts/build_deck.py /app/work/deck.json /app/output/deck.pptx --log /app/output/build_log.json
python3 scripts/render_preview.py --plan /app/work/deck.json --pptx /app/output/deck.pptx \
    --outdir /app/output/previews --log /app/work/render_log.json
```
- build_deck 纯标准库产出可编辑 16:9 pptx（含真实备注页），claim 以强调行上页。
- render_preview 手写 SVG 逐页预览 + index.html（零浏览器依赖）；检测到 soffice/libreoffice 时顺带转 PDF，否则 render_log 如实记 `no_office_renderer`，不伪造。
- 平台 office-renderer 可用时，用它对 pptx 出 PDF/PNG 存 `/app/output/previews`，替换/补充 SVG 预览。
- 抽查 SVG：标题/主张/要点/证据定位是否齐全、有无截断；发现问题改 deck.json 重跑第 3-4 步。

### 第 5 步 — 增益层：同输入消融 + 污染反例（必须真跑）
```bash
python3 scripts/ablate.py --plan /app/work/deck.json --source /app/work/source_text.txt \
    --constraints /app/work/constraints.json --result /app/output/result.json \
    --out /app/work/ablation_report.json --write
```
- 三臂同一校验器（verify_gate.evaluate）各跑一遍：A=skill 完整计划；B=消融臂（删证据映射/删问答预判/删页级主张，模拟搬运式基础路径）；P=A 的副本注入捏造主张+数字+引文。
- FAIL 数差与逐项指标差是机器判定；污染反例必须被闸门捕获（validator_sensitivity.machine_verdict=true），未捕获如实记 false。
- `--write` 把 `gain_evidence`（机制→指标映射+边界+失效条件）与 `efficiency` 写入 result.json（仅此脚本写这两个键）。

### 第 6 步 — result.json 定稿（字段只增不减）
- `deliverable.slides`：deck.json 全量内嵌（每页含 evidence locator+quote）；`evidence_map`：全部证据行；`render`：previews 路径 + render_log 状态；`gates`：gate_report.json 的 gates+metrics 内嵌。
- 回填 `status`（complete=闸门全 enforced 且 fail=0；partial=某阶段失败但有可评产物，写明哪步；failed=无可用产物仍写全字段；blocked=材料缺失，附原因）、`uncertainty`、`changelog`（取舍/修复逐条）。
- 内嵌超长分批写：先骨架与 slides 前半，再回填后半，每段 ≤1500 字。

## 2. 闸门四态
`enforced`（已执行计入总账）/ `skipped_not_provided`（参数未给，warn+登记）/ `not_found`（路径不存在，warn+登记）/ `unreadable`（存在但解析失败，warn+登记）。未跑 ≠ 通过；note 一律写明「下游不得宣称已核对」。

## 3. 异常处置与降级链（每级记 changelog）
| 情形 | 处置 |
|---|---|
| case.json 缺失/不可解析 | probe 照常 exit 0，骨架含通用字段，status=blocked |
| PDF 无文本层 | 平台 pdf-render-tool 整页渲染，locator 用页码，禁占位文本 |
| 源文本为空 | quote/数字闸门 skipped，ablate 如实登记「增益差不可机器判定」 |
| 页数超时长 | 先砍方法细节页，结果/限制页不砍，取舍记 narrative_rationale |
| 构建失败 | build_log 记 error，重试一轮，仍失败交 deck.json+SVG，status=partial |
| 无 soffice/office-renderer | SVG 预览交付，render 记 no_office_renderer，不伪造 PDF |
| 脚本任何异常 | 退出码恒 0，错误写进 JSON 与 uncertainty |

## 4. 最小调用示例（示意，非正式案例结果）
```bash
python3 scripts/probe_contract.py --case /input/case.json --input-dir /input --out /app/output/result.json --work /app/work   # → contract_fields 4, source_chars 323
python3 scripts/verify_gate.py --plan /app/work/deck.json --source /app/work/source_text.txt --out /app/work/gate_report.json # → verdict:pass, fails_total:0
python3 scripts/build_deck.py /app/work/deck.json /app/output/deck.pptx --log /app/output/build_log.json                      # → {"ok":true,"slides":6}
python3 scripts/render_preview.py --plan /app/work/deck.json --pptx /app/output/deck.pptx --outdir /app/output/previews       # → {"svg_ok":true,"pages":6}
python3 scripts/ablate.py --plan /app/work/deck.json --source /app/work/source_text.txt --result /app/output/result.json --write  # → diff fails_total:-18, sensitivity:true
```
plan 输入样例见 `examples/example_plan.json`（示意，非正式案例）。

## 5. 交付自查清单
- [ ] result.json 含 case_id 与 output_contract 全部字段，JSON 可解析，无未解释 null
- [ ] 构建前闸门 verdict=pass 且 6 闸门全 enforced、fail=0（未跑的如实 skipped）
- [ ] 每页唯一 claim、要点 ≤5、notes 40-800 字且含 Q: 预判追问
- [ ] quote 逐字回证、数字全部有据、未改写事实；示意图页不从图读数
- [ ] deck.pptx 可编辑、previews 有逐页 SVG（或平台渲染 PDF/PNG）、状态如实
- [ ] gain_evidence 与 efficiency 为本次真跑数字；污染反例被捕获
- [ ] status/uncertainty/changelog 诚实；取舍可复核
