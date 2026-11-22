---
name: library-annotate
description: Attach paragraph/field-located annotations to research documents and precipitate reusable knowledge cards linked back to annotation evidence. Use when the task is to annotate reading material and distill verified knowledge cards.
---

# Reading annotation & knowledge precipitation (阅读批注与知识沉淀)

A source-bound Skill for the Bohrium weekly research-efficiency contest (library track).
The agent reads the ACTUAL organizer-provided local material under /input, fills a
structured Reading IR, and a deterministic stdlib engine validates it, computes the
library index/search/classification/QA/annotations, and emits editable artifacts +
provenance + an honest result.json. No pre-baked answers; every record traces to a
real input file and paragraph.

## When to use
Attach paragraph/field-located annotations to research documents and precipitate reusable knowledge cards linked back to annotation evidence. Use when the task is to annotate reading material and distill verified knowledge cards.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case.
- The actual research material files (documents, companion tables, metadata, notes).
Read and register the real files; trust file content over filename/domain labels.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_library.py --input /input --out /app/output --work /app/work`
Auto-extracts the IR from the ACTUAL /input materials (registers every source file;
builds documents[] with titles/aliases/metadata + field evidence from metadata tables
and real file text; binds version-note chains; logs index/alias_fix/dedup/recover/
metadata_fill operations; derives taxonomy for classify; binds verbatim-quote
annotations for annotate), runs the engine to compute the real index/hashes/coverage,
and writes a complete honest result.json preserving every output_contract key +
case_id. Judgment fields it cannot verify (row->file mapping, inferred year/type,
taxonomy design, annotation selection) are flagged human_confirm — never fabricated;
missing metadata stays not_reported. THEN, within remaining budget, refine
judgment-heavy fields in /app/work/library_ir.json and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/library_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials) and register sources[] + documents[].
2. Read the material; fill the IR per `rules/rules_library_annotate.md` and the schema below.
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

## Domain rules — library_annotate
Goal: located annotations + reusable knowledge cards that trace back to evidence.
1. annotations[]: each {annotation_id, document_id, paragraph_id|field, note, kind reported|inferred}. document_id must be registered; a paragraph_id OR field locator is REQUIRED; note text required. inferred annotations carry uncertainty.
2. knowledge_cards[]: each {card_id, statement, evidence[] | from_annotations[]}. A card needs evidence or a link to known annotation_ids; from_annotations must reference real annotations. A card is a verified, reusable statement — not an ungrounded summary.
3. The engine checks every annotation locator against the actual document and reports locator_issues honestly (wrong paragraph / quote mismatch).
4. Output annotations.json (annotations + cards + locator_issues), library_index.json, provenance.json, report.md, result.json. n_annotations / n_knowledge_cards / n_locator_issues reported honestly.

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
`examples/annotate/`: input/ + ir.json. Run:
`python assemble.py --ir examples/annotate/ir.json --input examples/annotate/input --out /tmp/demo`
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
