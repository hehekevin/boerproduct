---
name: acwrite-structure
description: 论文结构与逻辑优化技能：把稿件拆成论断-论据链做结构诊断，问题定位到章节/段落/句子并分类（论证断裂/跳跃/循环/重复/顺序/结论越界），输出可执行编辑动作清单（移动/合并/拆分/收窄）+ 修订后全文。每处修改带逐字前后对照留痕（original/revised/reason/basis/段落定位），诊断报告与修订后全文完整嵌入 result.json，评分者无需打开原稿即可逐条复核。Use when the case asks to diagnose and fix paper structure, logic gaps, claim-evidence alignment, repetition, or overclaimed conclusions — producing traceable, executable edit operations rather than a rewrite.
---

# acwrite-structure — 结构诊断与逻辑优化（定位到句 · 逐字留痕 · 全文嵌入可复核）

结构优化不是重写一稿，而是**诊断到句、动作到段、留痕到字**。每条判断指回原文位置；每处修改给出逐字前后对照；诊断与修订全文完整嵌入 result.json，作者与复核者不用打开原稿即可核对。交付三件套：

1. **诊断报告**：structure_issues.jsonl（定位/类型/严重度/原文摘句/依据/动作）+ diagnosis.md（人读版）
2. **修订产物**：revised_outline.md（骨架+来源映射）+ revised.docx/md（修订后全文）+ edits_before_after.jsonl（逐字前后对照）
3. **可核验交付**：verify_report.json（动作落地自检）+ result.json（诊断 issues、逐字对照、修订全文全部嵌入）

## 0. 强制执行协议（置顶，任何情况下先走这一节）

1. **抄契约**：`cat /input/case.json`，把 `output_contract` 的字段名**逐字抄下**（一个不缺）记入 work 笔记；同时读 `/input/task.md` 与待诊断稿件，**以真实稿件内容为准，不依据标签猜内容**。
2. **立即落骨架**：`python scripts/extract_materials.py --input /input --outdir /app/work/extracted && python scripts/build_result.py --case /input/case.json --out /app/output/result.json --scaffold`。骨架含全部契约字段（值为 null）+ `status:"pending"`。**写盘自检**：`cat /app/output/result.json` 确认字段在盘上。
3. **广度优先**：先对全文六类问题（研究问题对齐/章节顺序/论证链/段落重复/结论边界/贡献错配）各扫一遍拿到问题清单，再深化；不要在一个章节上耗尽预算。
4. **熔断**：模型请求数 ≥48 或运行 ≥700 秒（平台预算 64 请求/900 秒，留安全余量）→ 立即跳到 Stage 4，用手头已有材料组装交付，`status` 如实标 `partial`，并说明缺了哪几步。**失败也要交付**：哪怕只有骨架，也交付 result.json（字段齐全、status 诚实）。
5. **每阶段结束写盘自检**：产物文件存在、非空、JSON 可解析，才进入下一阶段。

## 1. 阶段流程（线性 5 步）

### Stage 0 — 契约、材料抽取与骨架（协议第 1-2 条，1-2 次脚本）
```bash
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --scaffold
cat /app/output/result.json   # 写盘自检：契约字段一个不缺
```
constraints.json 记：诊断范围（哪些章节）、学科/体裁、稿件类型（全文/摘要/报告）。材料不足（缺章节/无参考文献/稿件截断/图表公式缺失）→ 记入 manifest 的 gaps，后续进 uncertainty，**不虚构**。

### Stage 1 — 结构快照与论断-论据链（1 次响应，/app/work/claim_chain.jsonl）
段落锚点：按"§章.节 para段序"编号。逐节抽取论断链：
`{"aid":"A01","kind":"research_question|contribution|method_claim|result_claim|conclusion","text":"逐字或近原句","locator":"§2 para3","evidence":["A05"],"evidence_kind":"本研究数据|文献[3]|逻辑推理|无"}`
- 专查：研究问题是否清楚提出并贯穿全文；贡献主张有几条、与实际工作是否一致；每条结论的支撑是什么。

### Stage 2 — 结构诊断（1-2 次响应，/app/work/structure_issues.jsonl）
每条问题一行：
`{"sid":"S01","location":"§4.2 para2","quote":"≤40字原文逐字摘句","type":"claim_evidence_gap|logic_jump|circular|repetition|structure_order|contribution_mismatch|conclusion_overreach|missing_limitation","severity":"high|mid|low","why":"依据：指认论断链哪条断裂/哪条重复","fix":"一句话动作","fix_ops":[{"op":"move|merge|split|narrow|delete|add_transition","target":"§4.2 para2","to":"§3.1 后","detail":"…"}]}`

