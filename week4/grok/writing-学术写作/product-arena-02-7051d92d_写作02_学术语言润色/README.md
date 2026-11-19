# arena-polish — 写作02 学术语言润色 (kind=polish)

Source-bound, segment-level academic language polishing skill for the Bohrium
weekly contest (play.bohrium.com, contest=bohr-product, period 4, grok agent).

## What it does
The Agent reads the ACTUAL organizer text under `/input`, fills a segment-level IR
(original<->revised + change_type + reason), and a deterministic stdlib engine:
- validates the IR (writekit cross-cutting checks + arena kind rules),
- checks preservation of numbers/units/citation markers/figure pointers and
  number-consistency of the polished text,
- builds editable `polished.md` + `polished.docx` + `track_changes.json`,
- writes `provenance.json` (claim_map + segment_map) and an honest `result.json`.

It is NOT pre-baked answers: the engine computes from the IR the Agent fills from
real material. Missing material → not_reported/insufficient_evidence + human_confirm.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Dependencies
Python 3.10+ standard library only (zipfile OOXML for docx). No python-docx, no
network, no numpy required. See requirements.txt.

## Files
- SKILL.md — trigger, workflow, IR schema, kind rules, self-check, runtime contract.
- assemble.py — CLI orchestration (w4kit case/result).
- arena_write_engine.py — shared validate+build engine for the 5 arena writing kinds.
- writekit.py — writing validation/claim_map/number-consistency (week3 core, KINDS extended).
- docxkit.py — stdlib md + editable docx (week3 core).
- w4kit.py — shared week4 case/result/provenance/normalize/dedup core.
- rules/rules_polish.md — domain rules.
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md.
- examples/polish/ — SYNTHETIC interface demo (input/ + ir.json + README).

## Scope & limits
IN: academic polishing with preservation + editable delivery. OUT: content
generation, reference management, LaTeX, PPT. Local env has no office-renderer;
docx is valid editable OOXML (true PDF/PNG render happens at runtime). Polish never
alters hedge strength or invents evidence; overclaims are flagged, not "fixed".

## Self-check
Run the synthetic example (examples/polish/README.md); confirm exit 0, validation ok,
preservation_issues empty, result.json honest. Hard limits: ≤50 UTF-8 text files,
≤500KB each, ≤2MB total, no binaries/__pycache__/symlinks (generated docx lives in
/app/output at runtime, never inside this package).