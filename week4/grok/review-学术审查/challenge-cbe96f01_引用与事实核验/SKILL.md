---
name: review-citation-fact-check
description: Citation and fact verification (引用与事实核验) over organizer-provided local material. Verifies each manuscript claim/citation against the ACTUAL provided source texts, grades support as supports/partial/insufficient/unrelated/contradicts per subclaim, normalizes DOI/title to detect mis-citations, and flags unsupported or over-generalized conclusions with exact evidence locators. Use when the task is to check whether citations support the claims, whether facts match their sources, and whether evidence locators land in the original text.
---

# Citation & fact verification (引用与事实核验)

A source-bound Skill for the Bohrium weekly contest (REVIEW track, contest
bohr-product period 4). The agent reads the ACTUAL organizer-provided local
material under /input (manuscript + provided reference texts/data), fills a
structured Review IR, and a deterministic stdlib engine validates it, verifies
every evidence quote against the real file text, normalizes DOI/title, rolls up
subclaim support, and emits editable artifacts + provenance + an honest
result.json. No pre-baked answers; "citation exists" is never treated as
"citation supports the claim".

## When to use
The workorder asks to verify claims/citations against provided sources (kind
`citation_fact_check`). NOT for paper polishing, review writing, or data
modeling; those may supply material but do not replace the verification verdicts.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case.
- The actual manuscript + provided reference full texts / metadata / data.
Read and register the real files; trust file content over filename labels.

## Autopilot — run this FIRST
One command auto-extracts a complete, genuinely-derived Review IR from the
ACTUAL /input materials (sources/documents auto-registered; reported stats
located with exact quote locators; stats_checks bound to the real data files;
methodological findings evidence-grounded), then runs the existing engine
(validate_ir + quote verification + REAL recomputation) and writes an honest
result.json preserving every output_contract key + case_id:

```
PYTHONDONTWRITEBYTECODE=1 python auto_review.py --input /input --out /app/output --work /app/work
```

- Stdlib only; additive (does not modify review_engine.py / assemble.py).
- Never fabricates: quotes are exact substrings of real paragraphs; anything
  not locatable becomes insufficient_evidence + human_confirm (honest partial).
- On ANY exception it still writes a failed/partial result.json — never exit
  without result.json. Empty input is handled honestly too.
- It also writes /app/work/review_ir.json: within budget, REFINE that IR
  (judgment fields, extra findings/stats_checks) and re-run
  `python assemble.py --ir /app/work/review_ir.json --input /input --out /app/output`
  to improve. Do NOT hand-fill the rigid IR from scratch before running this.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[]
   (manuscript + each provided reference); set manuscript_id.
2. Extract the manuscript's checkable claims; decompose into subclaims; read
   each cited source ACTUALLY provided and grade support per
   `rules/rules_citation_fact_check.md`. Fill claims[], references[], uncertainty[].
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir review_ir.json --input /input --out /app/output`
   → validate_ir → quote verification + DOI/title normalization + support rollup
   → review.json + checklist.csv + provenance.json + report.md → result.json.
4. Honest status: success only when every claim is graded against readable
   source material and all locators verify; partial when sources are not
   provided, support is insufficient, metadata mismatches exist, or locators
   fail; failed on IR/build error.

## Review IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto from /input/case.json>
kind: "citation_fact_check"
sources: [{id, path, role?}]
documents: [{document_id, source_id, role, title,
             metadata?: {title, doi, year, authors},   # for reference docs
             content_path?, paragraphs?}]
manuscript_id: <document_id>
claims: [{id, text, evidence[] (manuscript locator),
          citation_ref_ids?: [...],
          support?: supports|partial|insufficient|unrelated|contradicts,
          subclaims?: [{id, text, support, evidence[] (source locator), rationale?}],
          rationale?, recommendation?}]
references: [{ref_id, document_id? (provided ref doc),
              cited: {title?, doi?, year?, authors?},
              claim_ids?: [...], evidence?}]
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes[]}
```
Evidence locator = {source_id, document_id?, paragraph_id?, quote?, page?, table?, field?}.
paragraph_id = pN from blank-line-split paragraphs of the real text file.
Support vocabulary: supports | partial | insufficient | unrelated | contradicts.
With subclaims, the engine computes the claim support as the WORST subclaim
support (contradicts > unrelated > insufficient > partial > supports) and
records any override of the agent-declared value.

## Domain rules — citation_fact_check
Full rules: `rules/rules_citation_fact_check.md`. Key points:
1. Verify support, not existence: a real citation can still be unrelated or
   contradicted. Grade each subclaim against the ACTUAL cited text with a quote.
2. Over-generalization ("all cancer types" from one model) → partial or
   insufficient on the over-reaching subclaim, with the limiting source quote.
3. DOI/title normalization via w4kit (strip https://doi.org/, doi:, case,
   trailing dots; fuzzy title similarity). Cited-vs-actual metadata mismatch →
   metadata_mismatch flag (mis-citation), never silently corrected.
4. Reference not provided under /input → match_status not_provided +
   human_confirm; existence is NEVER assumed from the citation string.
5. Every verdict carries a locator into the manuscript AND (when available)
   the cited source; unsupported → insufficient + human_confirm.

## Scripts & dependencies
assemble.py (CLI), review_engine.py (validation + quote verification +
normalization + rollup), w4kit.py (shared core). Python 3.10+ standard library
only. See requirements.txt.

## Outputs (/app/output)
review.json (claims + subclaim support + reference metadata checks + flags),
checklist.csv, report.md, provenance.json, validation.json, result.json
(preserves output_contract + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Missing reference text → not_provided + human_confirm; unreadable source →
content_status recorded, affected subclaims insufficient; quote mismatch →
locator_status flagged; DOI/title conflict → metadata_mismatch with both
values; IR errors → honest partial with validation.json. Never fabricate.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/citation_fact_check/`: input/ + ir.json. Run:
`python assemble.py --ir examples/citation_fact_check/ir.json --input examples/citation_fact_check/input --out /tmp/demo`
The demo includes an over-generalized claim, a contradicted claim, a year
mis-citation, and an unprovided reference — demonstrating honest partial status.

## Self-check
- [ ] every used input file registered; manuscript_id set
- [ ] every claim has a manuscript locator; every graded subclaim a source quote
- [ ] support grades match the cited text semantics (existence ≠ support)
- [ ] DOI/title normalized on both sides; mismatches surfaced, not hidden
- [ ] unprovided references flagged not_provided + human_confirm
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this
work (filled by git_sync; currently PENDING_GIT_SYNC), line 2 = SKILL.md.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md → /app/output/result.json preserving
output_contract + case_id). Partial results identify their limits.