# ERROR_HANDLING — document_parse

| failure | detection | handling | status |
|---|---|---|---|
| workorder file absent | ls /input | fall back to task.md requested fields, then default fields (title/authors/abstract/methods/results/conclusion); note fallback in uncertainty | success/partial |
| requested field not in material | search all sections | item status=not_reported, value=null, human_confirm:true | partial |
| encrypted PDF / no text layer | extraction tool error | status=extraction_failed + reason; do NOT guess content | partial |
| garbled fonts / OCR noise | quote not verbatim-matchable | keep raw text in quote, flag uncertainty; never silently "fix" | partial |
| two material versions conflict | differing values | status=source_conflict, both evidence locators + conflict note | partial |
| section mapping ambiguous | heading absent | kind=inferred + uncertainty note; or insufficient_evidence | partial |
| IR validation errors | exit 2 + validation.json | fix IR (registered sources, locators, status vocabulary), re-run | partial until fixed |
| build exception | engine traceback in uncertainty | IR+validation still saved; result.json partial with limits | partial |

Rules: never fabricate missing content; absent ≠ zero; can't-judge is never written
as fact; every gap carries a human-takeover point (human_confirm).