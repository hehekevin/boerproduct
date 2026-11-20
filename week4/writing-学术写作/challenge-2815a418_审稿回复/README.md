# acwrite-rebuttal — 审稿回复与论文修改 Skill

面向「审稿回复与论文修改」场景（Bohrium 产品赛 · 学术写作赛道 challenge-2815a418）：把审稿意见清单 + 指定基线稿处理成**逐条回复信 + 修订稿**，每处修改带 revision_log 留痕、定位可机检、result.json 完整性由脚本保证。

## 核心方法

1. **意见拆解**：每条意见拆到子要求（一条意见多问必拆净），交叉意见关联。
2. **逐条决策**：adopted / partially_adopted / rejected + 理由；语气四档（accept/clarify/polite_pushback/appeal）。
3. **修改留痕**：每处改动带 `revision_log{original, revised, reason, basis}`，外科手术式 before/after。
4. **三方机检**：`ledger_audit.py` 校验 ① 子要求全覆盖 ② revision_log.revised 在修订稿可检索、original 在基线稿存在 ③ rejected 有理由 ④ 语气词 ⑤ 证据状态 ⑥ revision_log 四字段齐全。
5. **脚本保证交付**：`build_result.py` 五个子命令管理 result.json 全生命周期——骨架先行、主产物分批嵌入、失败自愈、写盘自检。**完整性靠脚本，不靠提示词纪律。**

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能本体：强制执行协议 + 线性五步流程 + 异常处置 |
| `scripts/build_result.py` | result.json 生命周期：init / embed / set / finalize / verify |
| `scripts/extract_materials.py` | 输入材料抽取（docx/pdf/txt/md/xlsx…→带锚点纯文本 + manifest） |
| `scripts/docx_build.py` | 结构化 draft.json → 可编辑 docx + md（python-docx 缺失时 stdlib 兜底） |
| `scripts/ledger_audit.py` | 回复信-修订稿-台账三方一致性机检 |
| `scripts/render_preview.py` | docx→PDF/PNG 预览（无渲染器时如实记 no_renderer，不伪造） |

依赖：仅 Python 3.8+ 标准库；可选 python-docx / PyMuPDF / pypdf / openpyxl / LibreOffice（缺失自动降级并在 manifest/render_log 如实记录）。无网络依赖、无平台专有路径（所有路径均可 `--input/--out/--case` 参数化，默认 `/input`、`/app/work`、`/app/output`）。

## 调用方式

由 Agent 按 `SKILL.md` 的线性五步执行（Stage 0 读输入+落骨架 → 1 意见拆解 → 2 决策台账 → 3 生成修订稿/回复信+分批嵌入 → 4 校验+收尾），关键命令见下例。

## 最小示例（示意，非正式案例结果）

输入：`/input/case.json`（含 output_contract）、`manuscript-baseline.md`、`reviewer-comments.md`

```bash
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":3,"extracted":3}}
python scripts/build_result.py init --case /input/case.json --out /app/output/result.json
# → 立即产出含全部契约字段的骨架 result.json（status=partial）

# ……模型按 SKILL.md 产出 comments.jsonl / response_ledger.jsonl / 两份 draft.json ……

python scripts/build_result.py embed --out /app/output/result.json --key letter_markdown --file /app/output/response_letter.md --part full
# → {"ok":true,"cmd":"embed","key":"letter_markdown","chars":4120}
python scripts/ledger_audit.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md --revised /app/output/revised.md --original /app/work/extracted --out /app/output/ledger_audit.json
# → {"verdict":"pass","subs":19,"problems":[]}
python scripts/build_result.py finalize --case /input/case.json --out /app/output/result.json --status complete --artifact /app/output/response_letter.docx --evidence /app/work/response_ledger.jsonl --audit /app/output/ledger_audit.json
python scripts/build_result.py verify --case /input/case.json --out /app/output/result.json
# → {"verdict":"pass","status":"complete","embedded_chars":{"letter_markdown":4120,"revised_markdown":8730}}
```

示意台账行（示意数据）：
```json
{"sid":"C01a","cm":"C01","decision":"adopted","decision_rationale":"意见合理",
 "edits":[{"eid":"E001","pid":"P12","locator":"§3.2 para4",
   "revision_log":{"original":"…50 participants…","revised":"…120 participants…","reason":"回应C01a样本量质疑","basis":"M02 表1"}}],
 "evidence":[{"what":"更新样本量","status":"done","source":"M02 表1"}],
 "letter_text":"感谢指出…已在§3.2更新…","tone":"accept"}
```

## 适用范围与边界

- 适用：基于意见摘要 + 指定基线稿的受控返修演练与真实逐条回复起草；意见类型覆盖方法/数据/写作/格式/伦理。
- 不适用：需联网核验原评审全文、补做真实实验、多文档库全文重写。材料不足时给替代说明并标注缺口，不伪造。
- 失败处理：任何阶段中断，result.json 始终合法；finalize 自愈重建骨架；partial 必须在 uncertainty 列缺口。

## 维护

- 脚本均为单文件、无状态、幂等；`ledger_audit.py` 的语气词表与 `build_result.py` 的嵌入键名可按期刊惯例扩展。
- 版本：2026-11-13 重做版（v2），变更记录见 `worklog.md`。
