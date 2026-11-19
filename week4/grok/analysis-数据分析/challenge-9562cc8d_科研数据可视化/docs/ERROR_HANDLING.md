# Error handling — analysis-data-viz

Principle: every glyph traces to a real row; never plot missing as 0; honest export fallback.

| Situation | Engine behavior | Agent action |
|---|---|---|
| Missing / non-numeric x or y | row skipped + counted (n_rows_skipped_missing); chart status partial | state caliber in caption; clean upstream if needed |
| No plottable rows | insufficient_evidence + reason | report gap; do not invent data |
| Empty / unreadable dataset | insufficient_evidence; dataset status recorded | register what exists; partial |
| matplotlib absent / render fails | png_status = honest fallback note; SVG remains authoritative | never claim a PNG not rendered |
| Too many categories | bars become unreadable | choose histogram/box/facet/aggregate; rationale |
| Truncated / log axis | must be labelled explicitly | label it; bars keep zero baseline |
| Undefined error bars | engine draws chosen kind + data-error-kind tag | DEFINE sd/se/ci95 in caption |
| CJK / special glyphs in labels | SVG text is UTF-8; PNG font may lack CJK | prefer ASCII labels or verify font; note limit |
| IR validation errors | validation.json; result still written (partial) | fix IR; rerun |
| Build exception | honest partial/failed + build_error | read traceback; fix; rerun |

Status: result success|partial|failed|stuck; chart rendered|partial|insufficient_evidence|failed.
Binary PNG/PDF are RUNTIME outputs under /app/output only — never inside the skill package
(hard limit: text-only resources). SVG is text and is the editable authoritative artifact.
Every gap: {item, reason, impact?, handling: human_confirm} in uncertainty[].