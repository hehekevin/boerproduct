# rules_document_parse — field extraction & structure rules

## 1. Sources
- Register every ACTUAL file read: `{id, path, title?, version?}`. Path relative to
  /input or absolute. Never register a file you did not open.
- Paragraph ids: use the material's own ids when present (P1, §2.1, page:3:block:2).
  Otherwise assign stable ids yourself (P1..Pn in reading order) and record the
  convention in provenance.pipeline notes. Multi-column text: read column-by-column
  in original order; never splice adjacent columns into one paragraph.

## 2. Items — one result per requested field_id
- Read the workorder (target-fields.json / task.md). Iterate EVERY requested field_id.
- Typical fields: title, authors, abstract, methods, results, conclusion; also
  affiliations, keywords, captions, references when requested.
- Each item: `field_id`, `value` (verbatim or faithfully structured), `units` when
  numeric, `kind` reported|inferred, `status`, `evidence[{source, paragraph_id, quote}]`.
- quote = exact substring of the material (verbatim). value may restructure (e.g.
  authors as list) but must not add content absent from the source.
- authors: keep order + affiliation markers as printed; do not normalize names away.
- abstract/methods/results/conclusion: extract the section's actual content; if the
  paper uses different headings, map by content and note the mapping in uncertainty.

## 3. Section hierarchy
- sections[]: `{id, title, level, parent_id, paragraph_ids[], page?}`.
- level 1 = top sections; numbering preserved (1, 1.1, 2...). parent_id must exist.
- Include captions/footnotes/references as sections or items when requested; do not
  mix page headers/footers into body paragraphs.

## 4. Status vocabulary (mandatory)
| situation | status | value | extra |
|---|---|---|---|
| found verbatim in material | reported | filled | quote+locator required |
| field absent from material | not_reported | null | human_confirm:true |
| two sources disagree | source_conflict | null or both | >=2 evidence + conflict note |
| material unreadable (encrypted/scan without text layer) | extraction_failed | null | reason |
| material present but insufficient to decide | insufficient_evidence | null | human_confirm:true |
- inferred structure (e.g. guessed section mapping) → kind=inferred + uncertainty note.
- Absent field is NOT zero/empty-string fact. Never fabricate.

## 5. Coverage
- The engine reads the workorder and checks one item per requested field_id; missing
  fields are auto-added to unanswered_parts with human_confirm. Prefer to emit an
  explicit not_reported item yourself.