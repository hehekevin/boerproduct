# ERROR_HANDLING — knowledge_graph

| failure | detection | handling | status |
|---|---|---|---|
| entity not actually in material | quote search | do NOT create the node; no commonsense补全 | must fix |
| relation without supporting evidence | quote search | edge status=insufficient_evidence, human_confirm; or drop edge | partial |
| conflicting relations across papers | comparison | keep both, status=source_conflict + conflict note + both locators | partial |
| alias ambiguity (same name, different objects) | label check | keep separate nodes + distinguishing evidence + uncertainty | success/partial |
| duplicate labels (true variants) | engine warning | merge with merge_basis + aliases + multi-locator evidence | should fix |
| PDF unreadable / no text layer | extraction error | affected records status=extraction_failed + reason | partial |
| query unanswerable from graph | traversal | answer="not_reported", node_ids=[], human_confirm | partial |
| relation type outside vocabulary | engine error | remap to controlled type or justify; fix IR, re-run | must fix |
| edge endpoint missing | engine error | create the evidenced node or fix the edge; re-run | must fix |
| SVG build failure | uncertainty entry | graph.json remains the editable artifact; result partial | partial |
| build exception | uncertainty entry | IR+validation saved; result.json partial with limits | partial |

Never fabricate entities, relations or citations; every gap has a human-takeover
point (human_confirm).