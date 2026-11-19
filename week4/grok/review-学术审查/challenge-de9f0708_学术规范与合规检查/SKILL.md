---
name: review-compliance-check
description: Academic norms and compliance checklist audit (学术规范与合规检查) over organizer-provided local material. Checks ethics approval and informed consent, conflicts of interest, data availability, authorship contributions, plagiarism/reuse risk, copyright and licensing, and reporting-guideline items (CONSORT/PRISMA/ARRIVE or target-journal requirements) — each item graded compliant/non_compliant/partial/not_applicable/insufficient_evidence with an evidence locator, the governing guideline, and an actionable missing-items list. Use when the task is to check a manuscript's compliance with academic norms, ethics, or submission requirements.
---

# Academic norms & compliance check (学术规范与合规检查)

A source-bound Skill for the Bohrium weekly contest (REVIEW track, contest
bohr-product period 4). The agent reads the ACTUAL organizer-provided local
material under /input (manuscript + any provided guidelines), fills a structured
Review IR, and a deterministic stdlib engine validates it, verifies every
evidence quote against the real file text, computes per-category coverage and
the missing-items list, and emits editable artifacts + provenance + an honest
result.json. No pre-baked answers; every judgment cites a guideline AND a
manuscript locator.

## When to use
The workorder asks for ethics/COI/data-availability/authorship/plagiarism-risk/
copyright/reporting-guideline/submission-requirement compliance checking (kind
`compliance_check`). Norm problems are reported separately from substantive
scientific problems. NOT a text-matching plagiarism service: reuse RISK is
flagged from observable signals (uncited adaptation, missing permissions),
never from fabricated similarity scores.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case (incl. target journal).
- The actual manuscript + any provided author guidelines / checklists.
Read and register the real files; trust file content over filename labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs; register sources[] + documents[] (manuscript/guideline/...);
   set manuscript_id. Register provided guidelines in guidelines[] with version.
2. Build the checklist per `rules/rules_compliance_check.md`: decompose the
   applicable guideline (CONSORT/PRISMA/ARRIVE/journal guide) into checkable
   items; map each to the manuscript; fill compliance_items[] + uncertainty[].
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir review_ir.json --input /input --out /app/output`
   → validate_ir → quote verification + coverage/rate computation →
   review.json + checklist.csv + provenance.json + report.md → result.json.
4. Honest status: success when every applicable item is gradable from the
   material and locators verify (non_compliant items are review RESULTS);
   partial when items are insufficient_evidence, material/guidelines are
   missing, or locators fail; failed on IR/build error.

## Review IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "compliance_check"
sources: [{id, path, role?}]
documents: [{document_id, source_id, role, title, content_path?, paragraphs?}]
manuscript_id: <document_id>
guidelines: [{id, name, version?, source_id?}]
compliance_items: [{id,
  category: ethics|coi|data_availability|authorship|plagiarism_risk|
            reporting_guideline|copyright|privacy|submission_requirements|other,
  guideline: "CONSORT 2010 item 23" | "ICMJE" | "journal guide v2024-01" | ...,
  item: <checklist text>,
  status: compliant|non_compliant|partial|not_applicable|insufficient_evidence,
  severity?: major|minor|suggestion,
  evidence[], missing?: [...], reason?, recommendation?}]
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes[]}
```
Evidence locator = {source_id, document_id?, paragraph_id?, quote?, page?, table?, field?}.
paragraph_id = pN from blank-line-split paragraphs of the real text file.
compliant/non_compliant/partial REQUIRE evidence; not_applicable requires a
reason; insufficient_evidence gets handling=human_confirm automatically.
The engine computes by-category counts, compliance_rate (compliant / assessed,
excluding not_applicable & insufficient) and the actionable missing_items list.

## Domain rules — compliance_check
Full rules: `rules/rules_compliance_check.md`. Key points:
1. Every judgment needs TWO anchors: the governing norm (guideline + item,
   with version/date when provided) and the manuscript locator/quote.
2. Ethics: approval body + number + scope; informed consent; animal welfare
   (ARRIVE) where applicable. A bare "approved" without number → partial.
3. COI / data availability / authorship: statement presence AND required
   content (per-author contributions, repository/accession, funding consistency).
4. Copyright/reuse: adapted figures/tables need source + permission/license;
   flag risk signals, never invent similarity percentages.
5. Reporting guidelines: decompose the ACTUAL applicable checklist; absent
   required item → non_compliant with the item number; cannot tell from the
   provided text → insufficient_evidence, not non_compliant.
6. Separate norm problems from scientific problems; severity matched to risk.

## Scripts & dependencies
assemble.py (CLI), review_engine.py (validation + quote verification +
coverage), w4kit.py (shared core). Python 3.10+ standard library only.

## Outputs (/app/output)
review.json (items + by-category coverage + compliance_rate + missing_items),
checklist.csv, report.md, provenance.json, validation.json, result.json
(preserves output_contract + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Guideline not provided → use named standard checklist with version stated as
"agent knowledge, human_confirm"; manuscript section unreadable → affected
items insufficient_evidence; quote mismatch → flagged; IR errors → honest
partial. Never fabricate approval numbers, registrations, or permissions.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/compliance_check/`: input/ + ir.json. Run:
`python assemble.py --ir examples/compliance_check/ir.json --input examples/compliance_check/input --out /tmp/demo`
The demo shows partial ethics approval, missing consent statement, an
unregistered CONSORT trial, an unlicensed adapted figure, and honest
insufficient_evidence items.

## Self-check
- [ ] every used input file registered; manuscript_id set
- [ ] every item names its guideline AND carries a manuscript locator
- [ ] compliant/non_compliant/partial quotes verify against real text
- [ ] not_applicable justified; insufficient_evidence → human_confirm
- [ ] missing_items list actionable; norm vs scientific problems separated
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL (filled by
git_sync; currently PENDING_GIT_SYNC), line 2 = SKILL.md.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md → /app/output/result.json preserving
output_contract + case_id). Partial results identify their limits.