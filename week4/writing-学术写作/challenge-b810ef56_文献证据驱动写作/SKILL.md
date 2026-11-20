---
name: acwrite-evidence
description: 文献证据驱动写作技能：先建逐字摘录证据池，再写作——把稿件拆成可判定论断单元，每条论断绑定证据池中的逐字摘录（locator+来源+证据等级+支撑范围），机器核验摘录真实性并生成论断↔来源双向映射矩阵，防孤儿引用与编造，证据强度与正文措辞相称。Use when the case asks to write or rewrite text so that every substantive claim is traceable to a verbatim source passage, grade evidence strength, or audit claim-citation correspondence.
---

# acwrite-evidence — 证据驱动写作（证据池先行 · 逐字可核验 · 双向映射）

核心不是多写，而是**每一句有依据的话都能被指认依据在哪里、依据有多强、且机器能复核摘录是真的**。交付三件套：

1. **正文**：draft.docx + draft.md（每条论断句末带 [E##] 证据标记）
2. **论断-证据表**：claims_evidence.jsonl（论断 → 证据池逐字摘录 → locator → 支撑范围 → 证据等级 → 措辞相称性）
3. **边界记录**：核验报告（含论断↔来源双向映射矩阵）+ uncertainty + changelog

硬规则：**先建证据池再写作**——论断只能绑定证据池里已存在的逐字摘录，禁止先写正文再回头找引用；没有证据池摘录的论断不得出现在正文（背景常识句除外，须显式标 common_knowledge）；证据等级决定措辞强度，等级降一档措辞跟着降。

## ★ 强制执行协议（每一步先做这三件事，再谈内容质量）

1. **抄契约**：开工第一步 `cat /input/case.json`，把 output_contract 全部字段名抄进 result.json 骨架——**一个字段都不能缺**（暂无值就填 null）。
2. **立即落骨架**：用脚本写出含 case_id + 全部契约字段 + status:"partial" 的 /app/output/result.json。此后任何阶段失败，磁盘上都有可评的诚实交付。
3. **广度优先 + 熔断**：预算 64 次模型请求 / 900 秒。按"骨架→证据池→论断表→正文→校验→result"线性推进（≤5 个内容步骤），每个阶段先出全量粗稿再打磨；**已用 48 次请求或 700 秒即停止打磨**，把现有内容写入产物、audit 结果如实记录、status 标 partial——失败也交付。
4. **写盘自检**：每阶段结束用 `ls -la` + `python -c "import json;json.load(open(...))"` 确认文件真的写成了、JSON 真的合法。
5. **诚实状态**：status 只在全部自查项通过后才是 complete；材料缺口、未核验项写进 uncertainty，不编造。

## 0. 运行环境与预算
- 输入：`/input/case.json` + `/input/task.md` + 文献材料（PDF/题录/摘录）。**读真实文件，不按标签猜内容**。
- 工作区 `/app/work`，交付 `/app/output`。脚本无第三方依赖时自动降级（三级容错），本地可直接双测。

## 1. 阶段流程

### Stage 0 — 定契约 + 落骨架（脚本，无条件先执行）
```bash
ls -la /input/ && cat /input/case.json
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial
```
- 抄 output_contract 全部字段 → 骨架 result.json；constraints.json 记：体裁、受众、字数、citation_style、required_sections、terms。
- materials_manifest.json 里 extracted:false 的材料如实标记，不得假设其内容。

### Stage 1 — 文献库（1 次响应，产出 /app/work/sources_registry.jsonl）
每篇文献一行：`{"id":"R1","title":…,"authors":…,"year":…,"venue":…,"doi":…,"type":"原始研究|综述|指南|预印本","mid":"M02","meta_status":"complete|missing_field(哪个)"}`。
- 元数据从材料文献条目**逐字抄录**；缺字段标 missing_field，不猜补。
- 二手转引（材料里引他人而原文不可得）：secondary_citation=true，正文只能转述"X 综述了 Y"，不得直接引其结论。

### Stage 2 — 证据池（1-2 次响应，产出 /app/work/evidence_pool.jsonl）★本技能核心第一步
**从 extracted/*.txt 全文（不是记忆、不是摘要）逐字摘录**可用片段，每条：
`{"qid":"Q01","source":"R3","mid":"M02","locator":"M02:p5|para12","quote":"逐字摘录(≤300字,不改写)","quote_type":"结果数据|方法描述|机制陈述|结论表述|研究设计","strength_hint":"meta分析|多中心RCT|单篇小样本|综述意见|专家观点","support_topics":["该摘录能支撑的话题关键词"]}`
- 广度优先：先覆盖所有文献的所有章节（结果、方法、讨论、局限都摘），再求深；每篇至少摘 3-5 条。
- 摘录含关键限定语（样本量、条件、时长）——**把边界一起摘进来**，写作时才不会丢。
- 只有题录无全文的文献：不进证据池（quote_type 标 fulltext_unavailable 可选登记）。

### Stage 3 — 论断拆解与绑定（1-2 次响应，产出 /app/work/claims_evidence.jsonl）
先拆论断：`{"cid":"C01","section":"引言","claim":"一句可判定的话","claim_kind":"背景|方法有效性|经验结果|机制|预测"}`；
再逐条绑定到证据池：`{"cid":"C01","sources":["R3"],"quote_ids":["Q01"],"locator":"M02:p5|para12","quote":"(从Q01复制逐字摘录)","support_scope":"直接支撑|部分支撑|仅相关","evidence_grade":"A|B|C|D","grade_basis":"…","status":"bound|unbound","wording_ok":"ok|fixed"}`
- **一条论断多篇文献**：sources 列多条、quote_ids 逐条对应；**一篇文献支撑多条论**：正常，双向矩阵会记录。
- **对得上**：摘录真的支撑这句论断（不是相近但更强/更弱的话）；不匹配就降级论断措辞，不许升格摘录。
- **分级**：A=系统综述/多源一致；B=高质量原始研究；C=单篇小样本/初步结果；D=综述转述/专家意见/机制推测。
- **措辞相称**：C/D 级必须带限定语；单篇小样本不得写成"研究表明…普遍…"；相关不得写成因果。
- **冲突证据**：相左结论都列出，正文写"结果不一，可能因X"。
- 绑不上的论断：status=unbound → 从正文删除或改写为待验证问题，列入 uncertainty。

### Stage 4 — 成稿（1 次响应 + 1 次脚本）
正文按论断单元组装；每条 bound 论断句末带 [E##]；参考文献表只含实际引用文献（元数据抄 sources_registry）。
```bash
python scripts/docx_build.py /app/work/draft.json --out-docx /app/output/draft.docx --out-md /app/output/draft.md
```

### Stage 5 — 三重机器校验（含逐字核验与双向矩阵）
```bash
python scripts/fact_ledger.py check --draft /app/output/draft.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python scripts/consistency_check.py --draft /app/output/draft.md --constraints /app/work/constraints.json --out /app/output/check_report.json
python scripts/evidence_audit.py --claims /app/work/claims_evidence.jsonl --draft /app/output/draft.md --sources /app/work/extracted --refs /app/work/sources_registry.jsonl --out /app/output/evidence_audit.json
```
evidence_audit 机器核验：①摘录逐字存在性（quote_not_verbatim=编造风险）②[E##]↔cid 双向对应 ③裸论断 ④等级-措辞 ⑤**论断↔来源双向映射矩阵 + 孤儿来源**。fail → 回 Stage 3 修复后重跑。

### Stage 6 — 渲染与自包含 result.json
```bash
python scripts/render_preview.py --src /app/output/draft.docx --outdir /app/output/previews
python scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact draft.docx --artifact-md draft.md \
  --claims /app/work/claims_evidence.jsonl --draft-json /app/work/draft.json \
  --fact-check /app/output/fact_check.json --consistency /app/output/check_report.json \
  --audit /app/output/evidence_audit.json --status complete
```
result.json 自包含：deliverable_text（成文全文）+ claims_evidence（论断-证据表）+ claim_source_matrix（双向矩阵）——评审者不看任何附属文件也能逐条复核。

## 2. 异常处置表

| 情形 | 处置 |
|---|---|
| 文献只有题录无全文 | 不进证据池；只能支撑元数据级论断，结果级论断列入 unbound |
| 摘录与论断强度不符 | 降级论断措辞匹配证据，不许升格摘录 |
| 一条论断需多篇文献 | sources/quote_ids 列多条，support_scope 逐条标 |
| 撤稿/版本差异线索 | status 标 retracted_risk，正文不引用，uncertainty 列出 |
| DOI 无法核验（离线） | 标 doi_unverified_offline，如实说明，不伪造核验结论 |
| 任务给的是摘要而非全文 | 只做元数据级绑定；结果级论断列入 unbound |
| PDF 是扫描件 | extract_materials 标记 extracted:false；OCR 工具可用则用，不可用如实标注缺口 |
| 术语不一致 | constraints.terms + consistency_check 机检 |
| 预算将尽（48次/700秒） | 停止打磨，写盘现有内容，status=partial，audit 如实记录 |

## 3. 最小调用示例（示意，非真实案例结果）
```bash
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
# （模型响应：sources_registry.jsonl 8篇 / evidence_pool.jsonl 31条逐字摘录 / claims_evidence.jsonl 24条:22 bound+2 unbound）
python scripts/docx_build.py /app/work/draft.json --out-docx /app/output/draft.docx --out-md /app/output/draft.md
python scripts/evidence_audit.py --claims /app/work/claims_evidence.jsonl --draft /app/output/draft.md --sources /app/work/extracted --refs /app/work/sources_registry.jsonl --out /app/output/evidence_audit.json
# → {"verdict":"pass","claims":24,"bound":22,"problems":[]}  （矩阵: sources_used 7, orphan_sources 0）
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --artifact draft.docx --claims /app/work/claims_evidence.jsonl --draft-json /app/work/draft.json --status complete
```

## 4. 交付自查清单
- [ ] result.json 含 case_id + 契约全部字段（无值填 null）+ status + uncertainty + changelog
- [ ] 证据池先行：每条 bound 论断的 quote 都来自证据池，逐字核验通过（无 quote_not_verbatim）
- [ ] 无裸论断；unbound 论断已删除/改写并列入 uncertainty
- [ ] [E##]↔cid 双向对应；双向矩阵无孤儿来源；文献表无编造条目
- [ ] 证据等级与措辞相称（C/D 带限定语；无因果升级；冲突证据未隐藏）
- [ ] fact_check / check_report / evidence_audit 三报告落盘；status 诚实
