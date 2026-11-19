---
name: research-lit-review
description: Generate a source-bound literature review over a organizer-provided local corpus - screen the real papers, induce themes FROM the sources, organize supporting/contradicting evidence per claim with exact citation locators and honest strength labels, and draft a review that covers main themes, method routes, pro/con evidence and conclusion divergence. Use when the task is literature review / narrative synthesis on provided papers (kind lit_review), NOT a pre-baked answer.
---

# Literature review generation (文献综述生成)

A source-bound Skill for the Bohrium weekly research-efficiency contest (research track).
The agent reads the ACTUAL organizer-provided literature under /input, fills a structured
Research IR, and a deterministic stdlib engine validates it, recomputes screening +
synthesis, re-verifies every quoted excerpt against the real files, and emits an editable
review draft (md/docx) + evidence matrix (csv) + screening log + PRISMA svg + bidirectional
provenance + an honest result.json. No pre-baked answers; every substantive claim is truly
supported by a cited paragraph and every citation traces to a real source_id + paragraph_id.

## When to use
Use for kind `lit_review`: a batch of real provided papers to be screened, thematically
organized and synthesized into a review draft that can enter scientific discussion. The
four steps are 筛选 (screening) -> 主题归纳 (theme induction) -> 证据组织 (evidence
organization) -> 综述草稿 (review draft). Rubric checks: papers really exist + metadata
accurate; each claim truly supported by its citation; citation strength matches the
original; coverage of main themes, method routes, pro/con evidence and conclusion
divergence; gaps grounded; literature list / screening log / evidence table / citation
locators / versions independently re-checkable.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete task rules for this case.
- The actual literature files (papers/docs/companion metadata tables). Read and register
  the real files; trust file content over filename/domain labels. PDFs arrive without a
  pre-extracted answer layer — parse yourself if a tool exists, else mark unverifiable.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register every used paper in sources[] with
   accurate metadata (title/authors/year/venue/doi) read from the real file.
2. Read the literature; fill research_ir.json per `rules/rules_lit_review.md` + schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output`
   -> validate_ir -> compute_screening/synthesis + check_quotes -> build review draft +
   evidence matrix + provenance.json -> summarize -> result.json.
4. Honest status: success only when validation clean + build complete; partial when
   errors/missing files/unverifiable quotes; failed on IR/build error. Save partial early.

## Research IR schema (agent fills from ACTUAL material; validated by engine.validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "lit_review"
sources: [{id, title, file, year?, doi?, type?}]   # accurate metadata from the real paper
protocol: {inclusion: [{id, text}], exclusion: [{id, text}],
           search_queries?: [{id, query, intent, executed?, date?, database?}]}
records: [{id, source_id, title, year?, doi?, stage, decision,
           criteria_applied?, reason?, reviewer?, duplicate_of?}]
  # stage: title_abstract|full_text ; decision: include|exclude|pending ; exclude needs reason
themes: [{id, name, basis}]   # REQUIRED for lit_review; induced FROM sources, basis cites them
claims: [{id, text, type?, strength, theme_id?, subquestion_id?, uncertainty?,
          evidence: [{source_id, paragraph_id, quote, stance?}]}]
  # type: fact|inference|gap|method|comparison
  # strength: established|supported|suggestive|contested|uncertain (must match the evidence)
  # stance: supports|contradicts|partial|context ; quote = EXACT substring of the paragraph
  # every claim needs >=1 evidence; established cannot carry contradicts
conflicts: [{id, topic, positions: [{source_id, paragraph_id, quote, stance?}], handling}]
gaps: [{id, type?, text, evidence? | search_scope_checked?, human_confirm?}]
research_question?: {main, subquestions?: [{id, question, depends_on?}]}
tool_log?: [{step, tool, params, result?}]
proposal?: {text, bounded: true}
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes: []}
```
Evidence locator = {source_id, paragraph_id, quote, page?, table?, field?}. Materials may
mark paragraphs as `[P3] ...`; the engine restricts quote search to that paragraph.

