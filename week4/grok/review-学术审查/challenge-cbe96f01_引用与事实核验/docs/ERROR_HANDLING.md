# ERROR HANDLING — review track

Principle: never fabricate, never silent-skip. Every failure mode has a recorded
state and a recovery path; the result stays honest (success/partial/failed).

| Situation | Detection | Handling | Status effect |
|---|---|---|---|
| IR missing/unreadable/bad JSON | assemble.py load | result.json status=failed + error + uncertainty(human_confirm) | failed |
| IR validation errors | validate_ir | validation.json lists each error; build still attempted; honest partial | partial |
| Material file missing | _resolve returns None | content_status=file_not_found; affected judgments insufficient_evidence | partial |
| Binary/PDF without text layer | suffix not parseable | content_status=binary_not_parsed; transcribe only actually readable text into documents[].paragraphs; rest human_confirm | partial |
| File read error (permissions etc.) | OSError caught | content_status=read_failed: ...; never guess content | partial |
| Quote not in real paragraph | _quote_ok false | locator_status=quote_mismatch + human_confirm; fix locator or record source_conflict | partial |
| paragraph_id not found | _bind_evidence | locator_status=paragraph_not_found + human_confirm | partial |
| Claimed sha256 differs from actual | hash check | hash_mismatch recorded on the document entry | flagged |
| Needed reference/data not provided | kind logic | not_provided / not_applicable / uncheckable WITH reason; existence never assumed | partial |
| Statistic not recomputable (n<2, missing field, bad expr) | stats engine | verdict=not_recomputable + note; reported values kept as reported | partial |
| Reported vs recomputed mismatch | tolerance compare | verdict=mismatch with abs/rel diff — a CONFIRMED review result, not a failure | success possible |
| Judgment cannot be supported | agent rule | insufficient_evidence + handling=human_confirm | partial |
| Build exception | assemble.py try/except | traceback printed; partial if some outputs exist else failed; build_error in result.json | partial/failed |

## Recovery checklist
1. Read validation.json / the printed errors; fix the IR, not the engine.
2. Re-read the actual material for any locator issue; correct quotes verbatim.
3. For genuinely missing material, add an uncertainty entry
   {item, reason, impact, handling: human_confirm} and keep the gap visible.
4. Re-run assemble.py; confirm status + summary reflect reality.
5. Never convert insufficient_evidence into confirmed to "complete" the review.

## Status semantics
- success: full coverage, all locators verified, no unresolved gaps. Confirmed
  findings (even major ones) are the PRODUCT of a successful review.
- partial: some checks unverifiable / material missing / locator issues /
  validation errors; limits listed in result.json.
- failed: IR or build could not produce artifacts; error recorded.