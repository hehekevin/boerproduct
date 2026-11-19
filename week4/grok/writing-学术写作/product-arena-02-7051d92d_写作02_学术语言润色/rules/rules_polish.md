# Domain rules — polish (学术语言润色)

The Agent follows these rules to fill the IR from the ACTUAL material. The engine
enforces the deterministic subset (preservation, terminology, traceability).

## 1. Segment, don't rewrite
- Split the text into sentence/clause-level `segments[]`. Each segment carries the
  exact `original` substring and a minimally-edited `revised`.
- Minimal-edit principle: change only what is wrong. Do not restructure information
  order, drop qualifiers, or swap technical synonyms that shift meaning.

## 2. Fix real errors (改得对)
- grammar/syntax: subject-verb agreement, tense/voice, articles/prepositions,
  singular/plural, dangling modifiers, punctuation, long-sentence splitting.
- clarity: remove redundancy/nominalization, fix ambiguous reference.
- terminology: unify a concept's spelling/translation/abbreviation via `glossary[]`;
  first-occurrence expansion of abbreviations; consistent case/hyphenation.
- tone/register: remove colloquial/promotional/absolute wording; match genre
  (journal vs thesis vs grant vs reviewer response vs abstract).

## 3. Preserve meaning (没改坏) — engine-checked
- Numbers, units, sample sizes, citation markers `[n]`/`\cite{}`/`(Author, year)`,
  and figure/table pointers must appear unchanged in `revised`. The engine flags any
  dropped/added number or citation marker (`preservation_issues`).
- Hedge strength: keep "may/might/suggests/associated with" vs "causes/proves".
  Never strengthen or weaken a conclusion. Causality vs correlation preserved.
- Negation scope, conditionals, quantifiers preserved.
- If the original overclaims, KEEP the author's wording and flag `human_confirm`
  in `uncertainty[]`; do not "correct" the science by inventing evidence.

## 4. Justify every edit (讲得清)
- Each segment: `change_type` (grammar/syntax/clarity/terminology/tone/punctuation/
  minimal_edit/cohesion/register) + `reason` explaining the fix.
- `meaning_preserved: true/false`; false → human_confirm.
- Record `revisions[]` {location, before, after, reason, status} for rollback.

## 5. Source binding & honesty
- Register every material file in `sources[]` with a locator; each segment cites
  `source` + `locator`. Declare `numbers[]` from the material so the engine's
  number-consistency check can verify the polished text.
- Missing/unclear original, terminology conflict, unknown target style → state the
  gap, polish only what is supported, flag `human_confirm`. Never fabricate.