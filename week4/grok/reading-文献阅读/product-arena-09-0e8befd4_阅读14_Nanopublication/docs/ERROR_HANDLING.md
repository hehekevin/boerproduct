# ERROR_HANDLING — nanopublication

| failure | detection | handling | status |
|---|---|---|---|
| assertion has no supporting fragment | quote search fails | status=insufficient_evidence, no assertion value, human_confirm | partial |
| assertion contradicts evidence | comparison | status=source_conflict, both locators + conflict note | partial |
| source unreadable (scan/encrypted) | extraction error | status=extraction_failed + reason | partial |
| authors/year/doi absent from material | metadata search | provenance fields null + not_reported note; never invent | success/partial |
| compound sentence | atomicity check | split into multiple nanopubs, each with own evidence | must fix |
| over-broad assertion (conditions dropped) | self-check | restore conditions field from原文 | must fix |
| duplicate triples | engine warning | merge nanopubs, keep all evidence locators | should fix |
| predicate outside vocabulary | engine warning | remap to controlled predicate or justify in uncertainty | should fix |
| evidence spans figure/table only | locator type | cite figure/table id + caption quote; if unavailable → insufficient_evidence | partial |
| IR validation errors | exit 2 + validation.json | fix sources/locators/status; re-run | partial until fixed |
| build exception | uncertainty entry | IR+validation saved; result.json partial with limits | partial |

Never fabricate assertions, metadata or citations; every gap has a human-takeover
point (human_confirm).