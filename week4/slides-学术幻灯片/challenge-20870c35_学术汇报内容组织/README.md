# talk-plan — 使用与方法说明

> 本 README 与提交版本一致；示例均为**示意**，不冒充平台正式案例结果。

## 1. 这是什么

一个可被 Agent 调用的「学术汇报内容组织」技能：输入一份研究材料 + 受众/时长/页数约束，输出

1. `talk_plan.json` — **主产物**：报告目标、听众画像、受众适配决策、叙事分段与时长、逐页四元组（目的/要点/证据/时长）、问答准备；
2. `deck.pptx` — 由 talk_plan **派生**的可编辑幻灯片（含讲稿备注）；
3. `check_report.json` — 19 项机械校验结果（时长加总、页数密度、逐字引文、数字出处…）；
4. `result.json` — 把上述主产物**整体内嵌**，评审无需打开附件即可核对。

**核心主张**：汇报的组织质量可以被机械验证的只有三件事——每页有唯一主张且挂得住证据、时间加总自洽、取舍有记录。技能把这三件事做成脚本可查，而不是靠自述。

**适用**：论文/材料 → 组会、答辩、评审、基金申请、课堂、科普汇报；需要页级规划、讲稿与问答准备。
**不适用**：论文精读、学术写作成稿、科研绘图生产（相邻课题负责）；纯 PPT 美化/模板设计；材料缺失且无法说明时（应报 failed 而非编造）。

## 2. 依赖与运行环境

| 项 | 要求 | 缺失时行为 |
|---|---|---|
| Python | ≥3.9（标准库足够跑 `check`） | — |
| PyMuPDF (`fitz`) | `extract` 解析 PDF | 退回 `pdftotext`；再不行按纯文本读，并记 warning |
| python-pptx | `build` 生成可编辑 pptx | `build` 返回 `python_pptx_missing`，交付 status=partial |
| LibreOffice (`soffice`) | `render` 导出 PDF/PNG | `render` 返回 `no_renderer`，如实记录，不伪造成"已渲染" |
| CJK 字体 | 默认 `Noto Sans CJK SC`，可用 `TALKPLAN_CJK_FONT` 覆盖 | 渲染乱码时换 `fc-list` 实际存在的字体重建 |

安装：`pip install pymupdf python-pptx`（Harbor 环境通常预装；无需网络）。脚本无第三方配置、无个人路径依赖，路径一律由命令行参数传入。

## 3. 完整调用步骤

```bash
# 1) 读契约与材料（受众/时长/页数上限、output_contract 字段）
ls -la /input && cat /input/case.json
python scripts/talkplan.py extract /input/materials/paper.pdf --outdir /app/work/extracted
#    → /app/work/extracted/source_text.txt（带 ===== PAGE n ===== 锚点）+ extract_manifest.json

# 2) 写 talk_plan.json（模型响应完成；字段见 SKILL.md S2 与 examples/）
#    规则：页数上限≈duration÷1.5；正片分钟之和=duration；每页一主张≤25字

# 3) 机械校验（必须 pass）
python scripts/talkplan.py check /app/work/talk_plan.json \
  --source /app/work/extracted/source_text.txt --out /app/output/check_report.json

# 4) 出稿（有模板就带 --template，母版不改）
python scripts/talkplan.py build /app/work/talk_plan.json /app/output/deck.pptx \
  --template /input/template.pptx --log /app/output/layout_log.json
python scripts/talkplan.py render /app/output/deck.pptx --outdir /app/output/previews

# 5) 写 result.json（deliverable.slides 全量内嵌），并 cp talk_plan.json /app/output/talk_plan.v1.json
```

`check` 退出码：`0`=无 fail；`1`=有 fail（输出清单，逐条改计划）；`2`=源材料提取失败。

### 校验项清单（19 项）

| 代码 | 检查 | 不通过意味着 |
|---|---|---|
| C1_contract | case_id / duration_min / slides_max | 没读契约 |
| C2_audience / C2_goal / C2_adaptation | 受众分型、目标可检查、适配决策含 because+from | 受众适配不可核验 |
| C3_pages / C3_quad | 页数≤上限、页号唯一有序、四元组完整 | 有页缺目的/要点/证据/时长 |
| C4_time_sum / C4_section_cover / C4_density / C4_backup_zero | 节=页=总时长、节覆盖全部正片、单页 0.4–2.5min、备用页 0 分钟 | 页数与时长脱节（本题已知高频缺陷） |
| C5_granularity | claim ≤25 字、points ≤5 条、每条 ≤40 字 | 页面在"搬段落" |
| C6_evidence / C6_verbatim | 每页有 locator、quote 逐字命中源文本 | 引用错位或改写事实 |
| C7_numbers | 页内每个数字都能在本页 quote 或源文本找到 | 编造/取整数字 |
| C8_strength | 强度标注合法、弱证据不用"证明/首次" | 结论强度虚高 |
| C9_figure | figure 版式必须有 figure_ref，反之亦然 | 图文不对应 |
| C10_notes / C10_notes_qa | 备注 40–600 字、非复述、含预判问题 | 讲稿缺失或复读页面 |
| C11_qa | ≥4 条、覆盖 ≥3 类、pointer 页与备用页真实存在 | 问答准备对不上页面 |

