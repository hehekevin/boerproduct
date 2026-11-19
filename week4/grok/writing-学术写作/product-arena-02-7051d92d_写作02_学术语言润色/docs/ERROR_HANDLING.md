# ERROR HANDLING — arena-polish

| Situation | Handling | status |
|-|-|-|
| Original text missing/unreadable | state gap; polish only supported segments; uncertainty + human_confirm | partial |
| Segment lacks reason/change_type | validation warning; add justification | success (warn) |
| Number dropped/added in revision | preservation_issues flag; restore original number or justify | success (warn) / partial if unresolved |
| Citation marker / figure ref lost | preservation_issues flag; restore marker | success (warn) |
| meaning_preserved=false | human_confirm; do not ship as a clean polish | partial |
| Terminology conflict in glossary | writekit error (conflicting renders); resolve to one render | partial until fixed |
| Source overclaims | keep author wording; flag human_confirm; never invent evidence | success (warn) |
| Unknown target style/genre | documented fallback (conservative academic register); note limit | success (warn) |
| Encoding / mixed CJK-Latin | normalize conservatively; note limits; do not guess characters | partial if lossy |
| Over-length input | segment fully; never drop evidence to fit | success |
| Build exception | IR + validation saved; uncertainty item "build"; fix and re-run | partial |

Always: save an honest partial result.json early; never fabricate missing material;
distinguish reported vs inferred vs not_reported; mark gaps human_confirm.