诊断规则（对号入座，禁止空泛写作原则）：
- **论断-论据断裂**：结论句在链上无 evidence 或 evidence_kind=无 → high。
- **论证跳跃**：指出缺哪一步中间环节（add_transition 或补论据）。
- **循环论证**：指出 A⇄B 回路的两个定位点。
- **重复内容**：指明保留哪处（保留信息更全者），另一处 merge/delete。
- **结构顺序**：铺垫后置/细节前置/章节该合并 → move + 理由。
- **贡献错配 / 结论越界**：narrow，**必须给出收窄后的替代表述**；越界含"相关写成因果""初步写成定论""缺局限说明"。
- severity 看影响面：动摇主结论=high；局部表达=low。**不把风格偏好当结构错误**；诊断不到的类别如实写"未发现该类问题"。

### Stage 3 — 修订与逐字留痕（1-2 次响应，核心可核验产物）
1. 执行全部结构类动作（move/merge/split）→ revised_outline.md（新骨架+每节来源映射"原§x.y para n"）。
2. 对 high 级问题执行语句级修复 → revised_draft.json → 全文：
```bash
python scripts/docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
```
3. **每处修改登记逐字前后对照**（/app/work/edits_before_after.jsonl）：
`{"sid":"S01","location":"§4.2 para2","original":"≤40字原句逐字","revised":"修改后句","reason":"一句话","basis":"依据 S01/论断链 A05"}`
   - original 必须是原稿逐字摘句（≤40 字，可在原稿中检索到）；revised 是落地到修订稿的句子；未改动的段落**逐字保留**。
4. 需作者决策的动作（如删整段）→ action_ledger.jsonl status=needs_author，**不在稿内擅自执行**。

### Stage 4 — 校验、嵌入与交付（3 次脚本 + 熔断出口）
```bash
python scripts/verify.py --edits /app/work/edits_before_after.jsonl --original /app/work/extracted --revised /app/output/revised.md --out /app/output/verify_report.json
python scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --embed-diagnosis /app/work/structure_issues.jsonl --embed-chain /app/work/claim_chain.jsonl \
  --embed-edits /app/work/edits_before_after.jsonl --embed-revised /app/output/revised.md \
  --artifact /app/output/revised.docx --verify /app/output/verify_report.json --status complete \
  --notes 'needs_author 项;诊断未覆盖章节及原因;收窄表述待作者确认'
python scripts/render_preview.py --src /app/output/revised.docx --outdir /app/output/previews   # 失败不阻塞
```
- verify.py 检查：每条 original 可在原稿定位、revised 已落进修订稿、无未授权改动 → verdict=pass/fail。
- build_result.py 把 **diagnosis.issues、claim_chain、edits_before_after、revised_text（修订全文）完整嵌入** result.json —— 复核者不需要打开原稿即可逐条核对。
- 最终写盘自检：`python -c "import json;d=json.load(open('/app/output/result.json',encoding='utf-8'));print(d['status'],len(d.get('diagnosis',{}).get('issues',[])),len(d.get('edits_before_after',[])))"`。字段缺失/值为 null 且无法补 → status 降级如实标注。

## 2. 异常处置表

| 情形 | 处置 |
|---|---|
| 稿件无明确研究问题 | type=missing_research_question，列候选问题，标 needs_author |
| 结论链全文无支撑 | 不改写全文；输出最小修复动作 + 需补实验/数据清单 |
| 重复段落是刻意呼应 | 保守不合并，why 说明判断依据 |
| 多章节长文档 | 按章诊断，跨章问题单列 type=cross_chapter_issue |
| 稿件被截断/缺章节 | gaps 记入 uncertainty，只诊断实际存在部分 |
| 诊断与作者风格冲突 | 语句级建议标 needs_author，结构级照常执行 |
| 稿件是摘要/短文 | 链抽取降到句级，诊断仍逐条定位 |

## 3. 最小调用示例（示意，非正式结果）
```bash
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --scaffold
# （模型响应：claim_chain.jsonl 31 条论断 / structure_issues.jsonl 14 条问题，全部带 locator+quote+fix_ops；
#   edits_before_after.jsonl 18 条逐字对照）
python scripts/docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
python scripts/verify.py --edits /app/work/edits_before_after.jsonl --original /app/work/extracted --revised /app/output/revised.md --out /app/output/verify_report.json
# → {"located_ratio":1.0,"landed_ratio":1.0,"unauthorized_changes":0,"verdict":"pass"}
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --embed-diagnosis /app/work/structure_issues.jsonl --embed-edits /app/work/edits_before_after.jsonl --embed-revised /app/output/revised.md --artifact /app/output/revised.docx --verify /app/output/verify_report.json --status complete
```

## 4. 交付自查清单
- [ ] result.json 契约字段一个不缺（骨架阶段已落盘，回填不覆盖）
- [ ] structure_issues 每条有 locator + ≤40 字逐字摘句 + 类型 + severity + 可执行 fix_ops
- [ ] 结论越界/贡献错配项给出收窄后替代表述
- [ ] edits_before_after 每条 original 逐字可检索、revised 已落地、reason+basis 齐全
- [ ] verify.py verdict=pass；needs_author 项显式列出
- [ ] diagnosis.issues / claim_chain / edits_before_after / revised_text 已完整嵌入 result.json
- [ ] status 诚实（complete/partial），uncertainty/changelog 如实
