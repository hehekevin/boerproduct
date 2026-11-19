# DOMAIN RULES — 文献智能问答 (kind=literature_qa)

## Focus
- Only given material (abstract/body/table text/captions/refs); no PDF-pixel/online retrieval.
- answers[] one per question with question_id/answer/conditions; never omit unanswerable ones.
- status distinguishes answered/partial/insufficient_evidence/input_error.
- claims[] kind reported/inferred with evidence; coverage read/unread.

## Rules
1. Read all provided material; record coverage (read/unread+reason).
2. Per question: answer + conditions + status; claims with evidence locators; inferred flagged.
3. Unanswerable → insufficient_evidence + unanswered_parts (not fabricated).
4. Emit answers[] preserving the contract; result.json honest.

## Self-check
- [ ] all questions answered or flagged
- [ ] status enum correct
- [ ] claims reported/inferred + evidence
- [ ] coverage + unanswered_parts present
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
