## Domain rules — library_classify
Goal: rule-driven, evidence-backed classification — not a plausible-sounding guess.
1. taxonomy{categories[{id, rules[{rule_id, keywords[]}]}]} is REQUIRED. Categories come from the task's classification scheme; each rule lists trigger keywords. A category with no rules never matches (flagged).
2. Build the index from actual documents. The engine matches each document's content+metadata against category rules and assigns the best-supported category with the matched rule_id + keyword evidence.
3. When no rule matches, the document is abstain (unclassified) — NEVER force-fit a category. Report n_classified vs n_abstain honestly.
4. Multi-match conflicts are surfaced with attribution, not silently resolved.
5. Output classification.json (per-doc category + matched rules + evidence + abstain list), library_index.json, provenance.json, report.md, result.json.
