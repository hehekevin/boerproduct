---
name: library-classify
description: Classify research documents into a rule-driven taxonomy with per-document category, matched-rule evidence and explicit abstain when no rule matches. Use when the task is to auto-categorize literature/materials by topic, type or project.
---

# Literature & material auto-classification (文献与资料自动分类)

A source-bound Skill for the Bohrium weekly research-efficiency contest (library track).
The agent reads the ACTUAL organizer-provided local material under /input, fills a
structured Reading IR, and a deterministic stdlib engine validates it, computes the
library index/search/classification/QA/annotations, and emits editable artifacts +
provenance + an honest result.json. No pre-baked answers; every record traces to a
real input file and paragraph.

## When to use
Classify research documents into a rule-driven taxonomy with per-document category, matched-rule evidence and explicit abstain when no rule matches. Use when the task is to auto-categorize literature/materials by topic, type or project.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case.
- The actual research material files (documents, companion tables, metadata, notes).
Read and register the real files; trust file content over filename/domain labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials) and register sources[] + documents[].
2. Read the material; fill the IR per `rules/rules_library_classify.md` and the schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir library_ir.json --input /input --out /app/output`
   → validate_ir → build index/compute → library_index.json + kind artifact
   (search_results/classification/qa_answers/annotations.json) + provenance.json
   + report.md → result.json.
4. Honest status: success only when no gaps; partial when alias conflicts, failed/
   skipped ops, unreadable docs, no_hits, abstain, insufficient_evidence or locator
   issues exist; failed on IR/build error. Save partial early; never write未完成 as完成.

## Reading IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"          # required literal
case_id: <auto from /input/case.json>
kind: <this skill's kind>
sources: [{id, path, ...}]  # register every actual input file used (no duplicates)
documents: [{
  document_id, source_id, title,
  aliases: [...],
  metadata: { <field>: {value, status, evidence, uncertainty?} },
  versions: [{version_id, supersedes?, note?, evidence?}]
}]
# kind-specific (see Domain rules):
operations: [...]   # library_manage
searches:   [...]   # library_search
taxonomy:   {...}   # library_classify
questions:  [...]   # library_qa
annotations: [...], knowledge_cards: [...]   # library_annotate
provenance: {pipeline}
uncertainty: [{item, reason, impact?, handling}]
```
metadata.status vocabulary: reported | inferred | not_reported | source_conflict | extraction_failed.
operation.status vocabulary: done | skipped | failed | conflict | pending.
Evidence locator = {source|document_id, paragraph_id, quote, page?, table?, field?}.

## Domain rules — library_classify
Goal: rule-driven, evidence-backed classification — not a plausible-sounding guess.
1. taxonomy{categories[{id, rules[{rule_id, keywords[]}]}]} is REQUIRED. Categories come from the task's classification scheme; each rule lists trigger keywords. A category with no rules never matches (flagged).
2. Build the index from actual documents. The engine matches each document's content+metadata against category rules and assigns the best-supported category with the matched rule_id + keyword evidence.
3. When no rule matches, the document is abstain (unclassified) — NEVER force-fit a category. Report n_classified vs n_abstain honestly.
4. Multi-match conflicts are surfaced with attribution, not silently resolved.
5. Output classification.json (per-doc category + matched rules + evidence + abstain list), library_index.json, provenance.json, report.md, result.json.

## Scripts & dependencies
assemble.py (CLI), library_engine.py (index/search/classify/QA/annotation + validation
+ provenance + report), w4kit.py (case load / source check / result.json). Python 3.10+
standard library only — no third-party packages required. See requirements.txt.

## Outputs (/app/output)
library_index.json, kind artifact (search_results.json / classification.json /
qa_answers.json / annotations.json), provenance.json, report.md, validation.json,
result.json (preserves output_contract + case_id + status + sources + uncertainty +
change_log).

## Error handling (docs/ERROR_HANDLING.md)
Missing metadata → not_reported (never guessed); unreadable/no-permission file →
recorded in unreadable[] + operation skipped with reason; duplicate by content hash →
grouped, not overwritten; alias/version conflict → surfaced with attribution;
unsupported answer → insufficient_evidence + human_confirm; bad locator →
locator_issues. Never fabricate; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/classify/`: input/ + ir.json. Run:
`python assemble.py --ir examples/classify/ir.json --input examples/classify/input --out /tmp/demo`
The example deliberately includes gaps (missing metadata / recovered copy / no_hits)
to demonstrate honest partial status. Real cases are supplied only at evaluation.

## Self-check
- [ ] every used input file registered in sources[]; documents have source_id
- [ ] dedup/version by CONTENT HASH, not filename; conflicts surfaced
- [ ] metadata fields carry status + evidence; missing = not_reported, not guessed
- [ ] kind artifact complete (one result per query/question/doc/annotation as asked)
- [ ] every hit/answer/annotation traces to a real paragraph/quote locator
- [ ] operations log replayable; skipped/failed/conflict have reasons
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this work,
line 2 = relative entry file (SKILL.md). Published under week4/grok in
github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers or
formal test outputs. Evaluator installs the Skill under /skills/weekly-skill and runs
the official DeepSeek Harness on each fixed original case (/input/case.json + task.md
→ /app/output/result.json preserving output_contract + case_id).
