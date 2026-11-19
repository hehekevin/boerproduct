# arena-nanopublication (阅读14Nanopublication, kind=nanopublication)

Source-bound Skill for the Bohrium weekly product-arena reading track. The Agent
reads the ACTUAL organizer material under /input, decomposes conclusions into atomic
assertions with minimal sufficient evidence and real provenance metadata; a
deterministic stdlib engine validates triples/predicates/locators/status, checks
duplicates and exports machine-readable nanopubs.json + TriG + honest result.json.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Files
- SKILL.md — trigger, workflow, IR schema, self-check (entry point)
- assemble.py — CLI; arena_read_engine.py — validate_ir + checks + TriG export + build; readkit.py / figkit.py — reused reading core
- rules/rules_nanopublication.md — atomicity/evidence/provenance rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md
- examples/nanopublication/ — SYNTHETIC interface demo (not a formal answer)

## Dependencies
Python 3.10+ standard library only. No third-party packages, no network, no RDF library
(TriG is emitted as plain text following the nanopub schema).

## Scope & limits
- Extracts from provided local material only; provenance metadata must exist in the
  material (gaps → not_reported, never invented DOIs/years).
- No pre-baked nanopubs; gaps use the status vocabulary + human_confirm; result.json
  honest success/partial/failed.

## Self-check
Run the synthetic example (see SKILL.md): exit 0, validation ok, nanopubs.json +
nanopubs.trig written, every nanopub has quote+locator+provenance, result.json honest.