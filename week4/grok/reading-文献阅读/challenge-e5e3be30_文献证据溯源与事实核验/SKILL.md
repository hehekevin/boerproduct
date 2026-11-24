---
name: literature-evidence-verification
description: Verify research claims by decomposing into checkable sub-claims, locating minimal sufficient evidence (section/paragraph/sentence), judging support degree (supports/partial/insufficient vs merely topic-related), and stating uncertainty; verifiable verification report + result.json. Use for the "文献证据溯源与事实核验" workorder (kind=evidence_verification).
---

# 文献证据溯源与事实核验 skill (evidence_verification)

Source-bound literature-reading skill. The Agent reads the ACTUAL material and fills
the reading IR (items/answers with locators+status+reported/inferred, claims+support,
matrix, formulas, cleaning, reproduction, coverage); the engine deterministically
validates, runs the domain helper, emits the structured deliverable and result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact.

## Focus (rubric)
- 拆得开: split complex claims into fact/comparison/causal/scope sub-claims, no miss/dup.
- 找得到: minimal sufficient evidence per sub-claim, precise to sentence.
- 判得准: support degree matches original wording; partial/insufficient ≠ topic-related.
- 说得清: sources & uncertainty explicit.

## Scope / trigger
Use when the case asks for 文献证据溯源与事实核验 (workorder kind=evidence_verification). Only given material;
no online retrieval / pixel-guessing unless provided & asked.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract), `/input/task.md`, material
(paragraph/table text, figures, formulas) + workorder files when present
(target-fields.json / comparison-workorder.json / benchmark workorder).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_read.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input papers+workorders, auto-fills the complete reading IR
into /app/work (requested fields/claims with EXACT [Pn] quote locators; honest not_reported /
insufficient_evidence for missing), runs the SAME validate+build path as the package assembler, and
ALWAYS writes an honest result.json (try/except fallback preserves every output_contract key +
case_id) — even on empty input or failure. Never fabricated. THEN, within remaining budget, refine
the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble_read.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/READING_WORKFLOW.md)
1. Read & register sources (document_id + paragraph/page locator + version).
2. Fill reading IR per `rules/rules_evidence_verification.md`.
3. `python assemble_read.py --ir reading_ir.json --input /input --out /app/output`
   → validate → domain helper (clean/formula/compare/benchmark) → reading_result.json
   + reading_result.md (+domain artifacts) → result.json.
4. Honest status: insufficient_evidence / input_error / partial with reason +
   human-takeover point; save partial early.

## Domain rules
See `rules/rules_evidence_verification.md`. Key:
- Decompose claims into typed sub-claims; note required evidence type.
- Match minimal sufficient evidence with locator; assign supports/partial/insufficient/unrelated/contradicts.
- Never judge 'supports' from topic relevance alone; handle secondary/cross-page/abstract-vs-body mismatch.
- Output verification report with per-sub-claim evidence + degree + uncertainty.

## Scripts & dependencies
assemble_read.py, readkit.py (validation/evidence/status), clean.py (unit conversion/dedup), formula.py (LaTeX structure + safe numeric check), compare.py (matrix/comparability/conflict), benchkit.py (tasks/rubric/eval), figkit.py (case/result). Deps: Python 3.10+ stdlib (no third-party required for core).

## Outputs (/app/output)
reading_result.json + reading_result.md, domain artifacts (cleaned.json /
formula_check.json / comparison.json / benchmark), reading_ir.json, provenance.json
(item_map), validation.json, result.json.

## Error handling (docs/ERROR_HANDLING.md + READING_WORKFLOW §3)
Missing/unreported → insufficient_evidence + unanswered_parts; input read failure →
input_error; inferred → kind=inferred + uncertainty; conflict → surface + attribution;
unit/parse failure → keep original + pending. Never fabricate.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/read_ex/`: ir_extract / ir_clean / ir_formula / ir_compare + input. Run e.g.:
`python assemble_read.py --ir examples/read_ex/ir_extract.json --input examples/read_ex/input --out /tmp/demo`
Interface demonstration only.

## Self-check
- [ ] sub-claims typed & complete
- [ ] minimal evidence located
- [ ] support degree valid (unrelated≠supports)
- [ ] uncertainty explicit; report traceable
- [ ] result.json honest (status/sources/uncertainty); item_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Concrete input interface (organizer revision v2)
Read the actual audit claims in /input/claims-to-verify.json. They are questions, not authoritative facts. Split compound claims and assess entailment against complete source context: supported, partially_supported, contradicted or insufficient_evidence. Preserve comparator, negation, significance and conditions. Unsupported extrapolation is not experimentally disproved; conflicting sources need both locations and a qualified verdict.
The public example remains synthetic. Real papers, concrete target values, hidden expected readings and formal claims are supplied only during evaluation, never during Skill authoring. Original public scoring remains unchanged.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
