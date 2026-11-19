# Domain rules — citation_fact_check (引用与事实核验)

Goal: for every checkable claim, decide whether the ACTUAL cited material
supports it, and make every verdict re-checkable down to the sentence.

## 1. Claim extraction
- Extract claims from abstract/results/discussion/conclusion that carry a
  citation or a verifiable factual assertion (numbers, dates, attributions).
- Record the claim text faithfully (verbatim or faithful paraphrase) and its
  manuscript locator {source_id, document_id, paragraph_id, quote}.
- Decompose compound claims into subclaims: each separately gradable unit
  (e.g., "50% reduction" vs "in all cancer types" are TWO subclaims).
- Distinguish author claims, cited others' views, and hypotheticals; only
  grade what is asserted as fact.

## 2. Support grading (per subclaim, against the real source text)
- supports: the source explicitly states the subclaim (quote it).
- partial: source supports a weaker/narrower version; name the gap
  (over-generalization, missing condition, stronger wording than source).
- insufficient: source provided but does not contain enough to decide;
  rationale required; handling=human_confirm.
- unrelated: source is real but about something else (mis-citation / 张冠李戴).
- contradicts: source states the opposite (quote the contradicting sentence).
- Claim-level support with subclaims is COMPUTED by the engine as the worst
  subclaim support; do not hand-wave an overall "supports".
- Without subclaims, claim-level support needs claim evidence + rationale.

## 3. Reference metadata verification
- references[]: one entry per cited work. cited{} = exactly what the manuscript
  claims (title/doi/year/authors as printed). document_id = the provided
  reference document, if any.
- The engine normalizes DOI (lowercase, strip URL/doi: prefix/trailing dot) and
  title (lowercase, punctuation→space) on both sides and compares; title
  similarity < 0.85 or DOI/year difference → metadata_mismatch with both values.
- Never silently fix a mis-citation; report it with the manuscript locator of
  the citation and the actual metadata locator.
- Reference NOT provided → match_status=not_provided + human_confirm. Do not
  assert existence, publisher status, or retraction status from memory.

## 4. Numeric / statistical consistency
When the claim quotes numbers, compare against the provided source/table with
an exact locator (table/field). Discrepancy → contradicts or partial with both
values shown. If only the manuscript is provided, mark insufficient.

## 5. Severity & recommendations
- contradicts/unrelated on a main conclusion = major; peripheral mis-citation =
  minor. Every flagged claim gets an actionable recommendation (restrict
  wording, replace citation, add evidence, correct metadata).

## 6. Honesty
- reported = stated in material; your grading is inferred judgment bound to quotes.
- Missing material → insufficient / not_provided + uncertainty + human_confirm.
- Record IR edits in provenance.changes.