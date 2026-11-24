---
name: arena-reference-manage
description: Source-bound reference & citation management (写作04参考文献与引用管理, kind=reference_manage). The Agent reads the ACTUAL manuscript + reference library under /input, fills an IR (references[] + in_text_citations[] + target_style), and a deterministic stdlib engine normalizes DOI/title, deduplicates with explainable provenance, formats to GB/T 7714 / APA / IEEE, checks in-text<->list consistency (missing/uncited/duplicate flags), and builds editable references.md + .bib + .docx + citation_map/dedup/consistency reports + honest result.json. Use when the workorder asks to manage references/citations, dedup a library, convert citation style, or verify citation consistency.
---

# 参考文献与引用管理 skill (reference_manage)

Source-bound reference/citation management. The Agent registers the real library and
in-text citation points; the engine deterministically normalizes, deduplicates,
formats and cross-checks. Every merged cluster keeps provenance (which input records
merged + why + field conflicts). Never fabricate references or metadata.

## Focus (rubric)
- 挂得对: each in-text marker bound to the claim/position that needs support.
- 编得顺: numbering continuous; in-text markers and end list stay in sync.
- 收得净: same work (CN/EN title, preprint vs published, different DB exports) merged
  into one entry with an explainable merge basis (DOI exact + fuzzy title/year).
- 对得上: every reference real & locatable; metadata accurate; claim<->reference match;
  missing/uncited/duplicate flagged.

## Scope / trigger
Use when the case asks for 参考文献与引用管理 / reference management / citation styling
(workorder kind=reference_manage). IN: dedup + format + consistency + editable delivery.
OUT: prose polishing, intro writing, LaTeX compile, PPT (other tracks).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, target_style),
`/input/task.md`, ACTUAL manuscript (md/txt/docx/pdf) + reference library
(json/bib/ris/csv/endnote/cnk export). READ files; trust content over labels.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_arena_write.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills the complete writing IR into
/app/work, runs the SAME validate+build path as the package assembler, and ALWAYS writes an honest
result.json (try/except fallback preserves every output_contract key + case_id) — even on empty
input or failure. Targets/translations it cannot verify are null + human_confirm; never invented.
THEN, within remaining budget, refine the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Read & register sources (manuscript + library) with locators.
2. Fill IR per `rules/rules_reference_manage.md`: `references[]` (raw records with
   id/authors/year/title/journal/doi/volume/issue/pages/source/locator),
   `in_text_citations[]` {id, marker, ref_id, claim_text, source, locator},
   `target_style` (GB/T 7714 / APA / IEEE).
3. Run:
   `python assemble.py --ir writing_ir.json --input /input --out /app/output`
   → validate → w4kit.normalize_doi/normalize_title + dedup_records (provenance +
   conflicts) → format unique list → in-text<->list consistency → references.md +
   references.bib + references.docx + citation_map.json + dedup_report.json +
   consistency.json → provenance.json → honest result.json.
4. Edit IR, re-run; keep provenance.changes[] for rollback.

## IR schema (kind=reference_manage)
```
ir_version "1.0", case_id, kind "reference_manage", title, target_style,
sources[] {id, locator, kind, version},
references[] {id, authors, year, title, journal, doi, volume, issue, pages, source, locator},
in_text_citations[] {id, marker, ref_id, claim_text, source, locator},
claims[] (optional, evidence-bound), uncertainty[], provenance{pipeline, changes[]}
```

## Kind rules
See `rules/rules_reference_manage.md`. Key: normalize DOI (strip https://doi.org/,
doi:, lowercase) and title before dedup; merge basis recorded (doi exact / fuzzy
title+year ≥0.85); never silently drop a record; field conflicts surfaced; format
preserves DOI/vol/issue/pages/type; flag missing (marker without reference), uncited
(reference without marker), duplicate; unverifiable metadata → uncertain + human_confirm.

## Scripts & dependencies
`assemble.py`, `arena_write_engine.py` (shared arena engine; dedup/format/consistency),
`w4kit.py` (normalize_doi/normalize_title/dedup_records, case/result),
`writekit.py` (cross-cutting checks), `docxkit.py` (stdlib md + editable docx).
Deps: Python 3.10+ stdlib only. No network (verification is against provided material,
not live DOI lookup). Run with `PYTHONDONTWRITEBYTECODE=1`.

## Outputs (/app/output)
`references.md` (formatted unique list), `references.bib`, `references.docx` (editable),
`citation_map.json` (in-text<->cluster), `dedup_report.json` (clusters + provenance +
conflicts), `consistency.json` (missing/uncited/conflicts), `writing_ir.json`,
`provenance.json` (claim_map + reference_map), `validation.json`, `result.json`.

## Error handling (docs/ERROR_HANDLING.md)
Missing library fields → format gracefully + flag incomplete; DOI parse failure →
keep raw + flag; ambiguous merge → keep separate + human_confirm; marker without
reference → missing flag + partial; unsupported file → state limit, parse what is
possible; fabricated/unverifiable entry → mark uncertain, never invent metadata.
Save honest partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/reference_manage/`: input/case.json + task.md + manuscript.txt + library.json
+ ir.json + README. `python assemble.py --ir examples/reference_manage/ir.json
--input examples/reference_manage/input --out /tmp/demo` (4 records -> 3 unique, ref4 uncited).

## Self-check
- [ ] DOI/title normalized; dedup merge basis + conflicts recorded
- [ ] every input record appears in exactly one cluster (none silently dropped)
- [ ] formatted list matches target_style; DOI/vol/issue/pages preserved
- [ ] in-text<->list consistency: missing/uncited/duplicate flagged
- [ ] result.json honest (status/sources/uncertainty/change_log); reference_map complete

## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-reference/per-citation results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.