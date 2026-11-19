## Domain rules — library_annotate
Goal: located annotations + reusable knowledge cards that trace back to evidence.
1. annotations[]: each {annotation_id, document_id, paragraph_id|field, note, kind reported|inferred}. document_id must be registered; a paragraph_id OR field locator is REQUIRED; note text required. inferred annotations carry uncertainty.
2. knowledge_cards[]: each {card_id, statement, evidence[] | from_annotations[]}. A card needs evidence or a link to known annotation_ids; from_annotations must reference real annotations. A card is a verified, reusable statement — not an ungrounded summary.
3. The engine checks every annotation locator against the actual document and reports locator_issues honestly (wrong paragraph / quote mismatch).
4. Output annotations.json (annotations + cards + locator_issues), library_index.json, provenance.json, report.md, result.json. n_annotations / n_knowledge_cards / n_locator_issues reported honestly.