## 4. 最小调用示例（示意，非正式案例结果）

**示例材料**（作者编写的演示文本，**不是真实论文**，为便于复跑而随文档给出）：

```text
===== PAGE 1 =====
示例材料：本文件仅用于演示接口，不是真实论文。
现有方案在 8 层堆叠下良率下降到 62%，主要原因是界面缺陷。
我们提出双层钝化工艺，在同样 8 层堆叠下把良率提升到 94%。
===== PAGE 2 =====
消融实验显示，去掉第二层钝化后良率回落到 71%。
作者指出，本结论仅在 4 英寸晶圆上验证，未覆盖 12 英寸产线。
```

把它存为 `/app/work/extracted/source_text.txt`，配合 `examples/example-talkplan.json`（15 分钟答辩、10 正片 + 2 备用页）：

```bash
python scripts/talkplan.py check examples/example-talkplan.json \
  --source /app/work/extracted/source_text.txt --out /tmp/check_report.json
```

真实输出（本机实测）：

```json
{"total": 19, "pass": 19, "fail": 0, "warn": 0, "verdict": "pass"}
{"duration_min": 15.0, "section_sum": 15.0, "slide_sum": 15.0,
 "main_slides": 10, "backup_slides": 2, "minutes_per_slide": 1.5,
 "evidence_rows": 13, "qa_items": 4}
```

```bash
python scripts/talkplan.py build examples/example-talkplan.json /tmp/deck.pptx --log /tmp/layout_log.json
# → {"ok": true, "slides": 12, "warnings": 0}   （12 页，备注已写入 notes）
python scripts/talkplan.py render /tmp/deck.pptx --outdir /tmp/previews
# → {"status": "no_renderer", "error": "soffice/libreoffice not found"}   本机无 LibreOffice 时的真实返回
```

### 标注示意：单页四元组长什么样

```json
{"no": 6, "section": "result", "layout": "bullets",
 "purpose": "用消融证明第二层不可省",
 "claim": "去掉第二层，良率回落到 71%",
 "points": ["完整双层：94%", "去掉第二层：71%"],
 "evidence": [{"locator": "示例材料 PAGE 2 第 1 句", "quote": "消融实验显示，去掉第二层钝化后良率回落到 71%。"},
              {"locator": "示例材料 PAGE 1 第 3 句", "quote": "我们提出双层钝化工艺，在同样 8 层堆叠下把良率提升到 94%。"}],
 "minutes": 1.5, "evidence_strength": "强", "figure_ref": null,
 "notes": "唯一强证据页：同条件消融对照。先给 94% 再给 71%，让差值自己说话；语气用『支持』而非『证明』，因为只有单批次。若被问批次一致性，指向第 12 页。"}
```

四个字段各管一件事，缺一个就不成页：`purpose`（这页要让听众相信什么）→ `claim`（唯一主张）→ `evidence`（挂哪句原文）→ `minutes`（值多少时间）。`notes` 是给讲者的话，与页面文字分离。

## 5. 失败处理与自查

- `check` 报 fail：改 `talk_plan.json`（改主张 / 删无据数字 / 调 section 分钟），**不要改校验规则**。
- 材料是扫描件：`extract` 返回 `scanned: true` → OCR 或整页渲染，locator 用 `PAGE n`，uncertainty 注明。
- 时间/页码冲突：先砍 `adaptation` 标为低优先级的内容，再重跑 check；取舍写进 `changelog`。
- 交付前跑 SKILL.md §4 的 8 项自查；`status` 只写事实（complete / partial / failed），失败阶段写明。

## 6. 维护信息

| 项 | 值 |
|---|---|
| 版本 | v2（2026-11，针对 72 分版重做：主产物内嵌 + 机械校验 + 单一事实源） |
| 维护 | 改校验规则须同步改本文 §3 清单与 `examples/`，并重跑示例保证 `verdict=pass` |
| 已知限制 | 语义层面（图号是否张冠李戴、机制解释是否正确）脚本查不出，需按 locator 回查原文/图片；PDF 版式复杂时 `pdftotext` 降级可能打乱引用顺序 |
