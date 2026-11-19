# Domain rules — logic_argument_review (论文逻辑与论证审查)

Goal: reported problems must really exist, point to a specific sentence, and
come with an executable fix (add which evidence, change which sentence, lower
which claim's strength).

## 1. Claim extraction
- Pull core claims from abstract, introduction, results, discussion/conclusion.
- Keep qualifiers ("in this model", "may", "under condition X") — dropping them
  fabricates a stronger claim than the author made.
- Tag each: author assertion / cited others' view / hypothetical. Audit
  assertions; cited views are checked for faithful representation, not re-graded
  as the author's own evidence.

## 2. Argument reconstruction (arguments[])
- conclusion: the asserted claim + its exact locator/quote.
- premises: the statements the author actually offers as support (reported,
  with locators). Unstated assumptions the argument NEEDS → status=inferred
  with a note; premises the material never provides → not_reported +
  human_confirm. Never invent premises.
- inference_type: deductive / inductive / causal / correlational / analogical / other.
- validity:
  - valid: conclusion follows at the stated strength from the premises.
  - gap: a missing link (name it in gaps[]: what evidence/step is absent).
  - fallacy: a named reasoning error (fallacy_type required).
  - insufficient_evidence: cannot judge from the material (human_confirm).

## 3. Fallacy catalog (name precisely, quote both ends)
- causal_from_correlation: association treated as causation without design support.
- circular_reasoning: conclusion restated as its own premise.
- hasty_generalization: one model/sample → universal claim.
- argument_from_ignorance: "not shown harmful" → "safe"; "unexplained" → "proven".
- extrapolation_beyond_data: conclusion outside the studied population/dose/time.
- equivocation / moving_goalposts: key term or promise shifts between sections.

## 4. Claim-evidence alignment
- For each claim: does supporting evidence exist, is it from this study or a
  cited source, and is it sufficient FOR THE STATED STRENGTH? "Conclusion
  exceeds data" and "citation does not support the view" are distinct findings.

## 5. Cross-section consistency (consistency_checks[])
- Pair the two actual statements (a, b) with locators: abstract vs body
  conclusion; introduction promise vs methods/results delivery; methods vs
  results口径; figure/table vs text description.
- verdict: consistent / inconsistent / unclear (unclear → human_confirm).

## 6. Severity & recommendations
- major: breaks the main conclusion or reproducibility; minor: local repairable
  jump; suggestion: wording strength. Every gap/fallacy/inconsistency gets a
  sentence-level fix: add experiment X, cite Y, rewrite sentence Z as "...",
  or downgrade claim to "...".

## 7. Honesty
- reported = in the text; inferred = your reconstruction (label it).
- Ambiguous wording → insufficient_evidence, not a forced fallacy verdict.
- Record IR edits in provenance.changes; same IR + material replays identically.