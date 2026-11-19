# Domain rules — quality_review (论文质量审查)

Goal: turn "what is wrong with this manuscript" into an itemized, locator-bound,
assignable problem list — not a prose critique.

## 1. Reading & registration
- Register EVERY actual input file in sources[] with its real path; one
  documents[] entry per logical document (manuscript, each provided reference,
  data table, guideline). Set manuscript_id to the document under review.
- Read the full manuscript. For text files the engine splits paragraphs on
  blank lines (p1, p2, ...); "Page N" marker lines set page numbers. Use those
  ids in locators, or transcribe the actual paragraphs into the IR.
- PDF/binary without a text layer: record content_status honestly; do not guess
  content. Transcribe only what you can actually read.

## 2. Six-category checklist (mandatory coverage)
Categories: fact_check, citation_support, methods_design, stats_reporting,
argument_chain, academic_norms.
- checked: you actually examined this facet (findings may be zero).
- not_applicable: facet genuinely absent (e.g., no citations at all) — reason required.
- uncheckable: needed material missing/unreadable — reason required; becomes a
  partial-status gap, never a silent skip.

## 3. Findings
Each finding: {id, dimension, severity, status, polarity, verdict, evidence[],
recommendation}.
- severity: major = threatens main conclusion, validity or reproducibility;
  minor = real but fixable reporting/consistency gap; suggestion = optional
  improvement. Do NOT label everything major.
- status: confirmed (defect demonstrably present in the text), suspected
  (likely but ambiguous wording — say why), insufficient_evidence (cannot
  verify locally; handling=human_confirm), not_applicable (reason required).
- polarity: issue (default) or strength. Strengths are findings too, with locators.
- evidence: at least one {source_id, document_id, paragraph_id, quote}; the
  quote must be an exact substring of the real paragraph (whitespace-normalized).
  The engine verifies it; mismatches are flagged, not hidden.
- verdict: one precise sentence naming the defect and where it is.
- recommendation: actionable — what to add/change/downgrade, in which sentence.

## 4. False-positive suppression
Do not flag: discipline writing conventions, target-journal format differences,
deliberate author scope choices, hedged statements that are appropriately
hedged. When unsure whether something is a defect, use suspected + note, or
insufficient_evidence — never confirmed without textual proof.

## 5. Dimension scores
novelty / rigor / clarity / significance (add structure if useful). Each:
numeric score on an explicit scale, a basis explaining the anchor, and evidence
locators. Unverifiable claims (e.g., novelty without literature) limit the
score and go to uncertainty — never invent prior work.

## 6. Overall recommendation
accept / minor_revision / major_revision / reject / undetermined. Must follow
from the findings (major unresolved validity defects → at least major_revision).
undetermined requires a reason and human_confirm.

## 7. Honesty
- reported = stated in the material; inferred = your judgment (say so in basis/verdict).
- Missing material → not_reported / insufficient_evidence + uncertainty entry.
- Every uncertainty item: {item, reason, impact?, handling: human_confirm}.
- Record IR edits in provenance.changes so a reviewer can replay.