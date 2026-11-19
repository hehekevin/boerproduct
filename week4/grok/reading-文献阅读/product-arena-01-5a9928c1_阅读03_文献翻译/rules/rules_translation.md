# rules_translation — segmentation, glossary, faithfulness

## 1. Sources & segmentation
- Register every ACTUAL file read: {id, path}. Use the material's paragraph ids
  (P1..Pn / page: block) as locators; keep original reading order (multi-column:
  column-by-column; cross-page continuation joined in order, noted in uncertainty).
- One segment per source paragraph (or per requested range). Segment ids unique and
  ordered; source_text = verbatim source paragraph; never merge two paragraphs into
  one segment or split one paragraph into overlapping segments.
- Cover the FULL requested range. A segment that cannot be translated (image-only
  formula, garbled text) stays in the list with status extraction_failed,
  target_text=null, reason + human_confirm — never silently dropped.

## 2. Glossary locking
- Build glossary BEFORE translating: extract recurring domain terms from the actual
  source (materials, methods, metrics). Honor any organizer-provided glossary file.
- One source_term → one target_term everywhere (title, abstract, body, captions,
  conclusion). The engine checks: if source_term occurs in a segment's source_text,
  target_term MUST occur in its target_text (term_inconsistent = must_fix).
- Abbreviations: keep the abbreviation as printed and gloss it once; record in glossary.

## 3. Faithfulness (关系准)
- Preserve ALL numbers and units exactly (engine checks each source number appears
  in the target). Do not convert units silently; if conversion is required by the
  task, keep original + conversion note.
- Preserve citation markers verbatim: [1], [2,3], [1-4] (engine checks).
- Preserve negation, hedges ("may", "suggests"),限定条件 (conditions, scope), causal
  and concessive relations. A hedged claim must not become a definite claim.
- Formulas: keep symbols/subscripts as text (e.g. E = mc^2); do not re-derive.
- No addition: do not insert explanations absent from the source into target_text;
  translator notes go into the segment's note/uncertainty fields.

## 4. Status vocabulary (mandatory per segment)
reported (fully translated + grounded) | not_reported (source passage absent) |
source_conflict (versions disagree; both locators) | extraction_failed (unreadable
source; reason) | insufficient_evidence (cannot decide meaning; human_confirm).
Gap statuses carry target_text=null. Uncertain term choice on an otherwise complete
segment: keep reported + uncertainty entry naming the term + alternatives.

## 5. Verification loop
After assemble, read translation_check.json. Any must_fix issue → fix target_text,
re-run until n_issues=0 or honestly flagged human_confirm with status partial.