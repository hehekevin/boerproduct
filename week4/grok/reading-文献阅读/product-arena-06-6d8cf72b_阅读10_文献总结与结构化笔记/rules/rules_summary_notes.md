# rules_summary_notes — field dictionary, alignment, grounding

## 1. Sources & section alignment
- Register every ACTUAL file read: {id, path}. Use the material's own paragraph ids.
- Map the paper's REAL structure first: sections[] {id, title, level, parent_id,
  paragraph_ids[]}. Notes must follow this skeleton (对得上), not a generic template.
- If headings are implicit, infer section boundaries from content → kind=inferred on
  affected items + uncertainty note describing the mapping.

## 2. Field dictionary (items[] — one per requested field_id)
| field_id | content | must preserve |
|---|---|---|
| research_question | the problem/gap the paper addresses | scope, hedging |
| data | dataset/sample/materials studied | size, source, conditions |
| methods | procedure + experimental CONDITIONS | parameters, units, controls |
| results | main findings with numbers | values, units, comparators, conditions |
| conclusion | authors' conclusion |限定 scope; not broader than原文 |
| limitations | stated limitations/threats to validity | exact wording; absence → not_reported |
Workorder fields override/extend this list. Every item: value, kind reported|inferred,
status, evidence[{source, paragraph_id, quote}] (quote verbatim). Attach `condition`
to any number whose validity depends on experimental context.

## 3. Reported vs inferred
- reported: content explicitly stated in the material (quote proves it).
- inferred: your synthesis (e.g. cross-section implication) → kind=inferred +
  uncertainty note; NEVER present inference as the authors' statement.
- Speculation ("may", "suggests") stays hedged in value; do not upgrade to fact.

## 4. Claims (optional but recommended for key findings)
claims[] {id, text, subclaims[{text, support, evidence}]}.
support ∈ supports | partial | insufficient | unrelated | contradicts.
"supports" REQUIRES evidence with locator+quote. Split compound findings into
subclaims so each is independently checkable.

## 5. Status vocabulary (mandatory per item)
reported | not_reported (field absent; value=null; human_confirm) |
source_conflict (>=2 locators + conflict note) | extraction_failed (reason) |
insufficient_evidence (human_confirm). Absent ≠ zero; never fabricate limitations
or numbers the paper does not report.

## 6. Coverage
Engine reads the workorder (target-fields.json / note-fields.json) and checks one
item per requested field_id; missing → unanswered_parts + human_confirm. Prefer an
explicit not_reported item over silence.