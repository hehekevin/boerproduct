# DOMAIN RULES — 学术格式与模板适配 (kind=format_template)

## Focus
- 认得准: extract columns/font/line-spacing/margins/heading levels/caption/ref-style/export as checkable spec, not guesswork.
- 排得对: heading hierarchy, numbering, captions, cross-refs, ref entries, header/footer match target item-by-item.
- 转得全: conversion preserves body/figures/formulas/footnotes/comments/revisions.
- 导出合规: export keeps layout/fonts/images; pptx/docx and export agree.

## Rules
1. Read the template file; emit a structured spec checklist (handle version/conflict).
2. Bind heading styles (not just bold/size); generate TOC/bookmarks; keep numbering & cross-refs consistent.
3. Three-line tables; caption position/size; figure numbering vs in-text refs; reference style uniform.
4. Verify conversion completeness + export (font substitution/image loss/overflow) and record deviations.

## Self-check
- [ ] template spec extracted & checkable
- [ ] hierarchy/numbering/cross-refs/refs match
- [ ] conversion complete; export matches source
- [ ] editable output; deviation log kept
- [ ] no facts/citations/numbers outside source; gaps flagged
- [ ] editable deliverable + provenance/claim_map + change log; result.json honest
