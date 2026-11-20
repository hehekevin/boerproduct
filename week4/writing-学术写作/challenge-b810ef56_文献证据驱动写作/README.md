# acwrite-evidence — 文献证据驱动写作 Skill

把「有引用」升级为「可指认、可核验、可复现」：先从文献全文逐字摘录建立**证据池**，写作时论断只能绑定池内摘录，最后机器核验摘录真实性并生成**论断↔来源双向映射矩阵**。防编造文献、防改写摘录、防孤儿引用。

## 快速开始

```bash
# 1. 提取材料（自动降级：python-docx/PyMuPDF→zipfile/pypdf 兜底，扫描件如实标记）
python scripts/extract_materials.py --input /input --outdir /app/work/extracted

# 2. 硬事实台账（数值/统计量/DOI 逐条登记）
python scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl

# 3. 落 result.json 骨架（契约字段一个不缺，status=partial）
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial

# 4-6. 模型按 SKILL.md Stage 1-4 产出 sources_registry / evidence_pool / claims_evidence / draft
python scripts/docx_build.py /app/work/draft.json --out-docx /app/output/draft.docx --out-md /app/output/draft.md

# 7. 三重机器校验（fact_ledger check / consistency_check / evidence_audit）
python scripts/evidence_audit.py --claims /app/work/claims_evidence.jsonl \
    --draft /app/output/draft.md --sources /app/work/extracted \
    --refs /app/work/sources_registry.jsonl --out /app/output/evidence_audit.json

# 8. 自包含 result.json（嵌入成文全文+论断-证据表+双向矩阵）
python scripts/build_result.py --case /input/case.json --out /app/output/result.json \
    --artifact draft.docx --artifact-md draft.md --claims /app/work/claims_evidence.jsonl \
    --draft-json /app/work/draft.json --status complete
```

最小示例输入见 `examples/example_input.json`（示意数据，非正式案例结果）。

## 核心方法

| 环节 | 机制 | 防什么 |
|---|---|---|
| 证据池先行 | Stage 2 先从全文逐字摘录（qid+locator+quote），Stage 3 论断只能绑池内摘录 | 先写后找引用导致的"引用贴皮" |
| 逐字核验 | evidence_audit 对每条摘录做空白归一化子串匹配回源文件 | 编造摘录、改写原文 |
| 双向矩阵 | claim→source 正向 + source→claims 反向索引 + 孤儿来源检测 | 孤儿引用（文献表有条目却无论断支撑） |
| 等级-措辞相称 | A/B/C/D 分级 + 机检 C/D 级句子限定语 | 单篇小样本写成领域共识、相关写成因果 |
| 协议置顶 | 抄契约→落骨架→字段不缺→熔断（48次/700秒）→写盘自检→失败也交付 | 中途失败交付空壳 |

## 证据分级口径

- **A**：系统综述 / 多源一致
- **B**：高质量原始研究（RCT/大队列）
- **C**：单篇小样本 / 初步结果
- **D**：综述转述 / 专家意见 / 机制推测

C/D 级论断正文必须带限定语（"初步结果显示""一项小样本研究提示"）。

## 文件清单

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 技能主流程与规则（≤250 行） |
| `scripts/extract_materials.py` | 材料→带锚点纯文本 + manifest |
| `scripts/fact_ledger.py` | 硬事实台账 build / 稿件数值回查 check |
| `scripts/evidence_audit.py` | 逐字核验 + 双向矩阵 + 裸论断/措辞审计 |
| `scripts/consistency_check.py` | 章节完整/引用对应/术语统一/字数 |
| `scripts/docx_build.py` | draft.json → docx（stdlib 兜底）+ md |
| `scripts/render_preview.py` | docx → PDF/PNG 预览（无渲染器时如实记录） |
| `scripts/build_result.py` | 组装自包含 result.json |
| `examples/example_input.json` | 最小示例输入（示意） |

依赖：Python 3.8+；可选 python-docx / PyMuPDF / pypdf / openpyxl（缺失自动降级）。无硬编码平台路径（所有路径由 CLI 参数传入，默认值仅为约定俗成的容器路径）。

## 适用范围与限制

- 适用：需要文献支撑的学术写作/改写任务，材料中含可提取全文或摘录。
- 限制：仅有题录无全文的文献只能支撑元数据级论断；逐字核验依赖 extract_materials 产出的 M*.txt，sources 目录缺失时核验降级并如实记录（不伪造通过）；DOI 真实性无法离线核验时标 doi_unverified_offline。

## 维护

版本 v2（2026-11）。变更记录见 worklog.md。
