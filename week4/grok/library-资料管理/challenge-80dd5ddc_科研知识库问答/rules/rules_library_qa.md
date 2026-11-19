## Domain rules — library_qa
Goal: answers grounded in the library, with honest boundaries.
1. questions[]: each {question_id, question, scope[] (document_ids), answer?, evidence[]}. question text required; scope must reference registered documents.
2. The agent reads the actual material and supplies an answer ONLY with evidence locators (paragraph_id + quote). An answer without evidence is a validation error.
3. The engine verifies quotes against actual paragraph text where readable and computes status: answered (evidence supports) vs insufficient_evidence (material does not contain the answer). Do NOT fabricate an answer the library cannot support; mark insufficient_evidence + human_confirm.
4. Distinguish reported (stated in source) from inferred (derived); inferred carries uncertainty.
5. Output qa_answers.json (per-question answer + evidence + status), library_index.json, provenance.json, report.md, result.json. n_answered vs n_insufficient_evidence reported honestly.
