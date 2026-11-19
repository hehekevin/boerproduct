# Domain rules — intro_related (引言与相关工作写作)

## 1. Ground every claim (说得实 / 对得上)
- Register the ACTUAL literature in `sources[]`; build `citations[]` with accurate
  authors/year/title/journal/DOI taken from the material (never invented).
- Each substantive `claim` binds `evidence[]` {source, locator, strength, supports}
  AND `citation_ids[]`. strength ∈ established/supported/hypothesized/uncertain/
  correlational. Causal wording with correlational evidence is flagged.
- Unsupported assertion → mark type=interpretation + strength=hypothesized, or flag
  insufficient_evidence + human_confirm. Do not state it as fact.

## 2. Introduction (立得住)
- Background → specific problem → technical constraint → why now. Avoid empty
  "recently attracted wide attention" filler. Each background claim cites a source.

## 3. Related Work grouped (分得清)
- Group by problem/method/technical route, NOT chronological abstract stacking.
- Define comparison dimensions (problem setting, method route, data/evaluation).
- Paraphrase each work's conclusion + applicable conditions + limitations accurately;
  bind to its citation. Do not overstate another work's result.

## 4. Research gap derived (说得实)
- `research_gap.statement` must follow from `derived_from[]` (registered citation ids)
  — common limitation, uncovered scenario, or conflicting conclusions of cited works.
- Explain how this work addresses the gap. Gap without cited basis → flag, do not assert.

## 5. Contributions bound (对得上)
- Each `contribution` binds `claim_ids[]`/`evidence[]` pointing to actual method/
  figure/result. Distinguish `status`: result-backed vs proposed.
- If this-work results are absent from the material, mark contribution proposed +
  human_confirm; never fabricate results to make a contribution "backed".

## 6. Completeness & consistency
- required_sections: Introduction / Related Work / Research Gap / Contributions;
  missing → flag explicitly. Declare `numbers[]` from material; engine runs
  number-consistency (citation markers stripped). Terminology uniform via glossary.
- Keep revisions traceable; editable md+docx; honest status/uncertainty/change_log.