## Domain rules — lit_review (detail: rules/rules_lit_review.md)
1. Metadata accuracy: sources[] title/authors/year/venue/doi must come from the real
   paper, not the filename. The engine hashes each cited file into provenance.source_map.
2. Screening: records[] with criteria + reasons; the engine recomputes PRISMA and
   cross-checks duplicates by DOI/fuzzy title (declare duplicate_of). Keep the full
   literature list re-checkable via screening_log.csv.
3. Theme induction: themes[] are REQUIRED and must grow FROM the sources — each theme
   carries a basis naming the papers it was induced from. Do not impose an external
   taxonomy. Map every claim to a theme_id so coverage of main themes is visible.
4. Claim-evidence rule: every substantive claim binds >=1 EXACT quote located to
   source_id + paragraph_id; the engine re-verifies it against the real file. Citation
   strength MUST match the original (supported/suggestive/contested/uncertain); any
   `contradicts` forbids `established`. Weak strengths need an uncertainty note.
5. Pro/con evidence & divergence: organize supporting AND contradicting evidence per
   claim; surface conclusion divergence as conflicts[] (>=2 located positions + handling).
   The engine flags contested claims and registered-but-uncited sources.
6. Grounded gaps: gaps[] need evidence OR a documented search_scope_checked + human_confirm.
   "Not found in this corpus" is NOT "nobody studied it". Keep the review bounded to the
   provided literature; no field-wide completeness/novelty, no completed-experiment wording.

## Scripts & dependencies
assemble.py (CLI), research_engine.py (validate_ir + compute_screening/synthesis +
check_quotes + build md/docx/csv/svg + provenance + summarize), w4kit.py (case load /
source check / dedup / result.json). Python 3.10+ standard library only — no third-party
packages required (numpy optional, never needed). See requirements.txt.

## Outputs (/app/output)
research_report.md (the review draft), research_report.docx, synthesis_matrix.csv
(claim x evidence), screening_log.csv, prisma_flow.svg, provenance.json, validation.json,
result.json (preserves every output_contract key + case_id + status + sources +
uncertainty + change_log + prisma + synthesis_stats + quote_check_summary + boundary).

## Error handling (docs/ERROR_HANDLING.md)
Missing/unreadable paper -> unverifiable quotes + uncertainty; quote not in file ->
validation error (fix, never fabricate); established+contradicts -> error; theme without
basis -> warning; exclusion without reason / PRISMA mismatch -> error; conflict -> both
positions surfaced; gap -> evidence or search scope + human_confirm; over-boundary wording
-> error; IR/build error -> honest failed/partial. Never fabricate; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/lit_review/`: input/ (8 fictional papers) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/lit_review/ir.json --input examples/lit_review/input --out /tmp/demo`
The example induces 3 themes from the sources, organizes pro/con evidence (C2 contested),
a conflict (CF1), grounded gaps (G1/G2) and a duplicate record (R7). Real cases are
supplied only at evaluation.

## Self-check
- [ ] every used paper registered with accurate metadata read from the real file
- [ ] themes REQUIRED, induced from sources with a basis; claims mapped to themes
- [ ] screening log complete; PRISMA recomputed and balanced; duplicates declared
- [ ] every claim binds an EXACT quote re-verified against the real file
- [ ] citation strength matches the original; pro/con evidence + divergence surfaced
- [ ] gaps grounded (evidence or search scope) + human_confirm
- [ ] review bounded to the corpus; no over-boundary wording
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this work,
line 2 = relative entry file (SKILL.md). Published under week4/grok in
github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers or
formal test outputs. The evaluator installs the Skill under /skills/weekly-skill and runs
the official DeepSeek Harness on each fixed original case (/input/case.json + task.md ->
/app/output/result.json preserving every output_contract field + case_id). Work under
/app/work; editable artifacts + real rendered previews belong under /app/output. Honest
status/sources/uncertainty/change_log; partial results identify their limits; never
fabricate missing software state or scientific data. Resources: <=50 UTF-8 text files,
<=500KB each, <=2MB total, no symlinks/binaries/__pycache__. Run with PYTHONDONTWRITEBYTECODE=1.