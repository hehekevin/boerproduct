# ERROR_HANDLING — summary_notes

| failure | detection | handling | status |
|---|---|---|---|
| requested note field absent (e.g. no limitations) | search all sections | item status=not_reported, value=null, human_confirm:true; never invent | partial |
| workorder file missing | ls /input | fall back to task.md fields, then default dictionary; note fallback in uncertainty | success/partial |
| encrypted PDF / no text layer | extraction error | status=extraction_failed + reason | partial |
| implicit headings / ambiguous structure | content-based mapping | kind=inferred + uncertainty note | success/partial |
| conflicting statements (text vs table) | differing values | status=source_conflict, both locators + conflict note | partial |
| compound finding | claim too broad | split into subclaims with individual support + evidence | success |
| speculation upgraded to fact | self-check | keep hedging; kind=inferred if synthesized | must fix |
| IR validation errors | exit 2 + validation.json | fix sources/locators/status/support vocabulary; re-run | partial until fixed |
| build exception | uncertainty entry | IR+validation saved; result.json partial with limits | partial |

Every gap carries a human-takeover point (human_confirm); can't-judge is never
written as fact.